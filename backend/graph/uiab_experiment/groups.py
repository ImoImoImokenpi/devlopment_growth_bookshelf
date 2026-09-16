"""グルーピング・感想。新UI/旧UIで機能を揃えるため、両UI共通の実装にする。"""
from __future__ import annotations

import uuid

from graph.main_kg.neo4j_driver import get_session


def create_group(participant_id: str, period: str, label: str, isbns: list[str]) -> str:
    group_id = str(uuid.uuid4())
    with get_session() as session:
        session.run(
            """
            CREATE (g:UiabGroup {
                groupId: $group_id, participantId: $pid, period: $period,
                label: $label, createdAt: datetime()
            })
            WITH g
            UNWIND $isbns AS isbn
            MATCH (b:Book {isbn: isbn})
            MERGE (b)-[:UIAB_GROUPED {participantId: $pid, period: $period}]->(g)
            """,
            group_id=group_id, pid=participant_id, period=period, label=label, isbns=isbns,
        )
    return group_id


def delete_group(group_id: str, participant_id: str) -> bool:
    with get_session() as session:
        row = session.run(
            """
            MATCH (g:UiabGroup {groupId: $gid, participantId: $pid})
            DETACH DELETE g
            RETURN true AS ok
            """,
            gid=group_id,
            pid=participant_id,
        ).single()
        return row is not None


def list_groups(participant_id: str, period: str) -> list[dict]:
    with get_session() as session:
        rows = session.run(
            """
            MATCH (b:Book)-[:UIAB_GROUPED {participantId: $pid, period: $period}]->(g:UiabGroup)
            WITH g, collect({isbn: b.isbn, title: b.title}) AS members
            RETURN g.groupId AS group_id, g.label AS label, members
            ORDER BY g.createdAt
            """,
            pid=participant_id,
            period=period,
        )
        return [dict(r) for r in rows]


def save_impression(participant_id: str, period: str, isbn: str, text: str) -> None:
    with get_session() as session:
        latest = session.run(
            """
            MATCH (:Book {isbn: $isbn})-[:HAS_UIAB_IMPRESSION]->(i:UiabImpression {participantId: $pid, period: $period})
            RETURN i.text AS text
            ORDER BY i.createdAt DESC
            LIMIT 1
            """,
            isbn=isbn, pid=participant_id, period=period,
        ).single()
        if latest and (latest["text"] or "") == (text or ""):
            return

        session.run(
            """
            MATCH (b:Book {isbn: $isbn})
            CREATE (i:UiabImpression {
                impressionId: randomUUID(), participantId: $pid, period: $period,
                isbn: $isbn, text: $text, createdAt: datetime()
            })
            MERGE (b)-[:HAS_UIAB_IMPRESSION]->(i)
            """,
            isbn=isbn, pid=participant_id, period=period, text=text,
        )


def get_latest_impression(participant_id: str, period: str, isbn: str) -> str:
    with get_session() as session:
        row = session.run(
            """
            MATCH (:Book {isbn: $isbn})-[:HAS_UIAB_IMPRESSION]->(i:UiabImpression {participantId: $pid, period: $period})
            RETURN i.text AS text
            ORDER BY i.createdAt DESC
            LIMIT 1
            """,
            isbn=isbn, pid=participant_id, period=period,
        ).single()
        return row["text"] if row else ""
