from abc import ABC, abstractmethod
from typing import Optional, Dict, Any
from pydantic import BaseModel

class TrackInfo(BaseModel):
    is_playing: bool = False
    track_name: Optional[str] = None
    artist: Optional[str] = None
    album_name: Optional[str] = None
    album_art: Optional[str] = None
    track_url: Optional[str] = None
    duration_ms: Optional[int] = None
    progress_ms: Optional[int] = None
    provider: str

class MusicProvider(ABC):
    @property
    @abstractmethod
    def provider_name(self) -> str:
        pass

    @abstractmethod
    def get_auth_url(self, state: str, redirect_uri: str) -> str:
        """Retorna a URL de autorização OAuth do provedor."""
        pass

    @abstractmethod
    def exchange_code_for_token(self, code: str, redirect_uri: str) -> Dict[str, Any]:
        """Troca o authorization code pelo access token e refresh token."""
        pass

    @abstractmethod
    def get_currently_playing(self, access_token: str) -> Optional[TrackInfo]:
        """Consulta a faixa atualmente tocando via API oficial."""
        pass

    @abstractmethod
    def refresh_access_token(self, refresh_token: str) -> Optional[Dict[str, Any]]:
        """Renova o access token usando o refresh token."""
        pass
