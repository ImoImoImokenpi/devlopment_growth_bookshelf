from fastapi import APIRouter, Depends, HTTPException, Body
from schemas import AddFromHandRequest
from sqlalchemy.orm import Session
from database import get_db
from models import MyHand, ShelfLayout
from neo4j_crud import add_book_with_meaning, groups_from_neo4j
from routers.google_books import fetch_book_metadata
from routers.bookshelf import calc_shelf_position
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

    for book_id in req.book_ids:
        # ① メタデータ取得
        book = fetch_book_metadata(book_id)
        # ② Neo4j に保存（意味・概念）
        add_book_with_meaning(book)

        hand_item = (
            db.query(MyHand)
            .filter(MyHand.book_id == book_id)
            .first()
        )
        if hand_item:
            db.delete(hand_item)

    rebuild_shelf_layout(db)

    db.commit()

    return {"message": "Success"}

@router.post("/add_from_hand")
def add_from_hand(req: AddFromHandRequest, db: Session = Depends(get_db)):
    if not req.book_ids:
        raise HTTPException(status_code=400, detail="No books selected")

    # 1. Neo4j にすべての本を保存（意味を解析）
    for book_id in req.book_ids:
        book = fetch_book_metadata(book_id)
        add_book_with_meaning(book)
        
        # 手元（MyHand）から削除
        hand_item = db.query(MyHand).filter(MyHand.book_id == book_id).first()
        if hand_item:
            db.delete(hand_item)

    # 2. 本棚全体のレイアウトを再計算して SQLite を更新
    rebuild_shelf_layout(db)
    return {"message": "Success"}


# 棚の制限変更用のAPI
@router.post("/rebuild")
def rebuild_shelf(books_per_shelf: int, db: Session = Depends(get_db)):
    rebuild_shelf_layout(db, books_per_shelf=books_per_shelf)
    return {"message": f"Rebuilt with {books_per_shelf} books per shelf"}

def rebuild_shelf_layout(db: Session, books_per_shelf: int=5):
    groups = groups_from_neo4j()

    # ② 先ほど作成した Python 関数で全書籍の座標を計算
    new_positions = calc_shelf_position(groups, books_per_shelf=books_per_shelf)

    unique_map = {pos["book_id"]: pos for pos in new_positions}
    final_positions = unique_map.values()

    # ③ SQLite の既存レイアウトを一度クリア（または全更新）
    db.query(ShelfLayout).delete()

    # ④ 新しい座標を保存
    for b in final_positions:
        layout = ShelfLayout(
            book_id=b['book_id'],
            x=b['row'], # row
            y=b['col']  # col
        )
        db.add(layout)

    db.commit()

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