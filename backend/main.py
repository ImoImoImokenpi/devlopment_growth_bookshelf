from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import requests  # ← 必須！
from database import Base, engine
import routers.myhand as myhand_router
import routers.knowledge_graph as knowledge_graph_router
import routers.bookshelf as bookshelf_router

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
app.include_router(knowledge_graph_router.router)
app.include_router(bookshelf_router.router)

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

