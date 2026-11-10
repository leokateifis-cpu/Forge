import uuid
from datetime import datetime
from enum import IntEnum

from sqlalchemy import Column, String, DateTime, Integer, Boolean, ForeignKey, Text, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.base import Base


class ProjectStage(IntEnum):
    HYPOTHESIS = 1
    CODE = 2
    DATA_SPLIT = 3
    DEVELOPMENT = 4
    VALIDATION = 5
    DONE = 6


class Project(Base):
    __tablename__ = "projects"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    title = Column(String, nullable=True)
    instrument = Column(String, nullable=True)       # "ES", "NQ", "AAPL", etc.
    timeframe = Column(String, default="1D")

    current_stage = Column(Integer, default=ProjectStage.HYPOTHESIS)
    oos_consumed = Column(Boolean, default=False)    # True after Stage 5 runs

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="projects")
    messages = relationship("Message", back_populates="project", cascade="all, delete-orphan")
    hypotheses = relationship("Hypothesis", back_populates="project", cascade="all, delete-orphan")
    strategy_versions = relationship("StrategyVersion", back_populates="project", cascade="all, delete-orphan")
    data_split = relationship("DataSplit", back_populates="project", uselist=False, cascade="all, delete-orphan")
    jobs = relationship("Job", back_populates="project", cascade="all, delete-orphan")
    report = relationship("Report", back_populates="project", uselist=False, cascade="all, delete-orphan")
    stage_events = relationship("StageEvent", back_populates="project", cascade="all, delete-orphan")


class StageEvent(Base):
    """Audit log of stage transitions (completed or skipped)."""
    __tablename__ = "stage_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False)
    stage = Column(Integer, nullable=False)
    action = Column(String, nullable=False)         # "completed" | "skipped"
    warning_shown = Column(Text, nullable=True)     # the warning text shown before skip
    created_at = Column(DateTime, default=datetime.utcnow)

    project = relationship("Project", back_populates="stage_events")
