import os
import uuid
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from sqlalchemy.orm import Session

from backend.database.connection import get_db
from backend.database.models import User, UserProfile
from backend.schemas.user_profile import UserProfileStats, UserProfileUpdate
from backend.security.auth import get_current_user
from backend.services.profile_service import ProfileService

router = APIRouter(prefix="/profiles", tags=["User Profiles & Productivity"])

# Upload directory
UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "..", "static", "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

# Allowed file types & max size (5 MB)
ALLOWED_MIME_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif"
}
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB

@router.get("/me", response_model=UserProfileStats)
def get_my_profile_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Retorna o perfil completo e estatísticas de produtividade do usuário logado."""
    stats = ProfileService.get_user_full_stats(db, current_user.id)
    if not stats:
        raise HTTPException(status_code=404, detail="Perfil não encontrado.")
    return stats

@router.get("/{user_id}", response_model=UserProfileStats)
def get_member_profile_stats(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Retorna o perfil e estatísticas de produtividade de qualquer membro da equipe."""
    stats = ProfileService.get_user_full_stats(db, user_id)
    if not stats:
        raise HTTPException(status_code=404, detail="Membro não encontrado.")
    return stats

@router.put("/me", response_model=UserProfileStats)
def update_my_profile(
    data: UserProfileUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Atualiza bio, status customizado ou privacidade de música do usuário."""
    ProfileService.update_profile(db, current_user.id, data)
    return ProfileService.get_user_full_stats(db, current_user.id)

@router.post("/upload/{asset_type}")
async def upload_profile_media(
    asset_type: str, # 'avatar' or 'banner'
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Upload seguro de Avatar ou Banner (JPG, PNG, WEBP, GIF animado)."""
    if asset_type not in ("avatar", "banner"):
        raise HTTPException(status_code=400, detail="asset_type deve ser 'avatar' ou 'banner'")

    content_type = file.content_type
    if content_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Tipo de arquivo não permitido ({content_type}). Permitidos: JPG, PNG, WEBP, GIF."
        )

    # Read content and validate size
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=400,
            detail="Arquivo excede o tamanho limite de 5MB."
        )

    # Validate Magic Bytes / File Signatures for safety
    is_valid_magic = False
    if content.startswith(b"\xff\xd8\xff"): # JPEG
        is_valid_magic = True
    elif content.startswith(b"\x89PNG\r\n\x1a\n"): # PNG
        is_valid_magic = True
    elif content.startswith(b"GIF87a") or content.startswith(b"GIF89a"): # GIF
        is_valid_magic = True
    elif content.startswith(b"RIFF") and b"WEBP" in content[:16]: # WEBP
        is_valid_magic = True

    if not is_valid_magic:
        raise HTTPException(status_code=400, detail="Arquivo corrompido ou formato de imagem inválido.")

    ext = ALLOWED_MIME_TYPES[content_type]
    safe_filename = f"{current_user.id}_{asset_type}_{uuid.uuid4().hex[:8]}{ext}"
    file_path = os.path.join(UPLOAD_DIR, safe_filename)

    with open(file_path, "wb") as f:
        f.write(content)

    file_url = f"/static/uploads/{safe_filename}"

    # Update profile record
    profile = ProfileService.get_or_create_profile(db, current_user.id)
    if asset_type == "avatar":
        profile.avatar_url = file_url
    else:
        profile.banner_url = file_url

    db.commit()
    db.refresh(profile)

    return {
        "success": True,
        "asset_type": asset_type,
        "url": file_url
    }
