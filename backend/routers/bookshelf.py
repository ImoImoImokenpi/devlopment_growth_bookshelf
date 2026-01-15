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

def calc_shelf_position(groups, books_per_shelf):
    positioned_books = []
    seen_ids = set()
    current_row = 0
    current_col = 0

    for group in groups:
        # 念のため重複排除
        filtered_group = [
            b for b in group if b["book_id"] not in seen_ids
        ]
        if not filtered_group:
            continue

        group_size = len(filtered_group)
        remaining_space = books_per_shelf - current_col

        # グループが現在段に収まらなければ改行
        if group_size > remaining_space and current_col > 0:
            current_row += 1
            current_col = 0

        for book in filtered_group:
            if current_col >= books_per_shelf:
                current_row += 1
                current_col = 0

            positioned_books.append({
                "book_id": book["book_id"],
                "row": current_row,
                "col": current_col
            })

            seen_ids.add(book["book_id"])
            current_col += 1

    return positioned_books

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
