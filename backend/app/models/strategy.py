import uuid
from datetime import datetime

from sqlalchemy import Column, String, DateTime, ForeignKey, Text, JSON, Boolean, Integer
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.base import Base


class StrategyVersion(Base):
    """
    One version of the generated strategy code.
    Every version is counted toward the Deflated Sharpe trial count.
    """
    __tablename__ = "strategy_versions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False)
    version_num = Column(Integer, nullable=False)    # 1, 2, 3... (increments per project)

    source_code = Column(Text, nullable=False)
    params = Column(JSON, nullable=False, default=dict)   # {name: value, ...}
    param_ranges = Column(JSON, nullable=True)            # {name: [min, max], ...}

    # Lookahead scan
    scan_passed = Column(Boolean, nullable=True)
    scan_findings = Column(JSON, nullable=True)      # list of finding dicts
    scanned_at = Column(DateTime, nullable=True)

    # Whether this version was selected for the validation pipeline
    is_active = Column(Boolean, default=False)

    created_at = Column(DateTime, default=datetime.utcnow)

    project = relationship("Project", back_populates="strategy_versions")
