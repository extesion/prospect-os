from pydantic import BaseModel
from typing import Optional, Dict, Any, List
from datetime import datetime

class NotificationCreate(BaseModel):
    type: str
    title: str
    message: str
    target_user_id: Optional[int] = None
    metadata: Optional[Dict[str, Any]] = None

class NotificationResponse(BaseModel):
    id: int
    type: str
    actor_user_id: Optional[int] = None
    actor_name: Optional[str] = None
    target_user_id: Optional[int] = None
    title: str
    message: str
    metadata: Optional[Dict[str, Any]] = None
    read_at: Optional[datetime] = None
    is_read: bool = False
    created_at: datetime

    class Config:
        from_attributes = True

class NotificationCountResponse(BaseModel):
    unread_count: int
