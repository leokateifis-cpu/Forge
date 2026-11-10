from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.db.base import get_db
from app.models.report import Report
from app.models.project import Project
from app.models.user import User
from app.core.security import get_current_user

router = APIRouter()


@router.get("/")
def get_report(
    project_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _get_project(project_id, user.id, db)
    report = db.query(Report).filter(Report.project_id == project_id).first()
    if not report:
        raise HTTPException(404, "Report not ready yet")
    return {
        "id": str(report.id),
        "score": report.score,
        "score_breakdown": report.score_breakdown,
        "findings": report.findings,
        "skipped_stages": report.skipped_stages,
        "created_at": report.created_at,
    }


def _get_project(project_id: UUID, user_id, db: Session) -> Project:
    p = db.query(Project).filter(Project.id == project_id, Project.user_id == user_id).first()
    if not p:
        raise HTTPException(404, "Project not found")
    return p
