from fastapi import APIRouter, Depends, HTTPException, Body
from schemas import AddFromHandRequest
from sqlalchemy.orm import Session
from database import get_db
from models import MyHand
from neo4j_crud import add_book_with_meaning
from routers.google_books import fetch_book_metadata
from routers.bookshelf import get_current_shelf_count, add_book_to_shelf_layout
# from routers.knowledge_graph import rebuild_knowledge_graph

router = APIRouter(prefix="/books", tags=["books"])

GOOGLE_BOOKS_API = "https://www.googleapis.com/books/v1/volumes"

@router.get("/myhand")
def get_myhand(db: Session = Depends(get_db)):
    items = db.query(MyHand).all()

    results = []
    for item in items:
        results.append({
            "book_id": item.book_id,
            "title": item.title,
            "author": item.author,
            "cover": item.cover,
        })

    return results

@router.post("/add_to_hand")
def add_to_hand(data: dict = Body(...), db: Session = Depends(get_db)):
    book_id = data["book_id"]

    existing = db.query(MyHand).filter(MyHand.book_id == book_id).first()
    if existing:
        return {"message": "already exists"}

    new_book = MyHand(
        book_id=book_id,
        title=data["title"],
        author=data["author"],
        cover=data["cover"],
    )
    db.add(new_book)
    db.commit()

    return {"message": "added", "book_id": book_id}

@router.post("/add_from_hand")
def add_from_hand(req: AddFromHandRequest, db: Session = Depends(get_db)):
    if not req.book_ids:
        raise HTTPException(status_code=400, detail="No books selected")

    added = 0
    removed = 0

    start_index = get_current_shelf_count(db)

    for i, book_id in enumerate(req.book_ids):
        # ① メタデータ取得
        book = fetch_book_metadata(book_id)
        # ② Neo4j に保存（意味・概念）
        add_book_with_meaning(book)
        added += 1

        # ③ SQLite に座標保存
        add_book_to_shelf_layout(
            db=db,
            book_id=book_id,
            index=start_index + i
        )

        hand_item = (
            db.query(MyHand)
            .filter(MyHand.book_id == book_id)
            .first()
        )
        if hand_item:
            db.delete(hand_item)
            removed += 1

    db.commit()

    return {"status": "ok", "added": added, "remove_from_hand": removed}

# 本を手元から削除
@router.delete("/remove_from_hand/{book_id}")
def remove_from_hand(book_id: str, db: Session = Depends(get_db)):
    # DBから該当本を検索
    book = db.query(MyHand).filter(MyHand.book_id == book_id).first()
    if not book:
        raise HTTPException(status_code=404, detail="本が見つかりません")

    db.delete(book)
    db.commit()
    return {"status": "success", "deleted_book_id": book_id}

# @router.post("/add_from_hand")
# def add_from_hand(data: dict = Body(...), db: Session = Depends(get_db)):
#     book_ids = data.get("book_ids", [])

#     if not book_ids:
#         raise HTTPException(status_code=400, detail="book_ids is empty")

#     hand_books = (
#         db.query(MyHand)
#         .filter(MyHand.book_id.in_(book_ids))
#         .all()
#     )

#     for h in hand_books:
#         # すでに本棚にあるか確認
#         exists = db.query(MyBookshelf).filter(MyBookshelf.book_id == h.book_id).first()
#         if not exists:
#             db.add(MyBookshelf(
#                 book_id=h.book_id,
#                 title=h.title,
#                 author=h.author,
#                 cover=h.cover,
#             ))

#         # 手元から削除
#         db.delete(h)

#     db.commit()
#     rebuild_knowledge_graph(db)
#     db.commit()

#     return {"message": "added", "count": len(hand_books)}