"""投影スタイル分析システムの動作確認用スクリプト。

ダミーの参加者3人分（各20〜30冊、うち1人はサブグループも含む）を生成して
投入し、構造指標の計算・保存、差分計算までを一通り実行する。

実行:
    cd backend
    python -m scripts.style_projection_demo
"""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from graph.style_projection.schema import ensure_style_projection_schema
from graph.style_projection.ingest import ingest_shelf_snapshot
from graph.style_projection.metrics import save_style_profile
from graph.style_projection.diff import compute_style_diff

random.seed(42)

GENRES = ["SF", "ミステリ", "歴史", "経営", "エッセイ"]
AUTHORS = [f"著者{i}" for i in range(1, 9)]


def _make_work(i: int) -> dict:
    genre = random.choice(GENRES)
    return {
        "work_id": f"WK{i:04d}",
        "title": f"{genre}の本 第{i}巻",
        "author": random.choice(AUTHORS),
        "published_year": random.randint(1990, 2026),
        "genre": genre,
    }


def _grouped_snapshot(participant_id: str, role: str, condition: str, n_books: int, with_subgroup: bool) -> dict:
    """本を数個のグループに、密にまとめて配置する参加者（几帳面な投影スタイル）。"""
    groups = [{"group_id": f"{participant_id}_g{g}", "name": f"棚{g}", "created_by": "manual"} for g in range(4)]
    if with_subgroup:
        groups.append({
            "group_id": f"{participant_id}_g0_sub",
            "name": "お気に入り",
            "created_by": "manual",
            "parent_group_id": f"{participant_id}_g0",
        })

    books = []
    for i in range(n_books):
        shelf = i % 4
        group_ids = [f"{participant_id}_g{shelf}"]
        if with_subgroup and shelf == 0 and i % 3 == 0:
            group_ids.append(f"{participant_id}_g0_sub")
        # 孤立本を数冊まぜる
        if i % 11 == 0:
            group_ids = []

        books.append({
            "shelved_id": f"{participant_id}_s{i:03d}",
            "x": (i % 8) * 10.0,
            "y": float(shelf) * 30.0,
            "shelf_id": f"shelf_{shelf}",
            "condition": condition,
            "work": _make_work(i + hash(participant_id) % 1000),
            "group_ids": group_ids,
            "comments": (
                [{"text": f"{i}冊目の感想メモ"}] if i % 5 == 0 else []
            ),
        })
    return {"participant_id": participant_id, "role": role, "groups": groups, "books": books}


def _scattered_snapshot(participant_id: str, role: str, condition: str, n_books: int) -> dict:
    """グループをほとんど作らず、座標もばらけて置く参加者（自由な投影スタイル）。"""
    groups = [{"group_id": f"{participant_id}_g0", "name": "なんとなく", "created_by": "manual"}]
    books = []
    for i in range(n_books):
        group_ids = [f"{participant_id}_g0"] if i % 4 == 0 else []
        books.append({
            "shelved_id": f"{participant_id}_s{i:03d}",
            "x": random.uniform(0, 80),
            "y": random.uniform(0, 90),
            "shelf_id": f"shelf_{i % 3}",
            "condition": condition,
            "work": _make_work(i + hash(participant_id) % 1000),
            "group_ids": group_ids,
            "comments": [],
        })
    return {"participant_id": participant_id, "role": role, "groups": groups, "books": books}


def run_demo() -> None:
    ensure_style_projection_schema()

    snapshots = [
        _grouped_snapshot("SP_OWNER1", "owner", "proposed_ui", n_books=28, with_subgroup=True),
        _scattered_snapshot("SP_VIEWER1", "viewer", "proposed_ui", n_books=22),
        _grouped_snapshot("SP_OWNER2", "owner", "control_ui", n_books=25, with_subgroup=False),
    ]

    for snapshot in snapshots:
        result = ingest_shelf_snapshot(snapshot, adjacency_mode="knn", k_neighbors=3)
        print(f"[ingest] {json.dumps(result, ensure_ascii=False)}")

    profiles = {}
    for snapshot in snapshots:
        pid = snapshot["participant_id"]
        profile = save_style_profile(pid)
        profiles[pid] = profile
        print(f"[profile] {json.dumps(profile, ensure_ascii=False, default=str)}")

    diff = compute_style_diff(viewer_id="SP_VIEWER1", owner_id="SP_OWNER1")
    print(f"[diff] {json.dumps(diff, ensure_ascii=False, default=str)}")


if __name__ == "__main__":
    run_demo()
