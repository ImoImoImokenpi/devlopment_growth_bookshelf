from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.orm import Session
from database import get_db
from models import MyHand, MyBookshelf
import requests
import math
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

router = APIRouter(prefix="/books")

GOOGLE_BOOKS_API = "https://www.googleapis.com/books/v1/volumes"

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

    books = db.query(MyBookshelf).all()
    N = len(books)
    if N < 1:
        raise HTTPException(status_code=400, detail="No books to arrange")

    # ---- 本のテキスト情報作成 ----
    texts = []
    for b in books:
        desc = ""
        try:
            r = requests.get(f"{GOOGLE_BOOKS_API}/{b.book_id}", timeout=5)
            if r.status_code == 200:
                desc = r.json().get("volumeInfo", {}).get("description", "")
        except:
            pass
        texts.append(f"{b.title} {b.author or ''} {desc}")

    # ---- 類似度マトリックス ----
    vec = TfidfVectorizer(max_features=5000)
    X = vec.fit_transform(texts)
    sim = cosine_similarity(X)
    dist = 1 - sim

    # ---- 棚マトリックス準備 ----
    cols = math.ceil(math.sqrt(N))
    rows = math.ceil(N / cols)
    shelf = [[None for _ in range(cols)] for _ in range(rows)]
    placed = {}

    # ---- 中央に最初の本 ----
    center = (rows // 2, cols // 2)
    shelf[center[0]][center[1]] = 0
    placed[0] = center

    # ---- Greedy 配置 ----
    for i in range(1, N):
        best_pos = None
        best_score = float("inf")
        for r in range(rows):
            for c in range(cols):
                if shelf[r][c] is not None:
                    continue
                score = sum(dist[i][j] * (abs(r-pr)+abs(c-pc)+1) for j, (pr, pc) in placed.items())
                if score < best_score:
                    best_score = score
                    best_pos = (r, c)
        shelf[best_pos[0]][best_pos[1]] = i
        placed[i] = best_pos

    # ---- DB 更新 & レスポンス ----
    nodes = []
    for i, b in enumerate(books):
        r, c = placed[i]
        b.row = r
        b.col = c
        nodes.append({
            "id": b.book_id,
            "title": b.title,
            "author": b.author,
            "cover": b.cover,
            "row": r,
            "col": c,
        })

    db.commit()
    
    return {
        "message": "added_to_shelf_and_arranged",
        "count": len(hand_books),
        "rows": rows,
        "cols": cols,
        "nodes": nodes
    }