from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import httpx
import xmltodict
import math
import asyncio
import json
import traceback

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

NDL_OPENSEARCH = "https://ndlsearch.ndl.go.jp/api/opensearch"

# ルータ登録
app.include_router(myhand_router.router)
app.include_router(knowledge_graph_router.router)
app.include_router(bookshelf_router.router)

# --- ユーティリティ関数 

def safe_field(field):
    """NDLのXMLデータを安全に文字列として取得"""
    if field is None: return ""
    if isinstance(field, list):
        fields = [safe_field(f) for f in field if f]
        return fields[0] if fields else ""
    if isinstance(field, dict): return field.get("#text", "")
    return str(field)

def extract_identifier(identifiers, target_type):
    """ISBNまたはJPNOを抽出。ISBNは長いもの(ISBN13)を優先"""
    if not identifiers: return None
    ids = identifiers if isinstance(identifiers, list) else [identifiers]
    found_values = []
    for i in ids:
        if isinstance(i, dict):
            id_type = i.get("@xsi:type", "")
            if id_type and target_type.upper() in id_type.upper():
                val = i.get("#text", "")
                if val: found_values.append(val.replace("-", "").strip())
    
    if not found_values: return None
    if target_type.upper() == "ISBN":
        found_values.sort(key=len, reverse=True)
    return found_values[0]

def ensure_list(value):
    if value is None: return []
    return value if isinstance(value, list) else [value]

# --- Google Books API 連携 ---

async def get_google_cover(isbn: str, client: httpx.AsyncClient):
    """Google Books APIからISBNをキーに書影URLを取得"""
    if not isbn:
        return "/noimage.png"
    try:
        # 検索クエリをisbnに絞ることで精度を高める
        url = f"https://www.googleapis.com/books/v1/volumes?q=isbn:{isbn}"
        res = await client.get(url, timeout=5.0)
        if res.status_code == 200:
            data = res.json()
            if "items" in data:
                volume_info = data["items"][0].get("volumeInfo", {})
                image_links = volume_info.get("imageLinks", {})
                # thumbnail優先。httpはhttpsに置換
                img_url = image_links.get("thumbnail") or image_links.get("smallThumbnail")
                if img_url:
                    return img_url.replace("http://", "https://")
    except Exception as e:
        print(f"[DEBUG] Google Books Error ({isbn}): {e}")
    return "/noimage.png"

# --- メインエンドポイント ---

@app.get("/search")
async def search_books(q: str = Query(...), page: int = 1, per_page: int = 20):
    FETCH_SIZE = 100 
    
    async def fetch_ndl_page(idx: int):
        async with httpx.AsyncClient(follow_redirects=True) as client:
            params = {"any": q, "cnt": FETCH_SIZE, "idx": idx}
            res = await client.get(NDL_OPENSEARCH, params=params, timeout=10.0)
            res.raise_for_status()
            return xmltodict.parse(res.text)

    def pre_process_items(raw_items):
        """NDLから基本データとISBNを抽出"""
        books = []
        for item in raw_items:
            ids_node = item.get("dc:identifier")
            isbn = extract_identifier(ids_node, "ISBN")
            
            # Google Booksで画像を出すためにISBNを必須とするが、
            # JPNOがあれば「画像なし」でもリストには含める運用
            if isbn:
                books.append({
                    "isbn": isbn,
                    "title": safe_field(item.get("dc:title")),
                    "authors": ensure_list(safe_field(item.get("dc:creator"))),
                    "publisher": safe_field(item.get("dc:publisher")),
                    "link": item.get("link"),
                    "cover": "/noimage.png" # 初期値
                })
        return books

    try:
        # 1. NDLからデータ取得
        data = await fetch_ndl_page(1)
        channel = data.get('rss', {}).get('channel', {})
        total_available = int(channel.get("openSearch:totalResults", 0))
        
        items = ensure_list(channel.get('item', []))
        collected_books = pre_process_items(items)

        # 件数が極端に少ない場合は次の100件もスキャン
        if len(collected_books) < per_page and total_available > FETCH_SIZE:
            extra_data = await fetch_ndl_page(101)
            extra_items = ensure_list(extra_data.get('rss', {}).get('channel', {}).get('item', []))
            collected_books.extend(pre_process_items(extra_items))

        # 2. 現在のページに必要な分だけ切り出す（API負荷軽減のため）
        start_idx = (page - 1) * per_page
        end_idx = start_idx + per_page
        target_page_books = collected_books[start_idx:end_idx]

        # 3. Google Books APIから画像を「並列」で取得
        if target_page_books:
            async with httpx.AsyncClient() as client:
                tasks = [get_google_cover(b["isbn"], client) for b in target_page_books]
                cover_urls = await asyncio.gather(*tasks)
                
                for i, url in enumerate(cover_urls):
                    target_page_books[i]["cover"] = url

        return {
            "books": target_page_books,
            "page": page,
            "total_items_found": len(collected_books),
            "total_pages": math.ceil(len(collected_books) / per_page)
        }

    except Exception as e:
        print(f"[ERROR] {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail="Search failed")

@app.get("/")
def root():
    return {"message": "Google Books Cover Mode Backend Running"}