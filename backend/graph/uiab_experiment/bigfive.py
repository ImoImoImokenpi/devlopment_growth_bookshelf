"""ビッグファイブ簡易尺度(TIPI-J相当、10項目・1回のみ)。

項目文言は別途確定とのことなので、ここではitem_keyの器だけ用意する
（10項目 x 5特性 x 逆転項目1つずつ、というTIPIの標準構成を想定した仮のキー）。
"""
from __future__ import annotations

from graph.main_kg.neo4j_driver import get_session

BIGFIVE_ITEM_KEYS = [
    "extraversion_1", "extraversion_2_r",
    "agreeableness_1_r", "agreeableness_2",
    "conscientiousness_1", "conscientiousness_2_r",
    "neuroticism_1", "neuroticism_2_r",
    "openness_1", "openness_2_r",
]


def save_bigfive_responses(participant_id: str, answers: dict[str, int]) -> None:
    unknown = set(answers) - set(BIGFIVE_ITEM_KEYS)
    if unknown:
        raise ValueError(f"未知のitem_key: {sorted(unknown)}")
    with get_session() as session:
        for item_key, score in answers.items():
            session.run(
                """
                MERGE (b:UiabBigFiveResponse {participantId: $pid, itemKey: $item_key})
                    ON CREATE SET b.answeredAt = datetime()
                SET b.score = $score
                WITH b
                MATCH (p:UiabParticipant {participantId: $pid})
                MERGE (b)-[:ANSWERED_BY]->(p)
                """,
                pid=participant_id, item_key=item_key, score=score,
            )


def get_bigfive_responses(participant_id: str) -> dict[str, int]:
    with get_session() as session:
        rows = session.run(
            "MATCH (b:UiabBigFiveResponse {participantId: $pid}) RETURN b.itemKey AS item_key, b.score AS score",
            pid=participant_id,
        )
        return {r["item_key"]: r["score"] for r in rows}
