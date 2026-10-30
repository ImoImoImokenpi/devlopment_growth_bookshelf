import re
import json
from pathlib import Path
from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session
from lxml import etree

from database import get_db
from models import MyHand, RegisteredBook, GenreTag
from participant import resolve_participant_id
from schemas import HeightUpdateRequest, ColorUpdateRequest, GenreTagRequest
from utils.llm_provider import get_llm_client
from graph.main_kg.neo4j_crud import update_book_attributes
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

# NDC(日本十進分類法)第1次区分 → ジャンルタグの自動シード用ラベル。
# 書誌データから機械的に決まる「粗いジャンル」で、ユーザーの手動タグと併用する。
NDC_L1_GENRE_LABELS = {
    "0": "総記", "1": "哲学", "2": "歴史", "3": "社会科学", "4": "自然科学",
    "5": "技術・工学", "6": "産業", "7": "芸術・美術", "8": "言語", "9": "文学",
}


def _seed_genre_tag_from_ndc(db: Session, isbn: str, ndc_full: str | None, participant_id: str) -> None:
    """登録時に、NDC分類から粗いジャンルタグを1件だけ自動生成する。
    NDCが無い/未知の区分なら何もしない（ユーザーの手動タグ付けに任せる）。"""
    if not ndc_full:
        return
    label = NDC_L1_GENRE_LABELS.get(ndc_full[0])
    if not label:
        return
    exists = (
        db.query(GenreTag)
        .filter(
            GenreTag.participant_id == participant_id,
            GenreTag.isbn == isbn,
            GenreTag.tag == label,
        )
        .first()
    )
    if exists:
        return
    db.add(GenreTag(participant_id=participant_id, isbn=isbn, tag=label, origin="ndc_auto"))


def backfill_genre_tags_from_ndc(db: Session) -> int:
    """このフェーズ1の仕組みを入れる前に登録・配置済みだった本には
    NDC由来のジャンルタグが無い。起動時に1回、現在棚に並んでいる
    (participant_id, isbn) の組み合わせぶんだけ穴埋めする（冪等）。
    フェーズ2(c)の興味分野質問が「現在棚にある本のジャンル」を
    候補にするため、これが無いと候補が空になってしまう参加者が出る。"""
    from models import ShelfLayout  # 循環import回避のため関数内import

    pairs = db.query(ShelfLayout.participant_id, ShelfLayout.isbn).distinct().all()
    ndc_by_isbn = {b.isbn: b.ndc for b in db.query(RegisteredBook).all()}
    existing = {
        (t.participant_id, t.isbn, t.tag)
        for t in db.query(GenreTag.participant_id, GenreTag.isbn, GenreTag.tag).all()
    }

    added = 0
    for participant_id, isbn in pairs:
        ndc = ndc_by_isbn.get(isbn)
        if not ndc:
            continue
        label = NDC_L1_GENRE_LABELS.get(ndc[0])
        if not label or (participant_id, isbn, label) in existing:
            continue
        db.add(GenreTag(participant_id=participant_id, isbn=isbn, tag=label, origin="ndc_auto"))
        existing.add((participant_id, isbn, label))
        added += 1

    if added:
        db.commit()
    return added


NDL_SRU_URL     = "https://ndlsearch.ndl.go.jp/api/sru"
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


# ============================================================
# 書籍登録サービス
# ============================================================

class BookRegistrationService:

    async def fetch_ndl_by_isbn(self, isbn: str) -> dict | None:
        """search.py と同じ SRU API + パース方法で書誌情報を取得"""
        clean = re.sub(r"[^0-9X]", "", isbn.upper())

        params = {
            "operation":      "searchRetrieve",
            "query":          f'isbn="{clean}"',
            "maximumRecords": 1,
            "recordSchema":   "dcndl",
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

        ndc              = _extract_ndc_from_bib(bib, BIB_NS)
        pages, height_mm = _extract_extent(extent)

        isbn13 = clean if len(clean) == 13 else _isbn10_to_13(clean)
        cover  = f"https://ndlsearch.ndl.go.jp/thumbnail/{isbn13}.jpg"

        openbd      = await fetch_openbd_descriptions([isbn13])
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

    @staticmethod
    def extract_dominant_color(image_data: bytes) -> str | None:
        """colorthief のメジアンカット法で代表色を抽出して 'R,G,B' 形式で返す。"""
        try:
            import io
            from colorthief import ColorThief

            cf       = ColorThief(io.BytesIO(image_data))
            r, g, b  = cf.get_color(quality=1)
            return f"{r},{g},{b}"
        except Exception:
            return None

    @staticmethod
    async def ocr_extract_text(image_data: bytes) -> str:
        """Tesseract OCR でテキスト抽出。0°/90°/270° を試して最長テキストを返す。"""
        try:
            import pytesseract
            from PIL import Image
            import io

            img  = Image.open(io.BytesIO(image_data))
            best = ""
            for angle in [0, 90, 270]:
                rotated = img.rotate(angle, expand=True) if angle else img
                text    = pytesseract.image_to_string(rotated, lang="jpn+eng", config="--psm 6")
                if len(text.strip()) > len(best.strip()):
                    best = text
            return best.strip()
        except ImportError:
            return ""
        except Exception:
            return ""

    async def ndl_search_by_keyword(self, keyword: str) -> dict | None:
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

            return await self.fetch_ndl_by_isbn(m.group())

        except Exception:
            return None


# ============================================================
# サービスインスタンス
# ============================================================

_registration_service = BookRegistrationService()
_llm                  = get_llm_client()


# ============================================================
# ルートハンドラ
# ============================================================

# ── 表紙画像をプロキシ ──────────────────────────────
@router.get("/cover/{isbn}")
async def proxy_cover(isbn: str, db: Session = Depends(get_db)):
    client = get_http_client()

    book       = db.query(RegisteredBook).filter(RegisteredBook.isbn == isbn).first()
    candidates = []
    if book and book.cover:
        candidates.append(book.cover)
    candidates.append(f"https://ndlsearch.ndl.go.jp/thumbnail/{isbn}.jpg")

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Referer":    "https://ndlsearch.ndl.go.jp/",
        "Accept":     "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
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
            "spine_color":    b.spine_color,
            "cover":          b.cover,
            "description":    b.description,
            "registered_at":  b.registered_at.isoformat() if b.registered_at else None,
        }
        for b in books
    ]


# ── 2ステップISBN抽出：OCR → NDL、失敗時は LLM（画像から読み取り） ────
@router.post("/extract-isbn")
async def extract_isbn(file: UploadFile = File(...)):
    image_data = await file.read()
    mime_type  = file.content_type or "image/jpeg"

    # ── Step 1: Tesseract OCR → NDL キーワード検索 ──────
    ocr_text = await _registration_service.ocr_extract_text(image_data)
    if ocr_text:
        # OCR テキストに ISBN パターンが含まれる場合は直接使う
        isbn_match = re.search(r"97[89][\-\d]{10,}", ocr_text)
        if isbn_match:
            isbn = re.sub(r"[^0-9X]", "", isbn_match.group())
            if len(isbn) == 13:
                book = await _registration_service.fetch_ndl_by_isbn(isbn)
                return {"isbn": isbn, "book": book, "method": "ocr_isbn"}

        # 先頭3行をキーワードとして NDL 検索
        lines   = [l.strip() for l in ocr_text.splitlines() if len(l.strip()) >= 2]
        keyword = " ".join(lines[:3])[:50]
        if len(keyword) >= 3:
            book = await _registration_service.ndl_search_by_keyword(keyword)
            if book:
                return {"isbn": book["isbn"], "book": book, "method": "ocr_ndl"}

    # ── Step 2: AI Vision ──────────────────────────────────
    prompt = (
        "この本の背表紙の画像からISBNコードを抽出してください。"
        "ISBNコードのみを返してください（数字とハイフンのみ）。"
        "見つからない場合は NOT_FOUND とだけ返してください。"
    )
    try:
        isbn_raw = _llm.generate_from_image(image_data, mime_type, prompt)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"AI API エラー: {e}")

    if "NOT_FOUND" in isbn_raw or not isbn_raw:
        raise HTTPException(status_code=422, detail="ISBNが画像から読み取れませんでした")
    isbn = re.sub(r"[^0-9X]", "", isbn_raw.upper())
    return {"isbn": isbn, "book": None, "method": "ai"}


# ── ISBNでNDL SRUを叩いて書誌情報を返す ─────────────
@router.get("/fetch/{isbn}")
async def fetch_by_isbn(isbn: str):
    book = await _registration_service.fetch_ndl_by_isbn(isbn)
    if book is None:
        raise HTTPException(status_code=404, detail=f"ISBN {isbn} の書誌情報が見つかりませんでした")
    return book


# ── 背表紙画像 + 書誌情報を紐づけて保存 ─────────────
@router.post("/save")
async def save_book(
    book_data: str = Form(...),
    image: UploadFile | None = File(None),
    db: Session = Depends(get_db),
    participant_id: str = Depends(resolve_participant_id),
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
    spine_color = None
    if image and image.filename:
        image_data = await image.read()
        ext        = image.filename.rsplit(".", 1)[-1].lower() if "." in image.filename else "jpg"
        SPINE_IMAGE_DIR.mkdir(parents=True, exist_ok=True)
        (SPINE_IMAGE_DIR / f"{isbn}.{ext}").write_bytes(image_data)
        spine_path  = f"/spine_image/{isbn}.{ext}"
        spine_color = _registration_service.extract_dominant_color(image_data)

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
        spine_color=spine_color,
        cover=ndl_cover,
        description=data.get("description"),
    )
    db.add(book)
    _seed_genre_tag_from_ndc(db, isbn, data.get("ndc_full"), participant_id)
    db.commit()
    return {"message": "saved", "isbn": isbn, "spine_image": spine_path, "spine_color": spine_color, "cover": ndl_cover}


# ============================================================
# フェーズ1: 属性タグ基盤（高さ・色の手動補正、ジャンルタグ）
# ============================================================

# ── 高さの手動補正 ────────────────────────────────
@router.patch("/{isbn}/height")
def update_height(isbn: str, body: HeightUpdateRequest, db: Session = Depends(get_db)):
    book = db.query(RegisteredBook).filter(RegisteredBook.isbn == isbn).first()
    if not book:
        raise HTTPException(status_code=404, detail="本が見つかりません")
    book.height_mm = body.height_mm
    book.height_source = "manual"
    db.commit()
    try:
        update_book_attributes(isbn, {"height_mm": body.height_mm})
    except Exception:
        pass  # Neo4jが落ちていてもSQLite側の補正は成立させる
    return {"isbn": isbn, "height_mm": book.height_mm, "height_source": book.height_source}


# ── ジャンルタグ ──────────────────────────────────
@router.get("/{isbn}/genre-tags")
def list_genre_tags(
    isbn: str,
    db: Session = Depends(get_db),
    participant_id: str = Depends(resolve_participant_id),
):
    tags = (
        db.query(GenreTag)
        .filter(GenreTag.participant_id == participant_id, GenreTag.isbn == isbn)
        .order_by(GenreTag.created_at)
        .all()
    )
    return [{"tag": t.tag, "origin": t.origin} for t in tags]


@router.post("/{isbn}/genre-tags")
def add_genre_tag(
    isbn: str,
    body: GenreTagRequest,
    db: Session = Depends(get_db),
    participant_id: str = Depends(resolve_participant_id),
):
    tag = body.tag.strip()
    if not tag:
        raise HTTPException(status_code=422, detail="タグを入力してください")
    if not db.query(RegisteredBook).filter(RegisteredBook.isbn == isbn).first():
        raise HTTPException(status_code=404, detail="本が見つかりません")

    existing = (
        db.query(GenreTag)
        .filter(GenreTag.participant_id == participant_id, GenreTag.isbn == isbn, GenreTag.tag == tag)
        .first()
    )
    if not existing:
        db.add(GenreTag(participant_id=participant_id, isbn=isbn, tag=tag, origin="manual"))
        db.commit()
    return list_genre_tags(isbn, db, participant_id)


@router.delete("/{isbn}/genre-tags/{tag}")
def delete_genre_tag(
    isbn: str,
    tag: str,
    db: Session = Depends(get_db),
    participant_id: str = Depends(resolve_participant_id),
):
    row = (
        db.query(GenreTag)
        .filter(GenreTag.participant_id == participant_id, GenreTag.isbn == isbn, GenreTag.tag == tag)
        .first()
    )
    if row:
        db.delete(row)
        db.commit()
    return list_genre_tags(isbn, db, participant_id)


# ── 1冊分の属性詳細（本詳細パネルの編集UI用）。
#    パスパラメータが1セグメントの他ルートと衝突しないよう、必ずファイル末尾に置く。──
@router.get("/{isbn}")
def get_book_detail(
    isbn: str,
    db: Session = Depends(get_db),
    participant_id: str = Depends(resolve_participant_id),
):
    book = db.query(RegisteredBook).filter(RegisteredBook.isbn == isbn).first()
    if not book:
        raise HTTPException(status_code=404, detail="本が見つかりません")
    return {
        "isbn":               book.isbn,
        "title":              book.title,
        "authors":            book.authors.split(",") if book.authors else [],
        "height_mm":          book.height_mm,
        "height_source":      book.height_source,
        "spine_color":        book.spine_color,
        "spine_color_source": book.spine_color_source,
        "ndc":                book.ndc,
        "genre_tags":         list_genre_tags(isbn, db, participant_id),
        # 本の詳細パネル用の書誌情報
        "publisher":          book.publisher,
        "published_year":     book.published_year,
        "pages":              book.pages,
        "cover":              book.cover,
        "description":        book.description,
    }
