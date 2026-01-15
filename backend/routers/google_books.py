# routers/google_books.py
import requests
from typing import Dict, Any

GOOGLE_BOOKS_API = "https://www.googleapis.com/books/v1/volumes"

def fetch_book_metadata(book_id: str) -> Dict[str, Any]:
    res = requests.get(f"{GOOGLE_BOOKS_API}/{book_id}")
    res.raise_for_status()
    
    data = res.json().get("volumeInfo", {})
    
    return {
        # 基本データ
        "book_id": book_id,
        "title": data.get("title"),
        "subtitle": data.get("subtitle"),
        "authors": data.get("authors", []),
        "publisher": data.get("publisher"),
        "publishedDate": data.get("publishedDate"),
        "description": data.get("description"),
        "industryIdentifiers": data.get("industryIdentifiers", []),
        "printType": data.get("printType"),
        
        # 分類
        "categories": data.get("categories", []),
        "mainCategory": data.get("mainCategory"),

        # 表紙画像
        "cover": data.get("imageLinks", {}).get("thumbnail"),

        # 言語
        "language": data.get("language"),
    }
