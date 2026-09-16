"""実験フロー制御システムの動作確認用スクリプト。

style_projection_demo.py のダミー生成関数を再利用して、P01〜P04として
StyleProfileが対照的になるよう偏らせた参加者を作り、
  1. TrialAssignmentの生成（対照ペアの混入、条件配分）
  2. experimental/control/transferそれぞれの条件で
     事前推測(全体・部分)→（experimentalのみ）構造差分・意味差分カード相当の生成
     →事後推測、を一通り実行
まで、UI無しでバックエンドの筋を通す。

実行:
    cd backend
    python -m scripts.experiment_demo
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database import SessionLocal
from graph.style_projection.schema import ensure_style_projection_schema
from graph.style_projection.ingest import ingest_shelf_snapshot
from graph.style_projection.metrics import save_style_profile
from graph.style_projection.diff import compute_style_diff
from graph.style_projection.groups import get_candidate_groups
from graph.experiment.schema import ensure_experiment_schema
from graph.experiment.assignment import generate_assignments, list_assignments, get_condition
from graph.experiment.guess_records import save_pre_guess, save_post_guess, get_guess
from graph.experiment.semantic_diff import build_semantic_diff
from graph.experiment.pairs import find_contrastive_pairs
from graph.experiment.export import export_guess_records, compute_progress
from utils.llm_provider import get_llm_client
from scripts.style_projection_demo import _grouped_snapshot, _scattered_snapshot


def _seed_participants() -> list[str]:
    snapshots = [
        _grouped_snapshot("P01", "owner", "proposed_ui", n_books=24, with_subgroup=True),
        _scattered_snapshot("P02", "owner", "proposed_ui", n_books=20),
        _grouped_snapshot("P03", "owner", "proposed_ui", n_books=18, with_subgroup=False),
        _scattered_snapshot("P04", "owner", "proposed_ui", n_books=16),
    ]
    for snapshot in snapshots:
        result = ingest_shelf_snapshot(snapshot, adjacency_mode="knn", k_neighbors=3)
        print(f"[ingest] {json.dumps(result, ensure_ascii=False)}")

    pids = [s["participant_id"] for s in snapshots]
    for pid in pids:
        profile = save_style_profile(pid)
        print(f"[profile] {json.dumps(profile, ensure_ascii=False, default=str)}")
    return pids


def _run_trial(llm, viewer_id: str, owner_id: str, condition_expected: str) -> None:
    print(f"\n--- trial: viewer={viewer_id} owner={owner_id} (expected condition={condition_expected}) ---")

    condition = condition_expected  # 実際のGuessRecordはassignment経由で解決済みの値をそのまま使う

    save_pre_guess(
        viewer_id=viewer_id, owner_id=owner_id, target_type="overall",
        text=f"{owner_id}さんは几帳面に整理する人だと思う", condition=condition,
    )

    candidates = get_candidate_groups(owner_id)
    if not candidates:
        print("  候補グループなし（スキップ）")
        return
    chosen = candidates[0]
    save_pre_guess(
        viewer_id=viewer_id, owner_id=owner_id, target_type="partial",
        text="同じジャンルの本をまとめている気がする", condition=condition,
        target_group_id=chosen["group_id"],
        candidate_group_ids=[c["group_id"] for c in candidates],
    )

    if condition == "transfer":
        print("  [transfer] 差分提示なし、事後推測へ直行")
    elif condition == "control":
        print("  [control] 固定ヒントのみ（LLM不使用）")
    else:
        diff = compute_style_diff(viewer_id=viewer_id, owner_id=owner_id)
        print(f"  [structural diff] {json.dumps(diff['diffs'], ensure_ascii=False)}")
        try:
            semantic = build_semantic_diff(llm, "同じジャンルの本をまとめている気がする", chosen["group_id"])
            print(f"  [semantic diff] {json.dumps(semantic, ensure_ascii=False)}")
        except Exception as e:
            print(f"  [semantic diff] 生成失敗（LLM未接続の可能性）: {e}")

    save_post_guess(viewer_id, owner_id, "overall", f"{owner_id}さんは思ったより文脈で整理していそう")
    save_post_guess(viewer_id, owner_id, "partial", "ジャンルというより、読んだ時期でまとまっているのかもしれない")

    overall = get_guess(viewer_id, owner_id, "overall")
    partial = get_guess(viewer_id, owner_id, "partial")
    print(f"  [saved overall] pre={overall['pre_text']!r} post={overall['post_text']!r} condition={overall['condition']}")
    print(f"  [saved partial] pre={partial['pre_text']!r} post={partial['post_text']!r} condition={partial['condition']}")


def run_demo() -> None:
    ensure_style_projection_schema()
    ensure_experiment_schema()

    pids = _seed_participants()

    print("\n[contrastive pairs]")
    pairs = find_contrastive_pairs(top_n=3)
    for p in pairs:
        print(f"  {p['participant_a']} <-> {p['participant_b']}: distance={p['distance']}")

    db = SessionLocal()
    try:
        result = generate_assignments(db, participant_ids=pids, force=True)
        print(f"\n[assignment generated] {result}")

        for pid in pids:
            assignments = list_assignments(db, pid)
            print(f"[assignments for {pid}] {assignments}")

        llm = get_llm_client()
        for pid in pids:
            assignments = list_assignments(db, pid)
            for a in assignments:
                _run_trial(llm, pid, a["owner_id"], a["condition"])

        print("\n[progress]")
        print(json.dumps(compute_progress(db), ensure_ascii=False, indent=2))

        print("\n[export]")
        print(json.dumps(export_guess_records(db), ensure_ascii=False, indent=2)[:2000])
    finally:
        db.close()


if __name__ == "__main__":
    run_demo()
