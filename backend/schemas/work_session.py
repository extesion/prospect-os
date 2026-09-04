from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime
from typing import Optional, List, Dict, Any

from backend.schemas.channel import ChannelCreate

class WorkSessionStart(BaseModel):
    daily_target: int = Field(160, ge=1, le=5000)
    target_hours: float = Field(8.0, ge=0.5, le=24.0)
    cycle_type: str = Field("8H", max_length=50)

class WorkSessionFinishRequest(BaseModel):
    session_id: Optional[int] = None
    active_seconds: Optional[int] = None
    paused_seconds: Optional[int] = None
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    daily_target: Optional[int] = None
    target_hours: Optional[float] = None
    cycle_type: Optional[str] = None
    channels: Optional[List[ChannelCreate]] = Field(default_factory=list)

class WorkSessionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    user_name: Optional[str] = None
    started_at: datetime
    ended_at: Optional[datetime] = None
    paused_at: Optional[datetime] = None
    last_resumed_at: datetime
    active_seconds: int
    current_active_seconds: int
    formatted_active_time: str
    status: str
    cycle_type: str
    daily_target: int
    target_hours: float
    target_per_hour: float
    target_per_hour_display: float
    collected_count: int
    current_rate: float
    remaining: int
    remaining_active_hours: float
    required_rate: float
    progress_percentage: float
    projected_finish_hours: Optional[float] = None
    projected_finish_display: Optional[str] = None
    status_indicator: str  # 'IN_TARGET', 'ABOVE_TARGET', 'BELOW_TARGET'
    is_target_completed: bool
    is_cycle_time_exceeded: bool
    inserted_count: Optional[int] = None
    already_exists_count: Optional[int] = None
    errors: Optional[List[str]] = None

class UserRankingItem(BaseModel):
    rank_position: int
    user_id: int
    user_name: str
    avatar_url: Optional[str] = None
    banner_url: Optional[str] = None
    total_active_seconds: int
    formatted_hours: str
    channels_collected: int

class TeamStatusItem(BaseModel):
    user_id: int
    user_name: str
    role: str = "USER"
    avatar_url: Optional[str] = None
    banner_url: Optional[str] = None
    presence: str = "offline"  # 'online', 'offline'; independent from work status
    session_id: Optional[int] = None
    session_status: str  # 'ACTIVE', 'PAUSED', 'IDLE'
    active_seconds: int = 0
    formatted_time: str = "00:00:00"
    collected_count: int = 0
    daily_target: int = 0
    current_rate: float = 0.0
    required_rate: float = 0.0
    progress_percentage: float = 0.0
    projected_finish_display: Optional[str] = None
    hours_today: float = 0.0
    hours_this_week: float = 0.0
    hours_this_month: float = 0.0
    total_hours_worked: float = 0.0
    channels_today: int = 0
    channels_this_week: int = 0
    channels_this_month: int = 0
    total_channels_collected: int = 0
    daily_avg_hours: float = 0.0
    daily_avg_channels: float = 0.0
    avg_channels_per_hour: float = 0.0
    completed_cycles_count: int = 0
    goals_reached_count: int = 0
    chart_7d: List[Dict[str, Any]] = Field(default_factory=list)
    now_playing: Optional[Dict[str, Any]] = None
    music_status: str = "Nada tocando"

class TeamSummaryResponse(BaseModel):
    users_working_count: int
    total_hours_today_seconds: int
    formatted_total_hours_today: str
    total_channels_today: int
    team_average_rate: float
    members: List[TeamStatusItem]

class CyclePresetItem(BaseModel):
    id: str
    name: str
    hours: float
    target: int
    rate: float

class CycleSettingsResponse(BaseModel):
    default_daily_target: int
    presets: List[CyclePresetItem]

class CycleSettingsUpdate(BaseModel):
    default_daily_target: int
    presets: Optional[List[CyclePresetItem]] = None

class SessionHistoryItem(BaseModel):
    id: int
    user_id: int
    user_name: str
    date_str: str
    started_at: datetime
    ended_at: Optional[datetime] = None
    active_seconds: int
    formatted_active_time: str
    cycle_type: str
    daily_target: int
    collected_count: int
    average_rate: float
    status: str
