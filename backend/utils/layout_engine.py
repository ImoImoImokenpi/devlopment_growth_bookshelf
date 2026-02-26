from sqlalchemy.orm import Session
from models import ShelfLayout, ShelfDesign
from admin_neo4j.neo4j_crud import groups_from_neo4j
import logging
import random

logger = logging.getLogger(__name__)

def first_position(groups, books_per_shelf: int):

    positioned_books = []
    seen_isbns = set()
    current_row = 0
    current_col = 0

    for group in groups:
        books = group.get("books", [])

        new_books = [b for b in books if b["isbn"] not in seen_isbns]
        if not new_books:
            continue

        for book in new_books:

            positioned_books.append({
                "isbn": book["isbn"],
                "row": current_row,
                "col": current_col
            })

            seen_isbns.add(book["isbn"])
            current_col += 1

            if current_col >= books_per_shelf:
                current_row += 1
                current_col = 0

    return positioned_books

def rebuild_shelf_layout(db: Session):

    design = db.query(ShelfDesign).first()
    if not design:
        raise Exception("ShelfDesign が存在しません")

    groups = groups_from_neo4j()
    if not groups:
        return

    new_positions = first_position(groups, design.books_per_shelf)

    max_row = max((pos["row"] for pos in new_positions), default=0)
    design.total_shelves = max_row + 1

    db.query(ShelfLayout).delete()

    bulk_data = [
        {
            "isbn": pos["isbn"],
            "x": pos["row"],
            "y": pos["col"]
        }
        for pos in new_positions
    ]

    if bulk_data:
        db.bulk_insert_mappings(ShelfLayout, bulk_data)

    db.commit()


def place_randomly(db: Session, isbn: str):

    design = db.query(ShelfDesign).first()
    if not design:
        raise Exception("ShelfDesign が存在しません")

    # 既にあるなら何もしない
    exists = db.query(ShelfLayout).filter(ShelfLayout.isbn == isbn).first()
    if exists:
        return

    # total_shelves が 0 の保険
    if design.total_shelves == 0:
        design.total_shelves = 1

    books_per_shelf = design.books_per_shelf
    total_shelves = design.total_shelves

    used_positions = db.query(ShelfLayout.x, ShelfLayout.y).all()
    used_set = {(pos.x, pos.y) for pos in used_positions}

    all_positions = [
        (row, col)
        for row in range(total_shelves)
        for col in range(books_per_shelf)
    ]

    free_positions = [pos for pos in all_positions if pos not in used_set]

    # 空きなし → 段追加
    if not free_positions:
        row = total_shelves
        col = 0
        design.total_shelves += 1
    else:
        row, col = random.choice(free_positions)

    new_layout = ShelfLayout(
        isbn=isbn,
        x=row,
        y=col
    )

    db.add(new_layout)
    db.commit()