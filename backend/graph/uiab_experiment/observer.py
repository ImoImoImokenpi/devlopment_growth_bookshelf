"""観察者評価(RQ2)。本棚の割当はオンデマンド(「次の1件をください」方式)にし、
研究者が事前に全員分の割当を作る必要はない。

ブラインド化: この モジュールは ui_variant を一切レスポンスに含めない。
observer.py を呼ぶルータ側も、割当・本棚データのレスポンスに
participant.uiVariant を混ぜないこと(混ぜてよいのは研究者向けの
export/管理APIだけ)。
"""
from __future__ import annotations

import random

from graph.main_kg.neo4j_driver import get_session


def get_or_create_next_trial(observer_id: str, max_trials: int = 10) -> dict | None:
    with get_session() as session:
        # 1. 未回答の割当があれば再開する
        pending = session.run(
            """
            MATCH (a:UiabObserverAssignment {observerId: $oid})
            WHERE NOT EXISTS {
                MATCH (:UiabObserverGuess {observerId: $oid, ownerId: a.ownerId, ownerPeriod: a.ownerPeriod})
            }
            RETURN a.ownerId AS owner_id, a.ownerPeriod AS owner_period, a.trialIndex AS trial_index
            ORDER BY a.trialIndex
            LIMIT 1
            """,
            oid=observer_id,
        ).single()
        if pending:
            return dict(pending)

        trial_count = session.run(
            "MATCH (a:UiabObserverAssignment {observerId: $oid}) RETURN count(a) AS n",
            oid=observer_id,
        ).single()["n"]
        if trial_count >= max_trials:
            return None

        assigned_owner_ids = [
            r["ownerId"] for r in session.run(
                "MATCH (a:UiabObserverAssignment {observerId: $oid}) RETURN a.ownerId AS ownerId",
                oid=observer_id,
            )
        ]

        # このobserverがこれまで見た群の内訳（新UI/旧UIを均等に見せるための調整）
        seen_variants = [
            r["v"] for r in session.run(
                """
                MATCH (a:UiabObserverAssignment {observerId: $oid})
                MATCH (p:UiabParticipant {participantId: a.ownerId})
                RETURN p.uiVariant AS v
                """,
                oid=observer_id,
            )
        ]
        new_count, old_count = seen_variants.count("new"), seen_variants.count("old")
        preferred_variant = "old" if new_count > old_count else ("new" if old_count > new_count else None)

        candidates = session.run(
            """
            MATCH (sess:UiabSession {period: 'period2'})
            WHERE sess.completedAt IS NOT NULL AND NOT sess.participantId IN $excluded
            MATCH (p:UiabParticipant {participantId: sess.participantId})
            OPTIONAL MATCH (existing:UiabObserverAssignment {ownerId: p.participantId})
            WITH p, count(existing) AS assigned_count
            RETURN p.participantId AS owner_id, p.uiVariant AS ui_variant, assigned_count
            """,
            excluded=assigned_owner_ids,
        ).data()

        if not candidates:
            return None

        pool = candidates
        if preferred_variant:
            filtered = [c for c in candidates if c["ui_variant"] == preferred_variant]
            if filtered:
                pool = filtered

        min_assigned = min(c["assigned_count"] for c in pool)
        pool = [c for c in pool if c["assigned_count"] == min_assigned]
        chosen = random.choice(pool)

        session.run(
            """
            CREATE (a:UiabObserverAssignment {
                observerId: $oid, ownerId: $owner_id, ownerPeriod: 'period2',
                trialIndex: $trial_index, assignedAt: datetime()
            })
            """,
            oid=observer_id, owner_id=chosen["owner_id"], trial_index=trial_count,
        )
        return {"owner_id": chosen["owner_id"], "owner_period": "period2", "trial_index": trial_count}


def save_guess(observer_id: str, owner_id: str, owner_period: str, item_key: str, score: int | None, text: str | None) -> None:
    with get_session() as session:
        session.run(
            """
            MERGE (g:UiabObserverGuess {
                observerId: $oid, ownerId: $owner_id, ownerPeriod: $owner_period, itemKey: $item_key
            })
            ON CREATE SET g.guessId = randomUUID()
            SET g.score = $score, g.text = $text, g.answeredAt = datetime()
            """,
            oid=observer_id, owner_id=owner_id, owner_period=owner_period,
            item_key=item_key, score=score, text=text,
        )


def list_guesses_for_trial(observer_id: str, owner_id: str, owner_period: str) -> list[dict]:
    with get_session() as session:
        rows = session.run(
            """
            MATCH (g:UiabObserverGuess {observerId: $oid, ownerId: $owner_id, ownerPeriod: $owner_period})
            RETURN g.itemKey AS item_key, g.score AS score, g.text AS text
            """,
            oid=observer_id, owner_id=owner_id, owner_period=owner_period,
        )
        return [dict(r) for r in rows]
