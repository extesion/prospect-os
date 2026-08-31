from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, ConfigDict

class CommercialSignalItem(BaseModel):
    type: str
    source: str
    value: str

class KeywordFoundItem(BaseModel):
    keyword: str
    source: str
    context: str

class LinkItem(BaseModel):
    platform: str
    url: str
    source: Optional[str] = None

class AnalyzedVideoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    video_id: str
    title: str
    description: Optional[str] = None
    published_at: Optional[datetime] = None
    view_count: int = 0
    like_count: Optional[int] = 0
    comment_count: Optional[int] = 0
    duration: Optional[str] = None
    tags: Optional[List[str]] = None

class QualificationResultResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    channel_id: str
    qualification_status: str # QUALIFIED, REVIEW, REJECTED, FAILED
    score: int
    detected_niche: Optional[str] = None
    niche_confidence: float = 0.0
    activity_status: str
    days_since_last_video: Optional[int] = None
    last_video_date: Optional[datetime] = None
    estimated_posting_frequency_days: Optional[float] = None
    
    subscribers: int = 0
    total_views: int = 0
    total_videos: int = 0
    channel_created_at: Optional[datetime] = None
    country: Optional[str] = None
    
    email: Optional[str] = None
    email_source: Optional[str] = None
    whatsapp: Optional[str] = None
    whatsapp_source: Optional[str] = None
    website: Optional[str] = None
    
    instagram: Optional[str] = None
    tiktok: Optional[str] = None
    twitter: Optional[str] = None
    facebook: Optional[str] = None
    linkedin: Optional[str] = None
    
    link_aggregators: Optional[List[Dict[str, Any]]] = None
    sales_platforms: Optional[List[Dict[str, Any]]] = None
    commercial_signals: Optional[List[Dict[str, Any]]] = None
    keywords_found: Optional[List[Dict[str, Any]]] = None
    score_breakdown: Optional[Dict[str, int]] = None
    qualification_reason: Optional[str] = None
    qualification_version: str = "v1"
    
    youtube_data_updated_at: Optional[datetime] = None
    qualified_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    
    analyzed_videos: Optional[List[AnalyzedVideoResponse]] = []

class EmailTemplateDataResponse(BaseModel):
    channel_id: str
    channel_name: str
    channel_handle: Optional[str] = None
    detected_niche: Optional[str] = None
    subscriber_count: int = 0
    last_video_title: Optional[str] = None
    last_video_date: Optional[str] = None
    website: Optional[str] = None
    email: Optional[str] = None
    instagram: Optional[str] = None
    commercial_signals: List[str] = []
    qualification_reason: Optional[str] = None

class QualificationJobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    channel_id: str
    status: str
    attempts: int
    max_attempts: int
    priority: int
    next_retry_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime

class QualificationStatsResponse(BaseModel):
    total_qualified: int = 0
    total_review: int = 0
    total_rejected: int = 0
    total_failed: int = 0
    pending_jobs: int = 0
    processing_jobs: int = 0
    completed_jobs: int = 0
    retry_jobs: int = 0
    failed_jobs: int = 0
    estimated_quota_used_today: int = 0
    daily_quota_limit: int = 9500

class ConfigUpdateRequest(BaseModel):
    daily_quota_limit: Optional[int] = None
    videos_to_analyze: Optional[int] = None
    requalification_interval_days: Optional[int] = None
    score_qualified_threshold: Optional[int] = None
    score_review_threshold: Optional[int] = None
    active_days_threshold: Optional[int] = None
    inactive_days_threshold: Optional[int] = None
