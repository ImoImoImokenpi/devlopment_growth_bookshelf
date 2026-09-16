"""GuessRecordのNeo4j CRUD（事前推測・事後推測・実験条件を統合した記録）。

以前は PreGuess（全体推測）と PartialGuess（部分推測）という別ノードだったが、
post_text・condition（experimental/control/transfer）を持たせるため
spec通りの単一ノード :GuessRecord に統合する。

一意性は (viewerId, ownerId, targetType)。1参加者が同じ相手の同じ対象を
複数回推測することは想定していない（試行の刺激本棚割り当ては
experiment.assignment で重複しないよう保証される）。
"""
from __future__ import annotations

from graph.main_kg.neo4j_driver import get_session

TARGET_TYPES = ("overall", "partial")
CONDITIONS = ("experimental", "control", "transfer")


def save_pre_guess(
    viewer_id: str,
    owner_id: str,
    target_type: str,
    text: str,
    condition: str,
    target_group_id: str | None = None,
    candidate_group_ids: list[str] | None = None,
) -> bool:
    """介入（差分提示）前の推測を記録する。初回のみ保存し、戻り値は新規保存できたか。
    既にあれば False を返し、呼び出し側は上書きしない（介入前の値だから意味がある）。"""
    with get_session() as session:
        existing = session.run(
            """
            MATCH (g:GuessRecord {viewerId: $viewer_id, ownerId: $owner_id, targetType: $target_type})
            RETURN g.guessId AS id
            """,
            viewer_id=viewer_id,
            owner_id=owner_id,
            target_type=target_type,
        ).single()
        if existing:
            return False
        session.run(
            """
            CREATE (g:GuessRecord {
                guessId:            randomUUID(),
                viewerId:           $viewer_id,
                ownerId:            $owner_id,
                targetType:         $target_type,
                targetGroupId:      $target_group_id,
                candidateGroupIds:  $candidate_group_ids,
                preText:            $text,
                postText:           null,
                condition:          $condition,
                createdAt:          datetime(),
                updatedAt:          datetime()
            })
            """,
            viewer_id=viewer_id,
            owner_id=owner_id,
            target_type=target_type,
            target_group_id=target_group_id,
            candidate_group_ids=candidate_group_ids,
            text=text,
            condition=condition,
        )
        return True


def save_post_guess(viewer_id: str, owner_id: str, target_type: str, text: str) -> bool:
    """事後推測を記録する。事前推測（pre_text）が無ければ保存できない
    （介入前の値を必ず経由させるため）。post_textは何度でも編集・上書きできる
    （spec3.4「pre_textを残したまま編集可能な形で再表示」に対応）。"""
    with get_session() as session:
        row = session.run(
            """
            MATCH (g:GuessRecord {viewerId: $viewer_id, ownerId: $owner_id, targetType: $target_type})
            SET g.postText = $text, g.updatedAt = datetime()
            RETURN g.guessId AS id
            """,
            viewer_id=viewer_id,
            owner_id=owner_id,
            target_type=target_type,
            text=text,
        ).single()
        return row is not None


def get_guess(viewer_id: str, owner_id: str, target_type: str) -> dict | None:
    with get_session() as session:
        row = session.run(
            """
            MATCH (g:GuessRecord {viewerId: $viewer_id, ownerId: $owner_id, targetType: $target_type})
            RETURN g.guessId AS guess_id, g.targetGroupId AS target_group_id,
                   g.candidateGroupIds AS candidate_group_ids,
                   g.preText AS pre_text, g.postText AS post_text, g.condition AS condition,
                   toString(g.createdAt) AS created_at, toString(g.updatedAt) AS updated_at
            """,
            viewer_id=viewer_id,
            owner_id=owner_id,
            target_type=target_type,
        ).single()
        return dict(row) if row else None


def list_guesses_by_viewer(viewer_id: str) -> list[dict]:
    with get_session() as session:
        rows = session.run(
            """
            MATCH (g:GuessRecord {viewerId: $viewer_id})
            RETURN g.guessId AS guess_id, g.viewerId AS viewer_id, g.ownerId AS owner_id,
                   g.targetType AS target_type, g.targetGroupId AS target_group_id,
                   g.preText AS pre_text, g.postText AS post_text, g.condition AS condition,
                   toString(g.createdAt) AS created_at, toString(g.updatedAt) AS updated_at
            ORDER BY g.createdAt ASC
            """,
            viewer_id=viewer_id,
        )
        return [dict(r) for r in rows]


def list_all_guesses() -> list[dict]:
    """研究者向けエクスポート用。全参加者分のGuessRecordを返す。"""
    with get_session() as session:
        rows = session.run(
            """
            MATCH (g:GuessRecord)
            RETURN g.guessId AS guess_id, g.viewerId AS viewer_id, g.ownerId AS owner_id,
                   g.targetType AS target_type, g.targetGroupId AS target_group_id,
                   g.preText AS pre_text, g.postText AS post_text, g.condition AS condition,
                   toString(g.createdAt) AS created_at, toString(g.updatedAt) AS updated_at
            ORDER BY g.viewerId ASC, g.createdAt ASC
            """
        )
        return [dict(r) for r in rows]
