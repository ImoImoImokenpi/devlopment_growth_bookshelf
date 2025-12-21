from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from database import get_db
from models import MyBookshelf
from math import ceil, sqrt

router = APIRouter(prefix="/bookshelf")

@router.get("/")
def get_my_bookshelf(db: Session = Depends(get_db)):
    books = db.query(MyBookshelf).all()
    N = len(books)

    if N == 0:
        return {
            "rows": 0,
            "cols": 0,
            "cells": []
        }

    # ============================
    # 1️⃣ 冊数から棚サイズ決定
    # ============================
    cols = ceil(sqrt(N))
    rows = ceil(N / cols)

    # ============================
    # 2️⃣ 座標正規化準備
    # ============================
    xs = [b.x for b in books if b.x is not None]
    ys = [b.y for b in books if b.y is not None]

    # フォールバック（座標が無い場合も壊れない）
    if xs and ys:
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)

        def norm(v, a, b):
            return 0.5 if a == b else (v - a) / (b - a)
    else:
        min_x = max_x = min_y = max_y = None

        def norm(v, a, b):
            return 0.5  # 中央寄せ

    # ============================
    # 3️⃣ 初期セル割当
    # ============================
    raw_cells = []
    for b in books:
        nx = norm(b.x, min_x, max_x) if b.x is not None else 0.5
        ny = norm(b.y, min_y, max_y) if b.y is not None else 0.5

        raw_cells.append({
            "row": int(ny * (rows - 1)),
            "col": int(nx * (cols - 1)),
            "book": {
                "id": b.book_id,
                "title": b.title,
                "cover": b.cover,
            }
        })

    # ============================
    # 4️⃣ 衝突解決（スパイラル探索）
    # ============================
    grid = [[None for _ in range(cols)] for _ in range(rows)]
    placed = []

    def spiral(r, c):
        yield r, c
        for d in range(1, max(rows, cols)):
            for dr in range(-d, d + 1):
                for dc in range(-d, d + 1):
                    nr, nc = r + dr, c + dc
                    if 0 <= nr < rows and 0 <= nc < cols:
                        yield nr, nc

    for cell in raw_cells:
        for r, c in spiral(cell["row"], cell["col"]):
            if grid[r][c] is None:
                cell["row"] = r
                cell["col"] = c
                grid[r][c] = cell
                placed.append(cell)
                break

    # ============================
    # 5️⃣ レスポンス
    # ============================
    return {
        "rows": rows,
        "cols": cols,
        "cells": placed
    }
