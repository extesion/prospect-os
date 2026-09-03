from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.database.connection import get_db
from backend.database.models import User, Notification
from backend.schemas.notification import NotificationResponse, NotificationCountResponse
from backend.security.auth import get_current_user
from backend.services.notification_service import NotificationService

router = APIRouter(prefix="/notifications", tags=["Notifications"])

@router.get("", response_model=List[NotificationResponse])
def list_notifications(
    limit: int = 50,
    unread_only: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Retorna a lista de notificações da equipe e pessoais do usuário."""
    return NotificationService.list_notifications(db, current_user, limit=limit, unread_only=unread_only)

@router.get("/unread-count", response_model=NotificationCountResponse)
def get_unread_count(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Retorna a contagem de notificações não lidas."""
    count = NotificationService.get_unread_count(db, current_user)
    return NotificationCountResponse(unread_count=count)

@router.post("/{notification_id}/read")
def mark_notification_read(
    notification_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Marca uma notificação específica como lida."""
    success = NotificationService.mark_as_read(db, notification_id, current_user)
    return {"success": success}

@router.post("/read-all")
def mark_all_notifications_read(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Marca todas as notificações como lidas."""
    count = NotificationService.mark_all_as_read(db, current_user)
    return {"success": True, "marked_count": count}
