from datetime import datetime, timezone
from sqlalchemy import (
    Column, Integer, String, DateTime, Text, Index
)
from backend.database.connection import Base

def utc_now():
    return datetime.now(timezone.utc)

class QualificationJob(Base):
    __tablename__ = "qualification_jobs"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    channel_id = Column(String(64), index=True, nullable=False)
    
    # Status: PENDING, PROCESSING, QUALIFIED, REVIEW, REJECTED, ERROR, RETRY, CANCELLED
    status = Column(String(20), default="PENDING", index=True, nullable=False)
    
    attempts = Column(Integer, default=0, nullable=False)
    max_attempts = Column(Integer, default=3, nullable=False)
    priority = Column(Integer, default=0, index=True, nullable=False)
    
    next_retry_at = Column(DateTime(timezone=True), nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    error_message = Column(Text, nullable=True)
    
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    __table_args__ = (
        Index("idx_job_status_priority", "status", "priority", "created_at"),
        Index("idx_job_channel_status", "channel_id", "status"),
    )
