# from fastapi import APIRouter, Depends
# from sqlalchemy.orm import Session
# from database import get_db
# # from models import MyBookshelf
# from math import ceil, sqrt

# router = APIRouter(prefix="/bookshelf")

# @router.get("/")
# def get_my_bookshelf(db: Session = Depends(get_db)):
#     books = db.query(MyBookshelf).all()
#     N = len(books)

#     if N == 0:
#         return {
#             "rows": 0,
#             "cols": 0,
#             "cells": []
#         }

#     # ============================
#     # 1️⃣ 冊数から棚サイズ決定
#     # ============================
#     cols = ceil(sqrt(N))
#     rows = ceil(N / cols)
    
#     # 2️⃣ 内容の近さ（y座標）でソート
#     sorted_books = sorted(
#         books, 
#         key=lambda b: (b.y if b.y is not None else 0, b.x if b.x is not None else 0)
#     )

#     # ============================
#     # 3️⃣ 行・列への割当
#     # ============================
#     placed = []
#     for index, b in enumerate(sorted_books):
#         # 通し番号から行と列を計算
#         # これにより、似たもの同士が横に並び、入り切らない分が次の行（段）に行く
#         r = index // cols
#         c = index % cols

#         placed.append({
#             "row": r,
#             "col": c,
#             "book": {
#                 "id": b.book_id,
#                 "title": b.title,
#                 "cover": b.cover,
#                 "y_coord": b.y, # デバッグ・調整用に座標も持たせる
#                 "concepts": b.concepts or []
#             }
#         })

#     return {
#         "rows": rows,
#         "cols": cols,
#         "cells": placed
#     }

from fastapi import APIRouter, Depends
from models import ShelfLayout
from sqlalchemy.orm import Session
from database import get_db
from neo4j_driver import get_session

router = APIRouter(prefix="/bookshelf", tags=["bookshelf"])

BOOK_WIDTH = 80
BOOK_HEIGHT = 120
BOOKS_PER_SHELF = 10

SHELF_MARGIN_X = 40
SHELF_MARGIN_Y = 30
SHELF_HEIGHT = 150
SHELF_GAP = 30

def calc_shelf_position(index: int):
    """
    index: 本棚に追加された順番（0,1,2,...）
    戻り値: (row, col)
    """
    row = index // BOOKS_PER_SHELF
    col = index % BOOKS_PER_SHELF
    return row, col

def get_current_shelf_count(db: Session) -> int:
    return db.query(ShelfLayout).count()

def add_book_to_shelf_layout(db: Session, book_id: str, index: int):
    row, col = calc_shelf_position(index)

    layout = ShelfLayout(
        book_id=book_id,
        x=row,
        y=col
    )
    db.add(layout)

def get_shelf_books(db: Session):
    layouts = db.query(ShelfLayout).all()
    layout_map = {
        l.book_id: {"row": l.x, "col": l.y}
        for l in layouts
    }

    if not layout_map:
        return {"books": []}
    
    with get_session() as session:
        result = session.run(
            """
            MATCH (b:Book)
            WHERE b.book_id IN $book_ids
            RETURN
                b.book_id AS id,
                b.title AS title,
                b.cover AS cover
            """,
            book_ids=list(layout_map.keys())
        )

        books = []
        for r in result:
            pos = layout_map.get(r["id"])
            if not pos:
                continue

            books.append({
                "id": r["id"],
                "title": r["title"],
                "cover": r["cover"],
                "x": pos["row"],
                "y": pos["col"]
            })

    return {"books": books}
    
@router.get("/")
def fetch_bookshelf(db: Session = Depends(get_db)):
    return get_shelf_books(db)
