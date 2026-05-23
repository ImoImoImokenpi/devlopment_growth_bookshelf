import re
import json
from pathlib import Path
from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session
from lxml import etree
from google import genai
from google.genai import types
from google.genai.errors import ClientError as GeminiClientError

from database import get_db
from models import MyHand, RegisteredBook
from routers.search import (
    get_http_client,
    _extract_ndc_from_bib,
    _extract_extent,
    _isbn10_to_13,
    NDL_TIMEOUT,
    fetch_openbd_descriptions,
    fetch_google_description,
)

router = APIRouter(prefix="/register", tags=["register"])

NDL_SRU_URL  = "https://ndlsearch.ndl.go.jp/api/sru"
GEMINI_API_KEY = "AIzaSyB8zNh8oity7aGZ_BrINetZRYTMOjxxcno"
SPINE_IMAGE_DIR = (
    Path(__file__).parent.parent.parent / "frontend" / "public" / "spine_image"
)

BIB_NS = {
    "rdf":    "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
    "dcterms":"http://purl.org/dc/terms/",
    "dc":     "http://purl.org/dc/elements/1.1/",
    "dcndl":  "http://ndl.go.jp/dcndl/terms/",
    "foaf":   "http://xmlns.com/foaf/0.1/",
}
SRW_NS = {"srw": "http://www.loc.gov/zing/srw/"}


def _gemini_client():
    return genai.Client(
        api_key=GEMINI_API_KEY,
        http_options=types.HttpOptions(api_version="v1"),
    )


async def _fetch_ndl_by_isbn(isbn: str) -> dict | None:
    """search.py と同じ SRU API + パース方法で書誌情報を取得"""
    clean = re.sub(r"[^0-9X]", "", isbn.upper())

    params = {
        "operation":    "searchRetrieve",
        "query":        f'isbn="{clean}"',
        "maximumRecords": 1,
        "recordSchema": "dcndl",
    }

    client   = get_http_client()
    response = await client.get(NDL_SRU_URL, params=params, timeout=NDL_TIMEOUT)
    response.raise_for_status()

    root         = etree.fromstring(response.content)
    record_nodes = root.xpath("//srw:recordData", namespaces=SRW_NS)
    if not record_nodes:
        return None

    raw_text = (record_nodes[0].text or "").strip()
    if not raw_text:
        return None

    rdf      = etree.fromstring(raw_text.encode("utf-8"))
    bib_list = rdf.xpath(".//dcndl:BibResource", namespaces=BIB_NS)
    if not bib_list:
        return None

    bib = bib_list[0]

    title = bib.xpath("dcterms:title/text()", namespaces=BIB_NS)
    if not title:
        title = bib.xpath("dc:title//rdf:value/text()", namespaces=BIB_NS)

    creators      = bib.xpath("dc:creator/text()",                       namespaces=BIB_NS)
    publisher     = bib.xpath("dcterms:publisher//foaf:name/text()",     namespaces=BIB_NS)
    issued        = bib.xpath("dcterms:issued/text()",                   namespaces=BIB_NS)
    subjects      = bib.xpath("dc:subject/text()",                       namespaces=BIB_NS)
    extent        = bib.xpath("dcterms:extent/text()",                   namespaces=BIB_NS)
    abstract      = bib.xpath("dcterms:abstract/text()",                 namespaces=BIB_NS)

    ndc             = _extract_ndc_from_bib(bib, BIB_NS)
    pages, height_mm = _extract_extent(extent)

    isbn13 = clean if len(clean) == 13 else _isbn10_to_13(clean)
    cover  = f"https://ndlsearch.ndl.go.jp/thumbnail/{isbn13}.jpg"

    description = abstract[0] if abstract else None
    if not description:
        openbd = await fetch_openbd_descriptions([isbn13])
        description = openbd.get(isbn13)
    if not description:
        description = await fetch_google_description(isbn13)

    return {
        "isbn":           clean,
        "title":          title[0] if title else None,
        "authors":        ",".join(creators),
        "publisher":      publisher[0] if publisher else None,
        "published_year": issued[0] if issued else None,
        "ndc_full":       ndc,
        "pages":          pages,
        "height_mm":      height_mm,
        "size_label":     None,
        "cover":          cover,
        "description":    description,
    }


# ── 表紙画像をプロキシ ──────────────────────────────
@router.get("/cover/{isbn}")
async def proxy_cover(isbn: str, db: Session = Depends(get_db)):
    client = get_http_client()

    book = db.query(RegisteredBook).filter(RegisteredBook.isbn == isbn).first()
    candidates = []
    if book and book.cover:
        candidates.append(book.cover)
    candidates.append(f"https://ndlsearch.ndl.go.jp/thumbnail/{isbn}.jpg")

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Referer": "https://ndlsearch.ndl.go.jp/",
        "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
    }
    for url in candidates:
        try:
            r = await client.get(url, timeout=8, follow_redirects=True, headers=headers)
            if r.status_code == 200 and "image" in r.headers.get("content-type", ""):
                return Response(content=r.content, media_type="image/jpeg")
        except Exception:
            continue

    raise HTTPException(status_code=404, detail="Cover not found")


# ── 登録済み一覧を返す ───────────────────────────────
@router.get("/list")
def list_registered(db: Session = Depends(get_db)):
    books = db.query(RegisteredBook).order_by(RegisteredBook.registered_at.desc()).all()
    return [
        {
            "isbn":           b.isbn,
            "title":          b.title,
            "authors":        b.authors.split(",") if b.authors else [],
            "publisher":      b.publisher,
            "published_year": b.published_year,
            "ndc":            b.ndc,
            "pages":          b.pages,
            "height_mm":      b.height_mm,
            "spine_image":    b.spine_image,
            "cover":          b.cover,
            "description":    b.description,
            "registered_at":  b.registered_at.isoformat() if b.registered_at else None,
        }
        for b in books
    ]


async def _ocr_extract_text(image_data: bytes) -> str:
    """Tesseract OCR でテキスト抽出。0°/90°/270° を試して最長テキストを返す。"""
    try:
        import pytesseract
        from PIL import Image
        import io

        img = Image.open(io.BytesIO(image_data))
        best = ""
        for angle in [0, 90, 270]:
            rotated = img.rotate(angle, expand=True) if angle else img
            text = pytesseract.image_to_string(rotated, lang="jpn+eng", config="--psm 6")
            if len(text.strip()) > len(best.strip()):
                best = text
        return best.strip()
    except ImportError:
        return ""
    except Exception:
        return ""


async def _ndl_search_by_keyword(keyword: str) -> dict | None:
    """キーワードでNDL SRUを検索し、1件のみヒットした場合に書誌情報を返す。"""
    params = {
        "operation":      "searchRetrieve",
        "query":          f'title all "{keyword}" OR creator all "{keyword}"',
        "maximumRecords": 2,
        "recordSchema":   "dcndl",
    }
    try:
        client   = get_http_client()
        response = await client.get(NDL_SRU_URL, params=params, timeout=NDL_TIMEOUT)
        response.raise_for_status()

        root     = etree.fromstring(response.content)
        total_el = root.xpath("//srw:numberOfRecords/text()", namespaces=SRW_NS)
        total    = int(total_el[0]) if total_el else 0
        if total != 1:
            return None

        record_nodes = root.xpath("//srw:recordData", namespaces=SRW_NS)
        if not record_nodes:
            return None

        raw_text = (record_nodes[0].text or "").strip()
        if not raw_text:
            return None

        rdf      = etree.fromstring(raw_text.encode("utf-8"))
        bib_list = rdf.xpath(".//dcndl:BibResource", namespaces=BIB_NS)
        if not bib_list:
            return None

        bib       = bib_list[0]
        isbn_text = bib.xpath(
            "dcterms:identifier[@rdf:datatype='http://ndl.go.jp/dcndl/terms/ISBN']/text()",
            namespaces=BIB_NS,
        )
        if not isbn_text:
            return None

        isbn_raw = isbn_text[0].strip()
        clean    = re.sub(r"[^0-9X]", "", isbn_raw.upper())
        m        = re.search(r"\d{13}|\d{9}[\dX]", clean)
        if not m:
            return None

        return await _fetch_ndl_by_isbn(m.group())

    except Exception:
        return None


# ── 2ステップISBN抽出：OCR → NDL、失敗時は Gemini ────
@router.post("/extract-isbn")
async def extract_isbn(file: UploadFile = File(...)):
    image_data = await file.read()
    mime_type  = file.content_type or "image/jpeg"

    # ── Step 1: Tesseract OCR → NDL キーワード検索 ──────
    ocr_text = await _ocr_extract_text(image_data)
    if ocr_text:
        # OCR テキストに ISBN パターンが含まれる場合は直接使う
        isbn_match = re.search(r"97[89][\-\d]{10,}", ocr_text)
        if isbn_match:
            isbn = re.sub(r"[^0-9X]", "", isbn_match.group())
            if len(isbn) == 13:
                book = await _fetch_ndl_by_isbn(isbn)
                return {"isbn": isbn, "book": book, "method": "ocr_isbn"}

        # 先頭3行をキーワードとして NDL 検索
        lines   = [l.strip() for l in ocr_text.splitlines() if len(l.strip()) >= 2]
        keyword = " ".join(lines[:3])[:50]
        if len(keyword) >= 3:
            book = await _ndl_search_by_keyword(keyword)
            if book:
                return {"isbn": book["isbn"], "book": book, "method": "ocr_ndl"}

    # ── Step 2: Gemini ────────────────────────────────────
    GEMINI_MODELS = ["gemini-2.0-flash", "gemini-1.5-flash", "gemini-2.0-flash-lite"]
    prompt = (
        "この本の背表紙の画像からISBNコードを抽出してください。"
        "ISBNコードのみを返してください（数字とハイフンのみ）。"
        "見つからない場合は NOT_FOUND とだけ返してください。"
    )
    client = _gemini_client()
    last_error = None
    for model in GEMINI_MODELS:
        try:
            response = client.models.generate_content(
                model=model,
                contents=[
                    types.Part.from_text(text=prompt),
                    types.Part.from_bytes(data=image_data, mime_type=mime_type),
                ],
            )
            isbn_raw = response.text.strip()
            if "NOT_FOUND" in isbn_raw or not isbn_raw:
                raise HTTPException(status_code=422, detail="ISBNが画像から読み取れませんでした")
            isbn = re.sub(r"[^0-9X]", "", isbn_raw.upper())
            return {"isbn": isbn, "book": None, "method": f"gemini/{model}"}
        except GeminiClientError as e:
            if e.status_code == 429:
                last_error = e
                continue  # 次のモデルを試す
            raise HTTPException(status_code=502, detail=f"Gemini API エラー: {e}")

    raise HTTPException(
        status_code=429,
        detail="Gemini API のクォータを超過しています。しばらく待ってから再試行してください。",
    )


# ── ISBNでNDL SRUを叩いて書誌情報を返す ─────────────
@router.get("/fetch/{isbn}")
async def fetch_by_isbn(isbn: str):
    book = await _fetch_ndl_by_isbn(isbn)
    if book is None:
        raise HTTPException(status_code=404, detail=f"ISBN {isbn} の書誌情報が見つかりませんでした")
    return book


# ── 背表紙画像 + 書誌情報を紐づけて保存 ─────────────
@router.post("/save")
async def save_book(
    book_data: str = Form(...),
    image: UploadFile | None = File(None),
    db: Session = Depends(get_db),
):
    data = json.loads(book_data)
    isbn = data.get("isbn")
    if not isbn:
        raise HTTPException(status_code=400, detail="ISBN is required")

    if db.query(RegisteredBook).filter(RegisteredBook.isbn == isbn).first():
        return {"message": "already_exists", "isbn": isbn}

    # 背表紙画像を spine_image/{isbn}.jpg として保存
    ndl_cover   = data.get("cover")        # NDL/Google Books の書影URL
    spine_path  = None
    if image and image.filename:
        ext = image.filename.rsplit(".", 1)[-1].lower() if "." in image.filename else "jpg"
        SPINE_IMAGE_DIR.mkdir(parents=True, exist_ok=True)
        (SPINE_IMAGE_DIR / f"{isbn}.{ext}").write_bytes(await image.read())
        spine_path = f"/spine_image/{isbn}.{ext}"

    book = RegisteredBook(
        isbn=isbn,
        title=data.get("title"),
        authors=data.get("authors") or "",
        publisher=data.get("publisher"),
        published_year=data.get("published_year"),
        ndc=data.get("ndc_full"),
        height_mm=data.get("height_mm") or 180,
        pages=data.get("pages") or 200,
        size_label=data.get("size_label"),
        spine_image=spine_path,
        cover=ndl_cover,
        description=data.get("description"),
    )
    db.add(book)
    db.commit()
    return {"message": "saved", "isbn": isbn, "spine_image": spine_path, "cover": ndl_cover}
