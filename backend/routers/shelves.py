"""本棚の管理 API（持ち主は本棚を複数持てる）。

本棚ごとに配置・知識グラフ・対話・おすすめをすべて分ける。各本棚にスコープID
（models.Bookshelf.scope_id）を割り当て、画面は今開いている本棚のIDを
X-Shelf-Id ヘッダで送る。ほかのAPIはそれを participant_id として使う
（participant.resolve_participant_id）。

本は1冊につきどれか1つの本棚に置く。本棚の間で移すと、移した先の本棚に
新しく加わった本として扱う（移す前の本棚の意味づけ・対話は、その本棚に残る）。
"""
import logging
import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from database import get_db
from graph.main_kg.neo4j_crud import add_book_with_meaning, remove_book_ownership
from graph.main_kg.neo4j_driver import get_session
from models import Bookshelf, GenreTag, MyHand, RegisteredBook, ShelfDesign, ShelfLayout
from participant import resolve_base_participant_id, resolve_participant_id, shelf_scope_id
from shelf_period import PRESENT
from utils.shelf_utils import ShelfService

router = APIRouter(prefix="/shelves", tags=["shelves"])
logger = logging.getLogger(__name__)

DEFAULT_SHELF_NAME = "本棚1"
MAX_NAME_LEN = 30
MAX_SHELVES = 10


def _ensure_default(db: Session, participant_id: str) -> None:
    """最初の本棚（スコープID = 持ち主のID、これまでのデータが入っている本棚）を用意する。"""
    exists = db.query(Bookshelf.id).filter(
        Bookshelf.participant_id == participant_id, Bookshelf.scope_id == participant_id,
    ).first()
    if not exists:
        db.add(Bookshelf(participant_id=participant_id, scope_id=participant_id,
                         name=DEFAULT_SHELF_NAME, sort_order=0))
        db.commit()


def _shelves(db: Session, participant_id: str) -> list[Bookshelf]:
    _ensure_default(db, participant_id)
    return (
        db.query(Bookshelf)
        .filter(Bookshelf.participant_id == participant_id)
        .order_by(Bookshelf.sort_order, Bookshelf.id)
        .all()
    )


def _get_shelf(db: Session, participant_id: str, shelf_id: int) -> Bookshelf:
    shelf = db.query(Bookshelf).filter(
        Bookshelf.id == shelf_id, Bookshelf.participant_id == participant_id,
    ).first()
    if not shelf:
        raise HTTPException(status_code=404, detail="本棚が見つかりません")
    return shelf


def _clean_name(name: str) -> str:
    name = re.sub(r"\s+", " ", name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="本棚の名前を入れてください")
    return name[:MAX_NAME_LEN]


def _shelf_json(shelf: Bookshelf, counts: dict[str, int]) -> dict:
    return {
        "id": shelf.id,
        "scope_id": shelf.scope_id,
        "name": shelf.name,
        "book_count": counts.get(shelf.scope_id, 0),
        "is_default": shelf.scope_id == shelf.participant_id,
        "created_at": shelf.created_at.isoformat() if shelf.created_at else None,
    }


def _counts(db: Session, scope_ids: list[str]) -> dict[str, int]:
    rows = (
        db.query(ShelfLayout.participant_id, func.count(ShelfLayout.id))
        .filter(ShelfLayout.participant_id.in_(scope_ids), ShelfLayout.period == PRESENT)
        .group_by(ShelfLayout.participant_id)
        .all()
    )
    return dict(rows)


# ============================================================
# 一覧・作成・名前の変更・削除
# ============================================================

@router.get("/")
def list_shelves(
    db: Session = Depends(get_db),
    participant_id: str = Depends(resolve_base_participant_id),
):
    shelves = _shelves(db, participant_id)
    counts = _counts(db, [s.scope_id for s in shelves])
    return {"shelves": [_shelf_json(s, counts) for s in shelves]}


class ShelfName(BaseModel):
    name: str


@router.post("/")
def create_shelf(
    body: ShelfName,
    db: Session = Depends(get_db),
    participant_id: str = Depends(resolve_base_participant_id),
):
    shelves = _shelves(db, participant_id)
    if len(shelves) >= MAX_SHELVES:
        raise HTTPException(status_code=400, detail=f"本棚は{MAX_SHELVES}個までつくれます")
    # 番号は使い回さない（消した本棚のスコープIDを再利用すると、残っていたデータと混ざるおそれがある）
    used = [s.scope_id for s in db.query(Bookshelf).filter(Bookshelf.participant_id == participant_id)]
    numbers = [int(m.group(1)) for sid in used if (m := re.fullmatch(rf"{re.escape(participant_id)}-S(\d+)", sid))]
    number = max(numbers + [1]) + 1
    scope_id = shelf_scope_id(participant_id, number)
    while db.query(ShelfLayout.id).filter(ShelfLayout.participant_id == scope_id).first():
        number += 1
        scope_id = shelf_scope_id(participant_id, number)
    shelf = Bookshelf(
        participant_id=participant_id, scope_id=scope_id, name=_clean_name(body.name),
        sort_order=max([s.sort_order for s in shelves] + [0]) + 1,
    )
    db.add(shelf)
    db.add(ShelfDesign(participant_id=scope_id, period=PRESENT, total_shelves=1))
    db.commit()
    return _shelf_json(shelf, {})


@router.patch("/{shelf_id}")
def rename_shelf(
    shelf_id: int,
    body: ShelfName,
    db: Session = Depends(get_db),
    participant_id: str = Depends(resolve_base_participant_id),
):
    shelf = _get_shelf(db, participant_id, shelf_id)
    shelf.name = _clean_name(body.name)
    db.commit()
    return _shelf_json(shelf, _counts(db, [shelf.scope_id]))


@router.delete("/{shelf_id}")
def delete_shelf(
    shelf_id: int,
    db: Session = Depends(get_db),
    participant_id: str = Depends(resolve_base_participant_id),
):
    """本が1冊もない本棚だけを消せる。その本棚の意味づけ・対話・おすすめの記録も消える。
    最初の本棚（これまでのデータが入っている本棚）は消せない。"""
    shelf = _get_shelf(db, participant_id, shelf_id)
    scope = shelf.scope_id
    if scope == participant_id or not scope.startswith(f"{participant_id}-S"):
        raise HTTPException(status_code=400, detail="最初の本棚は消せません")
    if db.query(ShelfLayout.id).filter(ShelfLayout.participant_id == scope).first():
        raise HTTPException(status_code=409, detail="本が残っている本棚は消せません。先に本をほかの本棚へ移してください")

    # 知識グラフ: この本棚の範囲のノード・関係だけを消す（Book などの共有ノードは残る）
    try:
        with get_session() as session:
            session.run("MATCH ()-[r {participantId: $scope}]-() DELETE r", scope=scope)
            session.run("MATCH (n {participantId: $scope}) DETACH DELETE n", scope=scope)
    except Exception as e:
        logger.exception("本棚の知識グラフを消せませんでした")
        raise HTTPException(status_code=503, detail=f"知識グラフに接続できませんでした: {e}")

    for model in (ShelfDesign, MyHand, GenreTag):
        db.query(model).filter(model.participant_id == scope).delete(synchronize_session=False)
    db.delete(shelf)
    db.commit()
    return {"status": "deleted", "id": shelf_id}


# ============================================================
# 本を別の本棚へ移す
# ============================================================

class MoveBookRequest(BaseModel):
    isbn: str
    to_shelf_id: int


@router.post("/move-book")
def move_book(
    body: MoveBookRequest,
    db: Session = Depends(get_db),
    base_id: str = Depends(resolve_base_participant_id),
    source: str = Depends(resolve_participant_id),
):
    """今開いている本棚から、別の本棚へ1冊移す。移した先では、最後の本の次のマスに置く。"""
    from routers.bookshelf import _sync_chain_from_db

    target = _get_shelf(db, base_id, body.to_shelf_id).scope_id
    if target == source:
        raise HTTPException(status_code=400, detail="同じ本棚には移せません")
    layout = (
        db.query(ShelfLayout)
        .filter(ShelfLayout.participant_id == source, ShelfLayout.period == PRESENT,
                ShelfLayout.isbn == body.isbn)
        .order_by(ShelfLayout.id)
        .first()
    )
    if not layout:
        raise HTTPException(status_code=404, detail="この本棚にその本はありません")
    book = db.query(RegisteredBook).filter(RegisteredBook.isbn == body.isbn).first()
    if not book:
        raise HTTPException(status_code=404, detail="本の書誌が見つかりません")

    db.delete(layout)
    db.commit()
    if ShelfService().add_to_shelf(db, book, target, PRESENT) != "placed":
        raise HTTPException(status_code=500, detail="移した先の本棚に置けませんでした")

    # 知識グラフ: 元の本棚では所有を外し（同じ本がもう無ければ）、移した先で新しく持つ
    remaining = db.query(ShelfLayout.id).filter(
        ShelfLayout.participant_id == source, ShelfLayout.period == PRESENT, ShelfLayout.isbn == body.isbn,
    ).count()
    try:
        if remaining == 0:
            remove_book_ownership(body.isbn, participant_id=source)
        add_book_with_meaning(book, participant_id=target)
        _sync_chain_from_db(db, source)
        _sync_chain_from_db(db, target)
    except Exception as e:
        logger.warning("本棚の移動を知識グラフへ写せませんでした: %s", e)
    return {"status": "moved", "isbn": body.isbn, "to_scope_id": target}
