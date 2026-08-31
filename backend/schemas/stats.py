from pydantic import BaseModel

class UserStats(BaseModel):
    user_id: int
    user_name: str
    today_count: int
    total_count: int

class TeamStats(BaseModel):
    today_count: int
    total_count: int
    active_users_today: int
