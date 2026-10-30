"""(6) デザインとしての配置と判断できるための根拠。

metrics.compute_placement_metrics が design_intent=True と判定したとき、
「なぜそう判断したか」を一言のfactではなく、根拠となった具体的な段・本への
リンク付きでグラフに残す。EVIDENCED_BY で辿れば、判定の元になった
ShelfPosition（＝どの段の、どの並びか）まで遡れる。
"""
from __future__ import annotations

import uuid
from datetime import datetime

from graph.main_kg.neo4j_driver import get_session
from graph.placement_analysis.books import attach_titles

EVIDENCE_TYPE_LABELS = {
    "symmetry": "高さの左右対称配置",
    "rhythm": "色相の周期的な繰り返し",
    "spacing_regularity": "間隔の均一さ",
    "color_gradient": "色のグラデーション配置",
    "color_uniformity": "色を統一したパレット配置",
}


def save_design_evidence(participant_id: str, evidence_candidate: dict) -> dict:
    """evidence_candidate: metrics.compute_placement_metrics が返す
    {"evidence_type", "score", "p_value", "shelf_index", "isbns"}。
    p_value は、本の属性をスロット間でランダムに入れ替えた帰無分布に対する
    経験的p値（metrics._permutation_p_value）。小さいほど、観測された配置が
    ランダムな帰無仮説では説明しにくいことを示す。"""
    evidence_id = str(uuid.uuid4())
    computed_at = datetime.now()

    with get_session() as session:
        # 同じ段・同じ種類の根拠は最新の1件だけを残す（並べ替えのたびに増え続けないように）
        session.run(
            """
            MATCH (:Participant {participantId: $pid})-[:HAS_DESIGN_EVIDENCE]->(old:DesignEvidence)
            WHERE old.shelfIndex = $shelf_index AND old.evidenceType = $evidence_type
            DETACH DELETE old
            """,
            pid=participant_id,
            shelf_index=evidence_candidate["shelf_index"],
            evidence_type=evidence_candidate["evidence_type"],
        )
        session.run(
            """
            MATCH (p:Participant {participantId: $pid})
            CREATE (e:DesignEvidence {
                evidence_id:   $evidence_id,
                participantId: $pid,
                evidenceType:  $evidence_type,
                label:         $label,
                score:         $score,
                pValue:        $p_value,
                shelfIndex:    $shelf_index,
                computedAt:    $computed_at
            })
            MERGE (p)-[:HAS_DESIGN_EVIDENCE]->(e)
            WITH e
            UNWIND $isbns AS isbn
            MATCH (pos:ShelfPosition {participantId: $pid})-[:LOCATES]->(:Book {isbn: isbn})
            MERGE (e)-[:EVIDENCED_BY]->(pos)
            """,
            pid=participant_id,
            evidence_id=evidence_id,
            evidence_type=evidence_candidate["evidence_type"],
            label=EVIDENCE_TYPE_LABELS.get(evidence_candidate["evidence_type"], evidence_candidate["evidence_type"]),
            score=evidence_candidate["score"],
            p_value=evidence_candidate.get("p_value"),
            shelf_index=evidence_candidate["shelf_index"],
            computed_at=computed_at,
            isbns=evidence_candidate["isbns"],
        )

    result = {
        "evidence_id": evidence_id,
        "evidence_type": evidence_candidate["evidence_type"],
        "label": EVIDENCE_TYPE_LABELS.get(evidence_candidate["evidence_type"], evidence_candidate["evidence_type"]),
        "score": evidence_candidate["score"],
        "p_value": evidence_candidate.get("p_value"),
        "shelf_index": evidence_candidate["shelf_index"],
        "isbns": evidence_candidate["isbns"],
        "computed_at": computed_at.isoformat(),
    }
    return attach_titles([result])[0]


def get_design_evidence_history(participant_id: str) -> list[dict]:
    with get_session() as session:
        rows = session.run(
            """
            MATCH (:Participant {participantId: $pid})-[:HAS_DESIGN_EVIDENCE]->(e:DesignEvidence)
            OPTIONAL MATCH (e)-[:EVIDENCED_BY]->(pos:ShelfPosition)-[:LOCATES]->(b:Book)
            WITH e, collect(DISTINCT b.isbn) AS isbns
            RETURN e.evidence_id AS evidence_id, e.evidenceType AS evidence_type,
                   e.label AS label, e.score AS score, e.pValue AS p_value,
                   e.shelfIndex AS shelf_index,
                   toString(e.computedAt) AS computed_at, isbns
            ORDER BY e.computedAt DESC
            """,
            pid=participant_id,
        )
        return attach_titles([dict(r) for r in rows])
