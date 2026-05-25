from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import List
from models import ShelfLayout, ShelfDesign, RegisteredBook
from sqlalchemy.orm import Session
from database import get_db
from admin_neo4j.neo4j_driver import get_session
from admin_neo4j.neo4j_crud import update_shelf_layout_chain, save_concept

router = APIRouter(prefix="/bookshelf", tags=["bookshelf"])

SHELF_MAX_WIDTH_PX = 800  # ShelfDesign.shelf_max_width に置き換えてもよい


@router.post("/add_shelves")
def add_shelves(db: Session = Depends(get_db)):
    design = db.query(ShelfDesign).first()
    if not design:
        design = ShelfDesign(total_shelves=1)
        db.add(design)
    else:
        design.total_shelves += 1
    db.commit()
    return {"total_shelves": design.total_shelves}


@router.post("/remove_shelves")
def remove_shelves(db: Session = Depends(get_db)):
    design = db.query(ShelfDesign).first()
    if not design or design.total_shelves <= 1:
        raise HTTPException(status_code=400, detail="これ以上段を削除できません")

    last_shelf_index = design.total_shelves -1

    # 一番下の段に本があるか確認
    books_on_last = db.query(ShelfLayout)\
        .filter(ShelfLayout.shelf_index == last_shelf_index)\
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
def fetch_bookshelf(db: Session = Depends(get_db)):
    design = db.query(ShelfDesign).first()
    if not design:
        design = ShelfDesign(total_shelves=1)
        db.add(design)
        db.commit()

    layouts = db.query(ShelfLayout)\
        .order_by(ShelfLayout.shelf_index, ShelfLayout.x_pos)\
        .all()

    if not layouts:
        return {"shelves": [], "total_shelves": design.total_shelves}

    layout_map = {l.isbn: l for l in layouts}

    title_map: dict[str, str] = {}
    with get_session() as session:
        result = session.run(
            "MATCH (b:Book) WHERE b.isbn IN $isbns RETURN b.isbn AS isbn, b.title AS title",
            isbns=list(layout_map.keys())
        )
        for r in result:
            title_map[r["isbn"]] = r["title"]

    reg_books = db.query(RegisteredBook).filter(RegisteredBook.isbn.in_(list(layout_map.keys()))).all()
    spine_map = {rb.isbn: rb.spine_image for rb in reg_books}
    ndc_map = {rb.isbn: rb.ndc for rb in reg_books}

    shelves: dict[int, list] = {}
    for l in layouts:
        shelves.setdefault(l.shelf_index, []).append({
            "isbn":            l.isbn,
            "title":           title_map.get(l.isbn, ""),
            "cover":           l.cover,
            "spine_image":     spine_map.get(l.isbn),
            "size_label":      l.size_label,
            "shelf_index":     l.shelf_index,
            "x_pos":           l.x_pos,
            "order_index":     l.order_index,
            "pages":           l.pages,
            "height_mm":       l.height_mm,
            "ndc":             ndc_map.get(l.isbn),
        })

    return {
        "shelves":       [{"shelf_index": k, "books": v} for k, v in sorted(shelves.items())],
        "total_shelves": design.total_shelves,
    }


@router.post("/sync-layout")
async def sync_layout(body: SyncLayoutRequest, db: Session = Depends(get_db)):
    try:
        for pos in body.layout:
            db.query(ShelfLayout)\
                .filter(ShelfLayout.isbn == pos.isbn)\
                .update({
                    "shelf_index": pos.shelf_index,
                    "x_pos":       round(pos.x_pos, 2),
                    "order_index": pos.order_index,
                }, synchronize_session=False)

        db.commit()

        isbns = [pos.isbn for pos in body.layout]
        pages_map = {
            r.isbn: r.pages
            for r in db.query(ShelfLayout).filter(ShelfLayout.isbn.in_(isbns)).all()
        }
        neo4j_payload = [
            {**pos.model_dump(), "pages": pages_map.get(pos.isbn, 200)}
            for pos in body.layout
        ]
        update_shelf_layout_chain(neo4j_payload)

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
def remove_book_from_shelf(isbn: str, db: Session = Depends(get_db)):
    layout = db.query(ShelfLayout).filter(ShelfLayout.isbn == isbn).first()
    if not layout:
        raise HTTPException(status_code=404, detail="本が見つかりません")
    db.delete(layout)
    db.commit()
    return {"status": "deleted", "isbn": isbn}


@router.post("/save-concept")
def save_concept_endpoint(body: SaveConceptRequest):
    if not body.meaning.strip():
        raise HTTPException(status_code=400, detail="meaning is required")
    if not body.isbns:
        raise HTTPException(status_code=400, detail="isbns is required")
    save_concept(isbns=body.isbns, meaning=body.meaning.strip())
    return {"status": "ok", "concept": body.meaning, "books": len(body.isbns)}


@router.post("/migrate-x-pos")
def migrate_x_pos(db: Session = Depends(get_db)):
    """order_index → x_pos への一回限りのマイグレーション"""
    layouts = db.query(ShelfLayout)\
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