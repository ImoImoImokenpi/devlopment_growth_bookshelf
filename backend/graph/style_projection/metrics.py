"""構造指標（StyleProfile）のバッチ計算。

ここで計算するすべての指標は、ノード数・エッジ数・階層構造だけから求まる
「内容に依存しない」構造指標である。Group.name や Comment.text など意味データは
一切参照しない（参照するのは投入時のみ）。

clustering_coefficient は Neo4j GDS の localClusteringCoefficient を使用する。
modularity は、GDSプロシージャの名称・提供有無がGDSのバージョンによって
変わりやすいため networkx で直接計算し（既存コードの network_analysis.py と
同じ依存）、GDSは Louvain によるコミュニティ検出とBELONGS_TOとのNMI比較
（modularity_nmi）の側で実際に使用する。スキーマ上の modularity: float は
GDSに依存しない前者を正とする。
"""
from __future__ import annotations

import math
import statistics
import uuid
from collections import Counter
from datetime import datetime

import networkx as nx

from graph.main_kg.neo4j_driver import get_session
from graph.style_projection.groups import get_max_group_depth


def _group_sizes(session, participant_id: str) -> list[int]:
    rows = session.run(
        """
        MATCH (:Participant {participantId: $pid})-[:OWNS]->(s:ShelvedBook)-[:BELONGS_TO]->(g:Group)
        RETURN count(DISTINCT s) AS size
        """,
        pid=participant_id,
    )
    return [r["size"] for r in rows]


def _isolated_ratio(session, participant_id: str) -> float:
    row = session.run(
        """
        MATCH (:Participant {participantId: $pid})-[:OWNS]->(s:ShelvedBook)
        WITH count(s) AS total
        MATCH (:Participant {participantId: $pid})-[:OWNS]->(s2:ShelvedBook)
        WHERE NOT (s2)-[:BELONGS_TO]->(:Group)
        RETURN total, count(s2) AS isolated
        """,
        pid=participant_id,
    ).single()
    if not row or not row["total"]:
        return 0.0
    return row["isolated"] / row["total"]


def _avg_multi_membership(session, participant_id: str) -> float:
    row = session.run(
        """
        MATCH (:Participant {participantId: $pid})-[:OWNS]->(s:ShelvedBook)
        OPTIONAL MATCH (s)-[:BELONGS_TO]->(g:Group)
        WITH s, count(g) AS memberships
        RETURN avg(memberships) AS avg_multi
        """,
        pid=participant_id,
    ).single()
    return float(row["avg_multi"]) if row and row["avg_multi"] is not None else 0.0


def _adjacency_graph(session, participant_id: str) -> nx.Graph:
    """ADJACENT_TOネットワークをnetworkXの無向グラフとして構築する
    （孤立本もノードとして含める）。"""
    graph = nx.Graph()
    for r in session.run(
        """
        MATCH (:Participant {participantId: $pid})-[:OWNS]->(s:ShelvedBook)
        RETURN s.shelved_id AS shelved_id
        """,
        pid=participant_id,
    ):
        graph.add_node(r["shelved_id"])

    for r in session.run(
        """
        MATCH (:Participant {participantId: $pid})-[:OWNS]->(a:ShelvedBook)
        MATCH (a)-[:ADJACENT_TO]-(b:ShelvedBook)<-[:OWNS]-(:Participant {participantId: $pid})
        WHERE a.shelved_id < b.shelved_id
        RETURN a.shelved_id AS a, b.shelved_id AS b
        """,
        pid=participant_id,
    ):
        graph.add_edge(r["a"], r["b"])

    return graph


def _belongs_to_communities(session, participant_id: str) -> dict[str, str]:
    """本ごとの「代表グループ」。複数所属の場合はgroup_id昇順で最小のものを採用する。
    どのグループにも属さない本は、他の本と混ざらないよう自分自身をコミュニティとする
    （＝孤立本同士がまとめて1つの巨大クラスタになるのを避ける）。"""
    community: dict[str, str] = {}
    for r in session.run(
        """
        MATCH (:Participant {participantId: $pid})-[:OWNS]->(s:ShelvedBook)
        OPTIONAL MATCH (s)-[:BELONGS_TO]->(g:Group)
        WITH s, min(g.group_id) AS primary_group
        RETURN s.shelved_id AS shelved_id, primary_group
        """,
        pid=participant_id,
    ):
        community[r["shelved_id"]] = r["primary_group"] or f"__isolated__{r['shelved_id']}"
    return community


def _modularity(graph: nx.Graph, community: dict[str, str]) -> float:
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


def _clustering_coefficient_gds(session, participant_id: str, node_count: int) -> float | None:
    """GDSのlocalClusteringCoefficientを、参加者専用の使い捨てグラフ射影で計算する。
    GDSが使えない環境ではNoneを返し、呼び出し側でnetworkXフォールバックする。"""
    if node_count < 2:
        return 0.0
    graph_name = f"sp_lcc_{participant_id}_{uuid.uuid4().hex[:8]}"
    try:
        session.run(
            """
            MATCH (p:Participant {participantId: $pid})-[:OWNS]->(s:ShelvedBook)
            OPTIONAL MATCH (s)-[:ADJACENT_TO]-(t:ShelvedBook)<-[:OWNS]-(p)
            WITH gds.graph.project(
                $graph_name, s, t, {}, {undirectedRelationshipTypes: ['*']}
            ) AS g
            RETURN g.graphName AS graphName
            """,
            pid=participant_id,
            graph_name=graph_name,
        ).single()

        row = session.run(
            """
            CALL gds.localClusteringCoefficient.stream($graph_name)
            YIELD localClusteringCoefficient
            RETURN avg(localClusteringCoefficient) AS avg_lcc
            """,
            graph_name=graph_name,
        ).single()
        return float(row["avg_lcc"]) if row and row["avg_lcc"] is not None else 0.0
    except Exception:
        return None
    finally:
        try:
            session.run("CALL gds.graph.drop($graph_name, false)", graph_name=graph_name)
        except Exception:
            pass


def _louvain_communities_gds(session, participant_id: str, node_count: int) -> dict[str, int] | None:
    """GDSのLouvainで求めたコミュニティ割当。GDSが使えなければNone。"""
    if node_count < 2:
        return None
    graph_name = f"sp_louvain_{participant_id}_{uuid.uuid4().hex[:8]}"
    try:
        session.run(
            """
            MATCH (p:Participant {participantId: $pid})-[:OWNS]->(s:ShelvedBook)
            OPTIONAL MATCH (s)-[:ADJACENT_TO]-(t:ShelvedBook)<-[:OWNS]-(p)
            WITH gds.graph.project(
                $graph_name, s, t, {}, {undirectedRelationshipTypes: ['*']}
            ) AS g
            RETURN g.graphName AS graphName
            """,
            pid=participant_id,
            graph_name=graph_name,
        ).single()

        rows = session.run(
            """
            CALL gds.louvain.stream($graph_name)
            YIELD nodeId, communityId
            RETURN gds.util.asNode(nodeId).shelved_id AS shelved_id, communityId
            """,
            graph_name=graph_name,
        )
        return {r["shelved_id"]: r["communityId"] for r in rows}
    except Exception:
        return None
    finally:
        try:
            session.run("CALL gds.graph.drop($graph_name, false)", graph_name=graph_name)
        except Exception:
            pass


def _nmi(labels_a: list, labels_b: list) -> float:
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


# 他モジュール（placement_analysis.metrics のジャンル×配置一致度など）から
# 同じ計算を再利用するための公開名。
modularity_for_communities = _modularity
normalized_mutual_information = _nmi


def compute_style_profile(participant_id: str) -> dict:
    """participant_idの現在のグラフ状態から構造指標を計算する（読み取りのみ、保存しない）。"""
    with get_session() as session:
        sizes = _group_sizes(session, participant_id)
        avg_group_size = statistics.fmean(sizes) if sizes else 0.0
        stdev_group_size = statistics.pstdev(sizes) if len(sizes) >= 2 else 0.0

        isolated_ratio = _isolated_ratio(session, participant_id)
        avg_multi_membership = _avg_multi_membership(session, participant_id)
        max_depth = get_max_group_depth(participant_id)

        graph = _adjacency_graph(session, participant_id)
        node_count = graph.number_of_nodes()

        clustering_coefficient = _clustering_coefficient_gds(session, participant_id, node_count)
        if clustering_coefficient is None:
            clustering_coefficient = nx.average_clustering(graph) if node_count >= 2 else 0.0

        community = _belongs_to_communities(session, participant_id)
        modularity = _modularity(graph, community)

        louvain = _louvain_communities_gds(session, participant_id, node_count)
        modularity_nmi = None
        if louvain is not None and node_count >= 2:
            shared_nodes = list(graph.nodes)
            louvain_labels = [louvain.get(n, -1) for n in shared_nodes]
            belongs_labels = [community.get(n, n) for n in shared_nodes]
            modularity_nmi = _nmi(louvain_labels, belongs_labels)

    return {
        "participant_id": participant_id,
        "avg_group_size": round(avg_group_size, 4),
        "stdev_group_size": round(stdev_group_size, 4),
        "isolated_ratio": round(isolated_ratio, 4),
        "avg_multi_membership": round(avg_multi_membership, 4),
        "max_depth": max_depth,
        "clustering_coefficient": round(clustering_coefficient, 4),
        "modularity": round(modularity, 4),
        "modularity_nmi": round(modularity_nmi, 4) if modularity_nmi is not None else None,
    }


def save_style_profile(participant_id: str) -> dict:
    """構造指標を計算し、新規のStyleProfileノードとして追記保存する
    （上書きせず、computed_atで履歴を追えるようにする）。"""
    profile = compute_style_profile(participant_id)
    profile_id = str(uuid.uuid4())
    computed_at = datetime.now()

    with get_session() as session:
        session.run(
            """
            MATCH (p:Participant {participantId: $pid})
            CREATE (sp:StyleProfile {
                profile_id: $profile_id,
                participantId: $pid,
                avg_group_size: $avg_group_size,
                stdev_group_size: $stdev_group_size,
                isolated_ratio: $isolated_ratio,
                avg_multi_membership: $avg_multi_membership,
                max_depth: $max_depth,
                clustering_coefficient: $clustering_coefficient,
                modularity: $modularity,
                modularity_nmi: $modularity_nmi,
                computed_at: $computed_at
            })
            MERGE (p)-[:HAS_PROFILE]->(sp)
            """,
            pid=participant_id,
            profile_id=profile_id,
            computed_at=computed_at,
            **{k: v for k, v in profile.items() if k != "participant_id"},
        )

    profile["profile_id"] = profile_id
    profile["computed_at"] = computed_at.isoformat()
    return profile
