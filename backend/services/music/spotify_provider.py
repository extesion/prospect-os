import os
import urllib.parse
import httpx
import logging
from typing import Optional, Dict, Any
from backend.services.music.music_provider import MusicProvider, TrackInfo

logger = logging.getLogger(__name__)

class SpotifyProvider(MusicProvider):
    def __init__(self):
        self.client_id = os.getenv("SPOTIFY_CLIENT_ID", "")
        self.client_secret = os.getenv("SPOTIFY_CLIENT_SECRET", "")
        self.auth_url = "https://accounts.spotify.com/authorize"
        self.token_url = "https://accounts.spotify.com/api/token"
        self.api_base = "https://api.spotify.com/v1"

    @property
    def provider_name(self) -> str:
        return "spotify"

    def is_configured(self) -> bool:
        return bool(self.client_id and len(self.client_id) > 5)

    def get_auth_url(self, state: str, redirect_uri: str) -> str:
        if not self.is_configured():
            return ""
        scopes = "user-read-currently-playing user-read-playback-state"
        params = {
            "client_id": self.client_id,
            "response_type": "code",
            "redirect_uri": redirect_uri,
            "state": state,
            "scope": scopes,
            "show_dialog": "true"
        }
        return f"{self.auth_url}?{urllib.parse.urlencode(params)}"

    def exchange_code_for_token(self, code: str, redirect_uri: str) -> Dict[str, Any]:
        if not self.is_configured():
            return {}
        try:
            with httpx.Client(timeout=10.0) as client:
                res = client.post(
                    self.token_url,
                    data={
                        "grant_type": "authorization_code",
                        "code": code,
                        "redirect_uri": redirect_uri,
                        "client_id": self.client_id,
                        "client_secret": self.client_secret
                    },
                    headers={"Content-Type": "application/x-www-form-urlencoded"}
                )
                if res.status_code == 200:
                    return res.json()
                logger.error(f"Spotify token exchange error: {res.text}")
        except Exception as e:
            logger.error(f"Exception during Spotify token exchange: {e}")
        return {}

    def refresh_access_token(self, refresh_token: str) -> Optional[Dict[str, Any]]:
        if not self.is_configured():
            return None
        try:
            with httpx.Client(timeout=10.0) as client:
                res = client.post(
                    self.token_url,
                    data={
                        "grant_type": "refresh_token",
                        "refresh_token": refresh_token,
                        "client_id": self.client_id,
                        "client_secret": self.client_secret
                    },
                    headers={"Content-Type": "application/x-www-form-urlencoded"}
                )
                if res.status_code == 200:
                    return res.json()
        except Exception as e:
            logger.error(f"Spotify token refresh error: {e}")
        return None

    def get_currently_playing(self, access_token: str) -> Optional[TrackInfo]:
        if not access_token:
            return None
        try:
            with httpx.Client(timeout=6.0) as client:
                res = client.get(
                    f"{self.api_base}/me/player/currently-playing",
                    headers={"Authorization": f"Bearer {access_token}"}
                )
                if res.status_code == 204 or not res.content:
                    return TrackInfo(provider="spotify", is_playing=False)
                if res.status_code == 200:
                    data = res.json()
                    item = data.get("item")
                    is_playing = data.get("is_playing", False)
                    if not item:
                        return TrackInfo(provider="spotify", is_playing=False)

                    track_name = item.get("name")
                    artists = ", ".join([a.get("name", "") for a in item.get("artists", [])])
                    album = item.get("album", {})
                    album_name = album.get("name")
                    images = album.get("images", [])
                    album_art = images[0].get("url") if images else None
                    track_url = item.get("external_urls", {}).get("spotify")

                    return TrackInfo(
                        provider="spotify",
                        is_playing=is_playing,
                        track_name=track_name,
                        artist=artists,
                        album_name=album_name,
                        album_art=album_art,
                        track_url=track_url,
                        duration_ms=item.get("duration_ms"),
                        progress_ms=data.get("progress_ms")
                    )
        except Exception as e:
            logger.debug(f"Spotify currently playing error: {e}")
        return None


class YouTubeMusicProvider(MusicProvider):
    """
    YouTube Music Provider (Arquitetura preparada).
    Como o YouTube Music não possui API pública oficial de 'Currently Playing' em tempo real,
    mantemos a interface preparada com status explícito 'EM BREVE' sem scraping inseguro.
    """
    @property
    def provider_name(self) -> str:
        return "youtube_music"

    def get_auth_url(self, state: str, redirect_uri: str) -> str:
        return ""

    def exchange_code_for_token(self, code: str, redirect_uri: str) -> Dict[str, Any]:
        return {}

    def get_currently_playing(self, access_token: str) -> Optional[TrackInfo]:
        return None

    def refresh_access_token(self, refresh_token: str) -> Optional[Dict[str, Any]]:
        return None
