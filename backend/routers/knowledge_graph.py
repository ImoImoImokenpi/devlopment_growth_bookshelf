import json
import logging
import random
import re

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from graph.main_kg.neo4j_crud import (
    get_book_relations, get_book_concepts, get_book_basic, save_book_impression,
    delete_concept_edge, get_growth_stats,
    list_participant_groups, remove_group_member, remove_group_members, add_group_members,
    rename_group, merge_groups, delete_group,
    log_group_highlight_event, log_mode_switch_event,
    set_possessed_since,
)
from graph.style_projection.diff import compute_style_diff, get_latest_style_profile
from graph.style_projection.bookshelf_bridge import sync_from_bookshelf
from graph.style_projection.groups import get_candidate_groups
from graph.experiment.guess_records import (
    save_pre_guess, get_guess, save_post_guess, TARGET_TYPES,
)
from graph.experiment.semantic_diff import build_semantic_diff
from graph.experiment.assignment import get_condition as get_trial_condition
from utils.llm_provider import get_llm_client
from database import get_db
from participant import resolve_participant_id, is_valid_participant_id
from models import RegisteredBook

router = APIRouter(prefix="/knowledge_graph")

_llm = get_llm_client()

@router.get("/book/{isbn}")
def get_book_detail(isbn: str, participant_id: str = Depends(resolve_participant_id)):
    """本棚で本をタップした時の詳細パネル用：書誌情報＋関連本（理由付き）＋部分グラフ"""
    data = get_book_relations(isbn, participant_id=participant_id)
    if not data:
        raise HTTPException(status_code=404, detail="本が見つかりません")
    return data


@router.get("/book/{isbn}/concepts")
def get_book_concepts_endpoint(isbn: str, participant_id: str = Depends(resolve_participant_id)):
    """本棚でカーソルを合わせた時のホバー強調用：
    その本の意味づけ(Concept)一覧と、それぞれを共有する本のISBNを返す。"""
    return {"concepts": get_book_concepts(isbn, participant_id=participant_id)}


@router.get("/book/{isbn}/basic")
def get_book_basic_endpoint(isbn: str, participant_id: str = Depends(resolve_participant_id)):
    """コンパクトな詳細パネル用：書誌情報と感想のみを返す（関連本の探索はしない）。"""
    data = get_book_basic(isbn, participant_id=participant_id)
    if not data:
        raise HTTPException(status_code=404, detail="本が見つかりません")
    return data


class PossessedSinceRequest(BaseModel):
    possessed_since: str  # "YYYY-MM-DD"


@router.post("/book/{isbn}/possessed-since")
def set_possessed_since_endpoint(
    isbn: str,
    body: PossessedSinceRequest,
    participant_id: str = Depends(resolve_participant_id),
):
    """本棚の「褪せ」表現の元になる、この本を持ち始めた日を手動で設定する。
    書誌APIからは分からない情報（本人しか知らない）なので手動入力のみ。"""
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", body.possessed_since):
        raise HTTPException(status_code=422, detail="possessed_since は YYYY-MM-DD 形式で指定してください")
    ok = set_possessed_since(isbn, participant_id=participant_id, possessed_since=body.possessed_since)
    if not ok:
        raise HTTPException(status_code=404, detail="本が見つかりません")
    return {"isbn": isbn, "possessed_since": body.possessed_since}


class ImpressionRequest(BaseModel):
    text: str


@router.post("/book/{isbn}/impression")
def save_book_impression_endpoint(
    isbn: str,
    body: ImpressionRequest,
    participant_id: str = Depends(resolve_participant_id),
):
    """意味づけ(Concept)とは別に、1冊ごとの個人的な感想を保存する。
    上書きではなく追記なので、感想の変遷が履歴として残る。"""
    save_book_impression(isbn, body.text, participant_id=participant_id)
    return {"ok": True}


@router.get("/growth")
def get_growth_endpoint(participant_id: str = Depends(resolve_participant_id)):
    """育成インジケータ（設計書6.4）の元になる量。
    画面側では数値を出さず、照明の強さに変換して見せる。"""
    return get_growth_stats(participant_id)


@router.delete("/concept-edge/{edge_id}")
def delete_concept_edge_endpoint(
    edge_id: str,
    participant_id: str = Depends(resolve_participant_id),
):
    """本詳細パネルの意味づけ一覧から「消す」を押したときの削除。
    Concept自体を削除するため、同じ意味づけを共有する他の本からも一括で消える。"""
    ok = delete_concept_edge(edge_id, participant_id=participant_id)
    if not ok:
        raise HTTPException(status_code=404, detail="エッジが見つかりません")
    return {"ok": True}


# ============================================================
# グループ管理（グルーピングモード）
#
# 「グループ」は既存の Concept(意味づけ)をそのまま使う。ここでは
# conceptId を起点にした一覧・リネーム・統合・メンバー追加削除・削除・
# 操作ログ記録用のエンドポイントを追加する。
# ============================================================

@router.get("/groups")
def list_groups_endpoint(participant_id: str = Depends(resolve_participant_id)):
    """グルーピングモードの左パネル用：全グループ(Concept)を所属冊数・メンバー付きで返す。"""
    return {"groups": list_participant_groups(participant_id=participant_id)}


class RenameGroupRequest(BaseModel):
    text: str


@router.patch("/groups/{concept_id}/rename")
def rename_group_endpoint(
    concept_id: str,
    body: RenameGroupRequest,
    participant_id: str = Depends(resolve_participant_id),
):
    text = body.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="text is required")
    result = rename_group(concept_id, text, participant_id=participant_id)
    if not result:
        raise HTTPException(status_code=404, detail="グループが見つかりません")
    return result


class MergeGroupsRequest(BaseModel):
    source_concept_ids: list[str]
    target_text: str


@router.post("/groups/merge")
def merge_groups_endpoint(
    body: MergeGroupsRequest,
    participant_id: str = Depends(resolve_participant_id),
):
    if len(body.source_concept_ids) < 2:
        raise HTTPException(status_code=400, detail="source_concept_ids は2件以上必要です")
    text = body.target_text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="target_text is required")
    result = merge_groups(body.source_concept_ids, text, participant_id=participant_id)
    if not result:
        raise HTTPException(status_code=404, detail="グループが見つかりません")
    return result


@router.delete("/groups/{concept_id}")
def delete_group_endpoint(
    concept_id: str,
    participant_id: str = Depends(resolve_participant_id),
):
    result = delete_group(concept_id, participant_id=participant_id)
    if not result:
        raise HTTPException(status_code=404, detail="グループが見つかりません")
    return result


class AddGroupMembersRequest(BaseModel):
    isbns: list[str]


@router.post("/groups/{concept_id}/members")
def add_group_members_endpoint(
    concept_id: str,
    body: AddGroupMembersRequest,
    participant_id: str = Depends(resolve_participant_id),
):
    if not body.isbns:
        raise HTTPException(status_code=400, detail="isbns is required")
    n = add_group_members(concept_id, body.isbns, participant_id=participant_id)
    return {"added": n}


@router.delete("/groups/{concept_id}/members/{isbn}")
def remove_group_member_endpoint(
    concept_id: str,
    isbn: str,
    participant_id: str = Depends(resolve_participant_id),
):
    ok = remove_group_member(concept_id, isbn, participant_id=participant_id)
    if not ok:
        raise HTTPException(status_code=404, detail="メンバーが見つかりません")
    return {"ok": True}


class RemoveGroupMembersRequest(BaseModel):
    isbns: list[str]


@router.post("/groups/{concept_id}/members/remove")
def remove_group_members_endpoint(
    concept_id: str,
    body: RemoveGroupMembersRequest,
    participant_id: str = Depends(resolve_participant_id),
):
    """複数選択でまとめてグループから外す。DELETEでのbody送信を避けるためPOSTにしている。"""
    if not body.isbns:
        raise HTTPException(status_code=400, detail="isbns is required")
    n = remove_group_members(concept_id, body.isbns, participant_id=participant_id)
    return {"removed": n}


class GroupHighlightEventRequest(BaseModel):
    action: str  # "on" | "off"


@router.post("/groups/{concept_id}/highlight-event")
def log_group_highlight_event_endpoint(
    concept_id: str,
    body: GroupHighlightEventRequest,
    participant_id: str = Depends(resolve_participant_id),
):
    """左パネルからのハイライト操作(オン/オフ)をログに記録するだけの、fire-and-forget用エンドポイント。"""
    log_group_highlight_event(concept_id, body.action, participant_id=participant_id)
    return {"ok": True}


class ModeSwitchEventRequest(BaseModel):
    mode: str  # "normal" | "grouping"


@router.post("/mode-switch-event")
def log_mode_switch_event_endpoint(
    body: ModeSwitchEventRequest,
    participant_id: str = Depends(resolve_participant_id),
):
    """通常モード⇄グルーピングモードの切り替えをログに記録するだけの、fire-and-forget用エンドポイント。"""
    log_mode_switch_event(body.mode, participant_id=participant_id)
    return {"ok": True}


# ============================================================
# 事前推測 → 差分提示 → 事後推測（フェーズ1）
#
# ステップ1: 本棚を一通り眺めた後、閲覧者の素の解釈（介入前の値）をGuessRecordに記録する。
# ステップ2-4: 事前推測(全体・部分)の送信を受けて、記録時に決まった条件に応じて
#   - experimental: StyleProfileの差分をLLMが断定を避けた自然文に翻訳したカード（2.7）
#   - control     : 同じ見た目で、パーソナライズしていない一般的な読み方のヒント（2.8）
#   - transfer    : 差分提示自体を行わない（転移テスト、フェーズ2）
#   を出し分ける。
# ステップ5: 差分提示（またはtransferでは提示なし）の後、post_textとして事後推測を記録する。
#
# 条件の割り当ては experiment.assignment（未実装、4章で追加予定）が本来の割当元になる。
# それまでは _resolve_condition が固定で "experimental" を返す暫定実装。
# ============================================================

# 統制群向けの固定ヒント。LLMを使わず静的な文言にすることで、「情報を与えること
# 自体の効果」だけを実験群と揃え、内容のパーソナライズ差が紛れ込まないようにする。
CONTROL_HINTS = [
    "本の並び方には、その人らしさが表れることがあるかもしれません。",
    "同じ本棚でも、どこから手に取るかで印象は変わるかもしれません。",
    "本の並べ方は、その日の気分や事情に左右されていることもあるかもしれません。",
    "整理の仕方は、人によって大事にしているものが違うのかもしれません。",
]

_DIFF_METRIC_JA = {
    "avg_group_size":        "1グループあたりの平均冊数",
    "stdev_group_size":      "グループの大きさのばらつき",
    "isolated_ratio":        "どのグループにも属さない本の割合",
    "avg_multi_membership":  "1冊が複数グループに属す度合い",
    "max_depth":             "グループを入れ子にする深さ",
    "clustering_coefficient": "本棚上で似た本同士が固まって置かれている度合い",
    "modularity":            "グループ分けと実際の配置のまとまり具合",
    "modularity_nmi":        "配置のまとまりとグループ分けの一致度",
}


def _build_diff_card_prompt(diff: dict) -> str:
    lines = [
        "あなたは2人の読書家の「本の整理の仕方」の違いを、断定を避けた柔らかい言い方で伝えるアシスタントです。",
        "以下は構造指標（本の内容ではなく、並べ方・グループ分けの仕方だけの違い）です。",
        "",
    ]
    for key, label in _DIFF_METRIC_JA.items():
        row = diff["diffs"].get(key)
        if not row or row.get("diff") is None:
            continue
        lines.append(f"- {label}: あなた={row['viewer']}, 相手={row['owner']}, 差={row['diff']}")

    lines.append("")
    lines.append("上記の差分のうち、はっきり違いが出ているものを1〜2個選び、その違いが伝わる短い文を作ってください。")
    lines.append("必ず断定を避け、「〜かもしれません」で終える言い方にしてください。日本語で1文ずつ、40〜70字程度。")
    lines.append("本の内容（ジャンルや好み）には触れず、並べ方・グループ分けの仕方の違いだけを扱ってください。")
    lines.append("出力は次のJSON形式のみとし、前置きや説明文、コードブロック記法は付けないでください。")
    lines.append('{"cards": ["文1", "文2"]}')
    return "\n".join(lines)


def _ensure_tentative_tone(text: str) -> str:
    text = text.strip()
    if "かもしれ" in text:
        return text
    return f"{text.rstrip('。')}かもしれません。"


def _parse_diff_cards(raw: str) -> list[str]:
    text = raw.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.MULTILINE).strip()
    obj_start, obj_end = text.find("{"), text.rfind("}")
    candidate = text[obj_start:obj_end + 1] if obj_start != -1 and obj_end > obj_start else text
    try:
        data = json.loads(candidate)
        cards = data.get("cards") if isinstance(data, dict) else None
        if isinstance(cards, list):
            result = [_ensure_tentative_tone(str(c)) for c in cards if str(c).strip()]
            if result:
                return result[:2]
    except (json.JSONDecodeError, AttributeError):
        pass
    return [_ensure_tentative_tone(text[:80])]


def _ensure_style_profile_exists(db: Session, pid: str) -> None:
    """diff計算に使うStyleProfileがまだ無ければその場で作る。
    本棚のドラッグ操作(/bookshelf/sync-layout)を一度も行っていない参加者は
    投影スタイル分析システム側にまだParticipantノードすら無いことがあるため、
    save_style_profile単体ではなくSQLiteの現在の棚状態から橋渡しし直す
    （bookshelf_bridge.sync_from_bookshelfと同じ経路）。"""
    if get_latest_style_profile(pid) is not None:
        return
    try:
        sync_from_bookshelf(db, participant_id=pid)
    except Exception as e:
        logging.getLogger(__name__).warning("StyleProfileの初回計算に失敗しました(%s): %s", pid, e)


def _require_comparable(other_id: str, participant_id: str) -> None:
    if not is_valid_participant_id(other_id):
        raise HTTPException(status_code=400, detail="other_id が不正です")
    if other_id == participant_id:
        raise HTTPException(status_code=400, detail="自分自身とは比較できません")


def _resolve_condition(db: Session, participant_id: str, other_id: str) -> str:
    """このtrial（viewer×owner）に割り当てる実験条件を解決する。
    experiment.assignment（研究者が実験管理画面で生成するTrialAssignment）に
    割当があればそれを使う。割当が無い参加者ペア（研究者の自由閲覧・デモ用途）は
    暫定的に "experimental" を既定値として返す。"""
    condition = get_trial_condition(db, participant_id, other_id)
    return condition or "experimental"


class PreGuessRequest(BaseModel):
    text: str


@router.post("/compare/{other_id}/pre-guess")
def submit_pre_guess(
    other_id: str,
    body: PreGuessRequest,
    db: Session = Depends(get_db),
    participant_id: str = Depends(resolve_participant_id),
):
    """フェーズ1ステップ1：本棚を一通り眺めた後の、閲覧者の素の解釈を記録する。
    差分カードを見せる前の値なので、一度記録したら上書きしない。"""
    _require_comparable(other_id, participant_id)
    text = body.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="text は必須です")
    condition = _resolve_condition(db, participant_id, other_id)
    saved = save_pre_guess(
        viewer_id=participant_id, owner_id=other_id,
        target_type="overall", text=text, condition=condition,
    )
    if not saved:
        raise HTTPException(status_code=409, detail="事前推測は既に記録されています")
    return {"ok": True}


@router.get("/compare/{other_id}/pre-guess")
def read_pre_guess(
    other_id: str,
    participant_id: str = Depends(resolve_participant_id),
):
    """再訪問時に、既に事前推測を送信済みかを判定するための読み取り。"""
    if not is_valid_participant_id(other_id):
        raise HTTPException(status_code=400, detail="other_id が不正です")
    guess = get_guess(viewer_id=participant_id, owner_id=other_id, target_type="overall")
    return {
        "submitted": guess is not None,
        "text": guess["pre_text"] if guess else None,
        "condition": guess["condition"] if guess else None,
    }


def _book_meta_map(db: Session, isbns: set[str]) -> dict:
    """候補グループの本を見せるための最小限の書誌情報（タイトル・表紙のみ）。
    書誌情報は全参加者で共有のテーブルなので、所有者IDに関係なくISBNだけで引ける。"""
    rows = db.query(RegisteredBook).filter(RegisteredBook.isbn.in_(isbns)).all()
    return {r.isbn: {"isbn": r.isbn, "title": r.title, "cover": r.cover} for r in rows}


@router.get("/compare/{other_id}/group-candidates")
def group_candidates(
    other_id: str,
    db: Session = Depends(get_db),
    participant_id: str = Depends(resolve_participant_id),
):
    """部分推測に出す候補グループ（2〜3個）をシステム側が自動選定して返す。
    Group.name（意味データ）はここでは返さない。名前は推測の答えそのものなので、
    候補提示のUIでは書誌情報（タイトル・表紙）だけを見せ、閲覧者に自由記述で答えさせる。"""
    _require_comparable(other_id, participant_id)
    _ensure_style_profile_exists(db, other_id)

    candidates = get_candidate_groups(other_id)
    isbns = {isbn for c in candidates for isbn in c["isbns"]}
    book_meta = _book_meta_map(db, isbns)
    for c in candidates:
        c["books"] = [book_meta.get(isbn, {"isbn": isbn, "title": None, "cover": None}) for isbn in c["isbns"]]

    return {"candidates": candidates}


class PartialGuessRequest(BaseModel):
    candidate_group_ids: list[str]
    chosen_group_id: str
    text: str


@router.post("/compare/{other_id}/partial-guess")
def submit_partial_guess(
    other_id: str,
    body: PartialGuessRequest,
    db: Session = Depends(get_db),
    participant_id: str = Depends(resolve_participant_id),
):
    """システムが提示した候補グループのうち、閲覧者が選んだ1つについての推測を記録する。
    自由選択にすると閲覧者ごとに推測対象がバラバラになり差分の質を比較できなくなるため、
    候補自体は全員共通（システム選定）にし、その中からの選択だけを閲覧者に委ねている。"""
    _require_comparable(other_id, participant_id)
    text = body.text.strip()
    if not text or not body.chosen_group_id:
        raise HTTPException(status_code=400, detail="chosen_group_id と text は必須です")
    if body.chosen_group_id not in body.candidate_group_ids:
        raise HTTPException(status_code=400, detail="chosen_group_id は candidate_group_ids に含まれている必要があります")

    # 全体推測(overall)と同じ条件を引き継ぐ（1試行の中で条件が割れないようにする）。
    # overallがまだ無い場合（想定外の呼び出し順）はその場で解決する。
    overall = get_guess(viewer_id=participant_id, owner_id=other_id, target_type="overall")
    condition = overall["condition"] if overall else _resolve_condition(db, participant_id, other_id)

    saved = save_pre_guess(
        viewer_id=participant_id, owner_id=other_id, target_type="partial",
        text=text, condition=condition,
        target_group_id=body.chosen_group_id, candidate_group_ids=body.candidate_group_ids,
    )
    if not saved:
        raise HTTPException(status_code=409, detail="部分推測は既に記録されています")
    return {"ok": True}


@router.get("/compare/{other_id}/partial-guess")
def read_partial_guess(
    other_id: str,
    participant_id: str = Depends(resolve_participant_id),
):
    if not is_valid_participant_id(other_id):
        raise HTTPException(status_code=400, detail="other_id が不正です")
    guess = get_guess(viewer_id=participant_id, owner_id=other_id, target_type="partial")
    return {
        "submitted": guess is not None,
        "chosen_group_id": guess["target_group_id"] if guess else None,
        "text": guess["pre_text"] if guess else None,
        "condition": guess["condition"] if guess else None,
    }


class PostGuessRequest(BaseModel):
    target_type: str  # "overall" | "partial"
    text: str


@router.post("/compare/{other_id}/post-guess")
def submit_post_guess(
    other_id: str,
    body: PostGuessRequest,
    participant_id: str = Depends(resolve_participant_id),
):
    """フェーズ1ステップ5：差分提示（介入・一般ヒント・またはtransferでは提示なし）の後の
    事後推測。pre_textを残したまま編集してもらう想定のため、送り直せば何度でも上書きできる。"""
    _require_comparable(other_id, participant_id)
    if body.target_type not in TARGET_TYPES:
        raise HTTPException(status_code=400, detail="target_type は overall か partial のいずれかです")
    text = body.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="text は必須です")
    saved = save_post_guess(
        viewer_id=participant_id, owner_id=other_id,
        target_type=body.target_type, text=text,
    )
    if not saved:
        raise HTTPException(status_code=400, detail="先に事前推測を送信してください")
    return {"ok": True}


@router.get("/compare/{other_id}/post-guess")
def read_post_guess(
    other_id: str,
    target_type: str = "overall",
    participant_id: str = Depends(resolve_participant_id),
):
    if not is_valid_participant_id(other_id):
        raise HTTPException(status_code=400, detail="other_id が不正です")
    if target_type not in TARGET_TYPES:
        raise HTTPException(status_code=400, detail="target_type は overall か partial のいずれかです")
    guess = get_guess(viewer_id=participant_id, owner_id=other_id, target_type=target_type)
    return {
        "submitted": bool(guess and guess.get("post_text")),
        "pre_text": guess["pre_text"] if guess else None,
        "text": guess["post_text"] if guess else None,
    }


@router.get("/compare/{other_id}/diff-cards")
def diff_cards(
    other_id: str,
    db: Session = Depends(get_db),
    participant_id: str = Depends(resolve_participant_id),
):
    """事前推測(全体・部分)の送信後に見せる「あなたとこの人の整理の仕方を比べてみると」カード。
    両方が記録済みであることを前提にする（介入前の値を守るため）。条件(experimental/control/
    transfer)は事前推測の記録時に決まったものをそのまま使う（このエンドポイントでは選べない）。"""
    _require_comparable(other_id, participant_id)

    whole_guess = get_guess(viewer_id=participant_id, owner_id=other_id, target_type="overall")
    partial_guess = get_guess(viewer_id=participant_id, owner_id=other_id, target_type="partial")
    if whole_guess is None or partial_guess is None:
        raise HTTPException(status_code=400, detail="先に事前推測（全体・部分）を送信してください")

    condition = whole_guess["condition"]

    if condition == "transfer":
        # 転移試行では差分提示自体を行わない。フロントは基本ここを呼ばない設計だが、
        # 直接叩かれても空カードを返すだけで安全にしておく。
        return {"condition": "transfer", "cards": []}

    if condition == "control":
        return {"condition": "control", "cards": random.sample(CONTROL_HINTS, k=min(2, len(CONTROL_HINTS)))}

    _ensure_style_profile_exists(db, participant_id)
    _ensure_style_profile_exists(db, other_id)
    try:
        diff = compute_style_diff(viewer_id=participant_id, owner_id=other_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    prompt = _build_diff_card_prompt(diff)
    try:
        raw = _llm.generate_json(prompt, max_tokens=300)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"差分の翻訳に失敗しました: {e}")
    structural_cards = _parse_diff_cards(raw)

    # 2.6 意味差分カード：部分推測で選ばれた対象グループ限定で、そのグループの
    # 実際のname/commentだけをLLMに渡す（他グループ・他参加者のデータは含めない）。
    semantic_card = None
    target_group_id = partial_guess.get("target_group_id")
    if target_group_id:
        try:
            semantic_card = build_semantic_diff(_llm, partial_guess["pre_text"], target_group_id)
        except Exception as e:
            logging.getLogger(__name__).warning("意味差分の生成に失敗しました(%s): %s", other_id, e)

    return {"condition": "experimental", "structural_cards": structural_cards, "semantic_card": semantic_card}
