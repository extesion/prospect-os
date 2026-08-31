from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.database.connection import get_db
from backend.database.models import User, YouTubeApiConfig, utc_now
from backend.security.auth import get_current_admin_user
from qualifier.services.youtube_api_manager import YouTubeApiManager

router = APIRouter(prefix="/youtube-apis", tags=["YouTube APIs (Admin Only)"])

class YouTubeApiCreateRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    api_key: str = Field(..., min_length=10, max_length=255)
    daily_limit: Optional[int] = Field(10000, ge=100)
    status: Optional[str] = Field("ACTIVE")

class YouTubeApiUpdateRequest(BaseModel):
    name: Optional[str] = None
    api_key: Optional[str] = None
    daily_limit: Optional[int] = None
    status: Optional[str] = None

@router.get("")
def get_youtube_apis_overview(
    db: Session = Depends(get_db),
    admin_user: User = Depends(get_current_admin_user)
):
    """Retorna visão consolidada de quotas, status e configurações de APIs cadastradas (Exclusivo ADMIN)."""
    return YouTubeApiManager.get_dashboard_summary(db)

@router.post("", status_code=status.HTTP_201_CREATED)
def create_youtube_api_config(
    body: YouTubeApiCreateRequest,
    db: Session = Depends(get_db),
    admin_user: User = Depends(get_current_admin_user)
):
    """Cadastra um novo projeto/chave da YouTube Data API v3 (Exclusivo ADMIN)."""
    key_clean = body.api_key.strip()
    existing = db.query(YouTubeApiConfig).filter(YouTubeApiConfig.api_key == key_clean).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Esta chave de API já está cadastrada no sistema."
        )

    new_cfg = YouTubeApiConfig(
        name=body.name.strip(),
        api_key=key_clean,
        daily_limit=body.daily_limit or 10000,
        status=body.status.upper() if body.status else "ACTIVE",
        created_at=utc_now(),
        updated_at=utc_now()
    )
    db.add(new_cfg)
    db.commit()
    db.refresh(new_cfg)

    return {
        "message": f"Configuração de API '{new_cfg.name}' cadastrada com sucesso.",
        "id": new_cfg.id,
        "name": new_cfg.name,
        "masked_key": YouTubeApiManager.mask_api_key(new_cfg.api_key),
        "status": new_cfg.status,
        "daily_limit": new_cfg.daily_limit
    }

@router.put("/{config_id}")
def update_youtube_api_config(
    config_id: int,
    body: YouTubeApiUpdateRequest,
    db: Session = Depends(get_db),
    admin_user: User = Depends(get_current_admin_user)
):
    """Edita nome, limite diário, status ou atualiza a chave de uma configuração existente (Exclusivo ADMIN)."""
    cfg = db.query(YouTubeApiConfig).filter(YouTubeApiConfig.id == config_id).first()
    if not cfg:
        raise HTTPException(status_code=404, detail="Configuração de API não encontrada.")

    if body.name is not None:
        cfg.name = body.name.strip()
    if body.daily_limit is not None:
        cfg.daily_limit = body.daily_limit
    if body.status is not None:
        cfg.status = body.status.upper()
    if body.api_key and body.api_key.strip():
        cfg.api_key = body.api_key.strip()

    cfg.updated_at = utc_now()
    db.commit()
    db.refresh(cfg)

    return {
        "message": "Configuração atualizada com sucesso.",
        "id": cfg.id,
        "name": cfg.name,
        "masked_key": YouTubeApiManager.mask_api_key(cfg.api_key),
        "status": cfg.status,
        "daily_limit": cfg.daily_limit
    }

@router.delete("/{config_id}")
def delete_youtube_api_config(
    config_id: int,
    db: Session = Depends(get_db),
    admin_user: User = Depends(get_current_admin_user)
):
    """Remove uma configuração de API (Exclusivo ADMIN)."""
    cfg = db.query(YouTubeApiConfig).filter(YouTubeApiConfig.id == config_id).first()
    if not cfg:
        raise HTTPException(status_code=404, detail="Configuração de API não encontrada.")

    db.delete(cfg)
    db.commit()
    return {"message": f"Configuração '{cfg.name}' removida com sucesso."}
