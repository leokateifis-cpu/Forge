import uuid
from datetime import datetime, date

from sqlalchemy import Column, String, DateTime, Date, ForeignKey, Integer, Boolean
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.base import Base


class DataSplit(Base):
    """
    Locked train/test split for a project.

    The test data object key is stored here but only handed to Stage 5 jobs.
    Stage 4 jobs are only given the train key.
    """
    __tablename__ = "data_splits"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False, unique=True)

    train_start = Column(Date, nullable=False)
    train_end = Column(Date, nullable=False)
    test_start = Column(Date, nullable=False)
    test_end = Column(Date, nullable=False)

    train_bars = Column(Integer, nullable=False)
    test_bars = Column(Integer, nullable=False)
    recommended_by = Column(String, nullable=False)   # "mtr" | "fraction" | "user"

    # Object storage keys (S3-compatible)
    train_data_key = Column(String, nullable=True)
    test_data_key = Column(String, nullable=True)     # never sent to Stage 4

    locked_at = Column(DateTime, nullable=True)
    locked = Column(Boolean, default=False)

    created_at = Column(DateTime, default=datetime.utcnow)

    project = relationship("Project", back_populates="data_split")
