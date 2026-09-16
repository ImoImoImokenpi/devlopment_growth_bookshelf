"""研究者向け一括エクスポート。"""
from __future__ import annotations

from graph.main_kg.neo4j_driver import get_session
from graph.uiab_experiment.identity import list_participants_with_variant
from graph.uiab_experiment import collection, layout, groups as groups_mod, events as events_mod, bigfive

PERIODS = ("period1", "period2")


def export_all() -> dict:
    """JSON版: 参加者ごとに時期別のデータをまとめてネストした形で返す。"""
    participants = list_participants_with_variant()
    result = []
    for p in participants:
        pid = p["participant_id"]
        periods_data = {}
        for period in PERIODS:
            periods_data[period] = {
                "collection":    collection.list_collection(pid, period),
                "positions":     layout.list_positions(pid, period),
                "groups":        groups_mod.list_groups(pid, period),
                "session":       layout.get_session_status(pid, period),
                "event_count":   len(events_mod.list_events(pid, period)),
            }
        result.append({
            "participant_id": pid,
            "ui_variant":      p["ui_variant"],
            "created_at":      p["created_at"],
            "bigfive":         bigfive.get_bigfive_responses(pid),
            "periods":         periods_data,
        })

    observer_rows = _list_observer_guesses_with_variant()

    return {"participants": result, "observer_guesses": observer_rows}


def export_events_flat() -> list[dict]:
    """CSV向け: 全参加者・全イベントをフラットな行のリストで返す。"""
    with get_session() as session:
        rows = session.run(
            """
            MATCH (e:UiabEvent)
            OPTIONAL MATCH (p:UiabParticipant {participantId: e.participantId})
            RETURN e.participantId AS participant_id, p.uiVariant AS ui_variant,
                   e.period AS period, e.eventType AS event_type, e.isbn AS isbn,
                   toString(e.occurredAt) AS occurred_at
            ORDER BY e.participantId, e.period, e.occurredAt
            """
        )
        return [dict(r) for r in rows]


def export_placements_flat() -> list[dict]:
    with get_session() as session:
        rows = session.run(
            """
            MATCH (s:UiabShelfPosition)-[:LOCATES]->(b:Book)
            OPTIONAL MATCH (p:UiabParticipant {participantId: s.participantId})
            RETURN s.participantId AS participant_id, p.uiVariant AS ui_variant,
                   s.period AS period, b.isbn AS isbn, b.title AS title,
                   s.shelfIndex AS shelf_index, s.xPos AS x_pos,
                   s.gridRow AS grid_row, s.gridCol AS grid_col
            ORDER BY s.participantId, s.period
            """
        )
        return [dict(r) for r in rows]


def export_self_reports_flat() -> list[dict]:
    with get_session() as session:
        rows = session.run(
            """
            MATCH (sess:UiabSession)
            OPTIONAL MATCH (p:UiabParticipant {participantId: sess.participantId})
            RETURN sess.participantId AS participant_id, p.uiVariant AS ui_variant,
                   sess.period AS period,
                   toString(sess.startedAt) AS started_at,
                   toString(sess.completedAt) AS completed_at,
                   sess.selfExpressionScore AS self_expression_score
            ORDER BY sess.participantId, sess.period
            """
        )
        return [dict(r) for r in rows]


def _list_observer_guesses_with_variant() -> list[dict]:
    with get_session() as session:
        rows = session.run(
            """
            MATCH (g:UiabObserverGuess)
            OPTIONAL MATCH (p:UiabParticipant {participantId: g.ownerId})
            RETURN g.observerId AS observer_id, g.ownerId AS owner_id,
                   p.uiVariant AS owner_ui_variant, g.ownerPeriod AS owner_period,
                   g.itemKey AS item_key, g.score AS score, g.text AS text,
                   toString(g.answeredAt) AS answered_at
            ORDER BY g.observerId, g.ownerId
            """
        )
        return [dict(r) for r in rows]


def export_observer_guesses_flat() -> list[dict]:
    return _list_observer_guesses_with_variant()
