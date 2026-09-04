from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from datetime import timedelta

from backend.database.connection import get_db
from backend.database.models import User, utc_now
from backend.schemas.auth import UserLogin, UserCreate, UserResponse, TokenResponse
from backend.security.auth import auth_service, get_password_hash, create_access_token, get_current_user
from backend.config.settings import settings

router = APIRouter(prefix="/auth", tags=["Authentication"])

@router.post("/heartbeat")
def heartbeat(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Registra presença recente do usuário autenticado."""
    current_user.last_seen_at = utc_now()
    db.commit()
    return {"status": "ok"}

@router.post("/login", response_model=TokenResponse)
def login(login_data: UserLogin, db: Session = Depends(get_db)):
    user = auth_service.authenticate(db, login_data.email, login_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="E-mail ou senha incorretos.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if not user.active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Usuário desativado. Contate o administrador.",
        )

    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": str(user.id), "email": user.email, "name": user.name, "role": user.role or "USER"},
        expires_delta=access_token_expires
    )

    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        user=UserResponse.model_validate(user)
    )

@router.get("/me", response_model=UserResponse)
def get_current_user_profile(current_user: User = Depends(get_current_user)):
    return UserResponse.model_validate(current_user)

@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register_user(user_data: UserCreate, db: Session = Depends(get_db)):
    """Convenience endpoint to register users for the team (always created as USER)."""
    email_clean = user_data.email.lower().strip()
    existing = db.query(User).filter(User.email == email_clean, User.is_deleted == False).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="E-mail já cadastrado.",
        )
    
    new_user = User(
        name=user_data.name.strip(),
        email=email_clean,
        password_hash=get_password_hash(user_data.password),
        role="USER",
        active=True,
        is_deleted=False
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return UserResponse.model_validate(new_user)
