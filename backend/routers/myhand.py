import asyncio
import re

from fastapi import APIRouter, Depends, HTTPException, Body, Query
from schemas import AddFromHandRequest
from sqlalchemy.orm import Session
from database import get_db
from models import MyHand, RegisteredBook, ShelfLayout
from participant import resolve_participant_id
from shelf_period import PRESENT, normalize_period
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

SEARCH_PER_SOURCE = 20   # 国会図書館・Google Books それぞれから取る件数
SEARCH_MAX_RESULTS = 40


@router.get("/search")
async def search_books(
    q: str = Query(..., min_length=1, max_length=100),
    db: Session = Depends(get_db),
    participant_id: str = Depends(resolve_participant_id),
):
    """本を探す（本を探す画面）。書名・著者・キーワード、またはISBNで探す。

    外部の検索は、おすすめで使っているもの（国会図書館 SRU と Google Books、
    routers/recommend.py の _search_ndl / _search_google）をそのまま使う。
    両方の結果をISBNでまとめ、両方で見つかった本・国会図書館で見つかった本を前に並べる。
    それぞれの本に、すでに今の本棚にあるか・手元にあるかを添える。
    """
    from routers.recommend import _isbn13, _search_google, _search_ndl

    query = re.sub(r"\s+", " ", q).strip()
    if not query:
        raise HTTPException(status_code=400, detail="探す言葉を入れてください")
    digits = re.sub(r"[-\s]", "", query)
    isbn_query = _isbn13(digits) if re.fullmatch(r"\d{9}[\dXx]|\d{13}", digits) else None

    if isbn_query:
        google, ndl = await asyncio.gather(
            _search_google(f"isbn:{isbn_query}", SEARCH_PER_SOURCE), _search_ndl(isbn_query, SEARCH_PER_SOURCE),
        )
    else:
        google, ndl = await asyncio.gather(
            _search_google(query, SEARCH_PER_SOURCE), _search_ndl(query, SEARCH_PER_SOURCE, all_words=True),
        )

    merged: dict[str, dict] = {}
    for source, books in (("ndl", ndl), ("google", google)):
        for b in books:
            # 中国の出版物（978-7）は Google Books の言語指定をすり抜けて混ざるので外す
            if b["isbn"].startswith("9787") or (isbn_query and b["isbn"] != isbn_query):
                continue
            cur = merged.get(b["isbn"])
            if cur is None:
                merged[b["isbn"]] = {**b, "sources": [source]}
                continue
            if source not in cur["sources"]:
                cur["sources"].append(source)
            for k, v in b.items():  # 片方にしかない書誌項目を補う
                if v and not cur.get(k):
                    cur[k] = v
    # 日本の本（978-4）→ 書名に探す言葉が多く入っている本 → 両方で見つかった本 → 国会図書館の本 の順
    # （国会図書館の「どこかに含む」検索は、目次などに言葉があるだけの本も返すため）
    words = [w.lower() for w in query.split()]

    def title_hits(b: dict) -> int:
        title = (b.get("title") or "").lower()
        return sum(1 for w in words if w in title)

    results = sorted(merged.values(), key=lambda b: (
        not b["isbn"].startswith("9784"), -title_hits(b), -len(b["sources"]), b["sources"][0] != "ndl"))
    results = results[:SEARCH_MAX_RESULTS]

    isbns = [b["isbn"] for b in results]
    registered = {r.isbn for r in db.query(RegisteredBook.isbn).filter(RegisteredBook.isbn.in_(isbns))}
    on_shelf = {r.isbn for r in db.query(ShelfLayout.isbn).filter(
        ShelfLayout.participant_id == participant_id, ShelfLayout.period == PRESENT, ShelfLayout.isbn.in_(isbns))}
    in_hand = {
        r.isbn for r in db.query(RegisteredBook.isbn)
        .join(MyHand, MyHand.registered_book_id == RegisteredBook.id)
        .filter(MyHand.participant_id == participant_id, RegisteredBook.isbn.in_(isbns))
    }
    for b in results:
        b["registered"] = b["isbn"] in registered
        b["on_shelf"] = b["isbn"] in on_shelf
        b["in_hand"] = b["isbn"] in in_hand
    return {"query": query, "isbn_query": isbn_query, "results": results}


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

    # 棚には同じ本を複数冊置けるので、既に棚にある本でも手元には入れられる
    # （もう1冊を棚に置くために、改めて手元→本棚の流れに乗せられるようにする）。

    db.add(MyHand(participant_id=participant_id, registered_book_id=reg_book.id))
    db.commit()
    return {"message": "added", "isbn": isbn}

@router.post("/add_from_hand")
async def add_from_hand(
    req: AddFromHandRequest,
    period: str = "present",
    db: Session = Depends(get_db),
    participant_id: str = Depends(resolve_participant_id),
):
    period = normalize_period(period)
    if not req.isbns:
        raise HTTPException(status_code=400, detail="No books selected")

    added, skipped = [], []

    for isbn in req.isbns:
        hand_book = _myhand_by_isbn(isbn, db, participant_id)
        if not hand_book:
            skipped.append(isbn)
            continue

        reg_book = hand_book.book  # RegisteredBook オブジェクト

        # 「過去」の棚は振り返り用の仮の並びで、実際の所有関係ではないため、
        # Neo4j側（Book/OWNS・概念グラフ）には一切書き込まない。
        if period == PRESENT:
            try:
                add_book_with_meaning(reg_book, participant_id=participant_id)
            except Exception as e:
                print(f"Neo4j保存エラー [{isbn}]: {e}")
                skipped.append(isbn)
                continue

        result = add_to_shelf(db, reg_book, participant_id=participant_id, period=period)

        if result == "error":
            print(f"棚への配置に失敗しました [{isbn}]（詳細は logs/app.log）")
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

    return {
        "message": "Success",
        "added": added,
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