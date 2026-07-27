"""NetworkXを使った蔵書ナレッジグラフの構造分析。

Neo4jから取得した Book-Book の関係(共通の意味づけ・著者・出版社・NDC分類・
本棚での隣接)を無向グラフとして構築し、ハブとなる本・コミュニティ(クラスタ)・
橋渡し役の本・孤立した本を抽出する。
"""
from __future__ import annotations

import networkx as nx


def analyze_book_network(nodes: list[dict], edges: list[dict], top_n: int = 5) -> dict:
    """
    nodes: [{"isbn": str, "title": str, ...}, ...]  グラフに含める全ての本
    edges: [{"source": isbn, "target": isbn, "type": "concept"|"author"|"publisher"|"ndc"|"shelf"}, ...]
    """
    graph = nx.Graph()
    title_map: dict[str, str] = {}

    for node in nodes:
        isbn = node.get("isbn")
        if not isbn:
            continue
        title_map[isbn] = node.get("title") or isbn
        graph.add_node(isbn)

    for edge in edges:
        src, tgt = edge.get("source"), edge.get("target")
        if not src or not tgt or src == tgt or src not in graph or tgt not in graph:
            continue
        if graph.has_edge(src, tgt):
            graph[src][tgt]["weight"] += 1
            graph[src][tgt]["types"].add(edge.get("type"))
        else:
            graph.add_edge(src, tgt, weight=1, types={edge.get("type")})

    def _book(isbn: str, extra: dict | None = None) -> dict:
        item = {"isbn": isbn, "title": title_map.get(isbn, isbn)}
        if extra:
            item.update(extra)
        return item

    num_nodes = graph.number_of_nodes()
    num_edges = graph.number_of_edges()

    if num_nodes == 0:
        return {
            "graph_stats": {"num_nodes": 0, "num_edges": 0, "num_components": 0, "density": 0.0},
            "hub_books": [],
            "communities": [],
            "bridge_books": [],
            "isolated_books": [],
        }

    degree_centrality = nx.degree_centrality(graph)
    betweenness = nx.betweenness_centrality(graph) if num_nodes > 2 else {n: 0.0 for n in graph.nodes}

    hub_books = sorted(
        (
            _book(isbn, {
                "degree_centrality": round(degree_centrality.get(isbn, 0.0), 4),
                "betweenness_centrality": round(betweenness.get(isbn, 0.0), 4),
            })
            for isbn in graph.nodes if graph.degree(isbn) > 0
        ),
        key=lambda item: (item["degree_centrality"], item["betweenness_centrality"]),
        reverse=True,
    )[:top_n]

    isolated_books = [_book(isbn) for isbn in graph.nodes if graph.degree(isbn) == 0]

    components = list(nx.connected_components(graph))

    try:
        raw_communities = list(nx.algorithms.community.greedy_modularity_communities(graph, weight="weight"))
    except Exception:
        raw_communities = components

    communities = [
        {"id": i, "size": len(community), "books": [_book(isbn) for isbn in sorted(community)]}
        for i, community in enumerate(raw_communities)
        if len(community) >= 2
    ]
    communities.sort(key=lambda c: -c["size"])

    try:
        bridge_isbns = list(nx.articulation_points(graph))
    except Exception:
        bridge_isbns = []

    return {
        "graph_stats": {
            "num_nodes": num_nodes,
            "num_edges": num_edges,
            "num_components": len(components),
            "density": round(nx.density(graph), 4),
        },
        "hub_books": hub_books,
        "communities": communities[:10],
        "bridge_books": [_book(isbn) for isbn in bridge_isbns],
        "isolated_books": isolated_books[:15],
    }
