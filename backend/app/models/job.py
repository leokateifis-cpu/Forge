import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import Column, String, DateTime, ForeignKey, JSON, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.base import Base


class JobStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"


class JobType(StrEnum):
    LOOKAHEAD_SCAN = "lookahead_scan"
    WALK_FORWARD = "walk_forward"
    SENSITIVITY = "sensitivity"
    OOS_VALIDATION = "oos_validation"
    PAPER_TEST = "paper_test"


class Job(Base):
    __tablename__ = "jobs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False)
    celery_task_id = Column(String, nullable=True, index=True)
    job_type = Column(String, nullable=False)
    status = Column(String, nullable=False, default=JobStatus.PENDING)
    result = Column(JSON, nullable=True)
    error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)

    project = relationship("Project", back_populates="jobs")
