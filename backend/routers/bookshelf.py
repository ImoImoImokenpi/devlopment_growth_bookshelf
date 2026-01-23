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

def calc_shelf_position(groups, books_per_shelf: int):
    positioned_books = []
    seen_ids = set()
    current_row = 0

    for group in groups:
        current_col = 0
        # 念のため重複排除
        for book in group:
            book_id = book["book_id"]

            # 重複排除
            if book_id in seen_ids:
                continue

            positioned_books.append({
                "book_id": book_id,
                "row": current_row,
                "col": current_col
            })

            seen_ids.add(book_id)
            current_col += 1

            if current_col >= books_per_shelf:
                current_row += 1
                current_col = 0
        
        if current_col > 0:
            current_row += 1

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
