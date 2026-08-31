from datetime import datetime, timezone
from sqlalchemy import (
    Column, Integer, String, BigInteger, DateTime, Text, JSON, ForeignKey, Index
)
from sqlalchemy.orm import relationship
from backend.database.connection import Base

def utc_now():
    return datetime.now(timezone.utc)

class AnalyzedVideo(Base):
    __tablename__ = "analyzed_videos"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    qualification_result_id = Column(Integer, ForeignKey("qualification_results.id", ondelete="CASCADE"), nullable=False, index=True)
    channel_id = Column(String(64), index=True, nullable=False)
    
    video_id = Column(String(64), nullable=False)
    title = Column(String(500), nullable=False)
    description = Column(Text, nullable=True)
    published_at = Column(DateTime(timezone=True), nullable=True)
    
    view_count = Column(BigInteger, default=0, nullable=False)
    like_count = Column(Integer, default=0, nullable=False)
    comment_count = Column(Integer, default=0, nullable=False)
    duration = Column(String(50), nullable=True)
    tags = Column(JSON, nullable=True)
    
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    qualification_result = relationship("QualificationResult", back_populates="analyzed_videos")

    __table_args__ = (
        Index("idx_vid_channel", "channel_id"),
        Index("idx_vid_video_id", "video_id"),
    )
