"""
Pipeline state machine endpoints.

Each stage has:
  - POST /{stage}/advance  — gate check, advance if passes
  - POST /{stage}/skip     — record warning, advance unconditionally
  - GET  /status           — current stage, all stages with status
"""
from uuid import UUID
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
import asyncio

from app.db.base import get_db
from app.models.project import Project, ProjectStage, StageEvent
from app.models.hypothesis import Hypothesis
from app.models.strategy import StrategyVersion
from app.models.data_split import DataSplit as DataSplitModel
from app.models.job import Job, JobStatus, JobType
from app.models.user import User
from app.core.security import get_current_user
from app.services.llm import generate_strategy_code, get_skip_warning
from forge_engine.lookahead import scan_strategy_code
from forge_engine.split import compute_recommended_split, apply_split, DataSplit
from forge_engine.data import load_instrument

router = APIRouter()


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------

STAGE_NAMES = {
    1: "Hypothesis",
    2: "Code",
    3: "Data Split",
    4: "Development",
    5: "Validation",
    6: "Done",
}


@router.get("/status")
def get_status(
    project_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    project = _get_project(project_id, user.id, db)
    events = db.query(StageEvent).filter(StageEvent.project_id == project.id).all()
    skipped = {e.stage for e in events if e.action == "skipped"}
    completed = {e.stage for e in events if e.action == "completed"}

    stages = []
    for stage_num in range(1, 7):
        status = "locked"
        if stage_num < project.current_stage:
            status = "skipped" if stage_num in skipped else "complete"
        elif stage_num == project.current_stage:
            status = "active"
        stages.append({
            "stage": stage_num,
            "name": STAGE_NAMES[stage_num],
            "status": status,
            "skipped": stage_num in skipped,
        })

    return {
        "current_stage": project.current_stage,
        "stages": stages,
        "oos_consumed": project.oos_consumed,
    }


# ---------------------------------------------------------------------------
# Skip a stage
# ---------------------------------------------------------------------------

class SkipRequest(BaseModel):
    confirmed: bool = False


@router.get("/{stage}/skip-warning")
def get_skip_warning_text(stage: int, project_id: UUID):
    return {"stage": stage, "warning": get_skip_warning(stage)}


@router.post("/{stage}/skip")
def skip_stage(
    project_id: UUID,
    stage: int,
    req: SkipRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    project = _get_project(project_id, user.id, db)
    if project.current_stage != stage:
        raise HTTPException(400, f"Project is at stage {project.current_stage}, not {stage}")
    if not req.confirmed:
        # Return the warning — UI will show it and require a second call with confirmed=True
        return {"requires_confirmation": True, "warning": get_skip_warning(stage)}

    warning_text = get_skip_warning(stage)
    event = StageEvent(
        project_id=project.id,
        stage=stage,
        action="skipped",
        warning_shown=warning_text,
    )
    db.add(event)
    project.current_stage = stage + 1
    db.commit()
    return {"status": "skipped", "next_stage": project.current_stage}


# ---------------------------------------------------------------------------
# Stage 2: Code generation and lookahead scan
# ---------------------------------------------------------------------------

@router.post("/code/generate")
async def generate_code(
    project_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    project = _get_project(project_id, user.id, db)
    if project.current_stage < ProjectStage.CODE:
        raise HTTPException(400, "Must complete hypothesis first")

    # Get confirmed hypothesis
    hyp = db.query(Hypothesis).filter(
        Hypothesis.project_id == project.id,
        Hypothesis.confirmed == True,
    ).order_by(Hypothesis.created_at.desc()).first()
    if not hyp:
        raise HTTPException(400, "No confirmed hypothesis")

    # Count previous versions for DSR trial count
    version_count = db.query(StrategyVersion).filter(
        StrategyVersion.project_id == project.id
    ).count()

    # Generate code
    code = await generate_strategy_code(hyp.raw_json or {
        "instrument": hyp.instrument,
        "timeframe": hyp.timeframe,
        "entry_rule": hyp.entry_rule,
        "exit_rule": hyp.exit_rule,
        "direction": hyp.direction,
        "claim": hyp.claim,
    })

    # Save version
    sv = StrategyVersion(
        project_id=project.id,
        version_num=version_count + 1,
        source_code=code,
        params={},
        is_active=False,
    )
    db.add(sv)
    db.commit()
    db.refresh(sv)

    return {"version_id": str(sv.id), "code": code, "version_num": sv.version_num}


@router.post("/code/{version_id}/scan")
def scan_code(
    project_id: UUID,
    version_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    project = _get_project(project_id, user.id, db)
    sv = db.query(StrategyVersion).filter(
        StrategyVersion.id == version_id,
        StrategyVersion.project_id == project.id,
    ).first()
    if not sv:
        raise HTTPException(404, "Strategy version not found")

    # Run AST scan (dynamic scan requires data, run separately)
    scan_result = scan_strategy_code(sv.source_code, run_dynamic=False)

    sv.scan_passed = not scan_result.has_lookahead
    sv.scan_findings = [
        {"kind": f.kind, "severity": f.severity, "description": f.description,
         "line": f.line, "snippet": f.code_snippet}
        for f in scan_result.findings
    ]
    sv.scanned_at = datetime.utcnow()
    db.commit()

    return {
        "passed": not scan_result.has_lookahead,
        "findings": sv.scan_findings,
    }


@router.post("/code/{version_id}/activate")
def activate_strategy(
    project_id: UUID,
    version_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Mark a strategy version as active and advance to Stage 3 (data split)."""
    project = _get_project(project_id, user.id, db)
    sv = db.query(StrategyVersion).filter(
        StrategyVersion.id == version_id,
        StrategyVersion.project_id == project.id,
    ).first()
    if not sv:
        raise HTTPException(404, "Strategy version not found")
    if not sv.scan_passed:
        raise HTTPException(400, "Strategy has not passed the lookahead scan")

    # Deactivate all others
    db.query(StrategyVersion).filter(
        StrategyVersion.project_id == project.id
    ).update({"is_active": False})
    sv.is_active = True

    if project.current_stage == ProjectStage.CODE:
        event = StageEvent(project_id=project.id, stage=ProjectStage.CODE, action="completed")
        db.add(event)
        project.current_stage = ProjectStage.DATA_SPLIT

    db.commit()
    return {"status": "activated", "next_stage": project.current_stage}


# ---------------------------------------------------------------------------
# Stage 3: Data split
# ---------------------------------------------------------------------------

class SplitRequest(BaseModel):
    test_start: Optional[str] = None    # ISO date, or None to use recommendation
    test_end: Optional[str] = None


@router.get("/split/recommendation")
def get_split_recommendation(
    project_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    project = _get_project(project_id, user.id, db)
    if not project.instrument:
        raise HTTPException(400, "Instrument not set")

    df = load_instrument(project.instrument, timeframe=project.timeframe)
    split = compute_recommended_split(df)

    return {
        "train_start": str(split.train_start),
        "train_end": str(split.train_end),
        "test_start": str(split.test_start),
        "test_end": str(split.test_end),
        "train_bars": split.train_bars,
        "test_bars": split.test_bars,
        "recommended_by": split.recommended_by,
        "total_bars": len(df),
    }


@router.post("/split/lock")
def lock_split(
    project_id: UUID,
    req: SplitRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Lock the train/test split. After this, Stage 4 jobs only get train data."""
    project = _get_project(project_id, user.id, db)
    if project.current_stage != ProjectStage.DATA_SPLIT:
        raise HTTPException(400, f"Project is at stage {project.current_stage}")

    df = load_instrument(project.instrument, timeframe=project.timeframe)

    if req.test_start:
        # User-specified split
        from forge_engine.split import DataSplit as DS
        import pandas as pd
        split = DS(
            train_start=df.index[0].date(),
            train_end=pd.Timestamp(req.test_start).date() - pd.Timedelta(days=1),
            test_start=pd.Timestamp(req.test_start).date(),
            test_end=df.index[-1].date(),
            train_bars=len(df[df.index < req.test_start]),
            test_bars=len(df[df.index >= req.test_start]),
            recommended_by="user",
        )
    else:
        split = compute_recommended_split(df)

    # In prod: serialize train/test DataFrames to S3-compatible storage
    # For now: store split dates; data is re-loaded from local source when needed
    existing = db.query(DataSplitModel).filter(DataSplitModel.project_id == project.id).first()
    if existing:
        db.delete(existing)

    db_split = DataSplitModel(
        project_id=project.id,
        train_start=split.train_start,
        train_end=split.train_end,
        test_start=split.test_start,
        test_end=split.test_end,
        train_bars=split.train_bars,
        test_bars=split.test_bars,
        recommended_by=split.recommended_by,
        locked=True,
        locked_at=datetime.utcnow(),
    )
    db.add(db_split)

    event = StageEvent(project_id=project.id, stage=ProjectStage.DATA_SPLIT, action="completed")
    db.add(event)
    project.current_stage = ProjectStage.DEVELOPMENT
    db.commit()

    return {
        "status": "locked",
        "train_start": str(split.train_start),
        "train_end": str(split.train_end),
        "test_start": str(split.test_start),
        "test_end": str(split.test_end),
        "train_bars": split.train_bars,
        "test_bars": split.test_bars,
    }


# ---------------------------------------------------------------------------
# Stages 4 & 5: Enqueue Celery jobs
# ---------------------------------------------------------------------------

@router.post("/development/run")
def run_development(
    project_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Enqueue walk-forward and sensitivity jobs on training data only."""
    project = _get_project(project_id, user.id, db)
    if project.current_stage < ProjectStage.DEVELOPMENT:
        raise HTTPException(400, "Data split must be locked first")

    from app.tasks.validation_tasks import run_development_task
    job = Job(project_id=project.id, job_type=JobType.WALK_FORWARD)
    db.add(job)
    db.commit()
    db.refresh(job)

    task = run_development_task.delay(str(project.id), str(job.id))
    job.celery_task_id = task.id
    db.commit()

    return {"job_id": str(job.id), "status": "queued"}


@router.post("/validation/run")
def run_validation(
    project_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Enqueue OOS validation. Can only run once — OOS is consumed."""
    project = _get_project(project_id, user.id, db)
    if project.current_stage < ProjectStage.VALIDATION:
        raise HTTPException(400, "Must complete development stage first")
    if project.oos_consumed:
        raise HTTPException(400, "OOS period already consumed. Create a new project to test a modified strategy.")

    from app.tasks.validation_tasks import run_oos_validation_task
    job = Job(project_id=project.id, job_type=JobType.OOS_VALIDATION)
    db.add(job)
    db.commit()
    db.refresh(job)

    task = run_oos_validation_task.delay(str(project.id), str(job.id))
    job.celery_task_id = task.id
    project.oos_consumed = True  # Mark immediately to prevent double-runs
    db.commit()

    return {"job_id": str(job.id), "status": "queued"}


@router.get("/jobs/{job_id}")
def get_job_status(
    project_id: UUID,
    job_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _get_project(project_id, user.id, db)
    job = db.query(Job).filter(Job.id == job_id, Job.project_id == project_id).first()
    if not job:
        raise HTTPException(404, "Job not found")
    return {
        "id": str(job.id),
        "type": job.job_type,
        "status": job.status,
        "result": job.result,
        "error": job.error,
        "created_at": job.created_at,
        "finished_at": job.finished_at,
    }


def _get_project(project_id: UUID, user_id, db: Session) -> Project:
    p = db.query(Project).filter(Project.id == project_id, Project.user_id == user_id).first()
    if not p:
        raise HTTPException(404, "Project not found")
    return p
