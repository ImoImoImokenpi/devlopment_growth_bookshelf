from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.orm import Session
from database import get_db
from models import MyHand, MyBookshelf
import requests

router = APIRouter(prefix="/books")

@router.get("/myhand")
def get_myhand(db: Session = Depends(get_db)):
    items = db.query(MyHand).all()

    results = []
    for item in items:
        results.append({
            "id": item.book_id,
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

@router.post("/add_from_hand")
def add_from_hand(data: dict = Body(...), db: Session = Depends(get_db)):
    book_ids = data.get("book_ids", [])

    if not book_ids:
        raise HTTPException(status_code=400, detail="book_ids is empty")

    hand_books = (
        db.query(MyHand)
        .filter(MyHand.book_id.in_(book_ids))
        .all()
    )

    for h in hand_books:
        # すでに本棚にあるか確認
        exists = db.query(MyBookshelf).filter(MyBookshelf.book_id == h.book_id).first()
        if not exists:
            db.add(MyBookshelf(
                book_id=h.book_id,
                title=h.title,
                author=h.author,
                cover=h.cover,
            ))

        # 手元から削除
        db.delete(h)

    db.commit()

    return {
        "message": "added_to_shelf",
        "count": len(hand_books)
    }

@router.get("/mybookshelf")
def get_my_bookshelf(db: Session = Depends(get_db)):
    items = db.query(MyBookshelf).all()

    results = []
    for item in items:
        results.append({
            "id": item.book_id,
            "title": item.title,
            "author": item.author,
            "cover": item.cover,
        })

    return results

