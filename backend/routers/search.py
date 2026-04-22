import re
import time
import asyncio
import traceback
import httpx
from contextlib import asynccontextmanager
from fastapi import APIRouter, Query, HTTPException, Request, FastAPI
from lxml import etree
from typing import List, Optional
import math

import logging
import logging.handlers
import sys
from pathlib import Path

LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)

def setup_logger(name: str = "search_api") -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)

    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)

    app_handler = logging.handlers.TimedRotatingFileHandler(
        filename=LOG_DIR / "app.log",
        when="midnight",
        backupCount=30,
        encoding="utf-8",
    )
    app_handler.setLevel(logging.DEBUG)
    app_handler.setFormatter(formatter)

    error_handler = logging.handlers.TimedRotatingFileHandler(
        filename=LOG_DIR / "error.log",
        when="midnight",
        backupCount=30,
        encoding="utf-8",
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(formatter)

    logger.addHandler(console_handler)
    logger.addHandler(app_handler)
    logger.addHandler(error_handler)

    return logger


logger = setup_logger("search_api")

# -----------------------------
# 共有HTTPクライアント（コネクションプール）
# -----------------------------
_http_client: Optional[httpx.AsyncClient] = None


def get_http_client() -> httpx.AsyncClient:
    """lifespan未登録時はオンデマンドで生成（フォールバック）"""
    global _http_client

    if _http_client is None:
        logger.warning(
            "[HTTP] 共有クライアント未初期化 → オンデマンド生成（lifespan を main.py に登録してください）"
        )
        _http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(connect=3.0, read=5.0, write=5.0, pool=5.0),
            limits=httpx.Limits(max_connections=50, max_keepalive_connections=20),
        )

    return _http_client


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _http_client

    _http_client = httpx.AsyncClient(
        timeout=httpx.Timeout(connect=3.0, read=5.0, write=5.0, pool=5.0),
        limits=httpx.Limits(max_connections=50, max_keepalive_connections=20),
    )

    logger.info("[HTTP] 共有クライアント初期化完了")
    yield
    await _http_client.aclose()
    logger.info("[HTTP] 共有クライアント終了")


router = APIRouter(prefix="/search", tags=["search"])

NDL_SRU_URL = "https://ndlsearch.ndl.go.jp/api/sru"
GOOGLE_BOOKS_API = "https://www.googleapis.com/books/v1/volumes"
OPENBD_API = "https://api.openbd.jp/v1/get"
NDL_THUMBNAIL_URL = "https://ndlsearch.ndl.go.jp/thumbnail/{isbn}.jpg"

NDL_TIMEOUT = httpx.Timeout(
    connect=5.0,
    read=20.0,
    write=10.0,
    pool=5.0,
)

GENRE_MAP = {
    "0": "総記",
    "1": "哲学",
    "2": "歴史",
    "3": "社会科学",
    "4": "自然科学",
    "5": "技術",
    "6": "産業",
    "7": "芸術",
    "8": "言語",
    "9": "文学",
}


def _extract_ndc(subjects: List[str]) -> Optional[str]:
    for s in subjects:
        if re.match(r"\d{3}", s):
            return s
    return None


def _extract_extent(extent: List[str]):
    pages = None
    height_mm = None

    if extent:
        pm = re.search(r"(\d+)p", extent[0])
        hm = re.search(r"(\d+)cm", extent[0])

        if pm:
            pages = int(pm.group(1))
        if hm:
            height_mm = int(hm.group(1)) * 10

    return pages, height_mm


def _isbn10_to_13(isbn10: str) -> str:
    digits = "978" + isbn10[:9]
    total = sum(int(d) * (1 if i % 2 == 0 else 3) for i, d in enumerate(digits))
    check = (10 - (total % 10)) % 10
    return digits + str(check)


# -----------------------------
# SRU検索
# -----------------------------
RETRY_COUNT = 3
async def search_ndl_sru(query: str, start: int, max_records: int):
    params = {
        "operation": "searchRetrieve",
        "query": f'title all "{query}" OR creator all "{query}"',
        "startRecord": start,
        "maximumRecords": max_records,
        "recordSchema": "dcndl",
    }

    t0 = time.perf_counter()
    logger.info("[NDL] リクエスト開始 query=%r start=%d max=%d", query, start, max_records)

    client = get_http_client()

    response = None

    for attempt in range(RETRY_COUNT):
        try:
            response = await client.get(
                NDL_SRU_URL,
                params=params,
                timeout=NDL_TIMEOUT
            )
            response.raise_for_status()
            break

        except httpx.TimeoutException:
            logger.error(
                "[NDL] タイムアウト query=%r attempt=%d elapsed=%.2fs",
                query,
                attempt + 1,
                time.perf_counter() - t0,
            )

            if attempt == RETRY_COUNT - 1:
                raise HTTPException(
                    status_code=504,
                    detail="NDL API timeout"
                )

            await asyncio.sleep(0.8 * (attempt + 1))

        except httpx.HTTPStatusError as e:
            logger.error(
                "[NDL] HTTPエラー status=%d query=%r",
                e.response.status_code,
                query,
            )

            if attempt == RETRY_COUNT - 1:
                raise HTTPException(
                    status_code=502,
                    detail=f"NDL API error",
                )

            await asyncio.sleep(0.8 * (attempt + 1))

        except httpx.RequestError:
            logger.error("[NDL] 接続エラー query=%r\n%s", query)

            if attempt == RETRY_COUNT - 1:
                raise HTTPException(
                    status_code=502,
                    detail="NDL connection failed",
                )

            await asyncio.sleep(0.8)

    # -------------------------
    # ここから先は response 必須
    # -------------------------
    if response is None:
        raise HTTPException(status_code=502, detail="NDL no response")

    logger.info(
        "[NDL] レスポンス受信 status=%d elapsed=%.2fs",
        response.status_code,
        time.perf_counter() - t0,
    )

    try:
        root = etree.fromstring(response.content)
    except etree.XMLSyntaxError:
        raise HTTPException(502, "NDL XML parse error")

    srw_ns = {"srw": "http://www.loc.gov/zing/srw/"}
    total_el = root.xpath("//srw:numberOfRecords/text()", namespaces=srw_ns)
    total_records = int(total_el[0]) if total_el else 0
    record_nodes = root.xpath("//srw:recordData", namespaces=srw_ns)

    bib_ns = {
        "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
        "dcterms": "http://purl.org/dc/terms/",
        "dc": "http://purl.org/dc/elements/1.1/",
        "dcndl": "http://ndl.go.jp/dcndl/terms/",
        "foaf": "http://xmlns.com/foaf/0.1/",
    }

    books = []
    skipped = 0

    for record_node in record_nodes:
        raw_text = (record_node.text or "").strip()
        if not raw_text:
            skipped += 1
            continue

        try:
            rdf = etree.fromstring(raw_text.encode("utf-8"))
        except etree.XMLSyntaxError:
            skipped += 1
            continue

        bib_list = rdf.xpath(".//dcndl:BibResource", namespaces=bib_ns)
        if not bib_list:
            skipped += 1
            continue

        bib = bib_list[0]

        title = bib.xpath("dcterms:title/text()", namespaces=bib_ns)
        if not title:
            title = bib.xpath("dc:title//rdf:value/text()", namespaces=bib_ns)

        isbn_text = bib.xpath(
            "dcterms:identifier[@rdf:datatype='http://ndl.go.jp/dcndl/terms/ISBN']/text()",
            namespaces=bib_ns,
        )

        if not isbn_text:
            skipped += 1
            continue

        isbn_raw = isbn_text[0].strip()
        isbn_normalized = re.sub(r"[-\s]", "", isbn_raw).upper()

        m = re.search(r"\d{13}|\d{9}[\dX]", isbn_normalized)
        if not m:
            skipped += 1
            continue

        isbn_normalized = m.group()

        creators = bib.xpath("dc:creator/text()", namespaces=bib_ns)
        publisher = bib.xpath("dcterms:publisher//foaf:name/text()", namespaces=bib_ns)
        issued = bib.xpath("dcterms:issued/text()", namespaces=bib_ns)
        subjects_nodes = bib.xpath("dc:subject/text()", namespaces=bib_ns)
        extent = bib.xpath("dcterms:extent/text()", namespaces=bib_ns)

        ndc = _extract_ndc(subjects_nodes)
        pages, height_mm = _extract_extent(extent)
        genre = GENRE_MAP.get(ndc[0], "その他") if ndc else None

        books.append({
            "isbn": isbn_normalized,
            "isbn_raw": isbn_raw,
            "title": title[0] if title else None,
            "authors": creators,
            "publisher": publisher[0] if publisher else None,
            "published_year": issued[0] if issued else None,
            "ndc": {"ndc_full": ndc} if ndc else None,
            "genre": genre,
            "height_mm": height_mm,
            "pages": pages,
            "subjects": subjects_nodes,
            "cover": None,
        })

    return books, total_records, len(record_nodes)
# -----------------------------
# 書影取得
# -----------------------------
async def fetch_ndl_cover(isbn: str) -> Optional[str]:
    isbn13 = _isbn10_to_13(isbn) if len(isbn) == 10 else isbn
    url = NDL_THUMBNAIL_URL.format(isbn=isbn13)

    try:
        r = await get_http_client().get(url)
        if r.status_code == 200:
            return url
        return None
    except Exception:
        return None


async def fetch_google_cover(isbn: str) -> Optional[str]:
    try:
        r = await get_http_client().get(
            GOOGLE_BOOKS_API,
            params={"q": f"isbn:{isbn}"},
        )
        r.raise_for_status()

        items = r.json().get("items")
        if not items:
            return None

        image_links = items[0].get("volumeInfo", {}).get("imageLinks", {})

        cover = (
            image_links.get("large")
            or image_links.get("medium")
            or image_links.get("small")
            or image_links.get("thumbnail")
            or image_links.get("smallThumbnail")
        )

        if cover:
            cover = cover.replace("http://", "https://")
            if "zoom=" not in cover:
                cover += "&zoom=0"

        return cover or None

    except Exception:
        return None


async def fetch_cover(isbn: str) -> Optional[str]:
    is_japanese = isbn.startswith("9784") or (
        len(isbn) == 10 and isbn.startswith("4")
    )

    if not is_japanese:
        logger.debug(
            "[Cover] 非日本語ISBNのため書影取得スキップ isbn=%s",
            isbn,
        )
        return None

    results = await asyncio.gather(
        fetch_ndl_cover(isbn),
        fetch_google_cover(isbn),
        return_exceptions=True,
    )

    for r in results:
        if isinstance(r, str) and r:
            return r

    logger.debug("[Cover] 書影取得できず isbn=%s", isbn)
    return None


# -----------------------------
# メインAPI
# -----------------------------
@router.get("/")
async def search_books(
    request: Request,
    q: str = Query(..., min_length=1, description="検索キーワード"),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=50),
):
    t_start = time.perf_counter()
    client_ip = request.client.host if request.client else "unknown"

    logger.info(
        "[API] リクエスト受信 ip=%s q=%r page=%d per_page=%d",
        client_ip,
        q,
        page,
        per_page,
    )

    fetch_size = min(per_page * 3, 200)
    skip_target = (page - 1) * per_page

    valid_seen = 0
    ndl_start = 1
    fetch_round = 0
    total_records = 0
    books_with_cover: list = []

    MAX_FETCH_ROUNDS = 5

    while (
        len(books_with_cover) < per_page
        and fetch_round < MAX_FETCH_ROUNDS
):
        fetch_round += 1

        logger.info(
            "[API] フェッチ round=%d ndl_start=%d fetch_size=%d 書影あり=%d/%d",
            fetch_round,
            ndl_start,
            fetch_size,
            len(books_with_cover),
            per_page,
        )

        batch, total_records, raw_count = await search_ndl_sru(
            q,
            ndl_start,
            fetch_size,
        )

        ndl_start += raw_count

        candidates = []

        for book in batch:
            valid_seen += 1
            if valid_seen <= skip_target:
                continue
            candidates.append(book)

        if not candidates:
            if raw_count == 0 or ndl_start > total_records:
                logger.info("[API] NDL レコード枯渇")
                break
            continue

        t_cover = time.perf_counter()
        covers = await asyncio.gather(
            *[fetch_cover(b["isbn"]) for b in candidates]
        )

        cover_hit = sum(1 for c in covers if c)

        logger.info(
            "[API] 書影取得 round=%d hit=%d/%d elapsed=%.2fs",
            fetch_round,
            cover_hit,
            len(candidates),
            time.perf_counter() - t_cover,
        )

        with_cover = []
        without_cover = []

        for book, cover in zip(candidates, covers):
            book["cover"] = cover
            if cover:
                with_cover.append(book)
            else:
                without_cover.append(book)

        books_with_cover.extend(with_cover)

        # 足りなければ補充
        if len(books_with_cover) < per_page:
            books_with_cover.extend(
                without_cover[:per_page - len(books_with_cover)]
            )

        if raw_count == 0 or ndl_start > total_records:
            logger.info("[API] NDL レコード枯渇")
            break

    total_pages = math.ceil(total_records / per_page) if total_records else 1
    total_elapsed = time.perf_counter() - t_start

    logger.info(
        "[API] レスポンス返却 q=%r books=%d total=%d elapsed=%.2fs",
        q,
        len(books_with_cover),
        total_records,
        total_elapsed,
    )

    return {
        "books": books_with_cover,
        "total": total_records,
        "page": page,
        "per_page": per_page,
        "total_pages": total_pages,
    }