from fastapi import APIRouter, Depends, HTTPException, Body
from schemas import AddFromHandRequest
from sqlalchemy.orm import Session
from database import get_db
from models import MyHand
from admin_neo4j.neo4j_crud import add_book_with_meaning

from utils.shelf_utils import add_to_shelf

# from routers.knowledge_graph import rebuild_knowledge_graph

router = APIRouter(prefix="/books", tags=["books"])

@router.get("/myhand")
def get_myhand(db: Session = Depends(get_db)):
    items = db.query(MyHand).all()

    results = []
    for item in items:
        results.append({
            "isbn": item.isbn,
            "title": item.title,
            "authors": item.authors.split(",") if item.authors else [],
            "cover": item.cover,
            "ndc": {"ndc_full": item.ndc},
            "height_mm": item.height_mm,
            "pagaes": item.pages,
            "size_label": item.size_label,
        })

    return results

@router.post("/add_to_hand")
def add_to_hand(
    data: dict = Body(...),
    db: Session = Depends(get_db)
):
    # -------------------------
    # ① ISBN チェック & 正規化
    # -------------------------
    isbn = data.get("isbn")
    if not isbn:
        raise HTTPException(status_code=400, detail="ISBN is required")

    # -------------------------
    # ② 既存チェック
    # -------------------------
    existing = db.query(MyHand).filter(MyHand.isbn == isbn).first()
    if existing:
        return {
            "message": "already exists",
            "isbn": isbn
        }

    # -------------------------
    # ③ メタデータ取得
    # -------------------------
    authors = data.get("authors") or []
    if isinstance(authors, list):
        authors_str = ",".join(str(a) for a in authors)
    else:
        authors_str = str(authors)
    # -------------------------
    # ④ MyHand に保存
    # -------------------------
    new_book = MyHand(
        isbn=isbn,
        title=data.get("title"),
        authors=authors_str,
        publisher=data.get("publisher"),      # 追加
        published_year=data.get("published_year"), # 追加
        cover=data.get("cover"),
        ndc=data.get("ndc_full"),             # 追加
        height_mm=data.get("height_mm"),       # 追加
        pages=data.get("pages"),               # 追加
        size_label=data.get("size_label"),     # 追加
    )

    db.add(new_book)
    db.commit()
    db.refresh(new_book)

    return {
        "message": "added",
        "isbn": isbn
    }

@router.post("/add_from_hand")
async def add_from_hand(
    req: AddFromHandRequest, 
    db: Session = Depends(get_db)
):
    if not req.isbns:
        raise HTTPException(status_code=400, detail="No books selected")

    added = []
    skipped = []

    for isbn in req.isbns:
        hand_book = db.query(MyHand).filter(MyHand.isbn == isbn).first()
        
        if not hand_book:
            skipped.append(isbn)
            continue

        # ✅ 修正②: Neo4j 保存失敗時はスキップ（SQLに触らない）
        try:
            add_book_with_meaning(hand_book)
        except Exception as e:
            print(f"Neo4j保存エラー [{isbn}]: {e}")
            skipped.append(isbn)
            continue

        # ✅ 修正③: SQL保存失敗時はNeo4j側との不整合をログに残す
        success = add_to_shelf(db, hand_book)
        if not success:
            print(f"警告: Neo4j保存済みだがSQL保存失敗 [{isbn}]")
            skipped.append(isbn)
            continue
        
        db.delete(hand_book)
        # ✅ 修正④: 1件ずつcommitして中途半端な状態を防ぐ
        try:
            db.commit()
            added.append(isbn)
        except Exception as e:
            db.rollback()
            print(f"コミットエラー [{isbn}]: {e}")
            skipped.append(isbn)

    return {
        "message": "Success",
        "added": added,
        "skipped": skipped
    }

# 本を手元から削除
@router.delete("/remove_from_hand/{isbn}")
def remove_from_hand(isbn: str, db: Session = Depends(get_db)):
    # DBから該当本を検索
    book = db.query(MyHand).filter(MyHand.isbn == isbn).first()
    if not book:
        raise HTTPException(status_code=404, detail="本が見つかりません")

    db.delete(book)
    db.commit()
    return {"status": "success", "deleted_book_id": isbn}