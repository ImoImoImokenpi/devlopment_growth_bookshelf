# routers/google_books.py
import requests

GOOGLE_BOOKS_API = "https://www.googleapis.com/books/v1/volumes"

def fetch_book_metadata(book_id: str):
    res = requests.get(f"{GOOGLE_BOOKS_API}/{book_id}")
    res.raise_for_status()
    data = res.json()["volumeInfo"]
    
    return {
        "book_id": book_id,
        "title": data.get("title"),
        "authors": data.get("authors", []),
        "isbn": next(
            (
                i["identifier"]
                for i in data.get("industryIdentifiers", [])
                if i["type"] == "ISBN_13"
            ),
            None,
        ),
        "published_date": data.get("publishedDate"),
        "description": data.get("description"),

        # 🔽 追加・整理ポイント
        "cover": data.get("imageLinks", {}).get("thumbnail"),
        "concepts": data.get("categories", []),
    }
