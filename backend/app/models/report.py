import uuid
from datetime import datetime

from sqlalchemy import Column, String, DateTime, ForeignKey, JSON, Float, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.base import Base


class Report(Base):
    __tablename__ = "reports"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False, unique=True)

    score = Column(Float, nullable=True)             # 0–100
    score_breakdown = Column(JSON, nullable=True)    # ScoreBreakdown as dict
    findings = Column(JSON, nullable=True)           # all validation results
    skipped_stages = Column(JSON, nullable=True)     # list of skipped stage numbers

    pdf_key = Column(String, nullable=True)          # S3 key for PDF

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    project = relationship("Project", back_populates="report")
