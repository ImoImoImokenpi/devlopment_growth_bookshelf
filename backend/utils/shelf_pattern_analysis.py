"""本棚の物理的な配置（高さ・ジャンル・色・著者・段など）から、
ユーザーが意識していそうな並べ方のルールを機械的に検出する。

対象とする12パターン（REFERENCE_PATTERNS）のうち、位置データから
検証できるものだけをヒューリスティックにチェックし、検出できた事実を
1文の日本語（fact）として返す。LLMへの分析コンテキストとして使う。
"""
from __future__ import annotations

import colorsys
from collections import Counter

PX_TO_MM_SCALE = 1.2

NDC_L1_NAMES = {
    "0": "総記", "1": "哲学", "2": "歴史・地理", "3": "社会科学",
    "4": "自然科学", "5": "技術", "6": "産業", "7": "芸術", "8": "言語", "9": "文学",
}

HUE_NAMES = ["赤", "橙", "黄", "黄緑", "緑", "青緑", "青", "青紫", "紫", "赤紫"]

REFERENCE_PATTERNS = [
    "高さに関する並び（左から/右から高さ順、または高さを意識しない）",
    "ジャンルに関する並び（まとめる/まとめない）",
    "高さとジャンル、どちらを優先しているか",
    "色に関する並び（意識する/意識しない）",
    "著者でそろえる",
    "段の上下による大きさの変化（上段を大きく/下段を大きく）",
    "興味に関する並び（関心の高い本を上段・中段・下段や左右のどこに置くか）",
    "ジャンルや著者などの変わり目を意識した間隔の取り方",
    "本の密度（上段・下段でぎっしり詰めるか、余裕を持たせるか）",
    "浮いている（他と共通点のない）本の存在",
    "端に大きな本を置く配置",
    "上記に当てはまらない、見た目重視でデザインされた配置",
]


def _spine_width_px(pages, height_mm=None) -> float:
    if not pages:
        return 20.0
    # 文庫(高さ160mm以下)は背幅を細めにする
    factor = 0.75 if height_mm and height_mm <= 160 else 1.0
    return min(100.0, max(1.0, pages * 0.08 * factor))


def _parse_spine_hsv(spine_color: str | None) -> tuple[float, float, float] | None:
    if not spine_color:
        return None
    try:
        r, g, b = (int(v) for v in spine_color.split(","))
    except (ValueError, AttributeError):
        return None
    return colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)


def _color_bucket(spine_color: str | None) -> str | None:
    hsv = _parse_spine_hsv(spine_color)
    if hsv is None:
        return None
    h, s, v = hsv
    if s < 0.15 or v < 0.15:
        return "無彩色"
    return HUE_NAMES[int(h * 10) % 10]


def _hue_angle(spine_color: str | None) -> float | None:
    """色相環上の連続値（0〜1、無彩色はNone）。10色相バケットへの離散化
    （_color_bucket）だと「隣同士でバケットが一致するか」しか見られず、
    バケットをまたいでなだらかに変化するグラデーションを検出できない。
    そのため、グラデーション判定（placement_analysis）にはこちらを使う。"""
    hsv = _parse_spine_hsv(spine_color)
    if hsv is None:
        return None
    h, s, v = hsv
    if s < 0.15 or v < 0.15:
        return None
    return h


def _ndc_l1(ndc: str | None) -> str | None:
    if not ndc:
        return None
    return NDC_L1_NAMES.get(ndc[0])


def _first_author(authors: str | None) -> str | None:
    if not authors:
        return None
    name = authors.split(",")[0].strip()
    return name or None


def _ranks(values: list[float]) -> list[float]:
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        avg_rank = (i + j) / 2 + 1
        for k in range(i, j + 1):
            ranks[order[k]] = avg_rank
        i = j + 1
    return ranks


def _rank_spearman(xs: list[float], ys: list[float]) -> float:
    """スピアマン順位相関係数（scipy無しの簡易実装）。"""
    n = len(xs)
    if n < 3:
        return 0.0
    rx, ry = _ranks(xs), _ranks(ys)
    mean_rx, mean_ry = sum(rx) / n, sum(ry) / n
    cov = sum((a - mean_rx) * (b - mean_ry) for a, b in zip(rx, ry))
    var_x = sum((a - mean_rx) ** 2 for a in rx)
    var_y = sum((b - mean_ry) ** 2 for b in ry)
    if var_x == 0 or var_y == 0:
        return 0.0
    return cov / (var_x ** 0.5 * var_y ** 0.5)


# 他モジュール（placement_analysis）から同じ計算を再利用するための公開名。
color_hue_bucket = _color_bucket
hue_angle = _hue_angle
spine_width_px = _spine_width_px
rank_spearman = _rank_spearman


def _count_runs(seq: list) -> int:
    if not seq:
        return 0
    runs = 1
    for prev, cur in zip(seq, seq[1:]):
        if cur != prev:
            runs += 1
    return runs


def _grouping_score(seq: list) -> float | None:
    """値が連続してまとまっているほど1に近づくスコア。まとめようのないデータはNone。"""
    values = [v for v in seq if v is not None]
    distinct = set(values)
    if len(values) < 3 or len(distinct) < 2 or len(distinct) == len(values):
        return None
    return len(distinct) / _count_runs(values)


# ============================================================
# パターンごとの検出関数（enriched: {shelf_index: [book, ...]}）
# ============================================================

def _finding_height_order(enriched):
    directions = []
    for shelf_idx, books in enriched.items():
        if len(books) < 3:
            continue
        corr = _rank_spearman([b["_x_px"] for b in books], [b["height_mm"] or 0 for b in books])
        if abs(corr) >= 0.5:
            directions.append((shelf_idx, corr))
    if not directions:
        return None
    avg_corr = sum(c for _, c in directions) / len(directions)
    if avg_corr >= 0.5:
        label = "左から右へ高さが大きくなる順"
    elif avg_corr <= -0.5:
        label = "左から右へ高さが小さくなる順（右側が高い）"
    else:
        return None
    sample_shelf = directions[0][0]
    return {
        "pattern_id": "height_order", "label": "高さの並び",
        "fact": f"{sample_shelf + 1}段目など複数の段で、本が{label}に並んでいます。",
        "isbns": [b["isbn"] for b in enriched[sample_shelf]],
    }


def _finding_genre_grouping(enriched):
    scores, sample = [], None
    for shelf_idx, books in enriched.items():
        score = _grouping_score([b["_ndc_l1"] for b in books])
        if score is not None:
            scores.append(score)
            if sample is None or score > sample[1]:
                sample = (shelf_idx, score)
    if not scores:
        return None
    avg = sum(scores) / len(scores)
    if avg >= 0.6:
        return {
            "pattern_id": "genre_grouping", "label": "ジャンルの並び",
            "fact": f"{sample[0] + 1}段目など、同じジャンル（NDC分類）の本がまとまって並べられている段があります。",
            "isbns": [b["isbn"] for b in enriched[sample[0]]],
        }
    if avg <= 0.35:
        return {
            "pattern_id": "genre_grouping", "label": "ジャンルの並び",
            "fact": "同じジャンルの本があえて分散して配置されており、ジャンルでまとめていない可能性があります。",
            "isbns": [],
        }
    return None


def _finding_height_genre_priority(enriched):
    within_corrs, global_corrs = [], []
    for shelf_idx, books in enriched.items():
        if len(books) < 4:
            continue
        global_corrs.append(abs(_rank_spearman([b["_x_px"] for b in books], [b["height_mm"] or 0 for b in books])))
        segments, cur_seg = [], [books[0]]
        for prev, cur in zip(books, books[1:]):
            if cur["_ndc_l1"] is not None and cur["_ndc_l1"] == prev["_ndc_l1"]:
                cur_seg.append(cur)
            else:
                segments.append(cur_seg)
                cur_seg = [cur]
        segments.append(cur_seg)
        for seg in segments:
            if len(seg) >= 3:
                within_corrs.append(abs(_rank_spearman([b["_x_px"] for b in seg], [b["height_mm"] or 0 for b in seg])))
    if not within_corrs or not global_corrs:
        return None
    avg_within = sum(within_corrs) / len(within_corrs)
    avg_global = sum(global_corrs) / len(global_corrs)
    if avg_within - avg_global >= 0.25:
        fact = "ジャンルでまとめた上で、その中で高さ順に並べているようです（ジャンルが優先）。"
    elif avg_global - avg_within >= 0.25:
        fact = "ジャンルよりも高さの順序のほうが優先されているようです。"
    else:
        return None
    return {"pattern_id": "height_genre_priority", "label": "高さとジャンルの優先度", "fact": fact, "isbns": []}


def _finding_color_grouping(enriched):
    scores, sample = [], None
    for shelf_idx, books in enriched.items():
        score = _grouping_score([b["_color"] for b in books])
        if score is not None:
            scores.append(score)
            if sample is None or score > sample[1]:
                sample = (shelf_idx, score)
    if not scores or sum(scores) / len(scores) < 0.6:
        return None
    return {
        "pattern_id": "color_grouping", "label": "色の並び",
        "fact": f"{sample[0] + 1}段目など、背表紙の色味が近い本がまとまって並んでいる段があります。",
        "isbns": [b["isbn"] for b in enriched[sample[0]]],
    }


def _finding_author_grouping(enriched):
    scores, sample = [], None
    for shelf_idx, books in enriched.items():
        score = _grouping_score([b["_author"] for b in books])
        if score is not None:
            scores.append(score)
            if sample is None or score > sample[1]:
                sample = (shelf_idx, score)
    if not scores or sum(scores) / len(scores) < 0.7:
        return None
    return {
        "pattern_id": "author_grouping", "label": "著者で揃える",
        "fact": f"{sample[0] + 1}段目などで、同じ著者の本が隣り合わせに並んでいます。",
        "isbns": [b["isbn"] for b in enriched[sample[0]] if b["_author"]],
    }


def _finding_row_size_by_position(enriched):
    rows = [(idx, books) for idx, books in enriched.items() if books]
    if len(rows) < 2:
        return None
    xs = [idx for idx, _ in rows]
    ys = [sum(b["height_mm"] or 0 for b in books) / len(books) for _, books in rows]
    corr = _rank_spearman(xs, ys)
    if corr >= 0.5:
        fact = "下の段ほど背が高い本が多く、上段が小さく下段が大きい配置になっています。"
    elif corr <= -0.5:
        fact = "上の段ほど背が高い本が多く、下段が小さい配置になっています。"
    else:
        return None
    return {"pattern_id": "row_size_by_position", "label": "段による大きさの変化", "fact": fact, "isbns": []}


def _finding_interest_arrangement(enriched, memo_isbns):
    if not memo_isbns:
        return None
    total_books = [b for books in enriched.values() for b in books]
    memo_books = [b for b in total_books if b["isbn"] in memo_isbns]
    if len(total_books) < 4 or len(memo_books) < 2:
        return None
    top_row = min(enriched.keys())
    row_counts = Counter(b["shelf_index"] for b in memo_books)
    top_ratio = row_counts.get(top_row, 0) / len(memo_books)
    overall_top_ratio = sum(1 for b in total_books if b["shelf_index"] == top_row) / len(total_books)
    if top_ratio - overall_top_ratio >= 0.25:
        return {
            "pattern_id": "interest_arrangement", "label": "興味の並び",
            "fact": "感想メモを書いた（＝関心の高い）本が、いちばん上の段に集まる傾向があります。",
            "isbns": [b["isbn"] for b in memo_books],
        }
    return None


def _finding_transition_awareness(enriched):
    gaps_at_change, gaps_no_change = [], []
    for books in enriched.values():
        for prev, cur in zip(books, books[1:]):
            gap = cur["_x_px"] - (prev["_x_px"] + prev["_width_px"])
            changed = (
                (prev["_ndc_l1"] != cur["_ndc_l1"])
                or (prev["_author"] and cur["_author"] and prev["_author"] != cur["_author"])
                or (prev["_color"] != cur["_color"])
            )
            (gaps_at_change if changed else gaps_no_change).append(gap)
    if len(gaps_at_change) < 2 or not gaps_no_change:
        return None
    avg_change = sum(gaps_at_change) / len(gaps_at_change)
    avg_no_change = sum(gaps_no_change) / len(gaps_no_change)
    if avg_change - avg_no_change >= 5:
        return {
            "pattern_id": "transition_awareness", "label": "変わり目の意識",
            "fact": "ジャンルや著者、色が変わる境目で、本の間隔が広めに取られている傾向があります。",
            "isbns": [],
        }
    return None


def _finding_row_density(enriched):
    densities = {}
    for shelf_idx, books in enriched.items():
        if not books:
            continue
        span = books[-1]["_x_px"] + books[-1]["_width_px"] - books[0]["_x_px"]
        if span <= 0:
            continue
        densities[shelf_idx] = sum(b["_width_px"] for b in books) / span
    if len(densities) < 2:
        return None
    rows_sorted = sorted(densities.items())
    mid = len(rows_sorted) // 2
    top_half = [d for _, d in rows_sorted[: mid + 1]]
    bottom_half = [d for _, d in rows_sorted[mid:]]
    avg_top, avg_bottom = sum(top_half) / len(top_half), sum(bottom_half) / len(bottom_half)
    if avg_top - avg_bottom >= 0.15:
        fact = "上の段は本がぎっしり詰まっていて、下の段は余裕があるようです。"
    elif avg_bottom - avg_top >= 0.15:
        fact = "下の段は本がぎっしり詰まっていて、上の段は余裕があるようです。"
    else:
        return None
    return {"pattern_id": "row_density", "label": "本の密度", "fact": fact, "isbns": []}


def _finding_floating_books(enriched):
    floaters = []
    for books in enriched.values():
        for i, b in enumerate(books):
            if i == 0 or i == len(books) - 1:
                continue
            left, right = books[i - 1], books[i + 1]

            def _shares(a, other):
                return (
                    (a["_ndc_l1"] and a["_ndc_l1"] == other["_ndc_l1"])
                    or (a["_author"] and a["_author"] == other["_author"])
                    or (a["_color"] and a["_color"] == other["_color"])
                )

            if _shares(b, left) or _shares(b, right):
                continue
            if abs((b["height_mm"] or 0) - (left["height_mm"] or 0)) >= 30 and \
               abs((b["height_mm"] or 0) - (right["height_mm"] or 0)) >= 30:
                floaters.append(b)
    if not floaters:
        return None
    top = floaters[0]
    return {
        "pattern_id": "floating_books", "label": "浮いている本",
        "fact": f"「{top['title']}」は、隣の本とジャンル・著者・色・高さのどれも共通点がなく、少し浮いた存在になっています。",
        "isbns": [b["isbn"] for b in floaters[:5]],
    }


def _finding_edge_big_books(enriched):
    edge_hits, eligible_rows, example = 0, 0, None
    for books in enriched.values():
        if len(books) < 4:
            continue
        eligible_rows += 1
        max_idx = max(range(len(books)), key=lambda i: books[i]["height_mm"] or 0)
        if max_idx == 0 or max_idx == len(books) - 1:
            edge_hits += 1
            if example is None:
                example = books[max_idx]
    if eligible_rows < 2 or edge_hits / eligible_rows < 0.6:
        return None
    return {
        "pattern_id": "edge_big_books", "label": "端に大きな本",
        "fact": f"「{example['title']}」のように、背の高い本を段の端に置く配置が複数の段で見られます。",
        "isbns": [example["isbn"]],
    }


_PATTERN_CHECKS = [
    _finding_height_order,
    _finding_genre_grouping,
    _finding_height_genre_priority,
    _finding_color_grouping,
    _finding_author_grouping,
    _finding_row_size_by_position,
    _finding_transition_awareness,
    _finding_row_density,
    _finding_floating_books,
    _finding_edge_big_books,
]


def analyze_shelf_patterns(shelves: dict[int, list[dict]], memo_isbns: set[str] | None = None) -> dict:
    """
    shelves: {shelf_index: [{"isbn", "title", "x_pos", "height_mm", "pages",
                              "ndc", "authors", "spine_color", "shelf_index"}, ...]}
    memo_isbns: ユーザーが感想メモを書いた本のISBN集合（興味の並び判定に使う）
    """
    enriched: dict[int, list[dict]] = {}
    for shelf_idx, books in shelves.items():
        ordered = sorted(books, key=lambda b: b.get("x_pos") or 0)
        for b in ordered:
            b["_ndc_l1"] = _ndc_l1(b.get("ndc"))
            b["_color"] = _color_bucket(b.get("spine_color"))
            b["_author"] = _first_author(b.get("authors"))
            b["_width_px"] = _spine_width_px(b.get("pages"), b.get("height_mm"))
            b["_x_px"] = (b.get("x_pos") or 0) * PX_TO_MM_SCALE
        enriched[shelf_idx] = ordered

    findings = [r for check in _PATTERN_CHECKS if (r := check(enriched))]

    interest = _finding_interest_arrangement(enriched, memo_isbns or set())
    if interest:
        findings.append(interest)

    if len(findings) <= 1:
        total_books = [b for books in enriched.values() for b in books]
        distinct_colors = {b["_color"] for b in total_books if b["_color"]}
        if len(total_books) >= 6 and len(distinct_colors) >= 4:
            findings.append({
                "pattern_id": "designed_layout", "label": "デザイン重視の配置",
                "fact": "高さ・ジャンル・著者・色のいずれにも強い規則性は見られず、見た目の印象を優先してデザインされた配置かもしれません。",
                "isbns": [],
            })

    return {"findings": findings, "reference_patterns": REFERENCE_PATTERNS}
