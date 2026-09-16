"""(1)(2)(4)(6) の指標計算。

いずれも enrich.py が ShelfPosition/SHELF_NEXT に書き込んだ派生プロパティ
（heightBucket/colorHue/ndcL1Cached/authorNorm/各similarityフラグ）だけを読む。
Book/Author/NDCなど共有ノードの内容には一切依存しない
（enrich_positions を先に呼んでおくこと）。

- 高さ・色・著者の「まとまり具合」は networkx の属性アソータティビティ係数
  （隣接ノード同士が同じ属性値を持ちやすいか、-1〜1）で測る。
  グラフ理論の標準的な指標をそのまま流用しており、独自のヒューリスティック
  ではない。
- ジャンル×配置の一致度（4）・内容テーマ×配置の一致度・意味づけ×配置の一致度は
  いずれも style_projection.metrics の modularity/NMI 実装を再利用する
  （コミュニティ定義をGroupからNDC-L1/Theme/Conceptに差し替えるだけ）。
  内容テーマ(Theme)はあらすじからLLMが生成する参加者ごとの分類（themes.py）、
  意味づけ(Concept)は参加者が本に付けたConceptをそのまま使う（新規計算不要）。
- 高さの「順序」（1の一部）は utils.shelf_pattern_analysis の
  スピアマン順位相関実装を再利用する。
- デザイン意図の根拠（6）は、上記の「機能的な説明」がすべて弱いときに、
  対称性・周期性・間隔の均一さという「積極的な意匠パターン」で判定する。
"""
from __future__ import annotations

import math
import random
import statistics
from collections import Counter

import networkx as nx

from graph.main_kg.neo4j_driver import get_session
from graph.style_projection.metrics import modularity_for_communities, normalized_mutual_information
from utils.shelf_pattern_analysis import rank_spearman, spine_width_px

FUNCTIONAL_THRESHOLD = 0.35  # これ未満なら「機能的な説明が弱い」とみなす
AESTHETIC_THRESHOLD = 0.5    # これ以上なら「意匠パターンが見られる」とみなす

GROUP_GAP_FACTOR = 3.0   # 通常間隔のこの倍以上あれば別グループの区切りとみなす
GROUP_GAP_MIN_PX = 20.0  # 上記に加えて、これ未満の絶対差なら誤差として区切らない

N_PERMUTATIONS = 1000  # 帰無分布のシミュレーション回数
# 再現性のための固定シード（研究者が同じデータで再計算しても同じp値になる）。
# experiment.assignment._ASSIGNMENT_SEED と同じ方針。
PERMUTATION_SEED = 0


def _fetch_enriched_positions(session, participant_id: str) -> list[dict]:
    return session.run(
        """
        MATCH (:Participant {participantId: $pid})-[:OWNS]->(b:Book)
              <-[:LOCATES]-(pos:ShelfPosition {participantId: $pid})
        RETURN b.isbn AS isbn, pos.shelfIndex AS shelf_index, pos.xPos AS x_pos,
               pos.heightBucket AS height_bucket, pos.colorHue AS color_hue,
               pos.hueAngle AS hue_angle,
               pos.ndcL1Cached AS ndc_l1, pos.authorNorm AS author_norm,
               b.height_mm AS height_mm, coalesce(b.pages, 200) AS pages
        """,
        pid=participant_id,
    ).data()


def _fetch_concept_primary(session, participant_id: str) -> dict[str, str]:
    """本ごとの「代表的な意味づけ」。複数のConceptに属す本はconceptId昇順で
    最小のものを採用する（style_projection._belongs_to_communitiesと同じ考え方）。"""
    rows = session.run(
        """
        MATCH (:Participant {participantId: $pid})-[:OWNS]->(b:Book)
        OPTIONAL MATCH (b)-[:CONCEPT {participantId: $pid}]->(c:Concept {participantId: $pid})
        WITH b, min(c.conceptId) AS primary_concept
        RETURN b.isbn AS isbn, primary_concept
        """,
        pid=participant_id,
    ).data()
    return {r["isbn"]: r["primary_concept"] for r in rows if r["primary_concept"]}


def _fetch_theme_map(session, participant_id: str) -> dict[str, str]:
    """本ごとのLLM生成テーマ名（themes.generate_book_themesで作成済みの場合のみ）。"""
    rows = session.run(
        """
        MATCH (:Participant {participantId: $pid})-[:OWNS]->(b:Book)
              -[:HAS_THEME {participantId: $pid}]->(t:Theme {participantId: $pid})
        RETURN b.isbn AS isbn, t.name AS theme
        """,
        pid=participant_id,
    ).data()
    return {r["isbn"]: r["theme"] for r in rows}


def _build_shelf_graph(session, participant_id: str, positions: list[dict]) -> nx.Graph:
    concept_map = _fetch_concept_primary(session, participant_id)
    theme_map = _fetch_theme_map(session, participant_id)

    graph = nx.Graph()
    for r in positions:
        graph.add_node(
            r["isbn"],
            height_bucket=r["height_bucket"] if r["height_bucket"] is not None else -1,
            color_hue=r["color_hue"] or "none",
            ndc_l1=r["ndc_l1"] or "none",
            author_norm=r["author_norm"] or "none",
            concept_id=concept_map.get(r["isbn"]),
            theme=theme_map.get(r["isbn"]),
        )
    for r in session.run(
        """
        MATCH (a:Book)-[:SHELF_NEXT {participantId: $pid, isCurrent: true}]->(b:Book)
        RETURN a.isbn AS a, b.isbn AS b
        """,
        pid=participant_id,
    ):
        if r["a"] in graph and r["b"] in graph:
            graph.add_edge(r["a"], r["b"])
    return graph


def _assortativity(graph: nx.Graph, attribute: str) -> float | None:
    """属性アソータティビティ係数（Newman 2003）の素朴な実装。
    networkx.attribute_assortativity_coefficient は内部でnumpyを要求するため、
    本プロジェクトの他の指標（style_projection._nmi等）と同じ方針で、
    追加依存を増やさず自前で計算する。"""
    edges = list(graph.edges())
    if not edges:
        return None

    pair_counts: dict[tuple, int] = {}
    marginal: dict = {}
    total = 0
    for u, v in edges:
        au = graph.nodes[u].get(attribute)
        av = graph.nodes[v].get(attribute)
        if au is None or av is None:
            continue
        # 無向グラフなので両方向を数える（対称な混合行列にするため）
        pair_counts[(au, av)] = pair_counts.get((au, av), 0) + 1
        pair_counts[(av, au)] = pair_counts.get((av, au), 0) + 1
        marginal[au] = marginal.get(au, 0) + 1
        marginal[av] = marginal.get(av, 0) + 1
        total += 2

    if total == 0:
        return None

    a = {k: v / total for k, v in marginal.items()}
    sum_eii = sum(pair_counts.get((k, k), 0) / total for k in a)
    sum_ai_squared = sum(v * v for v in a.values())
    denom = 1 - sum_ai_squared
    if denom == 0:
        return None
    r = (sum_eii - sum_ai_squared) / denom
    return round(max(-1.0, min(1.0, r)), 4)


def _by_shelf(positions: list[dict]) -> dict[int, list[dict]]:
    rows: dict[int, list[dict]] = {}
    for r in positions:
        rows.setdefault(r["shelf_index"], []).append(r)
    for shelf_index, rows_in_shelf in rows.items():
        rows_in_shelf.sort(key=lambda r: r["x_pos"] or 0)
    return rows


HEIGHT_TIE_TOLERANCE_MM = 5  # この差以内は「サイズ差なし」とみなす（height_mmの計測・丸め誤差を吸収）


def _height_order_score(by_shelf: dict[int, list[dict]]) -> float | None:
    corrs = []
    for rows in by_shelf.values():
        if len(rows) < 3:
            continue
        corr = rank_spearman([r["x_pos"] or 0 for r in rows], [r["height_mm"] or 0 for r in rows])
        corrs.append(abs(corr))
    return round(statistics.fmean(corrs), 4) if corrs else None


def _height_staircase_score(by_shelf: dict[int, list[dict]]) -> tuple[float | None, dict | None]:
    """隣接する本同士を1組ずつ高さ比較し、増加/減少がどれだけ連続して
    続くか（段々に並んでいるか）を見る。height_order_score（段全体の
    スピアマン順位相関）よりも素朴で、外れ値1冊に強く、方向（昇順/降順）も
    そのまま提示できる。HEIGHT_TIE_TOLERANCE_MM以内の高さ差は「サイズ差なし」
    とみなし、増加・減少のどちらの向きとも矛盾しない「非減少/非増加」として
    カウントする（誤差程度の差を昇順にも降順にも属さない扱いにすると、
    ほぼ同サイズの本が連続するだけで正しく並んでいる列のスコアが
    不当に下がるため）。"""
    best: dict | None = None
    scores = []
    for shelf_index, rows in by_shelf.items():
        heights = [(r["isbn"], r["height_mm"]) for r in rows if r["height_mm"] is not None]
        if len(heights) < 3:
            continue
        steps = [heights[i + 1][1] - heights[i][1] for i in range(len(heights) - 1)]
        non_decreasing = sum(1 for d in steps if d >= -HEIGHT_TIE_TOLERANCE_MM)
        non_increasing = sum(1 for d in steps if d <= HEIGHT_TIE_TOLERANCE_MM)
        total = len(steps)
        if total == 0:
            continue
        if non_decreasing >= non_increasing:
            ratio, direction = non_decreasing / total, "ascending"
        else:
            ratio, direction = non_increasing / total, "descending"
        scores.append(ratio)
        if best is None or ratio > best["score"]:
            best = {
                "score": ratio, "shelf_index": shelf_index,
                "isbns": [isbn for isbn, _ in heights], "direction": direction,
            }
    return (round(statistics.fmean(scores), 4) if scores else None), best


def _row_height_trend_score(by_shelf: dict[int, list[dict]]) -> float | None:
    """段をまたいだ高さの傾向（上段↔下段で本のサイズがどう変わるか）を見る。
    height_order_score/height_staircase_scoreは同じ段の中の左右方向しか
    見ないため、「段を追うごとになだらかに変化する」配置はどちらでも
    検出できない。段ごとの平均height_mmと段番号のスピアマン順位相関で、
    +1に近いほど下段が大きく、-1に近いほど上段が大きい。"""
    rows = [(shelf_index, books) for shelf_index, books in by_shelf.items() if books]
    if len(rows) < 3:
        return None
    xs = [shelf_index for shelf_index, _ in rows]
    ys = [statistics.fmean(b["height_mm"] or 0 for b in books) for _, books in rows]
    return round(rank_spearman(xs, ys), 4)


def _split_into_groups(rows: list[dict]) -> list[list[dict]]:
    """1段の中を、通常より明らかに大きく空いた間隔を境に複数グループへ分割する。
    間隔のばらつきから「異常な空き」を判断できるほどの冊数が無ければ分割しない
    （そのまま1グループとして扱う）。"""
    if len(rows) < 4:
        return [rows]

    gaps = []
    for a, b in zip(rows, rows[1:]):
        width_a = spine_width_px(a.get("pages"))
        gaps.append((b["x_pos"] or 0) - (a["x_pos"] or 0) - width_a)

    median_gap = statistics.median(gaps)
    baseline = max(median_gap, 1.0)

    groups: list[list[dict]] = [[rows[0]]]
    for row, gap in zip(rows[1:], gaps):
        is_boundary = gap >= baseline * GROUP_GAP_FACTOR and gap - median_gap >= GROUP_GAP_MIN_PX
        if is_boundary:
            groups.append([row])
        else:
            groups[-1].append(row)
    return groups


def _height_group_order_score(by_shelf: dict[int, list[dict]]) -> float | None:
    """height_order_scoreは1段全体を1つの並びとして順位相関を取るため、
    間隔で区切られた複数グループがそれぞれ逆向きに高さ順（山型・谷型など）に
    並んでいるケースを検出できない（グループ全体では非単調に見えて
    相関が打ち消し合うため）。ここでは_split_into_groupsで区切った
    グループごとに高さ順序を測ってから平均することで、その弱点を補う。"""
    corrs = []
    for rows in by_shelf.values():
        for group in _split_into_groups(rows):
            if len(group) < 3:
                continue
            corr = rank_spearman(
                [r["x_pos"] or 0 for r in group], [r["height_mm"] or 0 for r in group]
            )
            corrs.append(abs(corr))
    return round(statistics.fmean(corrs), 4) if corrs else None


def _circular_diff(h1: float, h2: float) -> float:
    """色相環（0〜1、循環）上でh1からh2への符号付き差分。値域は(-0.5, 0.5]。"""
    d = (h2 - h1) % 1.0
    if d > 0.5:
        d -= 1.0
    return d


def _color_gradient_score(by_shelf: dict[int, list[dict]]) -> tuple[float | None, dict | None]:
    """隣接する本同士の色相を比較し、色相環上を一定方向へなだらかに
    変化しているか（虹色のグラデーション配置）を見る。color_grouping_score
    （同じ色相バケットが隣り合うか＝離散一致）とは異なり、バケットをまたいで
    連続的に変化するケースも拾える。無彩色の本は列から除外して比較する。"""
    best: dict | None = None
    scores = []
    for shelf_index, rows in by_shelf.items():
        chromatic = [(r["isbn"], r["hue_angle"]) for r in rows if r["hue_angle"] is not None]
        if len(chromatic) < 4:
            continue
        hues = [h for _, h in chromatic]
        diffs = [_circular_diff(hues[i], hues[i + 1]) for i in range(len(hues) - 1)]
        positive = sum(1 for d in diffs if d > 0.015)
        negative = sum(1 for d in diffs if d < -0.015)
        total = len(diffs)
        if total == 0:
            continue
        consistency = max(positive, negative) / total
        avg_step = statistics.fmean(abs(d) for d in diffs)
        smoothness = max(0.0, 1 - avg_step / 0.5)  # 一歩ごとの変化が大きく飛ばないほど1に近づく
        score = consistency * smoothness
        if score > 0:
            scores.append(score)
            if best is None or score > best["score"]:
                direction = "ascending" if positive >= negative else "descending"
                best = {
                    "score": round(score, 4), "shelf_index": shelf_index,
                    "isbns": [isbn for isbn, _ in chromatic], "direction": direction,
                }
    return (round(statistics.fmean(scores), 4) if scores else None), best


def _color_uniformity_score(by_shelf: dict[int, list[dict]]) -> tuple[float | None, dict | None]:
    """段全体として使われている色数がどれだけ絞られているか（パレットの
    統一感）をシャノンエントロピーで測る。color_grouping_score（隣接ペアの
    一致率）と違い、「隣同士は違う色でも段全体では2〜3色しか使っていない」
    ような統一感も拾える。"""
    best: dict | None = None
    scores = []
    for shelf_index, rows in by_shelf.items():
        hues = [(r["isbn"], r["color_hue"]) for r in rows if r["color_hue"]]
        if len(hues) < 3:
            continue
        counts = Counter(h for _, h in hues)
        total = len(hues)
        if len(counts) <= 1:
            score = 1.0
        else:
            entropy = -sum((c / total) * math.log2(c / total) for c in counts.values())
            max_entropy = math.log2(len(counts))
            score = max(0.0, 1 - entropy / max_entropy)
        scores.append(score)
        if best is None or score > best["score"]:
            dominant_hue = counts.most_common(1)[0][0]
            best = {
                "score": round(score, 4), "shelf_index": shelf_index,
                "isbns": [isbn for isbn, hue in hues if hue == dominant_hue],
                "dominant_hue": dominant_hue,
            }
    return (round(statistics.fmean(scores), 4) if scores else None), best


def _placement_alignment_scores(graph: nx.Graph, attribute: str) -> tuple[float | None, float | None]:
    """本にどの属性（ジャンル=ndc_l1・内容テーマ=theme・意味づけ=concept_id）で
    コミュニティ分けをしても、それが物理的な配置（SHELF_NEXT）とどれだけ
    一致するかを、style_projection.metricsのmodularity/NMI実装で測る
    （コミュニティ定義を差し替えているだけで計算式は共通）。

    属性値が無い本（例: あらすじが無くThemeが未生成、意味づけをしていない）は
    互いにまとめず、1冊だけの単独コミュニティとして扱う。欠損値をまとめて
    1つの巨大な「なし」コミュニティにすると、それらの本の物理的な散らばり方
    次第でmodularityが見かけ上歪むため（style_projection._belongs_to_communities
    と同じ配慮）。"""
    if graph.number_of_edges() == 0:
        return None, None

    community: dict[str, str] = {}
    has_any_value = False
    for isbn, data in graph.nodes(data=True):
        value = data.get(attribute)
        if value is not None:
            has_any_value = True
            community[isbn] = value
        else:
            community[isbn] = f"__none__{isbn}"

    if not has_any_value:
        return None, None

    modularity = round(modularity_for_communities(graph, community), 4)

    try:
        raw_communities = list(nx.algorithms.community.greedy_modularity_communities(graph))
    except Exception:
        return modularity, None

    louvain_label: dict[str, int] = {}
    for i, community_nodes in enumerate(raw_communities):
        for isbn in community_nodes:
            louvain_label[isbn] = i

    nodes = list(graph.nodes)
    nmi = normalized_mutual_information(
        [louvain_label.get(n, -1) for n in nodes],
        [community.get(n, "none") for n in nodes],
    )
    return modularity, round(nmi, 4)


def _spacing_regularity(by_shelf: dict[int, list[dict]]) -> tuple[float | None, dict | None]:
    """段ごとの隙間（間隔）の変動係数から、間隔の均一さを 0〜1 で表す。
    戻り値は (平均スコア, 最も均一だった段の詳細)。"""
    best: dict | None = None
    scores = []
    for shelf_index, rows in by_shelf.items():
        gaps = []
        for a, b in zip(rows, rows[1:]):
            width_a = spine_width_px(a["pages"])
            gaps.append((b["x_pos"] or 0) - (a["x_pos"] or 0) - width_a)
        if len(gaps) < 3:
            continue
        mean = statistics.fmean(gaps)
        if mean <= 0:
            continue
        cv = statistics.pstdev(gaps) / mean
        score = max(0.0, 1 - min(1.0, cv))
        scores.append(score)
        if best is None or score > best["score"]:
            best = {"score": score, "shelf_index": shelf_index, "isbns": [r["isbn"] for r in rows]}
    return (round(statistics.fmean(scores), 4) if scores else None), best


def _symmetry_score(by_shelf: dict[int, list[dict]]) -> tuple[float | None, dict | None]:
    """段内の高さプロファイルが、中央を軸に鏡映対称に近いほど1に近づくスコア。"""
    best: dict | None = None
    scores = []
    for shelf_index, rows in by_shelf.items():
        heights = [r["height_mm"] or 0 for r in rows]
        n = len(heights)
        if n < 3:
            continue
        h_range = max(heights) - min(heights)
        if h_range == 0:
            continue
        diffs = [abs(heights[i] - heights[n - 1 - i]) for i in range(n // 2)]
        score = max(0.0, 1 - statistics.fmean(diffs) / h_range)
        scores.append(score)
        if best is None or score > best["score"]:
            best = {"score": score, "shelf_index": shelf_index, "isbns": [r["isbn"] for r in rows]}
    return (round(statistics.fmean(scores), 4) if scores else None), best


def _rhythm_score(by_shelf: dict[int, list[dict]]) -> tuple[float | None, dict | None]:
    """色相の並びが一定周期（2冊おき/3冊おき）で繰り返しているかのスコア。"""
    best: dict | None = None
    scores = []
    for shelf_index, rows in by_shelf.items():
        seq = [r["color_hue"] for r in rows if r["color_hue"]]
        if len(seq) < 4:
            continue
        row_best = 0.0
        for period in (2, 3):
            if len(seq) <= period:
                continue
            matches = sum(1 for i in range(len(seq) - period) if seq[i] == seq[i + period])
            total = len(seq) - period
            if total > 0:
                row_best = max(row_best, matches / total)
        if row_best > 0:
            scores.append(row_best)
            if best is None or row_best > best["score"]:
                best = {"score": row_best, "shelf_index": shelf_index, "isbns": [r["isbn"] for r in rows]}
    return (round(statistics.fmean(scores), 4) if scores else None), best


_SCORE_FUNCS = {
    "symmetry": _symmetry_score,
    "rhythm": _rhythm_score,
    "spacing_regularity": _spacing_regularity,
    "color_gradient": _color_gradient_score,
    "color_uniformity": _color_uniformity_score,
}


def _shuffle_by_shelf(by_shelf: dict[int, list[dict]], rng: random.Random) -> dict[int, list[dict]]:
    """各段内で、物理的なスロット位置(x_pos)を固定したまま、そこに座る本の
    属性（高さ・色・ページ数等）だけをランダムに入れ替える。「本の属性とスロットの
    対応がランダムである」という帰無仮説をシミュレートするための並べ替え
    （段をまたいだ入れ替えや、段内の本の総数は変えない）。"""
    shuffled: dict[int, list[dict]] = {}
    for shelf_index, rows in by_shelf.items():
        xs = [r["x_pos"] for r in rows]
        payloads = [{k: v for k, v in r.items() if k != "x_pos"} for r in rows]
        rng.shuffle(payloads)
        shuffled[shelf_index] = [{**payload, "x_pos": x} for payload, x in zip(payloads, xs)]
    return shuffled


def _permutation_p_value(
    by_shelf: dict[int, list[dict]],
    score_fn,
    observed_score: float,
    n_permutations: int = N_PERMUTATIONS,
    seed: int = PERMUTATION_SEED,
) -> float:
    """観測されたスコアが、本の属性をスロット間でランダムに入れ替えた帰無分布の
    どの位置にあるかを示す経験的p値（片側検定：帰無分布がobserved_score以上に
    なる割合）。0にはならないよう +1 補正する（North et al. 2002 の標準的な
    推定量。有限回のシミュレーションでp=0と報告してしまう誤りを避ける）。"""
    rng = random.Random(seed)
    count_ge = 0
    for _ in range(n_permutations):
        permuted_score, _ = score_fn(_shuffle_by_shelf(by_shelf, rng))
        if permuted_score is not None and permuted_score >= observed_score:
            count_ge += 1
    return round((count_ge + 1) / (n_permutations + 1), 4)


_EMPTY_METRICS = {
    "book_count": 0,
    "height_order_score": None,
    "height_staircase_score": None,
    "row_height_trend_score": None,
    "height_group_order_score": None,
    "height_grouping_score": None,
    "color_grouping_score": None,
    "color_gradient_score": None,
    "color_uniformity_score": None,
    "author_grouping_score": None,
    "genre_placement_modularity": None,
    "genre_placement_nmi": None,
    "theme_placement_modularity": None,
    "theme_placement_nmi": None,
    "concept_placement_modularity": None,
    "concept_placement_nmi": None,
    "symmetry_score": None,
    "rhythm_score": None,
    "spacing_regularity": None,
    "design_intent": False,
}


def compute_placement_metrics(participant_id: str) -> dict:
    """PlacementProfileに保存する全指標と、デザイン根拠(DesignEvidence)の
    候補を1回で計算する。戻り値の "evidence_candidate" は design_intent=True
    のときだけ、根拠として提示する段・本を含む。"""
    with get_session() as session:
        positions = _fetch_enriched_positions(session, participant_id)
        if not positions:
            return {**_EMPTY_METRICS, "evidence_candidate": None}
        graph = _build_shelf_graph(session, participant_id, positions)

    by_shelf = _by_shelf(positions)

    height_grouping = _assortativity(graph, "height_bucket")
    color_grouping = _assortativity(graph, "color_hue")
    author_grouping = _assortativity(graph, "author_norm")
    genre_modularity, genre_nmi = _placement_alignment_scores(graph, "ndc_l1")
    theme_modularity, theme_nmi = _placement_alignment_scores(graph, "theme")
    concept_modularity, concept_nmi = _placement_alignment_scores(graph, "concept_id")
    height_order = _height_order_score(by_shelf)
    height_staircase, _staircase_best = _height_staircase_score(by_shelf)
    row_height_trend = _row_height_trend_score(by_shelf)
    height_group_order = _height_group_order_score(by_shelf)

    symmetry, symmetry_best = _symmetry_score(by_shelf)
    rhythm, rhythm_best = _rhythm_score(by_shelf)
    spacing, spacing_best = _spacing_regularity(by_shelf)
    gradient, gradient_best = _color_gradient_score(by_shelf)
    uniformity, uniformity_best = _color_uniformity_score(by_shelf)

    functional_scores = [
        abs(s) for s in (
            height_grouping, color_grouping, author_grouping,
            genre_modularity, theme_modularity, concept_modularity,
            row_height_trend, height_group_order,
        )
        if s is not None
    ]
    max_functional = max(functional_scores, default=0.0)

    # symmetry/rhythm/spacing_regularity は「機能的な理由が弱いときの消極的根拠」。
    # gradient/uniformity は虹色配置・単色パレットのように、それ自体が明確な
    # 意匠意図のサインなので、機能スコアの強弱に関わらず積極的な根拠として扱う。
    aesthetic_candidates = [
        ("symmetry", symmetry, symmetry_best),
        ("rhythm", rhythm, rhythm_best),
        ("spacing_regularity", spacing, spacing_best),
    ]
    aesthetic_candidates = [c for c in aesthetic_candidates if c[1] is not None]
    weak_winning = max(aesthetic_candidates, key=lambda c: c[1], default=None)

    strong_candidates = [
        ("color_gradient", gradient, gradient_best),
        ("color_uniformity", uniformity, uniformity_best),
    ]
    strong_candidates = [c for c in strong_candidates if c[1] is not None]
    strong_winning = max(strong_candidates, key=lambda c: c[1], default=None)

    if strong_winning is not None and strong_winning[1] >= AESTHETIC_THRESHOLD:
        design_intent, winning = True, strong_winning
    else:
        design_intent = bool(
            weak_winning is not None
            and max_functional < FUNCTIONAL_THRESHOLD
            and weak_winning[1] >= AESTHETIC_THRESHOLD
        )
        winning = weak_winning if design_intent else None

    evidence_candidate = None
    if winning is not None and winning[2] is not None:
        evidence_type, score, best = winning
        p_value = _permutation_p_value(by_shelf, _SCORE_FUNCS[evidence_type], score)
        evidence_candidate = {
            "evidence_type": evidence_type,
            "score": score,
            "p_value": p_value,
            "shelf_index": best["shelf_index"],
            "isbns": best["isbns"],
        }

    return {
        "book_count": len(positions),
        "height_order_score": height_order,
        "height_staircase_score": height_staircase,
        "row_height_trend_score": row_height_trend,
        "height_group_order_score": height_group_order,
        "height_grouping_score": height_grouping,
        "color_grouping_score": color_grouping,
        "color_gradient_score": gradient,
        "color_uniformity_score": uniformity,
        "author_grouping_score": author_grouping,
        "genre_placement_modularity": genre_modularity,
        "genre_placement_nmi": genre_nmi,
        "theme_placement_modularity": theme_modularity,
        "theme_placement_nmi": theme_nmi,
        "concept_placement_modularity": concept_modularity,
        "concept_placement_nmi": concept_nmi,
        "symmetry_score": symmetry,
        "rhythm_score": rhythm,
        "spacing_regularity": spacing,
        "design_intent": design_intent,
        "evidence_candidate": evidence_candidate,
    }
