"""「他の参加者の本棚を観察する」画面の一覧表示用。

被験者ごとのデータそのものは participant.py のヘッダ経由で分離されているが、
一覧画面には「どんな参加者がいて、何冊くらい並んでいるか」を一目で示す
軽量なサマリーが要る。ここでは書き込みは一切行わない。
"""
from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from database import get_db
from models import ShelfLayout
from participant import ALL_PARTICIPANT_IDS, PROTOTYPE_PARTICIPANT_ID

router = APIRouter(prefix="/participants", tags=["participants"])


@router.get("/")
def list_participants(db: Session = Depends(get_db)):
    counts = dict(
        db.query(ShelfLayout.participant_id, func.count(ShelfLayout.id))
        .group_by(ShelfLayout.participant_id)
        .all()
    )
    return {
        "participants": [
            {
                "participant_id": pid,
                "is_prototype": pid == PROTOTYPE_PARTICIPANT_ID,
                "total_books": counts.get(pid, 0),
            }
            for pid in ALL_PARTICIPANT_IDS
        ]
    }
