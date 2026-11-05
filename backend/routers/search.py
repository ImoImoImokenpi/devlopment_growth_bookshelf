import os
import re
import time
import asyncio
import traceback
import httpx
from contextlib import asynccontextmanager
from dotenv import load_dotenv
from fastapi import APIRouter, Query, HTTPException, Request, FastAPI
from lxml import etree
from typing import List, Optional
import math

import logging
import logging.handlers
import sys
from pathlib import Path

load_dotenv(Path(__file__).parent.parent / ".env")
GOOGLE_BOOKS_API_KEY = os.environ.get("GOOGLE_BOOKS_API_KEY")

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

class HttpClientManager:

    TIMEOUT = httpx.Timeout(connect=3.0, read=5.0, write=5.0, pool=5.0)
    LIMITS  = httpx.Limits(max_connections=50, max_keepalive_connections=20)

    _client: Optional[httpx.AsyncClient] = None

    @classmethod
    def get(cls) -> httpx.AsyncClient:
        """lifespan未登録時はオンデマンドで生成（フォールバック）"""
        if cls._client is None:
            logger.warning(
                "[HTTP] 共有クライアント未初期化 → オンデマンド生成（lifespan を main.py に登録してください）"
            )
            cls._client = httpx.AsyncClient(timeout=cls.TIMEOUT, limits=cls.LIMITS)
        return cls._client

    @classmethod
    async def initialize(cls):
        cls._client = httpx.AsyncClient(timeout=cls.TIMEOUT, limits=cls.LIMITS)

    @classmethod
    async def shutdown(cls):
        if cls._client:
            await cls._client.aclose()


# -----------------------------
# NDL 検索・書影取得サービス
# -----------------------------

class NDLSearchService:

    SRU_URL       = "https://ndlsearch.ndl.go.jp/api/sru"
    GOOGLE_BOOKS  = "https://www.googleapis.com/books/v1/volumes"
    OPENBD_API    = "https://api.openbd.jp/v1/get"
    NDL_THUMBNAIL = "https://ndlsearch.ndl.go.jp/thumbnail/{isbn}.jpg"
    # 国会図書館の書影はブラウザらしいヘッダーがないと返らないことがある
    COVER_HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Referer":    "https://ndlsearch.ndl.go.jp/",
        "Accept":     "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
    }

    RETRY_COUNT = 3

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

    _NDC9_PREFIX  = "http://id.ndl.go.jp/class/ndc9/"
    _RDF_RESOURCE = "{http://www.w3.org/1999/02/22-rdf-syntax-ns#}resource"

    # ── パースユーティリティ ───────────────────────────────────────

    @staticmethod
    def _extract_ndc_from_bib(bib, bib_ns: dict) -> Optional[str]:
        """dc:subject テキスト（旧形式）と dcterms:subject rdf:resource（新形式）の両方に対応"""
        for s in bib.xpath("dc:subject/text()", namespaces=bib_ns):
            if re.match(r"\d{3}", s):
                return s
        for el in bib.xpath("dcterms:subject", namespaces=bib_ns):
            resource = el.get(NDLSearchService._RDF_RESOURCE, "")
            if resource.startswith(NDLSearchService._NDC9_PREFIX):
                return resource[len(NDLSearchService._NDC9_PREFIX):]
        return None

    @staticmethod
    def _extract_extent(extent: List[str]):
        pages     = None
        height_mm = None

        for entry in extent:
            if pages is None:
                pm = re.search(r"([\d]+(?:\s*[,、]\s*[\d]+)*)\s*(?:p|ページ|P)\b", entry)
                if pm:
                    pages = sum(int(n) for n in re.findall(r"\d+", pm.group(1)))
            if height_mm is None:
                hm = re.search(r"(\d+)\s*cm", entry)
                if hm:
                    height_mm = int(hm.group(1)) * 10

        return pages, height_mm

    @staticmethod
    def _isbn10_to_13(isbn10: str) -> str:
        digits = "978" + isbn10[:9]
        total  = sum(int(d) * (1 if i % 2 == 0 else 3) for i, d in enumerate(digits))
        check  = (10 - (total % 10)) % 10
        return digits + str(check)

    # ── SRU 検索 ─────────────────────────────────────────────────

    async def search_ndl_sru(self, query: str, start: int, max_records: int, cql: str | None = None):
        """cql を渡すとその検索式をそのまま使う（既定は書名・著者名での検索）。"""
        params = {
            "operation":      "searchRetrieve",
            "query":          cql or f'title all "{query}" OR creator all "{query}"',
            "startRecord":    start,
            "maximumRecords": max_records,
            "recordSchema":   "dcndl",
        }

        t0 = time.perf_counter()
        logger.info("[NDL] リクエスト開始 query=%r start=%d max=%d", query, start, max_records)

        client   = HttpClientManager.get()
        response = None

        for attempt in range(self.RETRY_COUNT):
            try:
                response = await client.get(
                    self.SRU_URL,
                    params=params,
                    timeout=self.NDL_TIMEOUT,
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
                if attempt == self.RETRY_COUNT - 1:
                    raise HTTPException(status_code=504, detail="NDL API timeout")
                await asyncio.sleep(0.8 * (attempt + 1))

            except httpx.HTTPStatusError as e:
                logger.error(
                    "[NDL] HTTPエラー status=%d query=%r",
                    e.response.status_code,
                    query,
                )
                if attempt == self.RETRY_COUNT - 1:
                    raise HTTPException(status_code=502, detail=f"NDL API error")
                await asyncio.sleep(0.8 * (attempt + 1))

            except httpx.RequestError:
                logger.error("[NDL] 接続エラー query=%r\n%s", query)
                if attempt == self.RETRY_COUNT - 1:
                    raise HTTPException(status_code=502, detail="NDL connection failed")
                await asyncio.sleep(0.8)

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
        total_el      = root.xpath("//srw:numberOfRecords/text()", namespaces=srw_ns)
        total_records = int(total_el[0]) if total_el else 0
        record_nodes  = root.xpath("//srw:recordData", namespaces=srw_ns)

        bib_ns = {
            "rdf":    "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
            "dcterms":"http://purl.org/dc/terms/",
            "dc":     "http://purl.org/dc/elements/1.1/",
            "dcndl":  "http://ndl.go.jp/dcndl/terms/",
            "foaf":   "http://xmlns.com/foaf/0.1/",
        }

        books   = []
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

            isbn_raw        = isbn_text[0].strip()
            isbn_normalized = re.sub(r"[-\s]", "", isbn_raw).upper()

            m = re.search(r"\d{13}|\d{9}[\dX]", isbn_normalized)
            if not m:
                skipped += 1
                continue

            isbn_normalized = m.group()

            creators  = bib.xpath("dc:creator/text()",                       namespaces=bib_ns)
            publisher = bib.xpath("dcterms:publisher//foaf:name/text()",     namespaces=bib_ns)
            issued    = bib.xpath("dcterms:issued/text()",                   namespaces=bib_ns)
            extent    = bib.xpath("dcterms:extent/text()",                   namespaces=bib_ns)
            subjects  = bib.xpath("dc:subject/text()",                       namespaces=bib_ns)

            ndc            = self._extract_ndc_from_bib(bib, bib_ns)
            pages, height_mm = self._extract_extent(extent)
            genre          = self.GENRE_MAP.get(ndc[0], "その他") if ndc else None

            books.append({
                "isbn":           isbn_normalized,
                "isbn_raw":       isbn_raw,
                "title":          title[0] if title else None,
                "authors":        creators,
                "publisher":      publisher[0] if publisher else None,
                "published_year": issued[0] if issued else None,
                "ndc":            {"ndc_full": ndc} if ndc else None,
                "genre":          genre,
                "height_mm":      height_mm,
                "pages":          pages,
                "subjects":       subjects,
                "cover":          None,
                "description":    None,
            })

        return books, total_records, len(record_nodes)

    # ── 書影取得 ──────────────────────────────────────────────────

    async def download_cover(self, url: str) -> Optional[bytes]:
        """書影URLから画像を取ってくる。画像でなければ None。"""
        try:
            r = await HttpClientManager.get().get(
                url, timeout=8, follow_redirects=True, headers=self.COVER_HEADERS,
            )
            if r.status_code == 200 and "image" in r.headers.get("content-type", ""):
                return r.content
        except Exception:
            pass
        return None

    async def fetch_ndl_cover(self, isbn: str) -> Optional[str]:
        isbn13 = self._isbn10_to_13(isbn) if len(isbn) == 10 else isbn
        url    = self.NDL_THUMBNAIL.format(isbn=isbn13)
        # URLがあっても画像が無いことがあるので、実際に画像が返るか確かめる
        return url if await self.download_cover(url) else None

    @staticmethod
    def _google_books_params(isbn: str) -> dict:
        params = {"q": f"isbn:{isbn}"}
        if GOOGLE_BOOKS_API_KEY:
            params["key"] = GOOGLE_BOOKS_API_KEY
        return params

    async def fetch_google_cover(self, isbn: str) -> Optional[str]:
        try:
            r = await HttpClientManager.get().get(
                self.GOOGLE_BOOKS,
                params=self._google_books_params(isbn),
            )
            r.raise_for_status()

            items = r.json().get("items")
            if not items:
                return None

            # Google Books は一致しない本も返すことがあるので、ISBNが合う本だけ使う
            want = {isbn, self._isbn10_to_13(isbn) if len(isbn) == 10 else isbn}
            info = next((
                it.get("volumeInfo", {}) for it in items
                if want & {i.get("identifier") for i in it.get("volumeInfo", {}).get("industryIdentifiers") or []}
            ), None)
            if info is None:
                return None
            image_links = info.get("imageLinks", {})

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

    async def fetch_openbd_descriptions(self, isbns: list) -> dict:
        """OpenBD から説明文を一括取得。{isbn: description} を返す"""
        if not isbns:
            return {}
        try:
            r = await HttpClientManager.get().get(
                self.OPENBD_API,
                params={"isbn": ",".join(isbns)},
            )
            r.raise_for_status()
            results = {}
            for item in r.json():
                if not item:
                    continue
                isbn = item.get("summary", {}).get("isbn", "")
                for tc in item.get("onix", {}).get("CollateralDetail", {}).get("TextContent", []):
                    if tc.get("TextType") in ("02", "03"):
                        text = tc.get("Text", "").strip()
                        if text:
                            results[isbn] = text
                        break
            return results
        except Exception:
            return {}

    async def fetch_google_description(self, isbn: str) -> Optional[str]:
        try:
            r = await HttpClientManager.get().get(
                self.GOOGLE_BOOKS,
                params=self._google_books_params(isbn),
            )
            r.raise_for_status()
            items = r.json().get("items")
            if not items:
                return None
            return items[0].get("volumeInfo", {}).get("description") or None
        except Exception:
            return None

    async def fetch_cover(self, isbn: str) -> Optional[str]:
        """書影URLを決める唯一の入り口（登録・おすすめ・表紙の中継で共通）。

        国会図書館（日本の本のみ）→ Google Books の順に探し、画像が見つかった最初のURLを返す。
        """
        isbn = (isbn or "").replace("-", "")
        is_japanese = isbn.startswith("9784") or (len(isbn) == 10 and isbn.startswith("4"))
        if is_japanese:
            url = await self.fetch_ndl_cover(isbn)
            if url:
                return url
        url = await self.fetch_google_cover(isbn)
        if url:
            return url
        logger.debug("[Cover] 書影取得できず isbn=%s", isbn)
        return None


# ============================================================
# モジュールレベル互換（既存の呼び出し元を変更なしで動作させる）
# ============================================================

_ndl_service = NDLSearchService()

get_http_client           = HttpClientManager.get
_extract_ndc_from_bib     = NDLSearchService._extract_ndc_from_bib
_extract_extent           = NDLSearchService._extract_extent
_isbn10_to_13             = NDLSearchService._isbn10_to_13
NDL_TIMEOUT               = NDLSearchService.NDL_TIMEOUT
fetch_openbd_descriptions = _ndl_service.fetch_openbd_descriptions
fetch_google_description  = _ndl_service.fetch_google_description
search_ndl_sru            = _ndl_service.search_ndl_sru
fetch_cover               = _ndl_service.fetch_cover
download_cover            = _ndl_service.download_cover
GOOGLE_BOOKS_URL          = NDLSearchService.GOOGLE_BOOKS


@asynccontextmanager
async def lifespan(app: FastAPI):
    await HttpClientManager.initialize()
    logger.info("[HTTP] 共有クライアント初期化完了")
    yield
    await HttpClientManager.shutdown()
    logger.info("[HTTP] 共有クライアント終了")
