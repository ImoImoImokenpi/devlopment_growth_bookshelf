"""参加者間（閲覧者/所有者）の投影スタイル差分計算。

出力は、後段のLLM翻訳モジュール（本タスクの範囲外）にそのまま渡せるよう
diff = viewer - owner の形でJSON化する。
"""
from __future__ import annotations

from graph.main_kg.neo4j_driver import get_session

_METRIC_FIELDS = [
    "avg_group_size",
    "stdev_group_size",
    "isolated_ratio",
    "avg_multi_membership",
    "max_depth",
    "clustering_coefficient",
    "modularity",
    "modularity_nmi",
]

# 他モジュール（experiment.pairsの対照ペア選定など）から参照するための公開名。
METRIC_FIELDS = _METRIC_FIELDS


def get_latest_style_profile(participant_id: str) -> dict | None:
    with get_session() as session:
        row = session.run(
            """
            MATCH (:Participant {participantId: $pid})-[:HAS_PROFILE]->(sp:StyleProfile)
            RETURN sp
            ORDER BY sp.computed_at DESC
            LIMIT 1
            """,
            pid=participant_id,
        ).single()
        if not row:
            return None
        profile = dict(row["sp"])
        if profile.get("computed_at") is not None:
            profile["computed_at"] = str(profile["computed_at"])
        return profile


def list_participants_with_profiles() -> list[dict]:
    """StyleProfileを1件以上持つ参加者の一覧（新規閲覧ページの参加者選択に使う）。"""
    with get_session() as session:
        rows = session.run(
            """
            MATCH (p:Participant)-[:HAS_PROFILE]->(sp:StyleProfile)
            WITH p, count(sp) AS profile_count, max(sp.computed_at) AS latest_computed_at
            RETURN p.participantId AS participant_id, p.role AS role,
                   profile_count, latest_computed_at
            ORDER BY participant_id
            """
        )
        result = []
        for r in rows:
            d = dict(r)
            if d.get("latest_computed_at") is not None:
                d["latest_computed_at"] = str(d["latest_computed_at"])
            result.append(d)
        return result


def get_style_profile_history(participant_id: str) -> list[dict]:
    """その参加者のStyleProfileを、計算した順（昔→今）に全件返す。
    上書きせず追記式で保存しているので、これがそのまま「変遷」になる。"""
    with get_session() as session:
        rows = session.run(
            """
            MATCH (:Participant {participantId: $pid})-[:HAS_PROFILE]->(sp:StyleProfile)
            RETURN sp
            ORDER BY sp.computed_at ASC
            """,
            pid=participant_id,
        )
        profiles = []
        for r in rows:
            profile = dict(r["sp"])
            if profile.get("computed_at") is not None:
                profile["computed_at"] = str(profile["computed_at"])
            profiles.append(profile)
        return profiles


def _diff_metrics(from_profile: dict, to_profile: dict) -> dict:
    diffs = {}
    for field in _METRIC_FIELDS:
        a, b = from_profile.get(field), to_profile.get(field)
        diffs[field] = {
            "from": a,
            "to": b,
            "diff": round(b - a, 4) if a is not None and b is not None else None,
        }
    return diffs


def compute_profile_diff(
    participant_id: str,
    from_profile_id: str | None = None,
    to_profile_id: str | None = None,
) -> dict:
    """同じ参加者の、昔のStyleProfileと今のStyleProfileを比較する。
    profile_idを省略した場合は「昔」=最初のスナップショット、「今」=最新
    のスナップショットを自動的に使う。"""
    history = get_style_profile_history(participant_id)
    if not history:
        raise ValueError(f"StyleProfileが見つかりません: participant_id={participant_id}")

    by_id = {p["profile_id"]: p for p in history}
    if from_profile_id and from_profile_id not in by_id:
        raise ValueError(f"profile_idが見つかりません: {from_profile_id}")
    if to_profile_id and to_profile_id not in by_id:
        raise ValueError(f"profile_idが見つかりません: {to_profile_id}")

    from_profile = by_id[from_profile_id] if from_profile_id else history[0]
    to_profile = by_id[to_profile_id] if to_profile_id else history[-1]

    return {
        "participant_id": participant_id,
        "from": from_profile,
        "to": to_profile,
        "diffs": _diff_metrics(from_profile, to_profile),
    }


def compute_style_diff(viewer_id: str, owner_id: str) -> dict:
    """viewer/ownerそれぞれの最新StyleProfileを取得し、指標ごとの差分を返す。
    diff = viewer - owner。どちらかにStyleProfileが無ければ ValueError。"""
    viewer_profile = get_latest_style_profile(viewer_id)
    owner_profile = get_latest_style_profile(owner_id)

    if viewer_profile is None:
        raise ValueError(f"StyleProfileが見つかりません: viewer_id={viewer_id}")
    if owner_profile is None:
        raise ValueError(f"StyleProfileが見つかりません: owner_id={owner_id}")

    diffs = {}
    for field in _METRIC_FIELDS:
        v = viewer_profile.get(field)
        o = owner_profile.get(field)
        diffs[field] = {
            "viewer": v,
            "owner": o,
            "diff": round(v - o, 4) if v is not None and o is not None else None,
        }

    return {
        "viewer_id": viewer_id,
        "owner_id": owner_id,
        "viewer_profile_id": viewer_profile.get("profile_id"),
        "owner_profile_id": owner_profile.get("profile_id"),
        "diffs": diffs,
    }
