"""(1)(2)(3) の下地: ShelfPositionとSHELF_NEXTに軸別の派生プロパティを書き込む。

update_shelf_layout_chain（配置同期）の後に呼ぶ想定。以後の指標計算
（metrics.py）・浮いている本の判定（isolation.py）はここで書いたプロパティ
だけを読めばよく、都度Book本体まで遡らずに済む。

参加者間で共有されている Book/Author/NDC ノードは一切書き換えず、
書き込み先は常に participantId を持つ ShelfPosition・SHELF_NEXT に限る。
"""
from __future__ import annotations

from graph.main_kg.neo4j_driver import get_session
from graph.placement_analysis.authors import author_group_key
from utils.shelf_pattern_analysis import color_hue_bucket, hue_angle

HEIGHT_BUCKET_COUNT = 5


def _height_bucket_assigner(height_values: list[float]):
    """参加者本人の蔵書内での相対的な高さ分位で5段階に離散化する
    （絶対mmでバケット化すると、小さい本ばかりの人・大きい本ばかりの人で
    バケットが偏ってしまうため）。"""
    values = sorted(v for v in height_values if v is not None)
    if len(values) < HEIGHT_BUCKET_COUNT:
        # データが少なければ意味のある分位ができないため、全冊同一バケットにする
        return lambda h: 0

    def bucket(h: float | None) -> int | None:
        if h is None:
            return None
        rank = sum(1 for v in values if v <= h) / len(values)
        return min(HEIGHT_BUCKET_COUNT - 1, int(rank * HEIGHT_BUCKET_COUNT))

    return bucket


def enrich_positions(participant_id: str) -> dict:
    """その参加者の現在のShelfPosition・SHELF_NEXTに、高さ・色・ジャンル・著者の
    派生プロパティを書き込む。戻り値は更新件数のサマリ。"""
    with get_session() as session:
        rows = session.run(
            """
            MATCH (:Participant {participantId: $pid})-[:OWNS]->(b:Book)
                  <-[:LOCATES]-(pos:ShelfPosition {participantId: $pid})
            OPTIONAL MATCH (b)-[:WRITTEN_BY]->(a:Author)
            OPTIONAL MATCH (b)-[:CLASSIFIED_AS]->(:NDC)-[:BROADER*0..6]->(l1:NDC {level: 1})
            RETURN pos.posId AS pos_id, b.isbn AS isbn, b.height_mm AS height_mm,
                   b.spine_color AS spine_color,
                   collect(DISTINCT {name: a.name, canonical: a.canonicalName})[0] AS author,
                   head(collect(DISTINCT l1.code)) AS ndc_l1
            """,
            pid=participant_id,
        ).data()

        if not rows:
            return {"positions_updated": 0, "edges_updated": 0}

        bucketer = _height_bucket_assigner([r["height_mm"] for r in rows])

        updates = []
        for r in rows:
            author = r["author"] or {}
            updates.append({
                "pos_id": r["pos_id"],
                "height_bucket": bucketer(r["height_mm"]),
                "color_hue": color_hue_bucket(r["spine_color"]),
                "hue_angle": hue_angle(r["spine_color"]),
                "ndc_l1": r["ndc_l1"],
                "author_norm": author_group_key(author.get("canonical"), author.get("name")),
            })

        session.run(
            """
            UNWIND $rows AS row
            MATCH (pos:ShelfPosition {posId: row.pos_id})
            SET pos.heightBucket = row.height_bucket,
                pos.colorHue     = row.color_hue,
                pos.hueAngle     = row.hue_angle,
                pos.ndcL1Cached  = row.ndc_l1,
                pos.authorNorm   = row.author_norm
            """,
            rows=updates,
        )

        edge_result = session.run(
            """
            MATCH (a:Book)-[r:SHELF_NEXT {participantId: $pid, isCurrent: true}]->(b:Book)
            MATCH (posA:ShelfPosition {participantId: $pid})-[:LOCATES]->(a)
            MATCH (posB:ShelfPosition {participantId: $pid})-[:LOCATES]->(b)
            SET r.heightSimilar = (posA.heightBucket IS NOT NULL AND posA.heightBucket = posB.heightBucket),
                r.colorSimilar  = (posA.colorHue IS NOT NULL AND posA.colorHue = posB.colorHue),
                r.genreSame     = (posA.ndcL1Cached IS NOT NULL AND posA.ndcL1Cached = posB.ndcL1Cached),
                r.authorSame    = (posA.authorNorm IS NOT NULL AND posA.authorNorm = posB.authorNorm)
            RETURN count(r) AS updated
            """,
            pid=participant_id,
        ).single()

        return {
            "positions_updated": len(updates),
            "edges_updated": edge_result["updated"] if edge_result else 0,
        }
