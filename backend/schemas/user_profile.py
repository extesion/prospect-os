from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime

class UserProfileUpdate(BaseModel):
    bio: Optional[str] = None
    custom_status: Optional[str] = None
    show_music_to_team: Optional[bool] = None

class UserProfileStats(BaseModel):
    user_id: int
    name: str
    email: str
    role: str
    active: bool
    avatar_url: Optional[str] = None
    banner_url: Optional[str] = None
    bio: Optional[str] = None
    custom_status: Optional[str] = None
    show_music_to_team: bool = True
    
    # Live Status
    presence_status: str # 'online', 'offline'
    work_session_status: str # 'ACTIVE', 'PAUSED', 'PARADO'
    
    # Active Session (if any)
    active_session: Optional[Dict[str, Any]] = None
    
    # Aggregated Stats
    total_hours_worked: float
    formatted_total_hours: str
    hours_today: float
    formatted_hours_today: str
    hours_this_week: float
    formatted_hours_this_week: str
    hours_this_month: float
    formatted_hours_this_month: str
    
    total_channels_collected: int
    channels_today: int
    channels_this_week: int
    channels_this_month: int
    
    # Averages (Calculated strictly over active days with work)
    active_days_count: int
    daily_avg_hours: float
    daily_avg_channels: float
    avg_channels_per_hour: float
    
    # Records & Milestones
    best_day_channels: int
    best_day_date: Optional[str] = None
    longest_session_hours: float
    formatted_longest_session: str
    completed_cycles_count: int
    goals_reached_count: int
    
    # Activity Chart Data (last 7, 30, 90 days)
    chart_7d: List[Dict[str, Any]]
    chart_30d: List[Dict[str, Any]]
    chart_90d: List[Dict[str, Any]]
    
    # Music Info
    now_playing: Optional[Dict[str, Any]] = None
    most_played_session_track: Optional[Dict[str, Any]] = None
