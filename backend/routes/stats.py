from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from backend.database.connection import get_db
from backend.database.models import User
from backend.schemas.stats import UserStats, TeamStats
from backend.services.channel_service import ChannelService
from backend.security.auth import get_current_user

router = APIRouter(prefix="/stats", tags=["Statistics"])

@router.get("/me", response_model=UserStats)
def get_my_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Retorna a quantidade de canais coletados hoje e no total pelo usuário logado.
    """
    return ChannelService.get_user_stats(db, current_user)

@router.get("/team", response_model=TeamStats)
def get_team_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Retorna métricas gerais da equipe (hoje, total e membros ativos).
    """
    return ChannelService.get_team_stats(db)
