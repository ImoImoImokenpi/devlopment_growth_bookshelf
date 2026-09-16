"""新本棚UI(自由配置) vs 旧本棚UI(グリッド) 比較実験API。

「投影のズレ」研究(register/bookshelf/knowledge_graph等)とは別の参加者プール・
別の研究なので、依存はNDL書誌検索(routers.search)のような純粋に客観的な
機能だけに留め、participant_id・ShelfLayout・Concept等には一切触れない。

観察者向けエンドポイント(/uiab/observe/*)は、応答に ui_variant を絶対に
含めないこと(ブラインド化)。含めてよいのは /uiab/admin/* のみ。
"""
from __future__ import annotations

import csv
import io

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from models import RegisteredBook
from uiab_participant import (
    resolve_uiab_participant_id, resolve_uiab_observer_id, validate_period,
)
from graph.uiab_experiment import (
    identity, collection, layout, groups as groups_mod, events as events_mod,
    bigfive, observer as observer_mod, export as export_mod,
)
from graph.uiab_experiment.bigfive import BIGFIVE_ITEM_KEYS
from graph.uiab_experiment.events import EVENT_TYPES

router = APIRouter(prefix="/uiab", tags=["uiab-experiment"])


# ============================================================
# 参加者: 群解決
# ============================================================

@router.get("/whoami")
def whoami(participant_id: str = Depends(resolve_uiab_participant_id)):
    """フロントが「どちらのUIを描画するか」を決めるための内部値。
    この文字列自体を参加者に見える形でそのまま表示しないこと。"""
    return {"ui_variant": identity.get_or_assign_ui_variant(participant_id)}


@router.get("/status")
def status(participant_id: str = Depends(resolve_uiab_participant_id)):
    """フロントの画面遷移(どの時期のどの段階か)をまとめて判定するための状態。"""
    p1 = layout.get_session_status(participant_id, "period1") or {}
    p2 = layout.get_session_status(participant_id, "period2") or {}
    bf = bigfive.get_bigfive_responses(participant_id)
    return {
        "period1": p1,
        "period2": p2,
        "bigfive_answered": len(bf) >= len(BIGFIVE_ITEM_KEYS),
    }


# ============================================================
# 蔵書申告(時期別)
# ============================================================

class CollectionAddRequest(BaseModel):
    isbn: str
    title: str | None = None
    authors: str | None = None
    publisher: str | None = None
    published_year: str | None = None
    height_mm: int | None = None
    pages: int | None = None
    spine_color: str | None = None  # "R,G,B"（任意。物理的に本が手元に無い場合など）
    cover: str | None = None


@router.get("/{period}/collection")
def get_collection(period: str, participant_id: str = Depends(resolve_uiab_participant_id)):
    validate_period(period)
    return collection.list_collection(participant_id, period)


@router.post("/{period}/collection")
def add_collection(
    period: str,
    body: CollectionAddRequest,
    db: Session = Depends(get_db),
    participant_id: str = Depends(resolve_uiab_participant_id),
):
    validate_period(period)
    # RegisteredBookは全研究共有のISBN→書誌キャッシュ。無ければ作る。
    if not db.query(RegisteredBook).filter(RegisteredBook.isbn == body.isbn).first():
        db.add(RegisteredBook(
            isbn=body.isbn, title=body.title, authors=body.authors or "",
            publisher=body.publisher, published_year=body.published_year,
            height_mm=body.height_mm or 180, pages=body.pages or 200,
            spine_color=body.spine_color, cover=body.cover,
        ))
        db.commit()

    collection.add_to_collection(participant_id, period, body.isbn, body.model_dump())
    return {"status": "added", "isbn": body.isbn}


@router.delete("/{period}/collection/{isbn}")
def delete_collection(
    period: str, isbn: str,
    participant_id: str = Depends(resolve_uiab_participant_id),
):
    validate_period(period)
    collection.remove_from_collection(participant_id, period, isbn)
    layout.remove_position(participant_id, period, isbn)
    return {"status": "removed", "isbn": isbn}


# ============================================================
# 配置
# ============================================================

class PositionRequest(BaseModel):
    isbn: str
    shelf_index: int | None = None
    x_pos: float | None = None
    grid_row: int | None = None
    grid_col: int | None = None


@router.get("/{period}/shelf")
def get_shelf(period: str, participant_id: str = Depends(resolve_uiab_participant_id)):
    validate_period(period)
    return layout.list_positions(participant_id, period)


@router.post("/{period}/shelf/position")
def set_position(
    period: str, body: PositionRequest,
    participant_id: str = Depends(resolve_uiab_participant_id),
):
    validate_period(period)
    layout.upsert_position(
        participant_id, period, body.isbn,
        shelf_index=body.shelf_index, x_pos=body.x_pos,
        grid_row=body.grid_row, grid_col=body.grid_col,
    )
    return {"status": "ok"}


@router.delete("/{period}/shelf/position/{isbn}")
def delete_position(
    period: str, isbn: str,
    participant_id: str = Depends(resolve_uiab_participant_id),
):
    """棚から外して「未配置」に戻す(蔵書からは削除しない)。"""
    validate_period(period)
    layout.remove_position(participant_id, period, isbn)
    return {"status": "unplaced", "isbn": isbn}


# ============================================================
# セッション(作業時間・自分らしさ評定)
# ============================================================

class SelfExpressionRequest(BaseModel):
    score: int  # 1-7想定


@router.post("/{period}/session/start")
def session_start(period: str, participant_id: str = Depends(resolve_uiab_participant_id)):
    validate_period(period)
    layout.start_session(participant_id, period)
    return {"status": "started"}


@router.post("/{period}/session/complete")
def session_complete(period: str, participant_id: str = Depends(resolve_uiab_participant_id)):
    validate_period(period)
    layout.complete_session(participant_id, period)
    return {"status": "completed"}


@router.get("/{period}/session")
def session_status(period: str, participant_id: str = Depends(resolve_uiab_participant_id)):
    validate_period(period)
    status = layout.get_session_status(participant_id, period)
    return status or {"started_at": None, "completed_at": None, "self_expression_score": None}


@router.post("/{period}/self-expression")
def post_self_expression(
    period: str, body: SelfExpressionRequest,
    participant_id: str = Depends(resolve_uiab_participant_id),
):
    validate_period(period)
    if not (1 <= body.score <= 7):
        raise HTTPException(status_code=422, detail="score は1〜7で指定してください")
    layout.save_self_expression_rating(participant_id, period, body.score)
    return {"status": "ok"}


# ============================================================
# グルーピング・感想
# ============================================================

class GroupCreateRequest(BaseModel):
    label: str
    isbns: list[str]


class ImpressionRequest(BaseModel):
    text: str


@router.get("/{period}/groups")
def get_groups(period: str, participant_id: str = Depends(resolve_uiab_participant_id)):
    validate_period(period)
    return groups_mod.list_groups(participant_id, period)


@router.post("/{period}/groups")
def post_group(
    period: str, body: GroupCreateRequest,
    participant_id: str = Depends(resolve_uiab_participant_id),
):
    validate_period(period)
    if not body.label.strip() or not body.isbns:
        raise HTTPException(status_code=422, detail="labelとisbnsは必須です")
    group_id = groups_mod.create_group(participant_id, period, body.label.strip(), body.isbns)
    return {"group_id": group_id}


@router.delete("/{period}/groups/{group_id}")
def delete_group(
    period: str, group_id: str,
    participant_id: str = Depends(resolve_uiab_participant_id),
):
    validate_period(period)
    ok = groups_mod.delete_group(group_id, participant_id)
    if not ok:
        raise HTTPException(status_code=404, detail="グループが見つかりません")
    return {"status": "deleted"}


@router.get("/{period}/impression/{isbn}")
def get_impression(
    period: str, isbn: str,
    participant_id: str = Depends(resolve_uiab_participant_id),
):
    validate_period(period)
    return {"text": groups_mod.get_latest_impression(participant_id, period, isbn)}


@router.post("/{period}/impression/{isbn}")
def post_impression(
    period: str, isbn: str, body: ImpressionRequest,
    participant_id: str = Depends(resolve_uiab_participant_id),
):
    validate_period(period)
    groups_mod.save_impression(participant_id, period, isbn, body.text)
    return {"status": "ok"}


# ============================================================
# 操作ログ
# ============================================================

class EventRequest(BaseModel):
    event_type: str
    isbn: str | None = None
    extra: dict = {}


@router.post("/{period}/event")
def post_event(
    period: str, body: EventRequest,
    participant_id: str = Depends(resolve_uiab_participant_id),
):
    validate_period(period)
    if body.event_type not in EVENT_TYPES:
        raise HTTPException(status_code=422, detail=f"event_type は {sorted(EVENT_TYPES)} のいずれかです")
    try:
        events_mod.log_event(participant_id, period, body.event_type, body.isbn, body.extra)
    except Exception as e:
        raise HTTPException(status_code=422, detail=str(e))
    return {"status": "logged"}


# ============================================================
# ビッグファイブ(1回のみ)
# ============================================================

class BigFiveRequest(BaseModel):
    answers: dict[str, int]


@router.get("/bigfive")
def get_bigfive(participant_id: str = Depends(resolve_uiab_participant_id)):
    return {"item_keys": BIGFIVE_ITEM_KEYS, "answers": bigfive.get_bigfive_responses(participant_id)}


@router.post("/bigfive")
def post_bigfive(body: BigFiveRequest, participant_id: str = Depends(resolve_uiab_participant_id)):
    try:
        bigfive.save_bigfive_responses(participant_id, body.answers)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return {"status": "ok"}


# ============================================================
# 観察者評価(ブラインド)
# ============================================================

class ObserverGuessRequest(BaseModel):
    owner_id: str
    owner_period: str
    item_key: str
    score: int | None = None
    text: str | None = None


@router.get("/observe/next")
def observe_next(observer_id: str = Depends(resolve_uiab_observer_id)):
    identity.ensure_observer(observer_id)
    trial = observer_mod.get_or_create_next_trial(observer_id)
    if trial is None:
        return {"done": True}
    shelf = layout.list_positions(trial["owner_id"], trial["owner_period"])
    groups = groups_mod.list_groups(trial["owner_id"], trial["owner_period"])
    return {
        "done": False,
        "trial_index": trial["trial_index"],
        "owner_id": trial["owner_id"],       # 分析用の内部IDで、参加者本人を特定する情報は含まない
        "owner_period": trial["owner_period"],
        "shelf": shelf,
        "groups": groups,
        # ui_variant は意図的に含めない(ブラインド化)
    }


@router.post("/observe/guess")
def observe_guess(body: ObserverGuessRequest, observer_id: str = Depends(resolve_uiab_observer_id)):
    observer_mod.save_guess(observer_id, body.owner_id, body.owner_period, body.item_key, body.score, body.text)
    return {"status": "ok"}


# ============================================================
# 研究者向け管理・エクスポート(認証は設けない。既存のExperimentAdminと同じ運用)
# ============================================================

@router.get("/admin/participants")
def admin_participants():
    return {"participants": identity.list_participants_with_variant()}


@router.get("/admin/export.json")
def admin_export_json():
    return export_mod.export_all()


def _csv_response(rows: list[dict], filename: str) -> StreamingResponse:
    buffer = io.StringIO()
    fieldnames = list(rows[0].keys()) if rows else []
    writer = csv.DictWriter(buffer, fieldnames=fieldnames)
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    buffer.seek(0)
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/admin/export/placements.csv")
def admin_export_placements_csv():
    return _csv_response(export_mod.export_placements_flat(), "uiab_placements.csv")


@router.get("/admin/export/self-reports.csv")
def admin_export_self_reports_csv():
    return _csv_response(export_mod.export_self_reports_flat(), "uiab_self_reports.csv")


@router.get("/admin/export/observer-guesses.csv")
def admin_export_observer_guesses_csv():
    return _csv_response(export_mod.export_observer_guesses_flat(), "uiab_observer_guesses.csv")


@router.get("/admin/export/events.csv")
def admin_export_events_csv():
    return _csv_response(export_mod.export_events_flat(), "uiab_events.csv")
