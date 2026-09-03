from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import Optional, List
import logging
from sqlalchemy.exc import SQLAlchemyError

from backend.database.connection import get_db
from backend.database.models import User
from backend.security.auth import get_current_user, get_current_admin_user
from backend.schemas.work_session import (
    WorkSessionStart, WorkSessionResponse, UserRankingItem,
    TeamStatusItem, TeamSummaryResponse, CycleSettingsResponse,
    CycleSettingsUpdate, SessionHistoryItem
)
from backend.services.work_session_service import WorkSessionService

router = APIRouter(prefix="/work-sessions", tags=["Work Sessions & Productivity"])
logger = logging.getLogger(__name__)

# Failures traced at the route boundary (no tokens/passwords logged).
_SQL_ERRORS = (SQLAlchemyError,)

@router.post("/start", response_model=WorkSessionResponse)
def start_work_session(
    data: WorkSessionStart,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Inicia uma sessão de trabalho de prospecção.
    Se o usuário já tiver uma sessão ativa ou pausada, retorna/retoma a sessão existente.
    """
    try:
        return WorkSessionService.start_session(db, current_user, data)
    except _SQL_ERRORS as e:
        db.rollback()
        # SQL statement parameters may contain secrets; log type and driver message only.
        driver_error = getattr(e, "orig", e)
        logger.error(
            "work_session_start_failed stage=database exception_type=%s message=%s",
            type(e).__name__, str(driver_error)[:500],
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Não foi possível iniciar a sessão de trabalho.",
        )
    except Exception as e:
        db.rollback()
        logger.error("work_session_start_failed stage=application exception_type=%s", type(e).__name__)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Não foi possível iniciar a sessão de trabalho.",
        )

@router.post("/pause", response_model=WorkSessionResponse)
def pause_work_session(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Pausa a sessão de trabalho ativa do usuário. O tempo pausado NÃO contabiliza no ranking.
    """
    try:
        return WorkSessionService.pause_session(db, current_user)
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

@router.post("/resume", response_model=WorkSessionResponse)
def resume_work_session(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Retoma a sessão de trabalho pausada do usuário.
    """
    try:
        return WorkSessionService.resume_session(db, current_user)
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

@router.post("/finish", response_model=WorkSessionResponse)
def finish_work_session(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Finaliza a sessão de trabalho atual do usuário e consolida as horas trabalhadas.
    """
    try:
        return WorkSessionService.finish_session(db, current_user)
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

@router.get("/current", response_model=Optional[WorkSessionResponse])
def get_current_session(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Retorna a sessão de trabalho ativa ou pausada do usuário logado (com métricas em tempo real).
    """
    return WorkSessionService.get_current_session(db, current_user)

@router.get("/ranking", response_model=List[UserRankingItem])
def get_hours_ranking(
    period: str = Query("today", pattern="^(today|week|month)$"),
    db: Session = Depends(get_db)
):

    """
    Retorna o ranking da equipe ordenado EXCLUSIVAMENTE por HORAS TRABALHADAS (active_seconds DESC).
    Filtros disponíveis: today (Hoje), week (Esta Semana), month (Este Mês).
    """
    return WorkSessionService.get_ranking(db, period=period)

@router.get("/team/status", response_model=TeamSummaryResponse)
def get_team_live_status(
    db: Session = Depends(get_db)
):
    """
    Retorna a visão geral da equipe em tempo real (usuários trabalhando, horas totais hoje e membros).
    """
    return WorkSessionService.get_team_summary(db)

@router.get("/history", response_model=List[SessionHistoryItem])
def get_sessions_history(
    user_id: Optional[int] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    admin_user: User = Depends(get_current_admin_user)
):
    """
    Histórico detalhado de sessões finalizadas para auditoria e acompanhamento (Exclusivo ADMIN).
    """
    return WorkSessionService.get_history(db, user_id=user_id, limit=limit, offset=offset)

@router.get("/settings", response_model=CycleSettingsResponse)
def get_cycle_settings(
    db: Session = Depends(get_db)
):
    """
    Retorna a meta diária padrão e os presets de ciclos (8h, 6h, Personalizado).
    """
    return WorkSessionService.get_cycle_settings(db)

@router.put("/settings", response_model=CycleSettingsResponse)
def update_cycle_settings(
    data: CycleSettingsUpdate,
    db: Session = Depends(get_db),
    admin_user: User = Depends(get_current_admin_user)
):
    """
    Atualiza as configurações de metas e presets de ciclos da equipe (Exclusivo ADMIN).
    """
    return WorkSessionService.update_cycle_settings(db, data)
