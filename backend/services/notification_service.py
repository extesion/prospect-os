import json
import logging
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import desc
from sqlalchemy.exc import IntegrityError

from backend.database.models import Notification, User, utc_now
from backend.schemas.notification import NotificationResponse, NotificationCreate

logger = logging.getLogger(__name__)

SESSION_STARTED = "SESSION_STARTED"
GOAL_REACHED = "GOAL_REACHED"
CYCLE_COMPLETED = "CYCLE_COMPLETED"


def _build_dedupe_key(notification_type: str, target_user_id: int, ref_id: int) -> str:
    return f"{notification_type}:{target_user_id}:{ref_id}"


def _to_response(n: Notification) -> NotificationResponse:
    meta: Dict[str, Any] = {}
    if n.metadata_json:
        try:
            meta = json.loads(n.metadata_json)
        except Exception:
            meta = {}
    actor_name = n.actor.name if n.actor else "PROSPECT OS"
    return NotificationResponse(
        id=n.id, type=n.type, actor_user_id=n.actor_user_id, actor_name=actor_name,
        target_user_id=n.target_user_id, title=n.title, message=n.message, metadata=meta,
        read_at=n.read_at, is_read=n.read_at is not None, created_at=n.created_at,
    )


class NotificationService:

    @staticmethod
    def _insert_idempotent(
        db: Session, notification_type: str, title: str, message: str,
        target_user_id: int, actor_user_id: Optional[int] = None,
        ref_id: Optional[int] = None, metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[Notification]:
        dedupe_key = None
        if ref_id is not None:
            dedupe_key = _build_dedupe_key(notification_type, target_user_id, ref_id)
            existing = db.query(Notification).filter(Notification.dedupe_key == dedupe_key).first()
            if existing:
                return existing
        notif = Notification(
            type=notification_type, actor_user_id=actor_user_id, target_user_id=target_user_id,
            title=title, message=message, metadata_json=json.dumps(metadata) if metadata else None,
            dedupe_key=dedupe_key, created_at=utc_now(),
        )
        db.add(notif)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            if dedupe_key:
                return db.query(Notification).filter(Notification.dedupe_key == dedupe_key).first()
        return notif

    @staticmethod
    def notify_session_started(db: Session, actor: User, session_id: int, cycle_type: str, daily_target: int) -> None:
        """SESSION_STARTED: 1 notif por destinatario+sessao. Caller faz commit."""
        recipients = db.query(User).filter(
            User.active == True, User.is_deleted == False, User.id != actor.id
        ).all()
        start_time_str = utc_now().strftime("%H:%M")
        for r in recipients:
            NotificationService._insert_idempotent(
                db=db, notification_type=SESSION_STARTED, title="Turno Iniciado",
                message=f"{actor.name} iniciou um turno de trabalho as {start_time_str}.",
                target_user_id=r.id, actor_user_id=actor.id, ref_id=session_id,
                metadata={"session_id": session_id, "cycle_type": cycle_type, "target": daily_target},
            )
        # Nota: commit feito pelo caller (work_session_service)

    @staticmethod
    def notify_goal_reached(db: Session, actor_user_id: int, session_id: int, daily_target: int, collected_count: int, actor_name: str) -> None:
        """GOAL_REACHED: 1 notif por sessao para o ator. Caller faz commit."""
        NotificationService._insert_idempotent(
            db=db, notification_type=GOAL_REACHED, title="Meta Atingida!",
            message=f"{actor_name} atingiu a meta de {daily_target} canais!",
            target_user_id=actor_user_id, actor_user_id=actor_user_id, ref_id=session_id,
            metadata={"session_id": session_id, "daily_target": daily_target, "collected_count": collected_count},
        )

    @staticmethod
    def notify_cycle_completed(db: Session, actor: User, session_id: int, collected_count: int, active_seconds: int, average_rate: float, time_str: str) -> None:
        """CYCLE_COMPLETED: 1 notif por sessao para o ator. Caller faz commit."""
        NotificationService._insert_idempotent(
            db=db, notification_type=CYCLE_COMPLETED, title="Ciclo Finalizado",
            message=f"{actor.name} finalizou seu ciclo: {collected_count} canais em {time_str} ({average_rate} canais/h).",
            target_user_id=actor.id, actor_user_id=actor.id, ref_id=session_id,
            metadata={"session_id": session_id, "collected_count": collected_count,
                      "active_seconds": active_seconds, "average_rate": average_rate},
        )

    @staticmethod
    def create_notification(db: Session, notification_type: str, title: str, message: str,
                            actor_user_id: Optional[int] = None, target_user_id: Optional[int] = None,
                            metadata: Optional[Dict[str, Any]] = None) -> Optional[Notification]:
        """Shim de compatibilidade."""
        effective_target = target_user_id if target_user_id is not None else actor_user_id
        if effective_target is None:
            return None
        ref_id = metadata.get("session_id") if metadata else None
        return NotificationService._insert_idempotent(
            db=db, notification_type=notification_type, title=title, message=message,
            target_user_id=effective_target, actor_user_id=actor_user_id, ref_id=ref_id, metadata=metadata,
        )

    @staticmethod
    def list_notifications(db: Session, current_user: User, limit: int = 50, unread_only: bool = False) -> List[NotificationResponse]:
        q = db.query(Notification).filter(Notification.target_user_id == current_user.id)
        if unread_only:
            q = q.filter(Notification.read_at == None)
        return [_to_response(n) for n in q.order_by(desc(Notification.created_at)).limit(limit).all()]

    @staticmethod
    def get_unread_count(db: Session, current_user: User) -> int:
        return db.query(Notification).filter(
            Notification.target_user_id == current_user.id, Notification.read_at == None
        ).count()

    @staticmethod
    def mark_as_read(db: Session, notification_id: int, current_user: User) -> bool:
        notif = db.query(Notification).filter(
            Notification.id == notification_id, Notification.target_user_id == current_user.id
        ).first()
        if not notif:
            return False
        if notif.read_at is None:
            notif.read_at = utc_now()
            db.commit()
        return True

    @staticmethod
    def mark_all_as_read(db: Session, current_user: User) -> int:
        count = db.query(Notification).filter(
            Notification.target_user_id == current_user.id, Notification.read_at == None
        ).update({Notification.read_at: utc_now()}, synchronize_session=False)
        db.commit()
        return count

