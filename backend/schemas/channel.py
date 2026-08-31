from pydantic import BaseModel, Field
from datetime import datetime
from typing import List, Dict, Optional

class CollectorInfo(BaseModel):
    id: int
    name: str

class ChannelStatus(BaseModel):
    exists: bool
    collected_by: Optional[CollectorInfo] = None
    collected_at: Optional[datetime] = None

class ChannelCheckRequest(BaseModel):
    channel_ids: List[str] = Field(..., max_length=500)

class ChannelCheckResponse(BaseModel):
    channels: Dict[str, ChannelStatus]

class ChannelCreate(BaseModel):
    channel_id: str = Field(..., min_length=2, max_length=100)
    channel_name: Optional[str] = Field("Canal YouTube", max_length=255)
    channel_handle: Optional[str] = Field(None, max_length=100)
    channel_url: Optional[str] = Field("", max_length=500)
    source: Optional[str] = Field("youtube_search", max_length=100)
    search_term: Optional[str] = Field(None, max_length=255)

class ChannelBulkCreate(BaseModel):
    channels: List[ChannelCreate] = Field(..., max_length=500)

class ChannelResponse(BaseModel):
    id: int
    channel_id: str
    channel_name: str
    channel_handle: Optional[str] = None
    channel_url: str
    source: str
    search_term: Optional[str] = None
    first_collected_by: CollectorInfo
    first_collected_at: datetime
    created_at: datetime

    class Config:
        from_attributes = True

class ChannelCollectResult(BaseModel):
    success: bool
    already_exists: bool
    message: str
    channel: Optional[ChannelResponse] = None

class ChannelBulkResponse(BaseModel):
    inserted: List[str]
    already_exists: List[str]
    errors: List[str]
