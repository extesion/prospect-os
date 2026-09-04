from datetime import datetime, timedelta, timezone
from typing import Optional
from jose import JWTError, jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
import bcrypt

from backend.config.settings import settings
from backend.database.connection import get_db
from backend.database.models import User

import hmac

security = HTTPBearer(auto_error=False)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"),
            hashed_password.encode("utf-8")
        )
    except Exception:
        return False

def verify_system_password(provided_password: Optional[str]) -> bool:
    """Valida a senha mestra do sistema com comparação segura de tempo constante."""
    if not provided_password:
        return False
    expected = settings.SYSTEM_ADMIN_PASSWORD or "883800"
    return hmac.compare_digest(str(provided_password).strip(), str(expected).strip())

def get_password_hash(password: str) -> str:
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


class AuthService:
    @staticmethod
    def authenticate(db: Session, email: str, password: str) -> Optional[User]:
        user = db.query(User).filter(
            User.email == email.lower().strip(),
            User.is_deleted.is_(False),
        ).first()
        if not user or not verify_password(password, user.password_hash):
            return None
        return user


auth_service = AuthService()


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt

def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: Session = Depends(get_db)
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Credenciais de autenticação inválidas ou expiradas.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if not credentials:
        raise credentials_exception
    
    token = credentials.credentials
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id: int = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
        
    user = db.query(User).filter(User.id == int(user_id)).first()
    if user is None or not user.active or getattr(user, "is_deleted", False):
        raise credentials_exception
        
    return user

def get_current_admin_user(
    current_user: User = Depends(get_current_user)
) -> User:
    if current_user.role != "ADMIN":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acesso restrito a administradores (403 Forbidden)."
        )
    return current_user
