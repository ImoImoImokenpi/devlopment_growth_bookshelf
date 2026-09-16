"""4章 実験フロー制御: TrialAssignment生成ロジック。

対照ペア（experiment.pairs）を優先的に混ぜ込みつつ、ExperimentConfigに従って
phase1（experimental/control）・phase2（transfer, 差分提示なし）の試行を
各参加者に割り当てる。試行数・条件配分・対照ペアの混入数はExperimentConfigで
研究者がコード修正なしに調整できる。
"""
from __future__ import annotations

import random

from sqlalchemy.orm import Session

from graph.experiment.guess_records import list_guesses_by_viewer
from graph.experiment.pairs import find_contrastive_pairs
from models import ExperimentConfig, TrialAssignment
from participant import ALL_PARTICIPANT_IDS, PROTOTYPE_PARTICIPANT_ID

# 割当の再現性のための固定シード。研究者が同じExperimentConfigで再生成すれば
# 同じ割当が得られる（デバッグ・レビューのしやすさのため）。
_ASSIGNMENT_SEED = 0


def get_or_create_config(db: Session) -> ExperimentConfig:
    config = db.query(ExperimentConfig).first()
    if not config:
        config = ExperimentConfig()
        db.add(config)
        db.commit()
        db.refresh(config)
    return config


def _eligible_participant_ids() -> list[str]:
    """プロトタイプ用データ(P00)は刺激本棚・閲覧者候補から除外する。"""
    return [pid for pid in ALL_PARTICIPANT_IDS if pid != PROTOTYPE_PARTICIPANT_ID]


def _has_existing_guesses(participant_id: str) -> bool:
    return len(list_guesses_by_viewer(participant_id)) > 0


def _pick_condition(config: ExperimentConfig, rng: random.Random) -> str:
    return "experimental" if rng.random() < config.condition_ratio else "control"


def generate_assignments(
    db: Session,
    participant_ids: list[str] | None = None,
    force: bool = False,
) -> dict:
    """対象参加者ごとにTrialAssignmentを生成する（既存分は削除して作り直す）。
    force=False の場合、既にGuessRecordが1件でもある参加者は収集済みデータを
    壊さないようスキップする。戻り値は生成した/スキップした参加者ID一覧。"""
    config = get_or_create_config(db)

    all_ids = _eligible_participant_ids()
    targets = [pid for pid in (participant_ids or all_ids) if pid in all_ids]

    contrastive_pairs = find_contrastive_pairs(top_n=len(all_ids) or 1)
    partners_by_pid: dict[str, list[str]] = {pid: [] for pid in all_ids}
    for pair in contrastive_pairs:
        a, b = pair["participant_a"], pair["participant_b"]
        partners_by_pid.setdefault(a, []).append(b)
        partners_by_pid.setdefault(b, []).append(a)

    rng = random.Random(_ASSIGNMENT_SEED)
    generated, skipped = [], []

    for pid in targets:
        if not force and _has_existing_guesses(pid):
            skipped.append(pid)
            continue

        db.query(TrialAssignment).filter(
            TrialAssignment.participant_id == pid
        ).delete(synchronize_session=False)

        candidates = [o for o in all_ids if o != pid]
        rng.shuffle(candidates)

        contrastive = [o for o in partners_by_pid.get(pid, []) if o in candidates]
        chosen_contrastive = contrastive[:config.contrastive_pair_count]
        remaining = [o for o in candidates if o not in chosen_contrastive]

        phase1_owners = (chosen_contrastive + remaining)[:config.phase1_trial_count]
        remaining_for_transfer = [o for o in candidates if o not in phase1_owners]
        phase2_owners = remaining_for_transfer[:config.transfer_trial_count]

        fixed_condition = (
            _pick_condition(config, rng) if config.condition_assignment_mode == "participant" else None
        )

        trial_index = 0
        for owner_id in phase1_owners:
            condition = fixed_condition if fixed_condition is not None else _pick_condition(config, rng)
            db.add(TrialAssignment(
                participant_id=pid, owner_id=owner_id, trial_index=trial_index,
                phase="phase1", condition=condition,
            ))
            trial_index += 1

        for owner_id in phase2_owners:
            db.add(TrialAssignment(
                participant_id=pid, owner_id=owner_id, trial_index=trial_index,
                phase="phase2", condition="transfer",
            ))
            trial_index += 1

        generated.append(pid)

    db.commit()
    return {"generated": generated, "skipped": skipped}


def get_condition(db: Session, participant_id: str, owner_id: str) -> str | None:
    row = (
        db.query(TrialAssignment)
        .filter(TrialAssignment.participant_id == participant_id, TrialAssignment.owner_id == owner_id)
        .first()
    )
    return row.condition if row else None


def list_assignments(db: Session, participant_id: str) -> list[dict]:
    rows = (
        db.query(TrialAssignment)
        .filter(TrialAssignment.participant_id == participant_id)
        .order_by(TrialAssignment.trial_index)
        .all()
    )
    return [
        {"owner_id": r.owner_id, "trial_index": r.trial_index, "phase": r.phase, "condition": r.condition}
        for r in rows
    ]


def list_all_assignments(db: Session) -> list[dict]:
    rows = (
        db.query(TrialAssignment)
        .order_by(TrialAssignment.participant_id, TrialAssignment.trial_index)
        .all()
    )
    return [
        {
            "participant_id": r.participant_id, "owner_id": r.owner_id,
            "trial_index": r.trial_index, "phase": r.phase, "condition": r.condition,
        }
        for r in rows
    ]
