"""本棚の物理配置分析API（backend/placement_analysis/ を参照）。

  (1)(2) 高さ・色の分布から「配置の癖」を捉える  → /profile/*
  (3) 著者管理（表記ゆれの検出・統合）             → /authors/*
  (4) ジャンル分布と本棚配置の一致度               → /profile/* の genre_placement_*
      内容テーマ（あらすじから生成）・意味づけとの一致度も同様に分析できる
      → /themes/*, /profile/* の theme_placement_*・concept_placement_*
  (5) 知識グラフ上で孤立している本の検出           → /isolation
  (6) デザインとしての配置と判断できる根拠         → /design-evidence, /profile/* の design_intent
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from participant import is_valid_participant_id
from graph.placement_analysis.profile import (
    compute_and_save_placement_profile,
    get_latest_placement_profile,
    get_placement_profile_history,
)
from graph.placement_analysis.isolation import compute_isolation, summarize_isolation
from graph.placement_analysis.evidence import get_design_evidence_history
from graph.placement_analysis.authors import (
    sync_author_canonical_names, find_author_duplicate_groups, merge_author_alias,
)
from graph.placement_analysis.narrative import build_placement_narrative
from graph.placement_analysis.themes import generate_book_themes, get_theme_summary
from graph.placement_analysis.content_alignment import compute_content_alignment
from utils.llm_provider import get_llm_client

_llm = get_llm_client()

router = APIRouter(prefix="/placement_analysis", tags=["placement_analysis"])


def _require_valid_participant(participant_id: str) -> None:
    if not is_valid_participant_id(participant_id):
        raise HTTPException(status_code=400, detail="participant_id が不正です")


@router.post("/{participant_id}/recompute")
def recompute_profile(participant_id: str):
    """配置完了イベントのタイミングで呼ぶバッチ処理。
    enrich→指標計算→(design_intentならDesignEvidence保存)→PlacementProfile追記保存、
    まで一括で行う。"""
    _require_valid_participant(participant_id)
    return compute_and_save_placement_profile(participant_id)


@router.get("/{participant_id}/profile/latest")
def latest_profile(participant_id: str):
    _require_valid_participant(participant_id)
    profile = get_latest_placement_profile(participant_id)
    if not profile:
        raise HTTPException(status_code=404, detail="PlacementProfileがまだありません")
    return profile


@router.get("/{participant_id}/profile/history")
def profile_history(participant_id: str):
    _require_valid_participant(participant_id)
    return {"profiles": get_placement_profile_history(participant_id)}


@router.get("/{participant_id}/isolation")
def isolation(participant_id: str):
    """(5) 孤立本の検出。軸別（トポロジー的/意味的/物理的/浮いている）の
    フラグ付きで全冊分を返す。"""
    _require_valid_participant(participant_id)
    records = compute_isolation(participant_id)
    return {"summary": summarize_isolation(records), "books": records}


@router.get("/{participant_id}/design-evidence")
def design_evidence(participant_id: str):
    """(6) これまでに「デザイン重視の配置」と判定された根拠の履歴。"""
    _require_valid_participant(participant_id)
    return {"evidence": get_design_evidence_history(participant_id)}


@router.post("/{participant_id}/themes/generate")
def generate_themes(participant_id: str):
    """(4拡張) あらすじからLLMで内容テーマを生成する。配置同期のたびの自動計算
    には含めていないため、参加者が明示的に呼ぶ必要がある（呼ばないと
    theme_placement_modularity/nmiはnullのまま）。"""
    _require_valid_participant(participant_id)
    try:
        return generate_book_themes(_llm, participant_id)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"内容テーマの生成に失敗しました: {e}")


@router.get("/{participant_id}/themes")
def list_themes(participant_id: str):
    _require_valid_participant(participant_id)
    return {"themes": get_theme_summary(participant_id)}


@router.get("/{participant_id}/content-alignment")
def content_alignment(participant_id: str):
    """配置分析と内容分析を組み合わせ、テーマ・意味づけごとに物理的な
    まとまり具合（clustering_rate）を個別に見る。theme_placement_modularity等
    （PlacementProfile）が全体を1つの数字にまとめるのに対し、こちらは
    「どのテーマ/意味づけをまとめていて、どれを分散させているか」の内訳。"""
    _require_valid_participant(participant_id)
    return compute_content_alignment(participant_id)


@router.get("/{participant_id}/narrative")
def narrative(participant_id: str):
    """構造指標（PlacementProfile・孤立本の集計・DesignEvidence）だけから、
    配置の癖を自然文で言語化する。都度LLMを呼ぶため、配置同期のたびの自動計算
    には含めず、参加者が見たいときに明示的に呼ぶ想定。"""
    _require_valid_participant(participant_id)
    try:
        result = build_placement_narrative(_llm, participant_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"言語化に失敗しました: {e}")
    return {
        "narrative": result["narrative"],
        "profile_id": result["profile"].get("profile_id"),
        "computed_at": result["profile"].get("computed_at"),
    }


# ============================================================
# (3) 著者管理
# ============================================================

@router.post("/authors/sync-canonical-names")
def sync_canonical_names():
    """全Authorノードに正規化キー(canonicalName)を付与する。
    新しい著者が登録されるたびに軽いので、研究者が任意のタイミングで呼べばよい。"""
    updated = sync_author_canonical_names()
    return {"updated": updated}


@router.get("/authors/duplicates")
def author_duplicates():
    """表記ゆれの疑いがあるAuthorのグループ（統合候補）。"""
    return {"groups": find_author_duplicate_groups()}


class MergeAuthorRequest(BaseModel):
    primary_name: str
    alias_name: str


@router.post("/authors/merge")
def merge_authors(body: MergeAuthorRequest):
    """研究者が確認した統合候補を実際に適用する。Authorノードは削除せず、
    ALIAS_OFを張った上でalias側の著作をprimary側からも辿れるようにする。"""
    ok = merge_author_alias(body.primary_name, body.alias_name)
    if not ok:
        raise HTTPException(status_code=404, detail="指定した著者が見つかりません")
    return {"ok": True}
