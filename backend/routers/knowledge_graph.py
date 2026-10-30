"""知識グラフ API（育つ本棚の画面から使うものだけ）。

- 本の詳細パネル: 感想の読み込み（/book/{isbn}/basic）と保存（/book/{isbn}/impression）
- 見出しの冊数など: /growth

意味づけ(Concept)の追加は本棚対話（routers/dialogue.py）から行う。
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from graph.main_kg.neo4j_crud import get_book_basic, get_growth_stats, save_book_impression
from participant import resolve_participant_id

router = APIRouter(prefix="/knowledge_graph")


@router.get("/book/{isbn}/basic")
def get_book_basic_endpoint(isbn: str, participant_id: str = Depends(resolve_participant_id)):
    """本の詳細パネル用：書誌情報と感想を返す。"""
    data = get_book_basic(isbn, participant_id=participant_id)
    if not data:
        raise HTTPException(status_code=404, detail="本が見つかりません")
    return data


class ImpressionRequest(BaseModel):
    text: str


@router.post("/book/{isbn}/impression")
def save_book_impression_endpoint(
    isbn: str,
    body: ImpressionRequest,
    participant_id: str = Depends(resolve_participant_id),
):
    """1冊ごとの個人的な感想を保存する。
    上書きではなく追記なので、感想の変遷が履歴として残る。"""
    save_book_impression(isbn, body.text, participant_id=participant_id)
    return {"ok": True}


@router.get("/growth")
def get_growth_endpoint(participant_id: str = Depends(resolve_participant_id)):
    """見出しの冊数などの元になる量（本の数・意味づけの数・感想の数）。"""
    return get_growth_stats(participant_id)
