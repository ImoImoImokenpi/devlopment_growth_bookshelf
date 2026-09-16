"""配置(新UI=自由座標／旧UI=グリッド)・作業セッション・自分らしさ評定。

新UI/旧UIで使うフィールドが違うだけで、ShelfPositionは1種類にまとめている
（時期をまたいだ編集距離の計算(RQ3)で同じ形のデータを扱えるようにするため）。
"""
from __future__ import annotations

from graph.main_kg.neo4j_driver import get_session


def upsert_position(
    participant_id: str,
    period: str,
    isbn: str,
    *,
    shelf_index: int | None = None,
    x_pos: float | None = None,
    grid_row: int | None = None,
    grid_col: int | None = None,
) -> None:
    pos_id = f"{participant_id}:{period}:{isbn}"
    with get_session() as session:
        session.run(
            """
            MERGE (s:UiabShelfPosition {posId: $pos_id})
            SET
                s.participantId = $pid,
                s.period        = $period,
                s.shelfIndex    = $shelf_index,
                s.xPos          = $x_pos,
                s.gridRow       = $grid_row,
                s.gridCol       = $grid_col,
                s.updatedAt     = datetime()
            WITH s
            MATCH (b:Book {isbn: $isbn})
            MERGE (s)-[:LOCATES]->(b)
            """,
            pos_id=pos_id, pid=participant_id, period=period, isbn=isbn,
            shelf_index=shelf_index, x_pos=x_pos, grid_row=grid_row, grid_col=grid_col,
        )


def remove_position(participant_id: str, period: str, isbn: str) -> None:
    pos_id = f"{participant_id}:{period}:{isbn}"
    with get_session() as session:
        session.run("MATCH (s:UiabShelfPosition {posId: $pos_id}) DETACH DELETE s", pos_id=pos_id)


def list_positions(participant_id: str, period: str) -> list[dict]:
    with get_session() as session:
        rows = session.run(
            """
            MATCH (s:UiabShelfPosition {participantId: $pid, period: $period})-[:LOCATES]->(b:Book)
            RETURN b.isbn AS isbn, b.title AS title, b.authors AS authors,
                   b.height_mm AS height_mm, b.pages AS pages, b.spine_color AS spine_color,
                   s.shelfIndex AS shelf_index, s.xPos AS x_pos,
                   s.gridRow AS grid_row, s.gridCol AS grid_col
            ORDER BY s.shelfIndex, s.xPos, s.gridRow, s.gridCol
            """,
            pid=participant_id,
            period=period,
        )
        return [dict(r) for r in rows]


# ── 作業セッション(開始/完了・作業時間・自分らしさ評定) ──────────────

def start_session(participant_id: str, period: str) -> None:
    with get_session() as session:
        session.run(
            """
            MERGE (sess:UiabSession {participantId: $pid, period: $period})
                ON CREATE SET sess.startedAt = datetime()
            """,
            pid=participant_id,
            period=period,
        )


def complete_session(participant_id: str, period: str) -> None:
    with get_session() as session:
        session.run(
            """
            MERGE (sess:UiabSession {participantId: $pid, period: $period})
                ON CREATE SET sess.startedAt = datetime()
            SET sess.completedAt = datetime()
            """,
            pid=participant_id,
            period=period,
        )


def save_self_expression_rating(participant_id: str, period: str, score: int) -> None:
    with get_session() as session:
        session.run(
            """
            MERGE (sess:UiabSession {participantId: $pid, period: $period})
                ON CREATE SET sess.startedAt = datetime()
            SET sess.selfExpressionScore = $score,
                sess.selfExpressionAnsweredAt = datetime()
            """,
            pid=participant_id,
            period=period,
            score=score,
        )


def get_session_status(participant_id: str, period: str) -> dict | None:
    with get_session() as session:
        row = session.run(
            """
            MATCH (sess:UiabSession {participantId: $pid, period: $period})
            RETURN toString(sess.startedAt) AS started_at,
                   toString(sess.completedAt) AS completed_at,
                   sess.selfExpressionScore AS self_expression_score
            """,
            pid=participant_id,
            period=period,
        ).single()
        return dict(row) if row else None
