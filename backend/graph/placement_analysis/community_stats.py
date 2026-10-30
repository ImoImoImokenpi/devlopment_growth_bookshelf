"""配置分析で使う、まとまり具合の計算（モジュラリティ・正規化相互情報量）。

以前は投影スタイル分析（graph/style_projection/metrics.py）にあったものを、
投影スタイル分析の削除に合わせてここへ移した。
"""
from __future__ import annotations

import math
from collections import Counter

import networkx as nx


def modularity_for_communities(graph: nx.Graph, community: dict[str, str]) -> float:
    """ノード→グループの割り当て(community)が、グラフのつながりとどれだけ一致するか。"""
    if graph.number_of_edges() == 0:
        return 0.0
    groups: dict[str, set] = {}
    for node in graph.nodes:
        groups.setdefault(community.get(node, node), set()).add(node)
    partition = [nodes for nodes in groups.values() if nodes]
    try:
        return float(nx.algorithms.community.quality.modularity(graph, partition))
    except (ZeroDivisionError, ValueError):
        return 0.0


def normalized_mutual_information(labels_a: list, labels_b: list) -> float:
    """正規化相互情報量。scikit-learnを追加依存させず素朴に実装する。"""
    n = len(labels_a)
    if n == 0:
        return 0.0
    count_a, count_b = Counter(labels_a), Counter(labels_b)
    joint = Counter(zip(labels_a, labels_b))

    def entropy(counts: Counter) -> float:
        h = 0.0
        for c in counts.values():
            p = c / n
            if p > 0:
                h -= p * math.log(p)
        return h

    h_a, h_b = entropy(count_a), entropy(count_b)
    if h_a == 0.0 or h_b == 0.0:
        return 1.0 if h_a == h_b else 0.0

    mi = 0.0
    for (a, b), c in joint.items():
        p_ab = c / n
        p_a, p_b = count_a[a] / n, count_b[b] / n
        mi += p_ab * math.log(p_ab / (p_a * p_b))
    return max(0.0, min(1.0, 2 * mi / (h_a + h_b)))
