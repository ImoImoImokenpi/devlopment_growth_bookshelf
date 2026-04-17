from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import List
from models import ShelfLayout, ShelfDesign
from sqlalchemy.orm import Session
from database import get_db
from admin_neo4j.neo4j_driver import get_session
from admin_neo4j.neo4j_crud import update_shelf_layout_chain  # Neo4j更新ロジック
from utils.layout_engine import rebuild_shelf_layout, place_randomly

router = APIRouter(prefix="/bookshelf", tags=["bookshelf"])

SHELF_MAX_WIDTH_PX = 800  # ShelfDesign.shelf_max_width に置き換えてもよい

# def calc_spine_width_px(pages: int | None) -> int:
#     """ページ数 → 背表紙の厚み(px)。最小8、最大36"""
#     if not pages or pages <= 0:
#         return 14
#     mm = max(4, min(18, pages / 500 * 30))
#     return int(mm * 2)

# def calc_spine_height_px(height_mm: int | None) -> int:
#     """本の高さ(mm) → 背表紙の高さ(px)。最小100、最大220"""
#     if not height_mm or height_mm <= 0:
#         return 160
#     return max(100, min(220, int(height_mm * 1.2)))

# def spine_fields(book) -> dict:
#     """MyHand → ShelfLayout の描画フィールドを返す"""
#     return {
#         "spine_width_px":  calc_spine_width_px(book.pages),
#         "spine_height_px": calc_spine_height_px(book.height_mm),
#         "cover":           book.cover,
#         "size_label":      book.size_label,
#     }

# # --- リクエストモデル ---
# class BookPosition(BaseModel):
#     isbn: str
#     shelf_index: int
#     order_index: int

# # ↓ リストをラップするモデルが必要
# class SyncLayoutRequest(BaseModel):
#     layout: List[BookPosition]

# BOOK_WIDTH = 80
# BOOK_HEIGHT = 120
# BOOKS_PER_SHELF = 10

# SHELF_MARGIN_X = 40
# SHELF_MARGIN_Y = 30
# SHELF_HEIGHT = 150
# SHELF_GAP = 30

# def add_to_shelf(db: Session, book) -> bool:
#     isbn = book.isbn
    
#     if db.query(ShelfLayout).filter(ShelfLayout.isbn == isbn).first():
#         return False

#     existing_count = db.query(ShelfLayout).count()
    
#     try:
#         if existing_count == 0:
#             print("初回配置")
#             rebuild_shelf_layout(db, trigger_book=book)
#         else:
#             print("追加配置")
#             place_randomly(db, book)
#     except Exception as e:
#         return False
    
#     # ← ここで必ず再構築
#     db.flush()
#     layouts = db.query(ShelfLayout).all()
#     neo4j_payload = [{"isbn": l.isbn, "x": l.x, "y": l.y} for l in layouts]
#     update_shelf_layout_chain(neo4j_payload)

#     return True

# @router.get("/")
# def fetch_bookshelf(db: Session = Depends(get_db)):

#     design = db.query(ShelfDesign).first()
#     if not design:
#         design = ShelfDesign(total_shelves=1)
#         db.add(design)
#         db.commit()

#     layouts = (
#         db.query(ShelfLayout)
#             .order_by(ShelfLayout.shelf_index, ShelfLayout.order_index)
#             .all()
#     )

#     # ← 早期returnをやめて、本が0冊でも total_shelves を返す
#     if not layouts:
#         return {"shelves": [], "total_shelves": design.total_shelves}

#     layout_map = {l.isbn: l for l in layouts}

#     title_map: dict[str, str] = {}
#     with get_session() as session:
#         result = session.run(
#             "MATCH (b:Book) WHERE b.isbn IN $isbns RETURN b.isbn AS isbn, b.title AS title",
#             isbns=list(layout_map.keys())
#         )
#         for r in result:
#             title_map[r["isbn"]] = r["title"]

#     shelves: dict[int, list] = {}
#     for l in layouts:
#         shelves.setdefault(l.shelf_index, []).append({
#             "isbn":            l.isbn,
#             "title":           title_map.get(l.isbn, ""),
#             "cover":           l.cover,
#             "size_label":      l.size_label,
#             "order_index":     l.order_index,
#             "spine_width_px":  l.spine_width_px,
#             "spine_height_px": l.spine_height_px,
#         })

#     return {
#         "shelves":       [{"shelf_index": k, "books": v} for k, v in sorted(shelves.items())],
#         "total_shelves": design.total_shelves,  # ← 常にDBの値を使う
#     }

# @router.post("/sync-layout")
# async def sync_layout(body: SyncLayoutRequest, db: Session = Depends(get_db)):
#     try:
#         # bulk_update_mappings は id(PK) が必要なので使わず、
#         # isbn で直接 UPDATE する
#         for pos in body.layout:
#             db.query(ShelfLayout)\
#                 .filter(ShelfLayout.isbn == pos.isbn)\
#                 .update({
#                     "shelf_index": pos.shelf_index,
#                     "order_index": pos.order_index,
#                 }, synchronize_session=False)

#         db.commit()

#         neo4j_payload = [item.model_dump() for item in body.layout]
#         update_shelf_layout_chain(neo4j_payload)

#         return {"status": "success"}

#     except Exception as e:
#         import traceback
#         traceback.print_exc()
#         db.rollback()
#         raise HTTPException(status_code=500, detail=str(e))


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
    x_pos:       int
    order_index: int = 0  # 互換性のため残す

class SyncLayoutRequest(BaseModel):
    layout: List[BookPosition]


def find_free_x(db: Session, shelf_index: int, spine_width: int) -> int:
    """
    指定の棚で空きスペースを左から探してx_posを返す。
    他の本と重ならない最初の位置。
    """
    books = db.query(ShelfLayout)\
        .filter(ShelfLayout.shelf_index == shelf_index)\
        .order_by(ShelfLayout.x_pos)\
        .all()

    candidate = FRAME
    for b in books:
        # candidate と b が重なるか
        if candidate + spine_width > b.x_pos and candidate < b.x_pos + b.spine_width_px:
            # 重なるので b の右に移動
            candidate = b.x_pos + b.spine_width_px + SPINE_GAP
    return candidate


def place_book(db: Session, book, design: "ShelfDesign") -> None:
    """
    空きを探して本を配置。全棚に収まらなければ新段を追加。
    """
    SHELF_MAX_WIDTH = 800  # ShelfDesign に持たせてもよい

    for shelf_idx in range(design.total_shelves):
        x = find_free_x(db, shelf_idx, book.spine_width_px)
        if x + book.spine_width_px + FRAME <= SHELF_MAX_WIDTH:
            # この棚に収まる
            order = db.query(ShelfLayout)\
                .filter(ShelfLayout.shelf_index == shelf_idx)\
                .count()
            layout = ShelfLayout(
                isbn            = book.isbn,
                shelf_index     = shelf_idx,
                x_pos           = x,
                order_index     = order,
                spine_width_px  = book.spine_width_px,
                spine_height_px = book.spine_height_px,
                cover           = book.cover,
                size_label      = book.size_label,
            )
            db.add(layout)
            return

    # 全棚に収まらなかった → 新段追加
    design.total_shelves += 1
    new_shelf = design.total_shelves - 1
    layout = ShelfLayout(
        isbn            = book.isbn,
        shelf_index     = new_shelf,
        x_pos           = FRAME,
        order_index     = 0,
        spine_width_px  = book.spine_width_px,
        spine_height_px = book.spine_height_px,
        cover           = book.cover,
        size_label      = book.size_label,
    )
    db.add(layout)


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

    shelves: dict[int, list] = {}
    for l in layouts:
        shelves.setdefault(l.shelf_index, []).append({
            "isbn":            l.isbn,
            "title":           title_map.get(l.isbn, ""),
            "cover":           l.cover,
            "size_label":      l.size_label,
            "shelf_index":     l.shelf_index,
            "x_pos":           l.x_pos,           # ← 追加
            "order_index":     l.order_index,
            "spine_width_px":  l.spine_width_px,
            "spine_height_px": l.spine_height_px,
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
                    "x_pos":       pos.x_pos,
                    "order_index": pos.order_index,
                }, synchronize_session=False)
        db.commit()

        neo4j_payload = [item.model_dump() for item in body.layout]
        update_shelf_layout_chain(neo4j_payload)

        return {"status": "success"}
    except Exception as e:
        import traceback
        traceback.print_exc()
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


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