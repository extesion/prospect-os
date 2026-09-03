from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
import logging

from backend.database.connection import get_db
from backend.database.models import (
    User, Channel, CollectionEvent, WorkSession, WorkSessionEvent,
    Notification, YouTubeApiUsage, AuditLog, UserMusicConnection, utc_now
)
from qualifier.models.qualification_result import QualificationResult
from qualifier.models.qualification_job import QualificationJob
from qualifier.models.analyzed_video import AnalyzedVideo
from backend.security.auth import get_current_admin_user, verify_system_password

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/system", tags=["System Administration (Admin Only)"])

class SystemResetRequest(BaseModel):
    system_password: str = Field(..., description="Senha mestra do sistema")
    confirmation: str = Field(..., description="Texto de confirmação 'RESETAR'")

@router.post("/reset")
def reset_system_operational_data(
    body: SystemResetRequest,
    db: Session = Depends(get_db),
    admin_user: User = Depends(get_current_admin_user)
):
    """
    Executa o reset seguro e transacional de todos os dados operacionais do Prospect OS:
    - Canais coletados
    - Histórico e eventos de coleta
    - Sessões de trabalho e produtividade
    - Qualificações, jobs e vídeos analisados
    - Notificações da equipe
    - Logs de uso de APIs do YouTube e auditorias operacionais

    PRESERVA INTEGRALMENTE:
    - Usuários e senhas
    - Níveis (ADMIN/USER)
    - Perfis (Avatares, Banners, Biografia)
    - Chaves e configurações de APIs do YouTube
    - Configurações e presets de metas/ciclos
    """
    # 1. Validação estrita da senha mestra do sistema
    if not verify_system_password(body.system_password):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Senha do sistema incorreta."
        )

    # 2. Validação estrita do texto de confirmação
    if body.confirmation.strip() != "RESETAR":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Confirmação inválida. Digite exatamente 'RESETAR' para confirmar a operação."
        )

    # 3. Execução atômica e transacional respeitando integridade referencial
    try:
        # A. Limpeza do Qualificador de Leads
        db.query(AnalyzedVideo).delete(synchronize_session=False)
        db.query(QualificationResult).delete(synchronize_session=False)
        db.query(QualificationJob).delete(synchronize_session=False)

        # B. Limpeza de Produtividade, Sessões e Eventos
        db.query(CollectionEvent).delete(synchronize_session=False)
        db.query(WorkSessionEvent).delete(synchronize_session=False)
        db.query(WorkSession).delete(synchronize_session=False)

        # C. Limpeza de Canais Coletados
        db.query(Channel).delete(synchronize_session=False)

        # D. Limpeza de Notificações
        db.query(Notification).delete(synchronize_session=False)

        # E. Limpeza de Logs Operacionais de API e Auditoria
        db.query(YouTubeApiUsage).delete(synchronize_session=False)
        db.query(AuditLog).delete(synchronize_session=False)

        # F. Reset de dados de reprodução ao vivo nas conexões de música mantendo tokens
        db.query(UserMusicConnection).update(
            {
                "current_track_name": None,
                "current_artist": None,
                "current_album_art": None,
                "current_track_url": None,
                "is_playing": False,
                "session_tracks_json": None,
                "most_played_track": None,
                "most_played_artist": None,
                "most_played_count": 0,
                "updated_at": utc_now()
            },
            synchronize_session=False
        )

        db.commit()
        logger.info(f"System reset executed successfully by admin {admin_user.email} (ID {admin_user.id}).")

        return {
            "success": True,
            "status": "success",
            "message": "Dados operacionais do sistema resetados com sucesso.",
            "cleared": {
                "channels": 0,
                "hours": 0,
                "sessions": 0,
                "notifications": 0,
                "qualifications": 0
            }
        }
    except Exception as e:
        db.rollback()
        logger.error(f"Erro durante o reset operacional do sistema: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Falha na execução do reset: {str(e)}"
        )
