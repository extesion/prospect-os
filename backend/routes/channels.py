from fastapi import APIRouter, Depends, status, HTTPException
from sqlalchemy.orm import Session
from backend.database.connection import get_db
from backend.database.models import User
from backend.schemas.channel import (
    ChannelCheckRequest, ChannelCheckResponse,
    ChannelCreate, ChannelBulkCreate,
    ChannelCollectResult, ChannelBulkResponse
)
from backend.services.channel_service import ChannelService
from backend.security.auth import get_current_user, get_current_admin_user

router = APIRouter(prefix="/channels", tags=["Channels"])

@router.post("/check", response_model=ChannelCheckResponse)
def check_channels(
    request: ChannelCheckRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Verifica em lote o status de existência e dados de coleta dos canais informados.
    """
    statuses = ChannelService.check_channels(db, request.channel_ids)
    return ChannelCheckResponse(channels=statuses)

@router.post("", response_model=ChannelCollectResult)
def collect_channel(
    channel_data: ChannelCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Coleta um canal individual de forma atômica, prevenindo duplicidades mesmo com múltiplos usuários.
    """
    result = ChannelService.collect_single_channel(db, channel_data, current_user)
    return result

@router.post("/bulk", response_model=ChannelBulkResponse)
def collect_channels_bulk(
    bulk_data: ChannelBulkCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Coleta múltiplos canais de uma vez, ignorando os que já existem e garantindo atomicidade.
    """
    result = ChannelService.collect_bulk(db, bulk_data, current_user)
    return result

@router.get("/list")
def list_collected_channels(
    limit: int = 200,
    offset: int = 0,
    db: Session = Depends(get_db),
    admin_user: User = Depends(get_current_admin_user)
):
    """
    Lista os canais coletados para a visualização na Dashboard da equipe.
    """
    from backend.database.models import Channel
    from sqlalchemy.orm import joinedload

    channels = (
        db.query(Channel)
        .options(joinedload(Channel.first_collector))
        .order_by(Channel.first_collected_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    return {
        "channels": [
            {
                "id": ch.id,
                "channel_id": ch.channel_id,
                "channel_name": ch.channel_name,
                "channel_handle": ch.channel_handle,
                "channel_url": ch.channel_url,
                "source": ch.source,
                "search_term": ch.search_term,
                "first_collected_by": {
                    "id": ch.first_collected_by_id,
                    "name": ch.first_collector.name if ch.first_collector else "Equipe"
                },
                "first_collected_at": ch.first_collected_at.isoformat() if ch.first_collected_at else None
            }
            for ch in channels
        ]
    }

