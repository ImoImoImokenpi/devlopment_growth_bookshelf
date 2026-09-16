from fastapi import APIRouter, Depends, HTTPException, Body
from schemas import AddFromHandRequest
from sqlalchemy.orm import Session
from database import get_db
from models import MyHand, RegisteredBook, ShelfLayout
from participant import resolve_participant_id
from graph.main_kg.neo4j_crud import add_book_with_meaning

from utils.shelf_utils import add_to_shelf

router = APIRouter(prefix="/books", tags=["books"])

def _myhand_by_isbn(isbn: str, db: Session, participant_id: str):
    return (
        db.query(MyHand)
        .join(RegisteredBook, MyHand.registered_book_id == RegisteredBook.id)
        .filter(MyHand.participant_id == participant_id, RegisteredBook.isbn == isbn)
        .first()
    )

@router.get("/myhand")
def get_myhand(
    db: Session = Depends(get_db),
    participant_id: str = Depends(resolve_participant_id),
):
    items = db.query(MyHand).filter(MyHand.participant_id == participant_id).all()
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
    db: Session = Depends(get_db),
    participant_id: str = Depends(resolve_participant_id),
):
    isbn = data.get("isbn")
    if not isbn:
        raise HTTPException(status_code=400, detail="ISBN is required")

    reg_book = db.query(RegisteredBook).filter(RegisteredBook.isbn == isbn).first()
    if not reg_book:
        raise HTTPException(status_code=404, detail=f"ISBN {isbn} は登録されていません")

    if _myhand_by_isbn(isbn, db, participant_id):
        return {"message": "already exists", "isbn": isbn}

    # 既に自分の棚にある本は手元に入れない。
    # 入れてしまうと棚へ移せず、手元に残り続けてしまう。
    on_shelf = (
        db.query(ShelfLayout)
        .filter(ShelfLayout.participant_id == participant_id, ShelfLayout.isbn == isbn)
        .first()
    )
    if on_shelf:
        return {"message": "already_on_shelf", "isbn": isbn}

    db.add(MyHand(participant_id=participant_id, registered_book_id=reg_book.id))
    db.commit()
    return {"message": "added", "isbn": isbn}

@router.post("/add_from_hand")
async def add_from_hand(
    req: AddFromHandRequest,
    db: Session = Depends(get_db),
    participant_id: str = Depends(resolve_participant_id),
):
    if not req.isbns:
        raise HTTPException(status_code=400, detail="No books selected")

    added, already_on_shelf, skipped = [], [], []

    for isbn in req.isbns:
        hand_book = _myhand_by_isbn(isbn, db, participant_id)
        if not hand_book:
            skipped.append(isbn)
            continue

        reg_book = hand_book.book  # RegisteredBook オブジェクト

        try:
            add_book_with_meaning(reg_book, participant_id=participant_id)
        except Exception as e:
            print(f"Neo4j保存エラー [{isbn}]: {e}")
            skipped.append(isbn)
            continue

        result = add_to_shelf(db, reg_book, participant_id=participant_id)

        if result == "error":
            print(f"棚への配置に失敗しました [{isbn}]（詳細は logs/app.log）")
            skipped.append(isbn)
            continue

        # 既に棚にある場合も手元からは取り除く。
        # ここで残すと、置けないのに手元に居座り続けて詰まってしまう。
        db.delete(hand_book)
        try:
            db.commit()
            (added if result == "placed" else already_on_shelf).append(isbn)
        except Exception as e:
            db.rollback()
            print(f"コミットエラー [{isbn}]: {e}")
            skipped.append(isbn)

    return {
        "message": "Success",
        "added": added,
        "already_on_shelf": already_on_shelf,
        "skipped": skipped,
    }


@router.delete("/remove_from_hand/{isbn}")
def remove_from_hand(
    isbn: str,
    db: Session = Depends(get_db),
    participant_id: str = Depends(resolve_participant_id),
):
    hand_book = _myhand_by_isbn(isbn, db, participant_id)
    if not hand_book:
        raise HTTPException(status_code=404, detail="本が見つかりません")
    db.delete(hand_book)
    db.commit()
    return {"status": "success", "deleted_book_id": isbn}