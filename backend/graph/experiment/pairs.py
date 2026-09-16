"""2.3 対照ペア選定機能。

全参加者の最新StyleProfileから、構造指標の距離が大きい「対照的なペア」を抽出する。
実験の刺激本棚割り当て（experiment.assignment）で、意図的に対照的なペアを
混ぜ込むために使う。

指標ごとに値のレンジが大きく異なる（例: avg_group_size は0〜15程度、
isolated_ratio は0〜1）ため、素のユークリッド距離を取るとレンジの広い指標に
支配されてしまう。そのため参加者間でz-score正規化してから距離を計算する。
"""
from __future__ import annotations

import statistics

from graph.style_projection.diff import (
    METRIC_FIELDS,
    compute_style_diff,
    get_latest_style_profile,
    list_participants_with_profiles,
)


def _normalized_vectors(profiles: dict[str, dict]) -> dict[str, dict[str, float]]:
    """指標ごとにz-score正規化した値を返す。値が欠けている参加者が1人でもいる指標
    （例: GDS未使用環境のmodularity_nmi）は、その指標自体を距離計算から除外する。
    全員が同じ値（stdev=0）の指標も、距離への寄与がないため除外する。"""
    usable_fields = [
        f for f in METRIC_FIELDS
        if all(p.get(f) is not None for p in profiles.values())
    ]

    normalized: dict[str, dict[str, float]] = {pid: {} for pid in profiles}
    for field in usable_fields:
        values = [profiles[pid][field] for pid in profiles]
        mean = statistics.fmean(values)
        stdev = statistics.pstdev(values)
        if stdev == 0:
            continue
        for pid in profiles:
            normalized[pid][field] = (profiles[pid][field] - mean) / stdev

    return normalized


def _distance(a: dict[str, float], b: dict[str, float]) -> float:
    shared_fields = set(a) & set(b)
    return sum((a[f] - b[f]) ** 2 for f in shared_fields) ** 0.5


def find_contrastive_pairs(top_n: int = 5) -> list[dict]:
    """StyleProfileを持つ全参加者から、正規化ユークリッド距離が大きい順に
    上位top_n組のペアを返す。各ペアには compute_style_diff と同じ形式の
    指標別内訳も添える。"""
    entries = list_participants_with_profiles()
    profiles: dict[str, dict] = {}
    for entry in entries:
        pid = entry["participant_id"]
        profile = get_latest_style_profile(pid)
        if profile is not None:
            profiles[pid] = profile

    if len(profiles) < 2:
        return []

    normalized = _normalized_vectors(profiles)

    pairs = []
    participant_ids = sorted(profiles.keys())
    for i, a in enumerate(participant_ids):
        for b in participant_ids[i + 1:]:
            distance = _distance(normalized[a], normalized[b])
            pairs.append({"participant_a": a, "participant_b": b, "distance": round(distance, 4)})

    pairs.sort(key=lambda p: -p["distance"])
    top = pairs[:top_n]
    for pair in top:
        pair["diffs"] = compute_style_diff(
            viewer_id=pair["participant_a"], owner_id=pair["participant_b"]
        )["diffs"]
    return top
