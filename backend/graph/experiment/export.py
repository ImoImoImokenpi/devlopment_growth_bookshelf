"""研究者向けエクスポート（CSV/JSON）。

GuessRecord（Neo4j）とTrialAssignment（SQLite、表示順・フェーズ情報）を
viewer_id×owner_idで突き合わせてフラット化する。
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from graph.experiment.guess_records import list_all_guesses
from graph.experiment.assignment import list_all_assignments

EXPORT_FIELDS = [
    "participant_id", "owner_id", "trial_index", "phase",
    "target_type", "condition", "pre_text", "post_text",
    "target_group_id", "created_at", "updated_at",
]


def export_guess_records(db: Session) -> list[dict]:
    assignments_by_pair = {
        (a["participant_id"], a["owner_id"]): a for a in list_all_assignments(db)
    }

    rows = []
    for guess in list_all_guesses():
        assignment = assignments_by_pair.get((guess["viewer_id"], guess["owner_id"]))
        rows.append({
            "participant_id": guess["viewer_id"],
            "owner_id": guess["owner_id"],
            "trial_index": assignment["trial_index"] if assignment else None,
            "phase": assignment["phase"] if assignment else None,
            "target_type": guess["target_type"],
            "condition": guess["condition"],
            "pre_text": guess["pre_text"],
            "post_text": guess["post_text"],
            "target_group_id": guess["target_group_id"],
            "created_at": guess["created_at"],
            "updated_at": guess["updated_at"],
        })
    rows.sort(key=lambda r: (r["participant_id"], r["trial_index"] if r["trial_index"] is not None else -1))
    return rows


def compute_progress(db: Session) -> list[dict]:
    """参加者ごとのphase1/phase2の進捗（完了試行数/割当試行数）。
    1試行の完了は「全体・部分どちらのGuessRecordもpost_textが埋まっていること」で判定する。"""
    assignments = list_all_assignments(db)

    completed_pairs: set[tuple[str, str]] = set()
    post_text_by_pair: dict[tuple[str, str], set[str]] = {}
    for guess in list_all_guesses():
        if not guess.get("post_text"):
            continue
        key = (guess["viewer_id"], guess["owner_id"])
        post_text_by_pair.setdefault(key, set()).add(guess["target_type"])
    for key, target_types in post_text_by_pair.items():
        if {"overall", "partial"}.issubset(target_types):
            completed_pairs.add(key)

    progress: dict[str, dict] = {}
    for a in assignments:
        pid = a["participant_id"]
        entry = progress.setdefault(pid, {
            "participant_id": pid,
            "phase1_total": 0, "phase1_completed": 0,
            "phase2_total": 0, "phase2_completed": 0,
        })
        is_done = (pid, a["owner_id"]) in completed_pairs
        if a["phase"] == "phase1":
            entry["phase1_total"] += 1
            if is_done:
                entry["phase1_completed"] += 1
        elif a["phase"] == "phase2":
            entry["phase2_total"] += 1
            if is_done:
                entry["phase2_completed"] += 1

    return sorted(progress.values(), key=lambda e: e["participant_id"])
