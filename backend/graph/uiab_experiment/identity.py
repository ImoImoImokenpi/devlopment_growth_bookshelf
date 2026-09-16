"""参加者の新UI/旧UI群への割り付け、観察者ノードの確保。

割り付けは「初めてこのIDでアクセスしたとき」に1回だけランダムに決め、
以降は同じ値を返す(MERGE ... ON CREATE SET)。参加者本人向けのAPIレスポンスは
このモジュールを呼ぶ側が uiVariant を含めるかどうかを選べるが、観察者向け
エンドポイントからは絶対に呼ばない・含めないこと(ブラインド化の要）。
"""
from __future__ import annotations

import random

from graph.main_kg.neo4j_driver import get_session

_VARIANTS = ["new", "old"]


def get_or_assign_ui_variant(participant_id: str) -> str:
    """このparticipant_idが初めてなら "new"/"old" をランダムに割り付けて返す。
    既に割り付け済みなら、その値をそのまま返す(呼ぶたびに変わらない)。"""
    variant = random.choice(_VARIANTS)
    with get_session() as session:
        row = session.run(
            """
            MERGE (p:UiabParticipant {participantId: $pid})
                ON CREATE SET p.uiVariant = $variant, p.createdAt = datetime()
            RETURN p.uiVariant AS uiVariant
            """,
            pid=participant_id,
            variant=variant,
        ).single()
        return row["uiVariant"]


def ensure_observer(observer_id: str) -> None:
    with get_session() as session:
        session.run(
            """
            MERGE (o:UiabObserver {observerId: $oid})
                ON CREATE SET o.createdAt = datetime()
            """,
            oid=observer_id,
        )


def list_participants_with_variant() -> list[dict]:
    """研究者向け：参加者IDと群の対応一覧（分析用。参加者本人には見せない）。"""
    with get_session() as session:
        rows = session.run(
            """
            MATCH (p:UiabParticipant)
            RETURN p.participantId AS participant_id, p.uiVariant AS ui_variant,
                   toString(p.createdAt) AS created_at
            ORDER BY p.participantId
            """
        )
        return [dict(r) for r in rows]
