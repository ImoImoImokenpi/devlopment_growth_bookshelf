# routers/book_data.py
import requests
from typing import Dict, Any, Optional, List

GOOGLE_BOOKS_API = "https://www.googleapis.com/books/v1/volumes"

def fetch_cover_by_isbn(isbn: str) -> Optional[str]:
    params = {
        "q": f"isbn:{isbn}",
        "maxResults": 1,
    }

    try:
        res = requests.get(GOOGLE_BOOKS_API, params=params, timeout=5)
        res.raise_for_status()
        data = res.json()

        items = data.get("items", [])
        if not items:
            return None

        return (
            items[0]
            .get("volumeInfo", {})
            .get("imageLinks", {})
            .get("thumbnail")
        )

    except requests.RequestException:
        return None

NDL_SEARCH_API = "https://iss.ndl.go.jp/api/opensearch"

def fetch_book_metadata(
    isbn: Optional[str] = None,
    title: Optional[str] = None,
    author: Optional[str] = None,
) -> Optional[Dict[str, Any]]:

    params = {
        "cnt": 1,
        "format": "json"
    }

    if isbn:
        params["isbn"] = isbn
    if title:
        params["title"] = title
    if author:
        params["creator"] = author

    res = requests.get(NDL_SEARCH_API, params=params, timeout=5)
    res.raise_for_status()
    data = res.json()

    items: List[Dict[str, Any]] = data.get("items", [])
    if not items:
        return None

    item = items[0]

    ndc = item.get("ndc")
    isbn_value = item.get("isbn")

    # Google Books から表紙を補完
    cover = fetch_cover_by_isbn(isbn_value) if isbn_value else None

    return {
        # Book
        "isbn": isbn_value,
        "title": item.get("title"),
        "authors": item.get("creator", []),
        "publisher": item.get("publisher"),
        "published_year": item.get("issued"),
        "language": item.get("language"),
        "description": item.get("description"),

        # Classification
        "ndc": {
            "ndc_full": ndc,
            "ndc_level1": ndc[:1] if ndc else None,
            "ndc_level2": ndc[:2] if ndc else None,
            "ndc_level3": ndc[:3] if ndc else None,
        } if ndc else None,

        # Subjects (NDLSH)
        "subjects": item.get("subject", []),

        # UI (supplement)
        "cover": cover,
    }