from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from typing import List
from models import ShelfLayout, ShelfDesign, RegisteredBook
from sqlalchemy.orm import Session
from database import get_db, SessionLocal
from participant import resolve_participant_id
from graph.main_kg.neo4j_driver import get_session
from graph.main_kg.neo4j_crud import (
    update_shelf_layout_chain, save_concept, remove_book_ownership,
)
from graph.style_projection.bookshelf_bridge import sync_from_bookshelf
from graph.placement_analysis.profile import compute_and_save_placement_profile
import logging

logger = logging.getLogger(__name__)


router = APIRouter(prefix="/bookshelf", tags=["bookshelf"])

SHELF_MAX_WIDTH_PX = 800  # ShelfDesign.shelf_max_width に置き換えてもよい


def _get_or_create_design(db: Session, participant_id: str) -> ShelfDesign:
    design = (
        db.query(ShelfDesign)
        .filter(ShelfDesign.participant_id == participant_id)
        .first()
    )
    if not design:
        design = ShelfDesign(participant_id=participant_id, total_shelves=1)
        db.add(design)
        db.flush()
    return design


@router.post("/add_shelves")
def add_shelves(
    db: Session = Depends(get_db),
    participant_id: str = Depends(resolve_participant_id),
):
    design = _get_or_create_design(db, participant_id)
    design.total_shelves = (design.total_shelves or 0) + 1
    db.commit()
    return {"total_shelves": design.total_shelves}


@router.post("/remove_shelves")
def remove_shelves(
    db: Session = Depends(get_db),
    participant_id: str = Depends(resolve_participant_id),
):
    design = (
        db.query(ShelfDesign)
        .filter(ShelfDesign.participant_id == participant_id)
        .first()
    )
    if not design or design.total_shelves <= 1:
        raise HTTPException(status_code=400, detail="これ以上段を削除できません")

    last_shelf_index = design.total_shelves -1

    # 一番下の段に本があるか確認
    books_on_last = db.query(ShelfLayout)\
        .filter(ShelfLayout.participant_id == participant_id,
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
    isbn:        str
    shelf_index: int
    x_pos:       float | None = 0
    order_index: int = 0  # 互換性のため残す

class SyncLayoutRequest(BaseModel):
    layout: List[BookPosition]



@router.get("/")
def fetch_bookshelf(
    db: Session = Depends(get_db),
    participant_id: str = Depends(resolve_participant_id),
):
    design = _get_or_create_design(db, participant_id)
    db.commit()

    layouts = db.query(ShelfLayout)\
        .filter(ShelfLayout.participant_id == participant_id)\
        .order_by(ShelfLayout.shelf_index, ShelfLayout.x_pos)\
        .all()

    if not layouts:
        return {"shelves": [], "total_shelves": design.total_shelves}

    layout_map = {l.isbn: l for l in layouts}

    title_map: dict[str, str] = {}
    possessed_since_map: dict[str, str | None] = {}
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
            "isbn":            l.isbn,
            "title":           title_map.get(l.isbn, ""),
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


def _run_style_projection_sync(participant_id: str) -> None:
    """配置完了イベントを受けて投影スタイル分析システムへ反映する（バックグラウンド実行）。
    GDSを使う構造指標の計算はそれなりに時間がかかるので、本棚の保存レスポンスを
    ブロックしないようレスポンス送出後に走らせる。失敗しても本棚の保存自体は無関係なので、
    警告ログに留めて無視する。"""
    db = SessionLocal()
    try:
        sync_from_bookshelf(db, participant_id=participant_id)
    except Exception as e:
        logger.warning("投影スタイル分析システムへの反映に失敗しました: %s", e)
    finally:
        db.close()


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
):
    try:
        for pos in body.layout:
            db.query(ShelfLayout)\
                .filter(ShelfLayout.participant_id == participant_id,
                        ShelfLayout.isbn == pos.isbn)\
                .update({
                    "shelf_index": pos.shelf_index,
                    "x_pos":       round(pos.x_pos, 2),
                    "order_index": pos.order_index,
                }, synchronize_session=False)

        db.commit()

        isbns = [pos.isbn for pos in body.layout]
        pages_map = {
            r.isbn: r.pages
            for r in db.query(ShelfLayout)
                       .filter(ShelfLayout.participant_id == participant_id,
                               ShelfLayout.isbn.in_(isbns))
                       .all()
        }
        neo4j_payload = [
            {**pos.model_dump(), "pages": pages_map.get(pos.isbn, 200)}
            for pos in body.layout
        ]
        update_shelf_layout_chain(neo4j_payload, participant_id=participant_id)

        background_tasks.add_task(_run_style_projection_sync, participant_id)
        background_tasks.add_task(_run_placement_analysis_sync, participant_id)

        return {"status": "success"}
    except Exception as e:
        import traceback
        traceback.print_exc()
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

class SaveConceptRequest(BaseModel):
    meaning: str
    isbns: List[str]


@router.delete("/remove-book/{isbn}")
def remove_book_from_shelf(
    isbn: str,
    db: Session = Depends(get_db),
    participant_id: str = Depends(resolve_participant_id),
):
    layout = (
        db.query(ShelfLayout)
        .filter(ShelfLayout.participant_id == participant_id, ShelfLayout.isbn == isbn)
        .first()
    )
    if not layout:
        raise HTTPException(status_code=404, detail="本が見つかりません")
    db.delete(layout)
    db.commit()
    # Book ノードは他の被験者も持ちうるので消さず、所有関係だけ外す
    remove_book_ownership(isbn, participant_id=participant_id)
    return {"status": "deleted", "isbn": isbn}


@router.post("/save-concept")
def save_concept_endpoint(
    body: SaveConceptRequest,
    participant_id: str = Depends(resolve_participant_id),
):
    if not body.meaning.strip():
        raise HTTPException(status_code=400, detail="meaning is required")
    if not body.isbns:
        raise HTTPException(status_code=400, detail="isbns is required")
    concept_id = save_concept(
        isbns=body.isbns,
        meaning=body.meaning.strip(),
        participant_id=participant_id,
    )
    return {
        "status": "ok",
        "concept": body.meaning,
        "concept_id": concept_id,
        "books": len(body.isbns),
    }


@router.post("/migrate-x-pos")
def migrate_x_pos(
    db: Session = Depends(get_db),
    participant_id: str = Depends(resolve_participant_id),
):
    """order_index → x_pos への一回限りのマイグレーション"""
    layouts = db.query(ShelfLayout)\
        .filter(ShelfLayout.participant_id == participant_id)\
        .order_by(ShelfLayout.shelf_index, ShelfLayout.order_index)\
        .all()
    shelves: dict[int, list] = {}
    for l in layouts:
        shelves.setdefault(l.shelf_index, []).append(l)
    for shelf_books in shelves.values():
        acc = FRAME
        for book in shelf_books:
            book.x_pos = acc
            acc += book.spine_width_px + SPINE_GAP
    db.commit()
    return {"status": "migrated"}