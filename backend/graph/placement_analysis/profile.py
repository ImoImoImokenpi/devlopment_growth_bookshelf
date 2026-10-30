"""PlacementProfileの計算・保存・履歴読み出し。

保存のたびに古いものを消し、参加者ごとに最新の1件だけを残す。

1回の呼び出しで:
  1. enrich_positions        … ShelfPosition/SHELF_NEXTへ派生プロパティを書く (1,2,3)
  2. compute_placement_metrics … 指標一式とデザイン根拠候補を計算する (1,2,4,6)
  3. design_intentがTrueなら DesignEvidence を保存する (6)
  4. PlacementProfileを追記保存する
まで一括で行う。「配置完了イベント」（/bookshelf/sync-layout）のたびに呼ぶ想定。
"""
from __future__ import annotations

import uuid
from datetime import datetime

from graph.main_kg.neo4j_driver import get_session
from graph.placement_analysis.enrich import enrich_positions
from graph.placement_analysis.metrics import compute_placement_metrics
from graph.placement_analysis.evidence import save_design_evidence

_PROFILE_FIELDS = [
    "book_count",
    "height_order_score",
    "height_staircase_score",
    "row_height_trend_score",
    "height_group_order_score",
    "height_grouping_score",
    "color_grouping_score",
    "color_gradient_score",
    "color_uniformity_score",
    "author_grouping_score",
    "genre_placement_modularity",
    "genre_placement_nmi",
    "theme_placement_modularity",
    "theme_placement_nmi",
    "concept_placement_modularity",
    "concept_placement_nmi",
    "symmetry_score",
    "rhythm_score",
    "spacing_regularity",
    "design_intent",
]


def compute_and_save_placement_profile(participant_id: str) -> dict:
    enrich_positions(participant_id)
    metrics = compute_placement_metrics(participant_id)

    evidence = None
    if metrics.get("design_intent") and metrics.get("evidence_candidate"):
        evidence = save_design_evidence(participant_id, metrics["evidence_candidate"])

    profile_id = str(uuid.uuid4())
    computed_at = datetime.now()

    with get_session() as session:
        session.run(
            """
            MATCH (p:Participant {participantId: $pid})
            CREATE (pp:PlacementProfile {
                profile_id: $profile_id,
                participantId: $pid,
                book_count: $book_count,
                height_order_score: $height_order_score,
                height_staircase_score: $height_staircase_score,
                row_height_trend_score: $row_height_trend_score,
                height_group_order_score: $height_group_order_score,
                height_grouping_score: $height_grouping_score,
                color_grouping_score: $color_grouping_score,
                color_gradient_score: $color_gradient_score,
                color_uniformity_score: $color_uniformity_score,
                author_grouping_score: $author_grouping_score,
                genre_placement_modularity: $genre_placement_modularity,
                genre_placement_nmi: $genre_placement_nmi,
                theme_placement_modularity: $theme_placement_modularity,
                theme_placement_nmi: $theme_placement_nmi,
                concept_placement_modularity: $concept_placement_modularity,
                concept_placement_nmi: $concept_placement_nmi,
                symmetry_score: $symmetry_score,
                rhythm_score: $rhythm_score,
                spacing_regularity: $spacing_regularity,
                design_intent: $design_intent,
                computed_at: $computed_at
            })
            MERGE (p)-[:HAS_PLACEMENT_PROFILE]->(pp)
            // 履歴は持たず、最新の1件だけを残す（並べ替えのたびに増え続けないように）
            WITH p, pp
            OPTIONAL MATCH (p)-[:HAS_PLACEMENT_PROFILE]->(old:PlacementProfile)
            WHERE old <> pp
            DETACH DELETE old
            """,
            pid=participant_id,
            profile_id=profile_id,
            computed_at=computed_at,
            **{k: metrics.get(k) for k in _PROFILE_FIELDS},
        )

    result = {k: metrics.get(k) for k in _PROFILE_FIELDS}
    result["profile_id"] = profile_id
    result["participant_id"] = participant_id
    result["computed_at"] = computed_at.isoformat()
    result["design_evidence"] = evidence
    return result


def get_latest_placement_profile(participant_id: str) -> dict | None:
    with get_session() as session:
        row = session.run(
            """
            MATCH (:Participant {participantId: $pid})-[:HAS_PLACEMENT_PROFILE]->(pp:PlacementProfile)
            RETURN pp
            ORDER BY pp.computed_at DESC
            LIMIT 1
            """,
            pid=participant_id,
        ).single()
        if not row:
            return None
        profile = dict(row["pp"])
        if profile.get("computed_at") is not None:
            profile["computed_at"] = str(profile["computed_at"])
        return profile


def get_placement_profile_history(participant_id: str) -> list[dict]:
    with get_session() as session:
        rows = session.run(
            """
            MATCH (:Participant {participantId: $pid})-[:HAS_PLACEMENT_PROFILE]->(pp:PlacementProfile)
            RETURN pp
            ORDER BY pp.computed_at ASC
            """,
            pid=participant_id,
        )
        profiles = []
        for r in rows:
            profile = dict(r["pp"])
            if profile.get("computed_at") is not None:
                profile["computed_at"] = str(profile["computed_at"])
            profiles.append(profile)
        return profiles
