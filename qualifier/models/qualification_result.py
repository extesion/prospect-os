from datetime import datetime, timezone
from sqlalchemy import (
    Column, Integer, String, BigInteger, DateTime, Float, Text, JSON, Index, ForeignKey, Boolean
)
from sqlalchemy.orm import relationship
from backend.database.connection import Base

def utc_now():
    return datetime.now(timezone.utc)

class QualificationResult(Base):
    __tablename__ = "qualification_results"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    channel_id = Column(String(64), unique=True, index=True, nullable=False)
    
    # Status & Score
    qualification_status = Column(String(20), index=True, nullable=False) # 'QUALIFIED', 'REVIEW', 'REJECTED', 'FAILED'
    score = Column(Integer, default=0, nullable=False)
    
    # Niche
    detected_niche = Column(String(100), nullable=True, index=True)
    niche_confidence = Column(Float, default=0.0, nullable=False)
    
    # Activity
    activity_status = Column(String(20), default="INACTIVE", nullable=False) # 'ACTIVE', 'LOW_ACTIVITY', 'INACTIVE'
    days_since_last_video = Column(Integer, nullable=True)
    last_video_date = Column(DateTime(timezone=True), nullable=True)
    last_video_title = Column(String(500), nullable=True)
    estimated_posting_frequency_days = Column(Float, nullable=True)
    
    # Analyzed Sources Verification Flags
    channel_description_analyzed = Column(Boolean, default=True)
    last_video_description_analyzed = Column(Boolean, default=True)

    # Channel Statistics
    subscribers = Column(BigInteger, default=0, nullable=False)
    total_views = Column(BigInteger, default=0, nullable=False)
    total_videos = Column(Integer, default=0, nullable=False)
    channel_created_at = Column(DateTime(timezone=True), nullable=True)
    country = Column(String(10), nullable=True)
    uploads_playlist_id = Column(String(100), nullable=True)
    
    # Contact and Links
    email = Column(String(255), nullable=True, index=True)
    email_source = Column(String(100), nullable=True)
    whatsapp = Column(String(100), nullable=True)
    whatsapp_source = Column(String(100), nullable=True)
    website = Column(String(500), nullable=True)
    
    # Social Media
    instagram = Column(String(500), nullable=True)
    tiktok = Column(String(500), nullable=True)
    twitter = Column(String(500), nullable=True)
    facebook = Column(String(500), nullable=True)
    linkedin = Column(String(500), nullable=True)
    
    # JSON Aggregations
    link_aggregators = Column(JSON, nullable=True) # e.g. [{"platform": "linktree", "url": "..."}]
    sales_platforms = Column(JSON, nullable=True)  # e.g. [{"platform": "hotmart", "url": "..."}]
    commercial_signals = Column(JSON, nullable=True) # [{"type": "course", "source": "video_1", "value": "..."}]
    keywords_found = Column(JSON, nullable=True)     # [{"keyword": "consultoria", "source": "channel_description", "context": "..."}]
    keywords_sources = Column(JSON, nullable=True)   # {"consultoria": ["channel_description"], "parcerias": ["last_video_description"]}
    score_breakdown = Column(JSON, nullable=True)    # {"email": 20, "website": 15, ...}
    qualification_config_snapshot = Column(JSON, nullable=True)
    qualification_config_version = Column(Integer, nullable=True)
    
    # Reasoning & Versioning
    qualification_reason = Column(Text, nullable=True)
    qualification_version = Column(String(20), default="v1", nullable=False)
    youtube_data_updated_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)
    qualified_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    # Relationships
    analyzed_videos = relationship("AnalyzedVideo", back_populates="qualification_result", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_qual_status", "qualification_status"),
        Index("idx_qual_score", "score"),
        Index("idx_qual_niche", "detected_niche"),
        Index("idx_qual_qualified_at", "qualified_at"),
    )
