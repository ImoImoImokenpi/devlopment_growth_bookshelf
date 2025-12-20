from fastapi import FastAPI, Query, HTTPException, Depends, Body
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from models import MyBookshelf
import requests  # ← 必須！

from database import Base, engine, get_db
import routers.myhand as myhand_router

from pydantic import BaseModel
from typing import List
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.manifold import MDS
import numpy as np
import math


# DB初期化
Base.metadata.create_all(bind=engine)

app = FastAPI()

# CORS設定
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

GOOGLE_BOOKS_API = "https://www.googleapis.com/books/v1/volumes"

# ルータ
app.include_router(myhand_router.router)

@app.get("/")
def root():
    return {"message": "backend running!"}

@app.get("/search")
def search_books(q: str = Query(...), page: int = 1, per_page: int = 20):
    try:
        start_index = (page - 1) * per_page
        params = {
            "q": q,
            "maxResults": per_page,
            "startIndex": start_index,
        }
        res = requests.get(GOOGLE_BOOKS_API, params=params, timeout=5)
        res.raise_for_status()
        data = res.json()

    except requests.RequestException as e:
        raise HTTPException(status_code=500, detail=str(e))

    books = []
    for item in data.get("items", []):
        info = item.get("volumeInfo", {})
        book_id = item.get("id")
        if not book_id:
            continue
        books.append({
            "id": book_id,
            "title": info.get("title", "不明"),
            "author": ", ".join(info.get("authors", [])) if "authors" in info else "不明",
            "cover": info.get("imageLinks", {}).get("thumbnail"),
            "isbn_13": next((i["identifier"] for i in info.get("industryIdentifiers", []) if i["type"]=="ISBN_13"), None),
            "isbn_10": next((i["identifier"] for i in info.get("industryIdentifiers", []) if i["type"]=="ISBN_10"), None),
        })

    total_items = data.get("totalItems", 0)
    total_pages = max(1, (total_items + per_page - 1) // per_page)

    return {
        "books": books,
        "page": page,
        "total_pages": total_pages,
        "total_items": total_items,
    }

@app.get("/mybookshelf")
def get_my_bookshelf(db: Session = Depends(get_db)): 
    items = db.query(MyBookshelf).all() 
    
    return [ 
        { 
            "id": b.book_id, 
            "title": b.title, 
            "author": b.author, 
            "cover": b.cover, 
            "row": b.row, 
            "col": b.col, 
        } 
        for b in items 
    ]

@app.get("/knowledge-graph")
def knowledge_graph(db: Session = Depends(get_db)):
    books = db.query(MyBookshelf).all()
    N = len(books)

    if N < 2:
        raise HTTPException(status_code=400, detail="Need at least 2 books")

    # ---- テキスト作成 ----
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

    # ---- 類似度 ----
    vec = TfidfVectorizer(max_features=5000)
    X = vec.fit_transform(texts)
    sim = cosine_similarity(X)
    dist = 1 - sim

    # ---- MDSで2次元配置 ----
    mds = MDS(
        n_components=2,
        dissimilarity="precomputed",
        random_state=42
    )
    coords = mds.fit_transform(dist)

    # ---- ノード ----
    nodes = []
    for i, b in enumerate(books):
        nodes.append({
            "id": b.book_id,
            "label": b.title,
            "author": b.author,
            "cover": b.cover,
            "x": float(coords[i][0]),
            "y": float(coords[i][1]),
        })

    # ---- エッジ（類似度しきい値）----
    edges = []
    THRESHOLD = 0.35
    for i in range(N):
        for j in range(i + 1, N):
            if sim[i][j] >= THRESHOLD:
                edges.append({
                    "source": books[i].book_id,
                    "target": books[j].book_id,
                    "weight": float(sim[i][j]),
                    "type": "similarity",
                })

    return {
        "nodes": nodes,
        "edges": edges,
    }