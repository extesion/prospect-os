import os
import uuid
import logging
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session

from backend.database.connection import get_db
from backend.database.models import User, UserProfile
from backend.schemas.user_profile import UserProfileStats, UserProfileUpdate
from backend.security.auth import get_current_user
from backend.services.profile_service import ProfileService

router = APIRouter(prefix="/profiles", tags=["User Profiles & Productivity"])

# Upload directory
UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "..", "static", "uploads")
try:
    os.makedirs(UPLOAD_DIR, exist_ok=True)
except Exception:
    pass

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

logger = logging.getLogger(__name__)

@router.post("/upload/{asset_type}")
async def upload_profile_media(
    asset_type: str, # 'avatar' or 'banner'
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Upload seguro de Avatar ou Banner (JPG, PNG, WEBP, GIF animado)."""
    logger.info(f"Upload request: user_id={current_user.id}, asset_type={asset_type}, filename={file.filename}, content_type={file.content_type}")
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
    logger.debug(f"Received file size: {len(content)} bytes")
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

    # If file can be written to disk, write it; also create Data URL for guaranteed persistence on serverless
    import base64
    # Store static URL relative path if saved to disk, with data_url as fallback
    ext = ALLOWED_MIME_TYPES[content_type]
    safe_filename = f"{current_user.id}_{asset_type}_{uuid.uuid4().hex[:8]}{ext}"
    file_path = os.path.join(UPLOAD_DIR, safe_filename)
    public_url = f"/static/uploads/{safe_filename}"

    disk_saved = False
    try:
        with open(file_path, "wb") as f:
            f.write(content)
        disk_saved = True
        logger.info(f"Saved uploaded file to {file_path}")
    except Exception as e:
        logger.warning(f"Disk write not available: {e}. Using Data URL.")

    # Generate Data URL (guaranteed across ephemeral/serverless environments and local dev)
    import base64
    b64_str = base64.b64encode(content).decode("utf-8")
    data_url = f"data:{content_type};base64,{b64_str}"

    # Use data_url to guarantee persistent preview and animated GIFs
    final_media_url = data_url

    # Update profile record
    profile = ProfileService.get_or_create_profile(db, current_user.id)
    try:
        if asset_type == "avatar":
            profile.avatar_url = final_media_url
        else:
            profile.banner_url = final_media_url
        db.commit()
        db.refresh(profile)
        logger.info(f"Profile {asset_type} URL updated for user {current_user.id}")
    except Exception as e:
        logger.error(f"Error updating profile media in DB: {e}", exc_info=True)
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to update profile media.")
    
    return {
        "success": True,
        "asset_type": asset_type,
        "url": final_media_url,
        "static_url": public_url if disk_saved else None
    }
