"""(5) 知識グラフ上で孤立している本の検出。

「孤立」を単一の真偽値にせず、意味の異なる4種類のフラグに分ける:
  - topological_isolated: 知識グラフ全体（意味づけ・著者・出版社・NDC・本棚隣接）
    のどの関係でも他の本とつながっていない（既存の analyze_book_network を再利用）
  - semantic_isolated: 意味づけ(Concept)を誰とも共有していない
  - physical_isolated: 本棚の同じ段に他の本が1冊もない（既存のShelfPosition.isIsolated）
  - floating: 隣（SHELF_NEXT）はあるが、高さ・色・ジャンル・著者のどの軸でも
    共通点がない（enrich_positions が書き込んだ類似度フラグを使う）

topological/physical はそれぞれ既存の実装（network_analysis / ShelfPosition）を
そのまま使い、ここで新しく計算し直さない。
"""
from __future__ import annotations

from graph.main_kg.neo4j_driver import get_session
from graph.main_kg.neo4j_crud import get_graph_overview, get_book_edges
from utils.network_analysis import analyze_book_network


def compute_isolation(participant_id: str) -> list[dict]:
    overview = get_graph_overview(participant_id)
    all_isbns = [b["isbn"] for b in overview["book_catalog"]]
    if not all_isbns:
        return []
    title_by_isbn = {b["isbn"]: b.get("title") for b in overview["book_catalog"]}

    edges = get_book_edges(participant_id)
    network = analyze_book_network(nodes=overview["book_catalog"], edges=edges)
    topological_isolated_isbns = {b["isbn"] for b in network["isolated_books"]}

    with get_session() as session:
        semantic_isolated_isbns = {
            r["isbn"]
            for r in session.run(
                """
                MATCH (:Participant {participantId: $pid})-[:OWNS]->(b:Book)
                WHERE NOT (b)-[:CONCEPT {participantId: $pid}]-()
                RETURN b.isbn AS isbn
                """,
                pid=participant_id,
            ).data()
        }

        physical_isolated_isbns = {
            r["isbn"]
            for r in session.run(
                """
                MATCH (:Participant {participantId: $pid})-[:OWNS]->(b:Book)
                      <-[:LOCATES]-(pos:ShelfPosition {participantId: $pid})
                WHERE pos.isIsolated = true
                RETURN b.isbn AS isbn
                """,
                pid=participant_id,
            ).data()
        }

        floating_isbns = {
            r["isbn"]
            for r in session.run(
                """
                MATCH (:Participant {participantId: $pid})-[:OWNS]->(b:Book)
                MATCH (b)-[r:SHELF_NEXT {participantId: $pid, isCurrent: true}]-(:Book)
                WITH b, collect(r) AS rels
                WHERE all(rel IN rels WHERE
                    coalesce(rel.heightSimilar, false) = false AND
                    coalesce(rel.colorSimilar, false)  = false AND
                    coalesce(rel.genreSame, false)     = false AND
                    coalesce(rel.authorSame, false)    = false)
                RETURN b.isbn AS isbn
                """,
                pid=participant_id,
            ).data()
        }

    return [
        {
            "isbn": isbn,
            "title": title_by_isbn.get(isbn) or isbn,
            "topological_isolated": isbn in topological_isolated_isbns,
            "semantic_isolated": isbn in semantic_isolated_isbns,
            "physical_isolated": isbn in physical_isolated_isbns,
            "floating": isbn in floating_isbns,
        }
        for isbn in sorted(all_isbns)
    ]


def summarize_isolation(records: list[dict]) -> dict:
    total = len(records)
    return {
        "book_count": total,
        "topological_isolated_count": sum(1 for r in records if r["topological_isolated"]),
        "semantic_isolated_count": sum(1 for r in records if r["semantic_isolated"]),
        "physical_isolated_count": sum(1 for r in records if r["physical_isolated"]),
        "floating_count": sum(1 for r in records if r["floating"]),
    }
