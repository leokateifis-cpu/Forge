from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional

from app.db.base import get_db
from app.models.project import Project, ProjectStage
from app.models.user import User
from app.core.security import get_current_user

router = APIRouter()


class ProjectCreate(BaseModel):
    title: Optional[str] = None


class ProjectResponse(BaseModel):
    id: UUID
    title: Optional[str]
    instrument: Optional[str]
    timeframe: str
    current_stage: int
    oos_consumed: bool

    class Config:
        from_attributes = True


@router.get("/", response_model=list[ProjectResponse])
def list_projects(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return db.query(Project).filter(Project.user_id == user.id).order_by(Project.created_at.desc()).all()


@router.post("/", response_model=ProjectResponse, status_code=201)
def create_project(
    req: ProjectCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    project = Project(user_id=user.id, title=req.title)
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


@router.get("/{project_id}", response_model=ProjectResponse)
def get_project(
    project_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    project = _get_or_404(project_id, user.id, db)
    return project


def _get_or_404(project_id: UUID, user_id, db: Session) -> Project:
    project = db.query(Project).filter(
        Project.id == project_id,
        Project.user_id == user_id,
    ).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project
