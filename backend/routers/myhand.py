from fastapi import APIRouter, Depends, HTTPException, Body
from schemas import AddFromHandRequest
from sqlalchemy.orm import Session
from database import get_db
from models import MyHand, RegisteredBook
from admin_neo4j.neo4j_crud import add_book_with_meaning

from utils.shelf_utils import add_to_shelf

router = APIRouter(prefix="/books", tags=["books"])

def _myhand_by_isbn(isbn: str, db: Session):
    return (
        db.query(MyHand)
        .join(RegisteredBook, MyHand.registered_book_id == RegisteredBook.id)
        .filter(RegisteredBook.isbn == isbn)
        .first()
    )

@router.get("/myhand")
def get_myhand(db: Session = Depends(get_db)):
    items = db.query(MyHand).all()
    return [
        {
            "isbn":           item.isbn,
            "title":          item.title,
            "authors":        item.authors.split(",") if item.authors else [],
            "cover":          item.cover,
            "spine_image":    item.spine_image,
            "ndc":            {"ndc_full": item.ndc},
            "height_mm":      item.height_mm,
            "pages":          item.pages,
            "size_label":     item.size_label,
        }
        for item in items
    ]

@router.post("/add_to_hand")
def add_to_hand(
    data: dict = Body(...),
    db: Session = Depends(get_db)
):
    isbn = data.get("isbn")
    if not isbn:
        raise HTTPException(status_code=400, detail="ISBN is required")

    reg_book = db.query(RegisteredBook).filter(RegisteredBook.isbn == isbn).first()
    if not reg_book:
        raise HTTPException(status_code=404, detail=f"ISBN {isbn} は登録されていません")

    if _myhand_by_isbn(isbn, db):
        return {"message": "already exists", "isbn": isbn}

    db.add(MyHand(registered_book_id=reg_book.id))
    db.commit()
    return {"message": "added", "isbn": isbn}

@router.post("/add_from_hand")
async def add_from_hand(
    req: AddFromHandRequest,
    db: Session = Depends(get_db)
):
    if not req.isbns:
        raise HTTPException(status_code=400, detail="No books selected")

    added, skipped = [], []

    for isbn in req.isbns:
        hand_book = _myhand_by_isbn(isbn, db)
        if not hand_book:
            skipped.append(isbn)
            continue

        reg_book = hand_book.book  # RegisteredBook オブジェクト

        try:
            add_book_with_meaning(reg_book)
        except Exception as e:
            print(f"Neo4j保存エラー [{isbn}]: {e}")
            skipped.append(isbn)
            continue

        success = add_to_shelf(db, reg_book)
        if not success:
            print(f"警告: Neo4j保存済みだがSQL保存失敗 [{isbn}]")
            skipped.append(isbn)
            continue

        db.delete(hand_book)
        try:
            db.commit()
            added.append(isbn)
        except Exception as e:
            db.rollback()
            print(f"コミットエラー [{isbn}]: {e}")
            skipped.append(isbn)

    return {"message": "Success", "added": added, "skipped": skipped}


@router.delete("/remove_from_hand/{isbn}")
def remove_from_hand(isbn: str, db: Session = Depends(get_db)):
    hand_book = _myhand_by_isbn(isbn, db)
    if not hand_book:
        raise HTTPException(status_code=404, detail="本が見つかりません")
    db.delete(hand_book)
    db.commit()
    return {"status": "success", "deleted_book_id": isbn}