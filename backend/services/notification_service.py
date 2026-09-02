import json
import logging
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import desc

from backend.database.models import Notification, User, WorkSession, utc_now
from backend.schemas.notification import NotificationResponse, NotificationCreate

logger = logging.getLogger(__name__)

class NotificationService:

    @staticmethod
    def create_notification(
        db: Session,
        notification_type: str,
        title: str,
        message: str,
        actor_user_id: Optional[int] = None,
        target_user_id: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Notification:
        """Cria e persiste uma notificação interna para a equipe."""
        meta_str = json.dumps(metadata) if metadata else None
        
        # Evitar duplicações de meta dentro da mesma sessão/ciclo
        if notification_type == "USER_REACHED_GOAL" and metadata and "session_id" in metadata:
            sess_id = metadata["session_id"]
            existing = (
                db.query(Notification)
                .filter(Notification.type == "USER_REACHED_GOAL")
                .filter(Notification.actor_user_id == actor_user_id)
                .all()
            )
            for n in existing:
                if n.metadata_json:
                    try:
                        n_meta = json.loads(n.metadata_json)
                        if n_meta.get("session_id") == sess_id:
                            logger.info(f"Meta já notificada para a sessão {sess_id}. Ignorando duplicata.")
                            return n
                    except Exception:
                        pass

        notif = Notification(
            type=notification_type,
            actor_user_id=actor_user_id,
            target_user_id=target_user_id,
            title=title,
            message=message,
            metadata_json=meta_str,
            created_at=utc_now()
        )
        db.add(notif)
        db.commit()
        db.refresh(notif)
        return notif

    @staticmethod
    def list_notifications(
        db: Session,
        current_user: User,
        limit: int = 50,
        unread_only: bool = False
    ) -> List[NotificationResponse]:
        """Lista notificações para o usuário logado (pessoais ou broadcast da equipe)."""
        query = db.query(Notification).filter(
            (Notification.target_user_id == current_user.id) | (Notification.target_user_id == None)
        )
        if unread_only:
            query = query.filter(Notification.read_at == None)

        notifs = query.order_by(desc(Notification.created_at)).limit(limit).all()

        results = []
        for n in notifs:
            meta = {}
            if n.metadata_json:
                try:
                    meta = json.loads(n.metadata_json)
                except Exception:
                    meta = {}
            
            actor_name = n.actor.name if n.actor else "PROSPECT OS"

            results.append(NotificationResponse(
                id=n.id,
                type=n.type,
                actor_user_id=n.actor_user_id,
                actor_name=actor_name,
                target_user_id=n.target_user_id,
                title=n.title,
                message=n.message,
                metadata=meta,
                read_at=n.read_at,
                is_read=bool(n.read_at is not None),
                created_at=n.created_at
            ))
        return results

    @staticmethod
    def mark_as_read(db: Session, notification_id: int, current_user: User) -> bool:
        """Marca uma notificação como lida."""
        notif = db.query(Notification).filter(Notification.id == notification_id).first()
        if notif:
            notif.read_at = utc_now()
            db.commit()
            return True
        return False

    @staticmethod
    def mark_all_as_read(db: Session, current_user: User) -> int:
        """Marca todas as notificações como lidas para o usuário."""
        now = utc_now()
        count = (
            db.query(Notification)
            .filter((Notification.target_user_id == current_user.id) | (Notification.target_user_id == None))
            .filter(Notification.read_at == None)
            .update({Notification.read_at: now}, synchronize_session=False)
        )
        db.commit()
        return count
