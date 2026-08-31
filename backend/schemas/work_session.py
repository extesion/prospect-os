from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime
from typing import Optional, List

class WorkSessionStart(BaseModel):
    daily_target: int = Field(160, ge=1, le=5000)
    target_hours: float = Field(8.0, ge=0.5, le=24.0)
    cycle_type: str = Field("8H", max_length=50)

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

class UserRankingItem(BaseModel):
    rank_position: int
    user_id: int
    user_name: str
    total_active_seconds: int
    formatted_hours: str
    channels_collected: int

class TeamStatusItem(BaseModel):
    user_id: int
    user_name: str
    session_id: Optional[int] = None
    session_status: str  # 'ACTIVE', 'PAUSED', 'IDLE', 'FINISHED'
    active_seconds: int
    formatted_time: str
    collected_count: int
    daily_target: int
    current_rate: float
    progress_percentage: float

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
