"""配置分析（どう並べているか）と内容分析（何が意味的にまとまっているか）を
組み合わせた分析。

theme_placement_modularity/concept_placement_modularity（PlacementProfile）は
「参加者全体として内容と配置がどれだけ一致しているか」を1つの数字にまとめて
しまうため、「このテーマはきっちり物理的にもまとめているが、こちらは色や
高さを優先して分散させている」という参加者内の偏りが分からない。

ここではテーマ・意味づけの単位まで分解し、それぞれについて
  - clustering_rate: そのグループの本のうち、同じグループの本と隣接して
    いる本の割合（1.0に近いほど物理的にひとまとまりに置かれている）
  - shelves_used: そのグループの本が何段に分かれて置かれているか
    （少ないほど1箇所にまとまっている）
を計算する。
"""
from __future__ import annotations

from graph.main_kg.neo4j_driver import get_session
from graph.placement_analysis.themes import get_theme_summary
from graph.placement_analysis.books import attach_titles


def _fetch_concept_groups(participant_id: str) -> list[dict]:
    with get_session() as session:
        rows = session.run(
            """
            MATCH (:Participant {participantId: $pid})-[:OWNS]->(b:Book)
                  -[:CONCEPT {participantId: $pid}]->(c:Concept {participantId: $pid})
            RETURN c.text AS name, collect(DISTINCT b.isbn) AS isbns
            """,
            pid=participant_id,
        ).data()
        return [{"name": r["name"], "isbns": r["isbns"]} for r in rows if r["name"]]


def _fetch_positions_and_adjacency(participant_id: str) -> tuple[dict[str, int], set[frozenset]]:
    with get_session() as session:
        positions = {
            r["isbn"]: r["shelf_index"]
            for r in session.run(
                """
                MATCH (:Participant {participantId: $pid})-[:OWNS]->(b:Book)
                      <-[:LOCATES]-(pos:ShelfPosition {participantId: $pid})
                RETURN b.isbn AS isbn, pos.shelfIndex AS shelf_index
                """,
                pid=participant_id,
            ).data()
        }
        adjacency = {
            frozenset((r["a"], r["b"]))
            for r in session.run(
                """
                MATCH (a:Book)-[:SHELF_NEXT {participantId: $pid, isCurrent: true}]-(b:Book)
                RETURN a.isbn AS a, b.isbn AS b
                """,
                pid=participant_id,
            )
        }
        return positions, adjacency


def _breakdown(groups: list[dict], positions: dict[str, int], adjacency: set[frozenset]) -> list[dict]:
    result = []
    for g in groups:
        isbns = [isbn for isbn in g["isbns"] if isbn in positions]
        n = len(isbns)
        if n < 2:
            continue
        isbn_set = set(isbns)
        adjacent_count = sum(
            1 for isbn in isbns
            if any(frozenset((isbn, other)) in adjacency for other in isbn_set if other != isbn)
        )
        result.append({
            "name": g["name"],
            "book_count": n,
            "clustering_rate": round(adjacent_count / n, 4),
            "shelves_used": len({positions[isbn] for isbn in isbns}),
            "isbns": isbns,
        })
    result.sort(key=lambda x: -x["clustering_rate"])
    return attach_titles(result)


def compute_content_alignment(participant_id: str) -> dict:
    """テーマ・意味づけそれぞれについて、物理的なまとまり具合を個別に見る。
    themes.generate_book_themesを一度も呼んでいなければthemesは空配列になる。"""
    positions, adjacency = _fetch_positions_and_adjacency(participant_id)

    themes = get_theme_summary(participant_id)
    theme_breakdown = _breakdown(themes, positions, adjacency)

    concepts = _fetch_concept_groups(participant_id)
    concept_breakdown = _breakdown(concepts, positions, adjacency)

    return {"themes": theme_breakdown, "concepts": concept_breakdown}
