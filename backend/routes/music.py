from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
import json
import logging

from backend.database.connection import get_db
from backend.database.models import User, UserMusicConnection, UserProfile, utc_now
from backend.security.auth import get_current_user
from backend.services.music.spotify_provider import SpotifyProvider, YouTubeMusicProvider

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/music", tags=["Music Integrations"])

spotify_provider = SpotifyProvider()
yt_music_provider = YouTubeMusicProvider()

@router.get("/status")
def get_music_status(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Retorna o status das conexões musicais do usuário (Spotify / YouTube Music)."""
    conn = db.query(UserMusicConnection).filter(UserMusicConnection.user_id == current_user.id).first()
    profile = db.query(UserProfile).filter(UserProfile.user_id == current_user.id).first()

    return {
        "spotify": {
            "configured": spotify_provider.is_configured(),
            "connected": bool(conn and conn.is_connected and conn.provider == "spotify"),
            "now_playing": {
                "track_name": conn.current_track_name if conn else None,
                "artist": conn.current_artist if conn else None,
                "album_art": conn.current_album_art if conn else None,
                "is_playing": conn.is_playing if conn else False
            } if conn and conn.is_connected else None,
            "most_played_session": {
                "track_name": conn.most_played_track if conn else None,
                "artist": conn.most_played_artist if conn else None,
                "count": conn.most_played_count if conn else 0
            } if conn and conn.most_played_track else None
        },
        "youtube_music": {
            "status": "EM_BREVE",
            "message": "Aguardando API oficial de playback do YouTube Music."
        },
        "privacy": {
            "show_music_to_team": profile.show_music_to_team if profile else True
        }
    }

@router.get("/spotify/auth-url")
def get_spotify_auth_url(
    redirect_uri: str = Query("https://prospect-os-seven.vercel.app/dashboard"),
    current_user: User = Depends(get_current_user)
):
    """Gera a URL oficial de autorização do Spotify."""
    if not spotify_provider.is_configured():
        raise HTTPException(
            status_code=400,
            detail="Integração Spotify não configurada no servidor (SPOTIFY_CLIENT_ID ausente)."
        )
    state = f"user_{current_user.id}"
    url = spotify_provider.get_auth_url(state=state, redirect_uri=redirect_uri)
    return {"auth_url": url}

@router.post("/spotify/callback")
def handle_spotify_callback(
    code: str = Query(...),
    redirect_uri: str = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Processa o código de retorno da autorização do Spotify e salva credenciais seguras."""
    tokens = spotify_provider.exchange_code_for_token(code=code, redirect_uri=redirect_uri)
    if not tokens or "access_token" not in tokens:
        raise HTTPException(status_code=400, detail="Falha ao trocar código de autorização do Spotify.")

    access_token = tokens.get("access_token")
    refresh_token = tokens.get("refresh_token")
    expires_in = tokens.get("expires_in", 3600)
    expires_at = utc_now() + timedelta(seconds=expires_in)

    conn = db.query(UserMusicConnection).filter(UserMusicConnection.user_id == current_user.id).first()
    if not conn:
        conn = UserMusicConnection(
            user_id=current_user.id,
            provider="spotify",
            is_connected=True,
            access_token=access_token,
            refresh_token=refresh_token,
            token_expires_at=expires_at,
            updated_at=utc_now()
        )
        db.add(conn)
    else:
        conn.provider = "spotify"
        conn.is_connected = True
        conn.access_token = access_token
        if refresh_token:
            conn.refresh_token = refresh_token
        conn.token_expires_at = expires_at
        conn.updated_at = utc_now()

    db.commit()
    db.refresh(conn)

    return {"success": True, "provider": "spotify", "connected": True}

@router.post("/spotify/disconnect")
def disconnect_spotify(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Desconecta a conta do Spotify."""
    conn = db.query(UserMusicConnection).filter(UserMusicConnection.user_id == current_user.id).first()
    if conn:
        conn.is_connected = False
        conn.access_token = None
        conn.refresh_token = None
        conn.is_playing = False
        conn.current_track_name = None
        conn.current_artist = None
        conn.updated_at = utc_now()
        db.commit()

    return {"success": True, "connected": False}
