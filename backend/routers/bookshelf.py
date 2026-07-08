from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import List
from models import ShelfLayout, ShelfDesign, RegisteredBook
from sqlalchemy.orm import Session
from database import get_db
from admin_neo4j.neo4j_driver import get_session
from admin_neo4j.neo4j_crud import update_shelf_layout_chain, save_concept
from utils.llm_provider import get_llm_client
import logging

logger = logging.getLogger(__name__)


router = APIRouter(prefix="/bookshelf", tags=["bookshelf"])

SHELF_MAX_WIDTH_PX = 800  # ShelfDesign.shelf_max_width に置き換えてもよい

_llm = get_llm_client()


@router.post("/add_shelves")
def add_shelves(db: Session = Depends(get_db)):
    design = db.query(ShelfDesign).first()
    if not design:
        design = ShelfDesign(total_shelves=1)
        db.add(design)
    else:
        design.total_shelves += 1
    db.commit()
    return {"total_shelves": design.total_shelves}


@router.post("/remove_shelves")
def remove_shelves(db: Session = Depends(get_db)):
    design = db.query(ShelfDesign).first()
    if not design or design.total_shelves <= 1:
        raise HTTPException(status_code=400, detail="これ以上段を削除できません")

    last_shelf_index = design.total_shelves -1

    # 一番下の段に本があるか確認
    books_on_last = db.query(ShelfLayout)\
        .filter(ShelfLayout.shelf_index == last_shelf_index)\
        .count()

    if books_on_last > 0:
        raise HTTPException(status_code=400, detail="一番下の段に本があるため削除できません")

    design.total_shelves -= 1
    db.commit()
    
    return {"total_shelves": design.total_shelves}

FRAME     = 20   # 棚の左右フレーム幅（フロントと合わせる）
SPINE_GAP = 2

class BookPosition(BaseModel):
    isbn:        str
    shelf_index: int
    x_pos:       float | None = 0
    order_index: int = 0  # 互換性のため残す

class SyncLayoutRequest(BaseModel):
    layout: List[BookPosition]



@router.get("/")
def fetch_bookshelf(db: Session = Depends(get_db)):
    design = db.query(ShelfDesign).first()
    if not design:
        design = ShelfDesign(total_shelves=1)
        db.add(design)
        db.commit()

    layouts = db.query(ShelfLayout)\
        .order_by(ShelfLayout.shelf_index, ShelfLayout.x_pos)\
        .all()

    if not layouts:
        return {"shelves": [], "total_shelves": design.total_shelves}

    layout_map = {l.isbn: l for l in layouts}

    title_map: dict[str, str] = {}
    with get_session() as session:
        result = session.run(
            "MATCH (b:Book) WHERE b.isbn IN $isbns RETURN b.isbn AS isbn, b.title AS title",
            isbns=list(layout_map.keys())
        )
        for r in result:
            title_map[r["isbn"]] = r["title"]

    reg_books = db.query(RegisteredBook).filter(RegisteredBook.isbn.in_(list(layout_map.keys()))).all()
    spine_map = {rb.isbn: rb.spine_image for rb in reg_books}
    ndc_map = {rb.isbn: rb.ndc for rb in reg_books}

    shelves: dict[int, list] = {}
    for l in layouts:
        shelves.setdefault(l.shelf_index, []).append({
            "isbn":            l.isbn,
            "title":           title_map.get(l.isbn, ""),
            "cover":           l.cover,
            "spine_image":     spine_map.get(l.isbn),
            "size_label":      l.size_label,
            "shelf_index":     l.shelf_index,
            "x_pos":           l.x_pos,
            "order_index":     l.order_index,
            "pages":           l.pages,
            "height_mm":       l.height_mm,
            "ndc":             ndc_map.get(l.isbn),
        })

    return {
        "shelves":       [{"shelf_index": k, "books": v} for k, v in sorted(shelves.items())],
        "total_shelves": design.total_shelves,
    }


@router.post("/sync-layout")
async def sync_layout(body: SyncLayoutRequest, db: Session = Depends(get_db)):
    try:
        for pos in body.layout:
            db.query(ShelfLayout)\
                .filter(ShelfLayout.isbn == pos.isbn)\
                .update({
                    "shelf_index": pos.shelf_index,
                    "x_pos":       round(pos.x_pos, 2),
                    "order_index": pos.order_index,
                }, synchronize_session=False)

        db.commit()

        isbns = [pos.isbn for pos in body.layout]
        pages_map = {
            r.isbn: r.pages
            for r in db.query(ShelfLayout).filter(ShelfLayout.isbn.in_(isbns)).all()
        }
        neo4j_payload = [
            {**pos.model_dump(), "pages": pages_map.get(pos.isbn, 200)}
            for pos in body.layout
        ]
        update_shelf_layout_chain(neo4j_payload)

        return {"status": "success"}
    except Exception as e:
        import traceback
        traceback.print_exc()
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

class SaveConceptRequest(BaseModel):
    meaning: str
    isbns: List[str]


# ── 意味付与ダイアログ（対話でAIが言語化を深める） ──────────

class ChatMessage(BaseModel):
    role: str  # "user" | "ai"
    text: str

class MeaningChatRequest(BaseModel):
    isbns: List[str]
    history: List[ChatMessage] = []
    message: str

class SaveMeaningDialogueRequest(BaseModel):
    isbns: List[str]
    history: List[ChatMessage]


def _fetch_titles(isbns: List[str]) -> List[str]:
    with get_session() as session:
        result = session.run(
            "MATCH (b:Book) WHERE b.isbn IN $isbns RETURN b.title AS title",
            isbns=isbns,
        )
        return [r["title"] for r in result if r["title"]]


def _format_dialogue(history: List[ChatMessage]) -> str:
    lines = []
    for m in history:
        speaker = "ユーザー" if m.role == "user" else "あなた"
        lines.append(f"{speaker}: {m.text}")
    return "\n".join(lines)


def _build_dialogue_prompt(titles: List[str], history: List[ChatMessage], message: str) -> str:
    book_list = "、".join(titles) if titles else "選択された本"
    return "\n".join([
        f"あなたは読書の伴走者です。ユーザーが「{book_list}」という本(たち)について、"
        "自分にとっての個人的な意味を言葉にする手助けをしてください。",
        "ユーザーの発言を否定せず受け止めた上で、具体的なエピソードや感情を引き出すような、"
        "焦点を絞った質問か短い気づきを1つだけ返してください。",
        "返答は日本語で2〜3文以内、箇条書きは使わないでください。",
        "",
        "これまでの対話:",
        _format_dialogue(history),
        f"ユーザー: {message}",
        "あなた:",
    ])


def _build_summary_prompt(titles: List[str], history: List[ChatMessage]) -> str:
    book_list = "、".join(titles) if titles else "選択された本"
    return "\n".join([
        f"以下はユーザーが「{book_list}」という本(たち)について、自分にとっての意味を言葉にするために交わした対話です。",
        "この対話全体から、ユーザーにとってのこの本(たち)の個人的な意味を、"
        "ユーザー自身の言葉を尊重しながら2〜4文の一つの文章に要約してください。",
        "説明や前置きは不要で、要約した文章のみを日本語で返してください。",
        "",
        "対話:",
        _format_dialogue(history),
    ])


@router.post("/meaning-chat")
async def meaning_chat(body: MeaningChatRequest):
    if not body.message.strip():
        raise HTTPException(status_code=400, detail="message is required")

    titles = _fetch_titles(body.isbns)
    prompt = _build_dialogue_prompt(titles, body.history, body.message)
    try:
        reply = _llm.generate_text(prompt, max_tokens=512)
    except Exception as e:
        logger.exception("AI呼び出し失敗")
        raise HTTPException(status_code=502, detail=f"AI応答に失敗しました: {e}")

    return {"reply": reply}


@router.post("/save-meaning-dialogue")
async def save_meaning_dialogue(body: SaveMeaningDialogueRequest):
    if not body.isbns:
        raise HTTPException(status_code=400, detail="isbns is required")
    if not body.history:
        raise HTTPException(status_code=400, detail="対話内容がありません")

    titles = _fetch_titles(body.isbns)
    prompt = _build_summary_prompt(titles, body.history)
    try:
        summary = _llm.generate_text(prompt, max_tokens=512)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"要約に失敗しました: {e}")

    save_concept(isbns=body.isbns, meaning=summary)
    return {"status": "ok", "concept": summary}

@router.delete("/remove-book/{isbn}")
def remove_book_from_shelf(isbn: str, db: Session = Depends(get_db)):
    layout = db.query(ShelfLayout).filter(ShelfLayout.isbn == isbn).first()
    if not layout:
        raise HTTPException(status_code=404, detail="本が見つかりません")
    db.delete(layout)
    db.commit()
    return {"status": "deleted", "isbn": isbn}


@router.post("/save-concept")
def save_concept_endpoint(body: SaveConceptRequest):
    if not body.meaning.strip():
        raise HTTPException(status_code=400, detail="meaning is required")
    if not body.isbns:
        raise HTTPException(status_code=400, detail="isbns is required")
    save_concept(isbns=body.isbns, meaning=body.meaning.strip())
    return {"status": "ok", "concept": body.meaning, "books": len(body.isbns)}


@router.post("/migrate-x-pos")
def migrate_x_pos(db: Session = Depends(get_db)):
    """order_index → x_pos への一回限りのマイグレーション"""
    layouts = db.query(ShelfLayout)\
        .order_by(ShelfLayout.shelf_index, ShelfLayout.order_index)\
        .all()
    shelves: dict[int, list] = {}
    for l in layouts:
        shelves.setdefault(l.shelf_index, []).append(l)
    for shelf_books in shelves.values():
        acc = FRAME
        for book in shelf_books:
            book.x_pos = acc
            acc += book.spine_width_px + SPINE_GAP
    db.commit()
    return {"status": "migrated"}