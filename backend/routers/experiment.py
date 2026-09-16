"""実験フロー制御（4章）・実験管理画面（3.5）向けAPI。

設定(ExperimentConfig)・割当(TrialAssignment)・対照ペア選定・進捗確認・
CSV/JSONエクスポートをまとめる。研究者向けの画面からのみ叩かれる想定で、
参加者本人向けの推測フロー(knowledge_graph.py)からは
experiment.assignment.get_condition のみを直接呼ぶ（このルータは経由しない）。
"""
from __future__ import annotations

import csv
import io

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from models import ExperimentConfig
from participant import is_valid_participant_id
from graph.experiment.assignment import (
    get_or_create_config, generate_assignments, list_assignments, list_all_assignments,
)
from graph.experiment.pairs import find_contrastive_pairs
from graph.experiment.export import export_guess_records, compute_progress, EXPORT_FIELDS

router = APIRouter(prefix="/experiment", tags=["experiment"])


class ExperimentConfigBody(BaseModel):
    phase1_trial_count: int
    transfer_trial_count: int
    contrastive_pair_count: int
    condition_assignment_mode: str  # "participant" | "trial"
    condition_ratio: float


def _config_to_dict(config: ExperimentConfig) -> dict:
    return {
        "phase1_trial_count": config.phase1_trial_count,
        "transfer_trial_count": config.transfer_trial_count,
        "contrastive_pair_count": config.contrastive_pair_count,
        "condition_assignment_mode": config.condition_assignment_mode,
        "condition_ratio": config.condition_ratio,
        "updated_at": config.updated_at.isoformat() if config.updated_at else None,
    }


@router.get("/config")
def get_config(db: Session = Depends(get_db)):
    return _config_to_dict(get_or_create_config(db))


@router.put("/config")
def put_config(body: ExperimentConfigBody, db: Session = Depends(get_db)):
    if body.condition_assignment_mode not in ("participant", "trial"):
        raise HTTPException(status_code=400, detail="condition_assignment_mode は participant か trial のいずれかです")
    if not (0.0 <= body.condition_ratio <= 1.0):
        raise HTTPException(status_code=400, detail="condition_ratio は0〜1の範囲で指定してください")
    if body.phase1_trial_count < 1 or body.transfer_trial_count < 0 or body.contrastive_pair_count < 0:
        raise HTTPException(status_code=400, detail="試行数は0以上（phase1_trial_countは1以上）で指定してください")

    config = get_or_create_config(db)
    config.phase1_trial_count = body.phase1_trial_count
    config.transfer_trial_count = body.transfer_trial_count
    config.contrastive_pair_count = body.contrastive_pair_count
    config.condition_assignment_mode = body.condition_assignment_mode
    config.condition_ratio = body.condition_ratio
    db.commit()
    db.refresh(config)
    return _config_to_dict(config)


class GenerateAssignmentsBody(BaseModel):
    participant_ids: list[str] | None = None
    force: bool = False


@router.post("/assignment/generate")
def post_generate_assignments(body: GenerateAssignmentsBody, db: Session = Depends(get_db)):
    if body.participant_ids:
        for pid in body.participant_ids:
            if not is_valid_participant_id(pid):
                raise HTTPException(status_code=400, detail=f"participant_id が不正です: {pid}")
    return generate_assignments(db, participant_ids=body.participant_ids, force=body.force)


@router.get("/assignment/{participant_id}")
def get_assignment(participant_id: str, db: Session = Depends(get_db)):
    if not is_valid_participant_id(participant_id):
        raise HTTPException(status_code=400, detail="participant_id が不正です")
    return {"assignments": list_assignments(db, participant_id)}


@router.get("/assignment")
def get_all_assignments(db: Session = Depends(get_db)):
    return {"assignments": list_all_assignments(db)}


@router.get("/contrastive-pairs")
def get_contrastive_pairs(top_n: int = 5):
    if top_n < 1:
        raise HTTPException(status_code=400, detail="top_n は1以上で指定してください")
    return {"pairs": find_contrastive_pairs(top_n=top_n)}


@router.get("/progress")
def get_progress(db: Session = Depends(get_db)):
    return {"progress": compute_progress(db)}


@router.get("/export.json")
def export_json(db: Session = Depends(get_db)):
    return {"records": export_guess_records(db)}


@router.get("/export.csv")
def export_csv(db: Session = Depends(get_db)):
    rows = export_guess_records(db)
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=EXPORT_FIELDS)
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    buffer.seek(0)
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=guess_records.csv"},
    )
