from pydantic import BaseModel, EmailStr
from datetime import datetime
from typing import Optional

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class UserCreate(BaseModel):
    name: str
    email: EmailStr
    password: str
    role: Optional[str] = "USER"

class UserAdminCreate(BaseModel):
    name: str
    email: EmailStr
    password: str
    role: str = "USER"  # 'ADMIN' or 'USER'
    active: bool = True

class UserAdminUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    role: Optional[str] = None
    active: Optional[bool] = None
    password: Optional[str] = None  # If provided, resets password

class UserResponse(BaseModel):
    id: int
    name: str
    email: EmailStr
    role: str = "USER"
    active: bool
    created_at: datetime

    class Config:
        from_attributes = True

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse
