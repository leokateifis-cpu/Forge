import uuid
from datetime import datetime

from sqlalchemy import Column, String, DateTime, ForeignKey, Text, JSON, Boolean
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.base import Base


class Hypothesis(Base):
    """Structured hypothesis produced in Stage 1."""
    __tablename__ = "hypotheses"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False)

    # Structured fields (extracted by LLM)
    instrument = Column(String, nullable=True)
    timeframe = Column(String, nullable=True)
    entry_rule = Column(Text, nullable=True)
    exit_rule = Column(Text, nullable=True)
    direction = Column(String, nullable=True)        # "long" | "short" | "both"
    expected_holding_period = Column(String, nullable=True)
    claim = Column(Text, nullable=True)              # the testable claim
    falsification_condition = Column(Text, nullable=True)

    raw_json = Column(JSON, nullable=True)           # full LLM-structured output
    confirmed = Column(Boolean, default=False)
    confirmed_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)

    project = relationship("Project", back_populates="hypotheses")
