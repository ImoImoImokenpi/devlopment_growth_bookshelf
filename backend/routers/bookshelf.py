from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel
from typing import List, Optional
from models import ShelfLayout, ShelfDesign, RegisteredBook
from sqlalchemy.orm import Session
from database import get_db
from participant import resolve_participant_id
from shelf_period import DEFAULT_PERIOD, PRESENT, normalize_period
from graph.main_kg.neo4j_driver import get_session
from graph.main_kg.neo4j_crud import (
    update_shelf_layout_chain, remove_book_ownership, reconcile_shelf,
)
from graph.dialogue.store import get_session_info as get_dialogue_session_info
from graph.placement_analysis.profile import compute_and_save_placement_profile
import logging

logger = logging.getLogger(__name__)


router = APIRouter(prefix="/bookshelf", tags=["bookshelf"])

SHELF_MAX_WIDTH_PX = 800  # ShelfDesign.shelf_max_width に置き換えてもよい


def _period_param(period: str = Query(DEFAULT_PERIOD)) -> str:
    """「過去/現在」2本棚の動作確認用。period="present"（既定）は従来通りの
    本棚で、Neo4j側の研究データ（OWNS・概念グラフ・配置分析・投影スタイル分析）
    とも連携する。period="past" はSQL上の並びだけを別に持つ振り返り用の棚で、
    Neo4j側には一切書き込まない（研究データを汚さないため）。"""
    return normalize_period(period)


def _get_or_create_design(db: Session, participant_id: str, period: str) -> ShelfDesign:
    design = (
        db.query(ShelfDesign)
        .filter(ShelfDesign.participant_id == participant_id, ShelfDesign.period == period)
        .first()
    )
    if not design:
        design = ShelfDesign(participant_id=participant_id, period=period, total_shelves=1)
        db.add(design)
        db.flush()
    return design


@router.post("/add_shelves")
def add_shelves(
    db: Session = Depends(get_db),
    participant_id: str = Depends(resolve_participant_id),
    period: str = Depends(_period_param),
):
    design = _get_or_create_design(db, participant_id, period)
    design.total_shelves = (design.total_shelves or 0) + 1
    db.commit()
    return {"total_shelves": design.total_shelves}


@router.post("/remove_shelves")
def remove_shelves(
    db: Session = Depends(get_db),
    participant_id: str = Depends(resolve_participant_id),
    period: str = Depends(_period_param),
):
    design = (
        db.query(ShelfDesign)
        .filter(ShelfDesign.participant_id == participant_id, ShelfDesign.period == period)
        .first()
    )
    if not design or design.total_shelves <= 1:
        raise HTTPException(status_code=400, detail="これ以上段を削除できません")

    last_shelf_index = design.total_shelves -1

    # 一番下の段に本があるか確認
    books_on_last = db.query(ShelfLayout)\
        .filter(ShelfLayout.participant_id == participant_id,
                ShelfLayout.period == period,
                ShelfLayout.shelf_index == last_shelf_index)\
        .count()

    if books_on_last > 0:
        raise HTTPException(status_code=400, detail="一番下の段に本があるため削除できません")

    design.total_shelves -= 1
    db.commit()

    return {"total_shelves": design.total_shelves}

FRAME     = 20   # 棚の左右フレーム幅（フロントと合わせる）
SPINE_GAP = 2

class BookPosition(BaseModel):
    id:          int  # ShelfLayoutの行id。棚に同じ本を複数冊置けるため、isbnだけでは1冊を特定できない
    isbn:        str
    shelf_index: int
    x_pos:       float | None = 0
    order_index: int = 0  # 互換性のため残す

class SyncLayoutRequest(BaseModel):
    layout: List[BookPosition]
    # ユーザーが実際にドラッグした本。挿し込みで押し出されただけの本と区別し、
    # 移動の記録・次の対話のきっかけ(pendingMoves)はこの本だけを対象にする。
    moved_isbns: List[str] = []
    # 対話パネルを開いている間の並べ替えなら、その対話のID。
    # 対話中の移動だけを移動履歴(PlacementEvent)として残す。
    dialogue_session_id: Optional[str] = None



@router.get("/")
def fetch_bookshelf(
    db: Session = Depends(get_db),
    participant_id: str = Depends(resolve_participant_id),
    period: str = Depends(_period_param),
):
    design = _get_or_create_design(db, participant_id, period)
    db.commit()

    layouts = db.query(ShelfLayout)\
        .filter(ShelfLayout.participant_id == participant_id, ShelfLayout.period == period)\
        .order_by(ShelfLayout.shelf_index, ShelfLayout.x_pos)\
        .all()

    if not layouts:
        return {"shelves": [], "total_shelves": design.total_shelves}

    layout_map = {l.isbn: l for l in layouts}

    title_map: dict[str, str] = {}
    possessed_since_map: dict[str, str | None] = {}
    # possessedSince（OWNS）は「今、実際に持っている本棚」を前提にした研究データ
    # なので、period="present" のときだけNeo4jから引く。「過去」の棚は仮の並びで
    # 実際の所有関係を表さないため、常に未設定（褪せ演出なし）として扱う。
    if period == PRESENT:
        with get_session() as session:
            result = session.run(
                """
                MATCH (b:Book) WHERE b.isbn IN $isbns
                OPTIONAL MATCH (:Participant {participantId: $pid})-[own:OWNS]->(b)
                RETURN b.isbn AS isbn, b.title AS title, toString(own.possessedSince) AS possessed_since
                """,
                isbns=list(layout_map.keys()),
                pid=participant_id,
            )
            for r in result:
                title_map[r["isbn"]] = r["title"]
                possessed_since_map[r["isbn"]] = r["possessed_since"]

    reg_books = db.query(RegisteredBook).filter(RegisteredBook.isbn.in_(list(layout_map.keys()))).all()
    # period="past" ではNeo4jを引かないので、タイトルはRegisteredBook（登録時に
    # NDL/Google Booksから取得済み）から補う。
    reg_title_map = {rb.isbn: rb.title for rb in reg_books}
    spine_map = {rb.isbn: rb.spine_image for rb in reg_books}
    ndc_map = {rb.isbn: rb.ndc for rb in reg_books}
    # ShelfLayout.cover は配置時に埋められておらず常に空のため、登録時に
    # NDL/Google Booksから取得済みの RegisteredBook.cover（表表紙）を使う
    cover_map = {rb.isbn: rb.cover for rb in reg_books}
    # 統制UI（グリッド型）のソート（著者・登録日等）に使うため、本棚UIでは
    # 使っていない書誌項目もここでまとめて持たせる（データ層は共通化する）
    authors_map = {rb.isbn: (rb.authors.split(",") if rb.authors else []) for rb in reg_books}
    publisher_map = {rb.isbn: rb.publisher for rb in reg_books}
    published_year_map = {rb.isbn: rb.published_year for rb in reg_books}
    registered_at_map = {rb.isbn: rb.registered_at.isoformat() if rb.registered_at else None for rb in reg_books}

    shelves: dict[int, list] = {}
    for l in layouts:
        shelves.setdefault(l.shelf_index, []).append({
            "id":              l.id,
            "isbn":            l.isbn,
            "title":           title_map.get(l.isbn) or reg_title_map.get(l.isbn, ""),
            "cover":           cover_map.get(l.isbn),
            "spine_image":     spine_map.get(l.isbn),
            "size_label":      l.size_label,
            "shelf_index":     l.shelf_index,
            "x_pos":           l.x_pos,
            "order_index":     l.order_index,
            "pages":           l.pages,
            "height_mm":       l.height_mm,
            "ndc":             ndc_map.get(l.isbn),
            "authors":         authors_map.get(l.isbn, []),
            "publisher":       publisher_map.get(l.isbn),
            "published_year":  published_year_map.get(l.isbn),
            "registered_at":   registered_at_map.get(l.isbn),
            "possessed_since": possessed_since_map.get(l.isbn),
        })

    return {
        "shelves":       [{"shelf_index": k, "books": v} for k, v in sorted(shelves.items())],
        "total_shelves": design.total_shelves,
    }


def _run_placement_analysis_sync(participant_id: str) -> None:
    """配置完了イベントを受けて本棚の物理配置分析（高さ・色・著者・ジャンル×配置・
    孤立本・デザイン根拠）を再計算する（バックグラウンド実行）。
    update_shelf_layout_chain がすでにSHELF_NEXT/ShelfPositionをNeo4jへ反映済みの
    前提で動くため、この関数の直前で呼ぶこと。失敗しても本棚の保存自体は無関係。"""
    try:
        compute_and_save_placement_profile(participant_id)
    except Exception as e:
        logger.warning("本棚配置分析システムへの反映に失敗しました: %s", e)


@router.post("/sync-layout")
async def sync_layout(
    body: SyncLayoutRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    participant_id: str = Depends(resolve_participant_id),
    period: str = Depends(_period_param),
):
    try:
        for pos in body.layout:
            # idで1冊ごとに更新する（isbnだけだと、同じ本が2冊あるとき
            # どちらの行を更新すべきか特定できない）。
            db.query(ShelfLayout)\
                .filter(ShelfLayout.id == pos.id,
                        ShelfLayout.participant_id == participant_id,
                        ShelfLayout.period == period)\
                .update({
                    "shelf_index": pos.shelf_index,
                    "x_pos":       round(pos.x_pos, 2),
                    "order_index": pos.order_index,
                }, synchronize_session=False)

        db.commit()

        # period="past" は振り返り用の仮の並びで、実際の所有関係ではない。
        # Neo4j側の SHELF_NEXT・投影スタイル分析・配置分析は「今の実際の蔵書」を
        # 前提にした研究データなので、period="present" のときだけ連携する。
        if period == PRESENT:
            ids = [pos.id for pos in body.layout]
            pages_map = {
                r.id: r.pages
                for r in db.query(ShelfLayout)
                           .filter(ShelfLayout.participant_id == participant_id,
                                   ShelfLayout.period == period,
                                   ShelfLayout.id.in_(ids))
                           .all()
            }
            neo4j_payload = [
                {**pos.model_dump(), "pages": pages_map.get(pos.id, 200)}
                for pos in body.layout
            ]
            # 終わった対話・他人の対話のIDが来たら、対話の外の並べ替えとして扱う
            dialogue_session_id = None
            if body.dialogue_session_id:
                info = get_dialogue_session_info(participant_id, body.dialogue_session_id)
                if info and info["status"] == "active":
                    dialogue_session_id = body.dialogue_session_id
            update_shelf_layout_chain(
                neo4j_payload, participant_id=participant_id, moved_isbns=body.moved_isbns,
                dialogue_session_id=dialogue_session_id,
            )
            # 画面の本棚にない本が知識グラフに残っていたら外す（SQLite側だけが変わった場合の残り）
            shelf_isbns = [
                r.isbn for r in db.query(ShelfLayout.isbn)
                .filter(ShelfLayout.participant_id == participant_id, ShelfLayout.period == PRESENT)
            ]
            reconcile_shelf(participant_id, shelf_isbns)

            # 投影スタイル分析(ShelvedBook/Work/Group/StyleProfile)の自動反映は止めた。
            # 「みんなの本棚」の比較で必要になったときだけ、その場で作られる
            # (routers/knowledge_graph.py の _ensure_style_profile_exists)。
            background_tasks.add_task(_run_placement_analysis_sync, participant_id)

        return {"status": "success"}
    except Exception as e:
        import traceback
        traceback.print_exc()
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/remove-book/{layout_id}")
def remove_book_from_shelf(
    layout_id: int,
    db: Session = Depends(get_db),
    participant_id: str = Depends(resolve_participant_id),
    period: str = Depends(_period_param),
):
    """layout_id は ShelfLayout の行id。棚には同じISBNの本を複数冊置けるため、
    isbnだけでは「どの1冊を外すか」を特定できない。"""
    layout = (
        db.query(ShelfLayout)
        .filter(ShelfLayout.id == layout_id,
                ShelfLayout.participant_id == participant_id,
                ShelfLayout.period == period)
        .first()
    )
    if not layout:
        raise HTTPException(status_code=404, detail="本が見つかりません")
    isbn = layout.isbn
    db.delete(layout)
    db.commit()
    if period != PRESENT:
        return {"status": "deleted", "isbn": isbn}
    # Book ノードは他の被験者も持ちうるので消さず、所有関係だけ外す。
    # ただし同じ本をまだ他に何冊か（present）棚に持っている場合は、
    # 所有関係自体は変わらないので外さない。
    remaining = db.query(ShelfLayout).filter(
        ShelfLayout.participant_id == participant_id,
        ShelfLayout.period == PRESENT,
        ShelfLayout.isbn == isbn,
    ).count()
    if remaining == 0:
        remove_book_ownership(isbn, participant_id=participant_id)
    return {"status": "deleted", "isbn": isbn}
