from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from graph.style_projection.ingest import ingest_shelf_snapshot, DEFAULT_K_NEIGHBORS
from graph.style_projection.groups import get_ancestor_groups, get_shelf_group_overlay
from graph.style_projection.metrics import save_style_profile, compute_style_profile
from graph.style_projection.diff import (
    get_latest_style_profile, compute_style_diff,
    list_participants_with_profiles, get_style_profile_history, compute_profile_diff,
)

router = APIRouter(prefix="/style_projection", tags=["style_projection"])


class WorkPayload(BaseModel):
    work_id: str
    title: str | None = None
    author: str | None = None
    published_year: int | None = None
    genre: str | None = None


class CommentPayload(BaseModel):
    comment_id: str | None = None
    text: str
    created_at: str | None = None


class BookPayload(BaseModel):
    shelved_id: str
    x: float = 0.0
    y: float = 0.0
    shelf_id: str | None = None
    condition: str | None = None
    work: WorkPayload
    group_ids: list[str] = []
    comments: list[CommentPayload] = []


class GroupPayload(BaseModel):
    group_id: str
    name: str | None = None
    created_by: str = "manual"
    parent_group_id: str | None = None


class ShelfSnapshotRequest(BaseModel):
    participant_id: str
    role: str | None = None  # "owner" | "viewer"
    groups: list[GroupPayload] = []
    books: list[BookPayload] = []
    adjacency_mode: str = "knn"  # "knn" | "threshold"
    k_neighbors: int = DEFAULT_K_NEIGHBORS
    distance_threshold: float | None = None


@router.post("/ingest")
def ingest_snapshot(body: ShelfSnapshotRequest):
    """本棚配置データ（座標・グループ所属・コメント）を投入する（upsert）。
    座標が含まれるため、ADJACENT_TOエッジもこの中で自動的に再計算される。"""
    payload = body.model_dump(exclude={"adjacency_mode", "k_neighbors", "distance_threshold"})
    try:
        return ingest_shelf_snapshot(
            payload,
            adjacency_mode=body.adjacency_mode,
            k_neighbors=body.k_neighbors,
            distance_threshold=body.distance_threshold,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/book/{shelved_id}/ancestor-groups")
def ancestor_groups(shelved_id: str):
    """その本が属する直接グループと、その祖先グループ一覧（depth昇順）。"""
    return {"groups": get_ancestor_groups(shelved_id)}


@router.post("/{participant_id}/profile/recompute")
def recompute_profile(participant_id: str):
    """構造指標を再計算し、新規のStyleProfileノードとして保存する
    （「配置完了イベント」のタイミングで呼ぶバッチ処理）。"""
    return save_style_profile(participant_id)


@router.get("/{participant_id}/profile/preview")
def preview_profile(participant_id: str):
    """保存せずに現在の構造指標だけを見たいとき用。"""
    return compute_style_profile(participant_id)


@router.get("/{participant_id}/shelf-overlay")
def shelf_overlay(participant_id: str):
    """本棚ビジュアルにグルーピング・孤立状況を重ねて見せるための読み取り専用データ。
    isbn（Work.work_id）をキーに、既存の本棚UI（/bookshelf/）とそのまま突き合わせられる。"""
    return get_shelf_group_overlay(participant_id)


@router.get("/{participant_id}/profile/latest")
def latest_profile(participant_id: str):
    profile = get_latest_style_profile(participant_id)
    if not profile:
        raise HTTPException(status_code=404, detail="StyleProfileがまだありません")
    return profile


@router.get("/participants")
def style_participants():
    """StyleProfileを1件以上持つ参加者の一覧（閲覧ページの選択肢用）。"""
    return {"participants": list_participants_with_profiles()}


@router.get("/{participant_id}/profile/history")
def profile_history(participant_id: str):
    """その参加者のStyleProfileを昔→今の順に全件返す（上書きせず追記保存しているため）。"""
    return {"profiles": get_style_profile_history(participant_id)}


@router.get("/{participant_id}/profile/diff")
def profile_diff(
    participant_id: str,
    from_profile_id: str | None = None,
    to_profile_id: str | None = None,
):
    """同一参加者内での、昔のStyleProfileと今のStyleProfileの差分。
    profile_idを省略すると最初のスナップショットと最新を自動比較する。"""
    try:
        return compute_profile_diff(participant_id, from_profile_id, to_profile_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/diff")
def style_diff(viewer_id: str, owner_id: str):
    """閲覧者と所有者の投影スタイル差分。後段のLLM翻訳にそのまま渡せる形式。"""
    try:
        return compute_style_diff(viewer_id, owner_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
