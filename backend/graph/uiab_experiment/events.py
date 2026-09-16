"""操作ログ(RQ3)。イベント種類ごとに専用テーブルを作らず、
eventType + そのイベント固有のプロパティだけを持つノード1種類にまとめる
（Neo4jはプロパティグラフなのでノードごとにプロパティ集合を変えられる。
将来イベント種別が増えてもマイグレーションが要らない）。

集計（試行錯誤の回数・時間帯ごとの操作頻度・詳細表示の滞在時間）は
保存時には行わず、分析時にCypherで occurredAt を集計すればよい設計にしている
（PlacementProfileがShelfPositionから都度計算するのと同じ考え方）。
"""
from __future__ import annotations

from graph.main_kg.neo4j_driver import get_session

# 許可するイベント種別。フロントから任意の文字列を受け付けると分析側が
# 種類のバリエーションに振り回されるため、ここで閉じる。
EVENT_TYPES = {
    "move",               # 配置変更: isbn + extra(from/toの座標)
    "group_create",
    "group_delete",
    "impression_edit",
    "detail_view_open",   # 新UIのみ: 色・厚み調整パネルを開いた
    "detail_view_close",
}


def log_event(participant_id: str, period: str, event_type: str, isbn: str | None, extra: dict) -> None:
    if event_type not in EVENT_TYPES:
        raise ValueError(f"未知のevent_type: {event_type}")
    with get_session() as session:
        session.run(
            """
            CREATE (e:UiabEvent {
                eventId: randomUUID(), participantId: $pid, period: $period,
                eventType: $event_type, isbn: $isbn, occurredAt: datetime()
            })
            SET e += $extra
            WITH e
            MATCH (p:UiabParticipant {participantId: $pid})
            MERGE (e)-[:LOGGED_BY]->(p)
            """,
            pid=participant_id, period=period, event_type=event_type, isbn=isbn, extra=extra,
        )


def list_events(participant_id: str, period: str) -> list[dict]:
    """分析・エクスポート用の生ログ取得。"""
    with get_session() as session:
        rows = session.run(
            """
            MATCH (e:UiabEvent {participantId: $pid, period: $period})
            RETURN e { .*, occurredAt: toString(e.occurredAt) } AS event
            ORDER BY e.occurredAt
            """,
            pid=participant_id,
            period=period,
        )
        return [r["event"] for r in rows]
