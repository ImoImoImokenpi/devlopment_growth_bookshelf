"""おすすめ API。知識グラフのノードを根拠に、本棚へ本を加える。

1冊を加える流れ（_recommend_one）:
  1. キーワードを集める: 根拠（意味づけ・内容テーマ・本棚の本）の言葉と、
     知識グラフでつながっているノード（本の内容テーマ・著者・ほかの意味づけ）
  2. 外部APIで検索する: Google Books と国立国会図書館（NDL）。持っている本は除く
  3. LLMが候補から最適な1冊を選び、理由と置き場所（どの本の左か右か）を決める
  4. 本棚（SQLite）と知識グラフ（Neo4j）に書き込む

きっかけは2つ。
  - /recommend/concept/{concept_id}: 対話の締めくくりで加わった意味づけから自動で1冊
  - /recommend/request/plan → /recommend/request/item: 対話の中で「本を入れて」と頼まれたとき。
    LLMが知識グラフを見て、1冊ごとの根拠とねらいを決めて（計画）、1冊ずつ加える

選ばれた本は「おすすめで加わった本」として印を付けて残す（graph/recommendation/store.py）。
"""
import asyncio
import logging
import re

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from graph.dialogue.store import get_shelf_books
from graph.main_kg.neo4j_crud import add_book_with_meaning, save_concept, update_shelf_layout_chain
from graph.recommendation import store
from models import RegisteredBook, ShelfLayout
from participant import resolve_participant_id
from routers.bookshelf import _get_or_create_design, _run_placement_analysis_sync
from routers.dialogue import _book_ids, _label, _llm, _neo4j_guard, _parse_json, _shelf_text
from routers.register import _registration_service, _seed_genre_tag_from_ndc
from routers.search import GOOGLE_BOOKS_API_KEY, GOOGLE_BOOKS_URL, fetch_cover, get_http_client, search_ndl_sru
from shelf_period import PRESENT
from utils.llm_modes import LLMDisabledError
from utils.shelf_geometry import INNER_X, SHELF_MODE, grid_x, spine_x
from utils.shelf_utils import ShelfService

router = APIRouter(prefix="/recommend", tags=["recommend"])
logger = logging.getLogger(__name__)

MAX_QUERIES = 6
MAX_QUERY_LEN = 25  # これより長い言葉（文のような意味づけなど）は検索に使わない
GOOGLE_PER_QUERY = 8
NDL_PER_QUERY = 5
MAX_CANDIDATES = 20
MAX_REQUEST_BOOKS = 5
SEARCH_TIMEOUT = httpx.Timeout(connect=5.0, read=12.0, write=5.0, pool=5.0)

# ============================================================
# 1. キーワードを集める
# ============================================================

AUTHOR_SUFFIX = re.compile(r"\s*[\[(（]?(著|訳|編|監修|作|文|絵|共著|編著)[\])）]?$")
MAX_AUTHOR_ONLY_CANDIDATES = 3  # 著者名だけで見つかった候補は、ここまでしか候補に入れない


def _author_name(name: str) -> str:
    """「又吉直樹 著」→「又吉直樹」。空白も外して比べやすくする。"""
    return re.sub(r"\s+", "", AUTHOR_SUFFIX.sub("", (name or "").strip()))


def _basis_authors(context: dict) -> set[str]:
    """根拠につながる本の著者（おすすめが同じ著者の本に偏らないよう、見分けるのに使う）。"""
    return {n for b in context["books"] for a in b.get("authors") or [] if (n := _author_name(a))}


def _same_author(candidate: dict, authors: set[str]) -> bool:
    names = {_author_name(a) for a in candidate.get("authors") or []}
    return any(n and (n in authors or any(n in a or a in n for a in authors)) for n in names)


def _collect_queries(context: dict, extra: list[str] | None = None) -> list[str]:
    """（計画で決めた言葉 →）根拠の言葉 → 内容テーマ → ほかの意味づけ の順に、
    つながる本に多く出てくるものから集める。根拠が本のときは、書名で探すと同じ本の
    別版ばかり見つかるので、書名は使わずテーマ・意味づけから探す。

    著者名は最後に1つだけ足す。同じ著者の本を選んでもよいが、著者名を先に・何度も使うと
    候補が同じ著者の本で埋まり、「同じ作者だから」というおすすめに偏るため。
    戻り値は (探す言葉, そのうち著者名の言葉)。"""
    def ranked(key: str) -> list[str]:
        counts: dict[str, int] = {}
        for b in context["books"]:
            for v in b.get(key) or []:
                v = (v or "").strip()
                if v:
                    counts[v] = counts.get(v, 0) + 1
        return sorted(counts, key=lambda v: -counts[v])

    authors = _basis_authors(context)
    queries = [q.strip() for q in (extra or []) if q and q.strip()]
    if context["kind"] == "book":
        queries += ranked("themes")[:2] + ranked("other_concepts")[:2]
    else:
        text = context["text"].strip()
        pieces = [p for p in re.split(r"[、。・／/「」『』\s]+", text) if len(p) >= 2]
        queries += [text] + [p for p in pieces if p != text][:2]
        queries += ranked("themes")[:2]
        queries += ranked("other_concepts")[:1]

    out = []
    for q in queries:
        # 文のように長い言葉は検索に向かないので使わない。
        # 著者名（計画が選んだものも）はいったん外し、最後に1つだけ足す
        q = AUTHOR_SUFFIX.sub("", q.strip())
        if q and len(q) <= MAX_QUERY_LEN and q not in out and _author_name(q) not in authors:
            out.append(q)
    out = out[:MAX_QUERIES - 1]
    author_queries = []
    for a in ranked("authors")[:1]:
        name = AUTHOR_SUFFIX.sub("", a.strip())
        if name and name not in out:
            out.append(name)
            author_queries.append(name)
    return out, author_queries


# ============================================================
# 2. 外部APIで検索する
# ============================================================

def _isbn13(raw: str | None) -> str | None:
    clean = re.sub(r"[^0-9X]", "", (raw or "").upper())
    if len(clean) == 13:
        return clean
    if len(clean) == 10:
        digits = "978" + clean[:9]
        check = (10 - sum(int(d) * (1 if i % 2 == 0 else 3) for i, d in enumerate(digits)) % 10) % 10
        return digits + str(check)
    return None


async def _search_google(query: str, limit: int = GOOGLE_PER_QUERY) -> list[dict]:
    params = {"q": query, "langRestrict": "ja", "printType": "books", "maxResults": limit}
    if GOOGLE_BOOKS_API_KEY:
        params["key"] = GOOGLE_BOOKS_API_KEY
    try:
        r = await get_http_client().get(GOOGLE_BOOKS_URL, params=params, timeout=SEARCH_TIMEOUT)
        r.raise_for_status()
    except Exception as e:
        logger.warning("[recommend] Google Books 検索に失敗 query=%r: %s", query, e)
        return []
    books = []
    for item in r.json().get("items") or []:
        info = item.get("volumeInfo", {})
        ids = {i.get("type"): i.get("identifier") for i in info.get("industryIdentifiers") or []}
        isbn = _isbn13(ids.get("ISBN_13") or ids.get("ISBN_10"))
        if not isbn or not info.get("title"):
            continue
        title = info["title"] + (f" : {info['subtitle']}" if info.get("subtitle") else "")
        books.append({
            "isbn": isbn,
            "title": title,
            "authors": info.get("authors") or [],
            "publisher": info.get("publisher"),
            "published_year": info.get("publishedDate"),
            "pages": info.get("pageCount"),
            "description": (info.get("description") or "")[:160],
        })
    return books


async def _search_ndl(query: str, limit: int = NDL_PER_QUERY, all_words: bool = False) -> list[dict]:
    """all_words=True なら、空白で区切った言葉をすべて含む本を探す（本を探す画面用）。
    False（おすすめ）は、言葉をひと続きのまま探す。"""
    words = [w.replace('"', "") for w in query.split()] if all_words else [query.replace('"', "")]
    # 本だけに絞る。以前の mediatype=1 は今の国会図書館サーチでは0件になるので、"books" を使う
    cql = " AND ".join(f'anywhere="{w}"' for w in words if w) + ' AND mediatype="books"'
    try:
        books, _, _ = await search_ndl_sru(query, start=1, max_records=limit, cql=cql)
    except Exception as e:
        logger.warning("[recommend] NDL 検索に失敗 query=%r: %s", query, e)
        return []
    out = []
    for b in books:
        isbn = _isbn13(b.get("isbn"))
        if not isbn or not b.get("title"):
            continue
        out.append({
            "isbn": isbn,
            "title": b["title"],
            "authors": b.get("authors") or [],
            "publisher": b.get("publisher"),
            "published_year": b.get("published_year"),
            "pages": b.get("pages"),
            "height_mm": b.get("height_mm"),
            "ndc": (b.get("ndc") or {}).get("ndc_full"),
            "description": "",
        })
    return out


async def _search_candidates(queries: list[str], exclude_isbns: set[str]) -> list[dict]:
    """全部のキーワードで並行して検索し、ISBNでまとめる。
    多くのキーワードで見つかった本ほど前に並べる。"""
    tasks = [fn(q) for q in queries for fn in (_search_google, _search_ndl)]
    results = await asyncio.gather(*tasks)
    exclude13 = {_isbn13(i) or i for i in exclude_isbns}

    merged: dict[str, dict] = {}
    for idx, books in enumerate(results):
        query = queries[idx // 2]
        for b in books:
            # 日本の出版物（978-4）に絞る。Google Books は langRestrict=ja でも中国語の本が混ざる
            if b["isbn"] in exclude13 or not b["isbn"].startswith("9784"):
                continue
            cur = merged.get(b["isbn"])
            if cur is None:
                merged[b["isbn"]] = {**b, "hit_by": [query]}
                continue
            if query not in cur["hit_by"]:
                cur["hit_by"].append(query)
            for k, v in b.items():  # 片方にしかない書誌項目を補う
                if v and not cur.get(k):
                    cur[k] = v

    ranked = sorted(merged.values(), key=lambda b: -len(b["hit_by"]))
    return ranked[:MAX_CANDIDATES]


# ============================================================
# 3. LLMが選ぶ
# ============================================================

SYSTEM_RULES = """あなたは、本棚の持ち主の知識グラフを根拠に本を1冊選び、本棚のどこに置くかを決める司書です。

根拠は、持ち主の知識グラフにあるノード（意味づけ・内容テーマ・本棚の本）です。
意味づけとは、持ち主が自分の言葉で本どうしのつながりや並べた理由を名付けたものです。
外部の書誌検索で見つかった候補の中から、根拠とそれにつながる本に加えるのに最もふさわしい1冊を選びます。
持ち主のお願いやこの1冊のねらいが書かれていれば、それにも沿うものを選びます。

選び方のきまり:
- 必ず候補のリストにある本から選ぶ。リストにない本を作らない。
- 根拠の言葉と、根拠につながる本の内容（内容テーマ・意味づけ）の両方に照らして選ぶ。
- 根拠の本と同じ著者の本を選んでもよい。ただし、著者が同じというだけで選ばない。
  内容でも根拠とつながる本を選ぶ。
- 検索の言葉がたまたま書名に含まれるだけの本や、雑誌・問題集・図録など根拠と関係の薄い本は避ける。
- 本棚にある本と同じ本の別版・翻訳・シリーズの同じ巻は選ばない。
- 「持ち主が外したおすすめ」があれば、持ち主の本棚に合わなかった手がかりとして読む。
  外した本と同じ方向の本（同じ分野・同じ読み味・同じ理由づけ）は避け、根拠への別の切り口を探す。
  外した本と似ていても選ぶときは、外した本と何が違うのかを reason に書く。
- ふさわしい本がなければ pick を空文字にする。

置き場所のきまり:
- 本棚のリストにある本を1冊基準にして、その左（left）か右（right）に置く。
- 基本は根拠につながる本の隣にする。その本たちの並びの流れ（年代・難しさ・テーマの移り方など）が
  読み取れるときは、その流れに合う位置を選ぶ。
- 本棚の一覧に「□ 空きマス」があれば、それは持ち主が空けたまとまりの区切り。
  根拠につながる本と同じまとまりの側に置く。

理由のきまり:
- reason: なぜこの根拠にこの本なのかを、根拠の言葉とつながりのある本の書名を挙げて1〜2文、80字程度で。
  つながりは内容（扱うテーマ・問い・場面・読み味など）を中心に書く。同じ著者であることは添える程度にし、
  それだけを理由にしない。
- placement_reason: なぜその位置なのかを1文、40字程度で。
- 本は書名で呼び、B1 や C1 のようなIDは理由に出さない。
- 持ち主の意図を決めつけず、「〜とつながりそうです」のように控えめに書く。

出力のきまり:
- 次の形のJSONだけを出力する。
  {"pick": "C1", "reason": "理由", "anchor": "B1", "side": "right", "placement_reason": "位置の理由"}"""

RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "pick": {"type": "string"},
        "reason": {"type": "string"},
        "anchor": {"type": "string"},
        "side": {"type": "string", "enum": ["left", "right"]},
        "placement_reason": {"type": "string"},
    },
    "required": ["pick", "reason", "anchor", "side", "placement_reason"],
    "additionalProperties": False,
}


def _book_line(b: dict, isbn_to_id: dict[str, str]) -> str:
    details = []
    if b.get("authors"):
        details.append("著者: " + "、".join(b["authors"]))
    if b.get("themes"):
        details.append("内容テーマ: " + "、".join(b["themes"]))
    if b.get("other_concepts"):
        details.append("意味づけ: " + "、".join(b["other_concepts"]))
    suffix = f"（{' / '.join(details)}）" if details else ""
    head = _label(b, isbn_to_id) if b["isbn"] in isbn_to_id else f"「{b.get('title') or '（書名不明）'}」"
    return f"- {head}{suffix}"


def _basis_text(context: dict, isbn_to_id: dict[str, str], wish: str | None, aim: str | None) -> str:
    lines = []
    if wish:
        lines += [f"# 持ち主のお願い\n「{wish}」\n"]
    if aim:
        lines += [f"# この1冊のねらい\n{aim}\n"]
    lines += [f"# 根拠（知識グラフ）\n{context['label']}\n", "# 根拠につながる本"]
    lines += [_book_line(b, isbn_to_id) for b in context["books"]] or ["（なし）"]
    return "\n".join(lines)


def _candidates_text(candidates: list[dict]) -> str:
    lines = []
    for i, c in enumerate(candidates):
        details = []
        if c.get("authors"):
            details.append("著者: " + "、".join(c["authors"][:3]))
        if c.get("publisher"):
            details.append(f"出版社: {c['publisher']}")
        if c.get("published_year"):
            details.append(f"刊行: {c['published_year']}")
        details.append("見つかった言葉: " + "、".join(c["hit_by"]))
        if c.get("same_author"):
            details.append("根拠の本と同じ著者")
        line = f"- C{i + 1}「{c['title']}」（{' / '.join(details)}）"
        if c.get("description"):
            line += f"\n  内容: {c['description']}"
        lines.append(line)
    return "\n".join(lines)


def _call_llm(system_blocks: list[str], content: str, schema: dict, max_tokens: int) -> dict:
    try:
        raw = _llm.chat(system_blocks, [{"role": "user", "content": content}],
                        max_tokens=max_tokens, json_schema=schema)
    except LLMDisabledError:
        raise HTTPException(status_code=503, detail="おすすめは停止中です（LLM_MODE=off）")
    except Exception as e:
        logger.exception("おすすめのLLM呼び出しに失敗しました")
        raise HTTPException(status_code=502, detail=f"LLMの応答を取得できませんでした: {e}")
    return _parse_json(raw)


REMOVED_FOR_LLM = 6  # 本を選ぶLLMに見せる「外したおすすめ」の数（新しい順）


def _removed_text(removed: list[dict]) -> str:
    """持ち主が外したおすすめ（合わなかった本）を文にする。"""
    lines = []
    for r in removed:
        details = [f"根拠: {r['basis']}"] if r.get("basis") else []
        if r.get("authors"):
            details.append("著者: " + "、".join(r["authors"][:2]))
        if r.get("reason"):
            details.append(f"そのときのおすすめの理由: {r['reason'][:80]}")
        lines.append(f"- 『{r.get('title') or '（書名不明）'}』（{' / '.join(details)}）")
    return "\n".join(lines)


def _choose(context: dict, books: list[dict], isbn_to_id: dict[str, str], candidates: list[dict],
            wish: str | None = None, aim: str | None = None, removed: list[dict] | None = None) -> dict:
    system_blocks = [SYSTEM_RULES, f"# 持ち主の本棚（知識グラフより）\n{_shelf_text(books, isbn_to_id)}"]
    removed_block = (
        f"# 持ち主が外したおすすめ（本棚に合わなかった本。新しい順）\n{_removed_text(removed)}\n\n" if removed else ""
    )
    content = (
        f"{_basis_text(context, isbn_to_id, wish, aim)}\n\n"
        f"{removed_block}"
        f"# 候補（外部の書誌検索で見つかった、持ち主がまだ持っていない本）\n{_candidates_text(candidates)}\n\n"
        "この根拠に最もふさわしい1冊を選び、置き場所と理由を決めてください。"
    )
    return _call_llm(system_blocks, content, RESPONSE_SCHEMA, max_tokens=600)


# ============================================================
# 4. 本棚に置く
# ============================================================

def _ensure_registered(db: Session, picked: dict, detail: dict | None, participant_id: str) -> RegisteredBook:
    """書誌を登録する（国会図書館の詳しい書誌があればそちらを優先する）。"""
    book = db.query(RegisteredBook).filter(RegisteredBook.isbn == picked["isbn"]).first()
    if book:
        return book
    d = detail or {}
    authors = d.get("authors") or ",".join(picked.get("authors") or [])
    book = RegisteredBook(
        isbn=picked["isbn"],
        title=d.get("title") or picked["title"],
        authors=authors,
        publisher=d.get("publisher") or picked.get("publisher"),
        published_year=d.get("published_year") or picked.get("published_year"),
        ndc=d.get("ndc_full") or picked.get("ndc"),
        height_mm=d.get("height_mm") or picked.get("height_mm") or 180,
        pages=d.get("pages") or picked.get("pages") or 200,
        cover=d.get("cover") if detail else picked.get("cover"),
        description=d.get("description") or picked.get("description"),
    )
    db.add(book)
    _seed_genre_tag_from_ndc(db, book.isbn, book.ndc, participant_id)
    db.flush()
    return book


def _lay_out(seq: list[ShelfLayout], w) -> None:
    """1段の並び（左から順）の位置を決める。左からぶつかる本だけ右へ押し、
    右端を越えたら右から詰める（離れた右側の本はなるべく動かさない）。"""
    cursor = 0.0
    for r in seq:
        r.x_pos = max(r.x_pos, cursor)
        cursor = r.x_pos + w(r)
    limit = INNER_X
    for r in reversed(seq):
        if r.x_pos + w(r) > limit:
            r.x_pos = limit - w(r)
        limit = r.x_pos
    for i, r in enumerate(seq):
        r.x_pos = round(max(0.0, r.x_pos), 2)
        r.order_index = i


def _insert_into_grid(
    db: Session, participant_id: str, book: RegisteredBook, anchor_isbn: str | None, side: str,
) -> tuple[ShelfLayout, bool]:
    """グリッド版。基準の本の左か右のマスに置く。そのマスがふさがっていれば、
    同じ行の空きマスの方へ本を1マスずつずらして空ける（間の本の並びは崩さない）。
    行に空きがなければ基準の真下のマスへ（ふさがっていれば下に行を足してそこへ）。"""
    service = ShelfService()
    service.normalize_grid(db, participant_id, PRESENT)
    cols = service.grid_cols(db, participant_id, PRESENT)
    rows = (
        db.query(ShelfLayout)
        .filter(ShelfLayout.participant_id == participant_id, ShelfLayout.period == PRESENT)
        .all()
    )
    cell = {(r.shelf_index, r.order_index): r for r in rows}
    anchor = next((r for r in rows if r.isbn == anchor_isbn), None)

    def put(row: int, col: int) -> ShelfLayout:
        new_row = ShelfLayout(
            participant_id=participant_id, period=PRESENT, isbn=book.isbn,
            shelf_index=row, order_index=col, x_pos=grid_x(col, cols),
            height_mm=book.height_mm, pages=book.pages, size_label=book.size_label,
        )
        db.add(new_row)
        db.flush()
        design = _get_or_create_design(db, participant_id, PRESENT)
        design.total_shelves = max([design.total_shelves or 1, row + 1] + [r.shelf_index + 1 for r in rows])
        return new_row

    def shift(row: int, start: int, stop: int, step: int) -> None:
        """start から stop の手前まで（step 方向）の本を1マス step 側へずらす。"""
        for c in range(stop - step, start - step, -step):
            r = cell.pop((row, c))
            r.order_index = c + step
            r.x_pos = grid_x(r.order_index, cols)
            cell[(row, r.order_index)] = r

    if anchor is None:
        # 基準が無ければ、最後の本の次のマス
        last = max(rows, key=lambda r: (r.shelf_index, r.order_index), default=None)
        if last is None:
            return put(0, 0), False
        if last.order_index + 1 < cols:
            return put(last.shelf_index, last.order_index + 1), False
        return put(last.shelf_index + 1, 0), False

    row, a = anchor.shelf_index, anchor.order_index
    # 「この位置の前に差し込む」と考える: 左なら基準の位置、右なら基準の次
    p = a if side == "left" else a + 1
    if p < cols and (row, p) not in cell:
        return put(row, p), True
    if side == "left" and p - 1 >= 0 and (row, p - 1) not in cell:
        return put(row, p - 1), True
    # 右側に空きがあれば、p から右の本を右へずらす
    empty_right = next((c for c in range(p, cols) if (row, c) not in cell), None)
    if empty_right is not None:
        shift(row, p, empty_right, 1)
        return put(row, p), True
    # 左側に空きがあれば、p より左の本を左へずらす（新しい本は p-1 に入る）
    empty_left = next((c for c in range(p - 1, -1, -1) if (row, c) not in cell), None)
    if empty_left is not None:
        shift(row, p - 1, empty_left, -1)
        return put(row, p - 1), True
    # 行がいっぱい: 基準の真下のマスが空いていればそこへ。ふさがっていれば下に行を足す
    if (row + 1, a) not in cell:
        return put(row + 1, a), False
    for r in rows:
        if r.shelf_index > row:
            r.shelf_index += 1
    return put(row + 1, a), False


def _insert_into_shelf(
    db: Session, participant_id: str, book: RegisteredBook, anchor_isbn: str | None, side: str,
) -> tuple[ShelfLayout, bool]:
    """基準の本の左か右に差し込む。本棚の幅は固定なので、段に収まらなくなったら
    右端からあふれた本を、すぐ下の段の左端へ移す（収まらなければすぐ下に段を足す）。
    戻り値は (置いた行, 基準の本と同じ段に置けたか)。"""
    if SHELF_MODE == "grid":
        return _insert_into_grid(db, participant_id, book, anchor_isbn, side)
    rows = (
        db.query(ShelfLayout)
        .filter(ShelfLayout.participant_id == participant_id, ShelfLayout.period == PRESENT)
        .order_by(ShelfLayout.shelf_index, ShelfLayout.x_pos)
        .all()
    )
    by_shelf: dict[int, list[ShelfLayout]] = {}
    for r in rows:
        by_shelf.setdefault(r.shelf_index, []).append(r)

    def w(r) -> float:
        return spine_x(r.pages, r.height_mm)

    anchor = next((r for r in rows if r.isbn == anchor_isbn), None)
    if anchor:
        shelf_idx = anchor.shelf_index
        new_x = anchor.x_pos if side == "left" else anchor.x_pos + w(anchor)
    else:
        # 基準が無ければ、いちばん下の段の左端から続く並びの終わりに置く
        shelf_idx = max(by_shelf, default=0)
        new_x = 0.0
        for r in by_shelf.get(shelf_idx, []):
            if r.x_pos > new_x + 0.5:
                break
            new_x = r.x_pos + w(r)

    new_row = ShelfLayout(
        participant_id=participant_id, period=PRESENT, isbn=book.isbn,
        shelf_index=shelf_idx, x_pos=new_x, order_index=0,
        height_mm=book.height_mm, pages=book.pages, size_label=book.size_label,
    )
    db.add(new_row)
    db.flush()

    # この段の並び順: 差し込む位置より左の本 → 新しい本 → 右の本
    shelf_rows = by_shelf.get(shelf_idx, [])
    seq = [r for r in shelf_rows if r.x_pos < new_x - 0.01] + [new_row] + \
          [r for r in shelf_rows if r.x_pos >= new_x - 0.01]

    # 段に収まらない分は、右端の本から下の段へ
    overflow: list[ShelfLayout] = []
    while len(seq) > 1 and sum(w(r) for r in seq) > INNER_X + 0.01:
        overflow.insert(0, seq.pop())

    _lay_out(seq, w)

    if overflow:
        below = by_shelf.get(shelf_idx + 1, [])
        if below and sum(w(r) for r in overflow + below) <= INNER_X + 0.01:
            # すぐ下の段に収まるなら、その段の左端に続ける（読む順につながる）
            for r in overflow:
                r.shelf_index = shelf_idx + 1
                r.x_pos = 0.0
            _lay_out(overflow + below, w)
        else:
            # 収まらなければすぐ下に段を足す: それより下の段を1つずつ下げてから、左から並べる
            for r in rows:
                if r.shelf_index > shelf_idx and r not in overflow:
                    r.shelf_index += 1
            for r in overflow:
                r.shelf_index = shelf_idx + 1
                r.x_pos = 0.0
            _lay_out(overflow, w)

    design = _get_or_create_design(db, participant_id, PRESENT)
    last = max([r.shelf_index for r in rows] + [new_row.shelf_index])
    design.total_shelves = max(design.total_shelves or 1, last + 1)

    exact = anchor is not None and new_row.shelf_index == anchor.shelf_index
    return new_row, exact


# ============================================================
# 1冊を加える（共通）
# ============================================================

async def _recommend_one(
    db: Session, participant_id: str, context: dict, background_tasks: BackgroundTasks, *,
    trigger: str, extra_queries: list[str] | None = None, wish: str | None = None,
    aim: str | None = None, dialogue_session_id: str | None = None,
) -> dict:
    # 1. キーワード → 2. 検索（持っている本・棚にある本は除く）
    queries, author_queries = _collect_queries(context, extra_queries)
    owned = _neo4j_guard(store.get_owned_isbns, participant_id)
    on_shelf = {r.isbn for r in db.query(ShelfLayout.isbn).filter(ShelfLayout.participant_id == participant_id)}
    # 外したおすすめは、合わなかった本なので二度とおすすめしない（次の本選びの手がかりにも使う）
    removed = _neo4j_guard(store.get_removed_recommendations, participant_id, REMOVED_FOR_LLM)
    removed_isbns = set(_neo4j_guard(store.get_removed_isbns, participant_id))
    candidates = await _search_candidates(queries, owned | on_shelf | removed_isbns)
    if not candidates:
        raise HTTPException(status_code=404, detail="外部の書誌検索で候補が見つかりませんでした")
    # 著者名だけで見つかった候補は少しだけにする（同じ著者の本で候補が埋まらないように）。
    # 内容の言葉でも見つかった本は、同じ著者でもそのまま残す。
    author_only = [c for c in candidates if set(c["hit_by"]) <= set(author_queries)]
    drop = {id(c) for c in author_only[MAX_AUTHOR_ONLY_CANDIDATES:]}
    candidates = [c for c in candidates if id(c) not in drop]
    authors = _basis_authors(context)
    for c in candidates:
        c["same_author"] = _same_author(c, authors)

    # 3. LLMが選ぶ
    books = _neo4j_guard(get_shelf_books, participant_id)
    isbn_to_id, id_to_isbn = _book_ids(books)
    data = await asyncio.to_thread(_choose, context, books, isbn_to_id, candidates, wish, aim, removed)
    pick = str(data.get("pick") or "").strip()
    m = re.fullmatch(r"C(\d+)", pick)
    if not m or not (1 <= int(m.group(1)) <= len(candidates)):
        if pick:
            logger.warning("おすすめのLLM応答を解釈できませんでした: %s", data)
        raise HTTPException(status_code=404, detail=f"{context['label']}にふさわしい本が候補の中にありませんでした")
    picked = candidates[int(m.group(1)) - 1]

    basis_isbns = [b["isbn"] for b in context["books"] if b["isbn"] in isbn_to_id]
    anchor_isbn = id_to_isbn.get(str(data.get("anchor") or "").strip())
    if anchor_isbn is None and basis_isbns:
        anchor_isbn = basis_isbns[-1]
    side = data.get("side") if data.get("side") in ("left", "right") else "right"

    # 4. 本棚（SQLite）に置く
    try:
        detail = await _registration_service.fetch_ndl_by_isbn(picked["isbn"])
    except Exception:
        detail = None
    if not detail:
        # 国会図書館に詳しい書誌がなくても、書影は共通の取り方で探す
        picked["cover"] = await fetch_cover(picked["isbn"])
    try:
        book = _ensure_registered(db, picked, detail, participant_id)
        row, exact = _insert_into_shelf(db, participant_id, book, anchor_isbn, side)
        db.commit()
    except Exception as e:
        db.rollback()
        logger.exception("おすすめの本を棚に置けませんでした")
        raise HTTPException(status_code=500, detail=f"本棚に置けませんでした: {e}")

    # 知識グラフ: 所有・位置・隣り合わせ・（根拠が意味づけなら）意味づけ・おすすめの記録
    layout = (
        db.query(ShelfLayout)
        .filter(ShelfLayout.participant_id == participant_id, ShelfLayout.period == PRESENT)
        .all()
    )
    payload = [
        {"id": r.id, "isbn": r.isbn, "shelf_index": r.shelf_index, "x_pos": r.x_pos,
         "order_index": r.order_index, "pages": r.pages or 200}
        for r in layout
    ]
    reason = str(data.get("reason") or "").strip()
    placement_reason = str(data.get("placement_reason") or "").strip() if exact else ""

    def write_graph():
        add_book_with_meaning(book, participant_id=participant_id)
        store.mark_recommended_ownership(participant_id, book.isbn, context["label"])
        update_shelf_layout_chain(payload, participant_id=participant_id, moved_isbns=[])
        if context["kind"] == "concept":
            save_concept(
                [book.isbn], context["text"], participant_id=participant_id,
                origin="recommendation", confidence="suggested", strength=0.5,
            )
        return store.save_recommendation(
            participant_id, context["kind"], context["key"], book.isbn,
            reason=reason, placement_reason=placement_reason,
            anchor_isbn=anchor_isbn if exact else None, side=side if exact else None,
            queries=queries, candidate_count=len(candidates),
            trigger=trigger, wish=wish, aim=aim, dialogue_session_id=dialogue_session_id,
        )

    recommendation_id = _neo4j_guard(write_graph)
    background_tasks.add_task(_run_placement_analysis_sync, participant_id)

    anchor_title = next((b.get("title") for b in books if b["isbn"] == anchor_isbn), None)
    if exact and anchor_title:
        where = f"『{anchor_title}』の{'左' if side == 'left' else '右'}"
    elif anchor_title and SHELF_MODE == "grid":
        where = f"上から{row.shelf_index + 1}行目（『{anchor_title}』の行に空きがなく、下の行に置きました）"
    elif anchor_title:
        where = f"上から{row.shelf_index + 1}段目（『{anchor_title}』の段に収まらず、下の段に置きました）"
    elif SHELF_MODE == "grid":
        where = f"上から{row.shelf_index + 1}行目"
    else:
        where = f"上から{row.shelf_index + 1}段目"
    return {
        "recommendation_id": recommendation_id,
        "basis": context["label"],
        "concept": context["text"] if context["kind"] == "concept" else None,
        "layout_id": row.id,
        "book": {
            "isbn": book.isbn, "title": book.title,
            "authors": [a for a in (book.authors or "").split(",") if a],
            "publisher": book.publisher, "cover": book.cover,
        },
        "reason": reason,
        "placement": {
            "shelf_index": row.shelf_index, "anchor_isbn": anchor_isbn if exact else None,
            "side": side if exact else None, "text": where, "reason": placement_reason,
        },
        "queries": queries,
        "candidate_count": len(candidates),
    }


# ============================================================
# お願いされたときの計画
# ============================================================

NDC_L1_LABELS = {
    "0": "総記", "1": "哲学・宗教・心理", "2": "歴史・地理", "3": "社会科学", "4": "自然科学",
    "5": "技術・工学", "6": "産業", "7": "芸術・スポーツ", "8": "言語", "9": "文学", "": "分類なし",
}

PLAN_RULES = """あなたは、本棚の持ち主の知識グラフを読んで、持ち主のお願いどおりに本を加える計画を立てる司書です。

持ち主から「本を加えてほしい」と頼まれました。加える1冊ごとに、知識グラフのどのノードを根拠に探すかと、
その1冊のねらいを決めてください。実際の本は、あとで根拠のノードとそのつながりから外部検索して選びます。

計画のきまり:
- 根拠は必ず、下のリストにあるノードのIDから選ぶ（K: 意味づけ、T: 内容テーマ、B: 本棚の本）。
  リストにないものを根拠にしない。
- 持ち主のお願い（例: バランスよく、小説を、仕事に役立つ）に沿うように根拠を選ぶ。
  「バランスよく」なら、同じ根拠や似た根拠に偏らせず、意味づけ・テーマ・分野が散らばるようにする。
  冊数の少ない分野や、まだ本の少ない意味づけを優先してもよい。
- 同じ根拠は、お願いがその根拠に絞られている場合を除いて2回使わない。
- keywords: 外部検索に使う言葉を1〜3個。根拠のノードとそのつながり（テーマ・意味づけ）にある、
  内容を表す言葉から選ぶ。著者名や書名は使わない（著者名はあとで1つだけ自動で足すので、
  ここで使うと同じ著者・同じ本の別版ばかり見つかる）。
  お願いに分野の指定があれば、その分野を表す言葉を1つ足してよい。
- aim: その1冊のねらいを1文、30字程度で（例: 「旅の本に、写真で見る一冊を足す」）。
- plans の数は、頼まれた冊数にする。

出力のきまり:
- 次の形のJSONだけを出力する。
  {"plans": [{"basis": "K1", "keywords": ["言葉"], "aim": "ねらい"}]}"""

PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "plans": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "basis": {"type": "string"},
                    "keywords": {"type": "array", "items": {"type": "string"}},
                    "aim": {"type": "string"},
                },
                "required": ["basis", "keywords", "aim"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["plans"],
    "additionalProperties": False,
}


def _overview_text(overview: dict, books: list[dict], isbn_to_id: dict[str, str]) -> tuple[str, dict]:
    """計画用の知識グラフの一覧と、ID → (種類, キー, 名前) の対応を作る。"""
    ids: dict[str, tuple[str, str, str]] = {}
    lines = ["# 意味づけ（K）"]
    for i, c in enumerate(overview["concepts"]):
        kid = f"K{i + 1}"
        ids[kid] = ("concept", c["key"], c["text"])
        titles = "、".join(f"『{t}』" for t in c["titles"][:5])
        lines.append(f"- {kid}「{c['text']}」（{len(c['titles'])}冊: {titles}）")
    if not overview["concepts"]:
        lines.append("（まだない）")
    lines.append("\n# 内容テーマ（T）")
    for i, t in enumerate(overview["themes"]):
        tid = f"T{i + 1}"
        ids[tid] = ("theme", t["key"], t["text"])
        lines.append(f"- {tid}「{t['text']}」（{t['count']}冊）")
    if not overview["themes"]:
        lines.append("（まだない）")
    lines.append("\n# 分野ごとの冊数（NDCの大きな区分）")
    lines += [f"- {NDC_L1_LABELS.get(n['l1'], n['l1'])}: {n['count']}冊" for n in overview["ndc"]] or ["（なし）"]
    for b in books:
        ids[isbn_to_id[b["isbn"]]] = ("book", b["isbn"], b.get("title") or "")
    lines.append(f"\n# 本棚の本（B）\n{_shelf_text(books, isbn_to_id)}")
    return "\n".join(lines), ids


class PlanRequest(BaseModel):
    count: int
    wish: str = ""
    dialogue_session_id: str | None = None


class PlanItem(BaseModel):
    basis_kind: str
    basis_key: str
    keywords: list[str] = []
    aim: str = ""
    wish: str = ""
    dialogue_session_id: str | None = None


@router.post("/request/plan")
async def plan_requested_books(body: PlanRequest, participant_id: str = Depends(resolve_participant_id)):
    """持ち主に「本を入れて」と頼まれたとき、1冊ごとの根拠（知識グラフのノード）とねらいを決める。"""
    count = max(1, min(MAX_REQUEST_BOOKS, body.count))
    overview = _neo4j_guard(store.get_graph_overview, participant_id)
    books = _neo4j_guard(get_shelf_books, participant_id)
    if not books:
        raise HTTPException(status_code=400, detail="本棚に本がないので、根拠にできる知識グラフがありません")
    isbn_to_id, _ = _book_ids(books)
    text, ids = _overview_text(overview, books, isbn_to_id)
    content = (
        f"# 持ち主のお願い\n「{body.wish or f'本を{count}冊加えて'}」\n\n# 加える冊数\n{count}冊\n\n"
        f"# 持ち主の知識グラフ\n{text}\n\n計画を立ててください。"
    )
    data = await asyncio.to_thread(_call_llm, [PLAN_RULES], content, PLAN_SCHEMA, 1200)

    plans, used = [], set()
    for p in data.get("plans") or []:
        if not isinstance(p, dict) or str(p.get("basis", "")).strip() not in ids:
            continue
        kind, key, name = ids[str(p["basis"]).strip()]
        keywords = [str(k).strip() for k in (p.get("keywords") or []) if str(k).strip()][:3]
        plans.append({
            "basis_kind": kind, "basis_key": key, "label": store.basis_label(kind, name),
            "keywords": keywords, "aim": str(p.get("aim") or "").strip(),
        })
        used.add((kind, key))
        if len(plans) >= count:
            break

    # LLMの計画が足りなければ、まだ使っていない根拠（意味づけ → テーマ → 本）で埋める
    for kind, key, name in ids.values():
        if len(plans) >= count:
            break
        if (kind, key) not in used:
            plans.append({"basis_kind": kind, "basis_key": key, "label": store.basis_label(kind, name),
                          "keywords": [], "aim": ""})
            used.add((kind, key))
    return {"count": count, "wish": body.wish, "plans": plans}


@router.post("/request/item")
async def add_requested_book(
    body: PlanItem,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    participant_id: str = Depends(resolve_participant_id),
):
    """計画の1冊ぶんを、根拠のノードから探して本棚に加える。"""
    if body.basis_kind not in store.BASIS_KINDS:
        raise HTTPException(status_code=400, detail="根拠の種類が正しくありません")
    context = _neo4j_guard(store.get_basis_context, participant_id, body.basis_kind, body.basis_key)
    if not context:
        raise HTTPException(status_code=404, detail="根拠のノードが知識グラフに見つかりません")
    return await _recommend_one(
        db, participant_id, context, background_tasks,
        trigger="request", extra_queries=body.keywords, wish=body.wish or None,
        aim=body.aim or None, dialogue_session_id=body.dialogue_session_id,
    )


# ============================================================
# エンドポイント（意味づけから・外したとき）
# ============================================================

# 知識グラフの育ち具合に合わせて、自動でおすすめを足す（対話の締めくくりのあとに呼ぶ）。
# 対話のたびに意味づけ1つにつき1冊足すと、本の増え方が知識グラフの育ち方より速く、
# 手がかりの少ない意味づけからも探すので外れやすい。そこで、
#   - 持ち主が付けた意味づけのつながり（本と意味づけの線）が AUTO_STEP_LINKS 本増えるごとに1冊
#   - 根拠は、本が AUTO_MIN_BOOKS 冊以上つながっていて、まだおすすめを出していない意味づけ
# にする。1回に足すのは1冊まで。
AUTO_STEP_LINKS = 4
AUTO_MIN_BOOKS = 2
AUTO_MAX_TRIES = 2  # 根拠の候補で本が見つからなかったら、次の候補を試す回数


class AutoRequest(BaseModel):
    # この対話で加わった・育った意味づけ（根拠に選ぶとき優先する）
    concept_ids: list[str] = []


@router.post("/auto")
async def recommend_auto(
    body: AutoRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    participant_id: str = Depends(resolve_participant_id),
):
    """育ち具合が足りていれば1冊足す。戻り値の status:
    added（足した）/ waiting（まだ育ち具合が足りない）/ no_basis（根拠にできる意味づけがまだない）/
    not_found（根拠はあるが、ふさわしい本が見つからなかった）。"""
    links = _neo4j_guard(store.count_meaning_links, participant_id)
    checkpoint = _neo4j_guard(store.get_recommend_checkpoint, participant_id)
    grown = links - checkpoint
    progress = {"grown": max(0, grown), "step": AUTO_STEP_LINKS, "remaining": max(0, AUTO_STEP_LINKS - grown)}
    if grown < AUTO_STEP_LINKS:
        return {"status": "waiting", "progress": progress}

    bases = _neo4j_guard(store.pick_auto_concepts, participant_id, AUTO_MIN_BOOKS, body.concept_ids, AUTO_MAX_TRIES)
    if not bases:
        return {"status": "no_basis", "progress": progress, "min_books": AUTO_MIN_BOOKS}

    last_error = None
    for basis in bases:
        context = _neo4j_guard(store.get_basis_context, participant_id, "concept", basis["concept_id"])
        if not context:
            continue
        try:
            result = await _recommend_one(db, participant_id, context, background_tasks, trigger="concept")
        except HTTPException as e:
            if e.status_code not in (404,):
                raise
            last_error = e.detail
            continue
        _neo4j_guard(store.set_recommend_checkpoint, participant_id, links)
        return {"status": "added", "progress": {**progress, "remaining": AUTO_STEP_LINKS}, "recommendation": result}
    return {"status": "not_found", "progress": progress, "detail": last_error}


@router.post("/concept/{concept_id}")
async def recommend_from_concept(
    concept_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    participant_id: str = Depends(resolve_participant_id),
):
    """対話の締めくくりで加わった意味づけから、自動で1冊加える。"""
    context = _neo4j_guard(store.get_basis_context, participant_id, "concept", concept_id)
    if not context:
        raise HTTPException(status_code=404, detail="意味づけが見つかりません")
    return await _recommend_one(db, participant_id, context, background_tasks, trigger="concept")


@router.post("/{recommendation_id}/removed")
def mark_recommendation_removed(recommendation_id: str, participant_id: str = Depends(resolve_participant_id)):
    """持ち主がおすすめの本を本棚から外したとき（本棚からの削除は /bookshelf/remove-book で行う）。"""
    if not _neo4j_guard(store.mark_removed, participant_id, recommendation_id):
        raise HTTPException(status_code=404, detail="おすすめが見つかりません")
    return {"status": "removed"}
