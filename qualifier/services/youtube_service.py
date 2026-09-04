import os
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timedelta, timezone
import requests
import logging
import threading
from functools import lru_cache
from sqlalchemy.orm import Session

from backend.database.models import YouTubeApiConfig, utc_now
from qualifier.config.qualification_config import qualification_config
from qualifier.services.youtube_api_manager import YouTubeApiManager, YouTubeQuotaExceededException

logger = logging.getLogger(__name__)

# -------------------------------------------------------------------------
# Cost table for each endpoint (real YouTube API cost, not estimate)
# -------------------------------------------------------------------------
ENDPOINT_COSTS: Dict[str, int] = {
    "channels.list": 1,
    "channels.list (handle)": 1,
    "videos.list": 1,
    "playlistItems.list": 1,
}

# Internal in-memory LRU cache (TTL=300s. 5 minutes. Easy reset.)
_YT_CACHE: Optional[Dict[str, tuple]] = None
_CACHE_LOCK = threading.Lock()
CACHE_TTL_SECONDS = 300  # 5 minutes


def _init_cache() -> None:
    global _YT_CACHE
    if _YT_CACHE is None:
        _YT_CACHE = {}


def _get_cached(key: str) -> Optional[Any]:
    if _YT_CACHE is None:
        return None
    val, expiry = _YT_CACHE.get(key, (None, None))
    if expiry and datetime.now(timezone.utc) < expiry:
        return val
    return None


def _set_cached(key: str, value: Any, ttl_seconds: int = CACHE_TTL_SECONDS) -> None:
    if _YT_CACHE is None:
        _init_cache()
    expiry = datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)
    _YT_CACHE[key] = (value, expiry)


_cache_get = _get_cached
_cache_set = _set_cached


def _clear_cache() -> None:
    global _YT_CACHE
    with _CACHE_LOCK:
        _YT_CACHE = {}


# -------------------------------------------------------------------------
# Helper functions for error classification and key fallback
# -------------------------------------------------------------------------
def _is_invalid_key_error(status_code: int, response_text: str) -> bool:
    """Checks if HTTP response indicates an invalid or revoked API key."""
    if status_code == 400:
        lower = response_text.lower()
        if any(term in lower for term in ["api_key_invalid", "keyinvalid", "api key not valid", "invalid_argument", "badrequest"]):
            return True
        return True  # Any 400 with key parameter on YouTube API is bad request/key argument
    if status_code == 403:
        lower = response_text.lower()
        if any(term in lower for term in ["keyinvalid", "api_key_invalid", "api key not valid", "accessnotconfigured", "servicedisabled"]):
            return True
    return False


def _is_quota_exceeded_error(status_code: int, response_text: str) -> bool:
    """Checks if HTTP response indicates quota exhaustion."""
    if status_code == 403:
        lower = response_text.lower()
        if any(term in lower for term in ["quotaexceeded", "daily limit", "ratelimitexceeded", "user_rate_limit"]):
            return True
    return False


# -------------------------------------------------------------------------
# Robust tracked YouTube API execution with Multi-Key Fallback
# -------------------------------------------------------------------------
def _call_with_retry(
    db: Session,
    endpoint: str,
    operation: str,
    params: Dict[str, Any],
    max_retries_per_key: int = 3,
    base_delay: float = 1.0
) -> Tuple[Dict[str, Any], int]:
    """
    Executes a tracked YouTube request with multi-key fallback and transient retry.
    - If a key returns API_KEY_INVALID: marks key as ERROR in DB immediately, skips 3x retry, falls back to next key.
    - If a key returns QUOTA_EXCEEDED: marks key as QUOTA_EXCEEDED in DB, falls back to next key.
    - If transient failure (5xx, 429, timeout): retries current key up to max_retries_per_key with backoff.
    - Quota is recorded ONLY for valid successful calls (never for invalid keys).
    - Masks secrets in logs.
    """
    import time

    exclude_config_ids: List[int] = []
    last_exc: Optional[Exception] = None

    while True:
        try:
            config, api_key = YouTubeApiManager.select_active_config(db, exclude_ids=exclude_config_ids)
        except (ValueError, YouTubeQuotaExceededException) as e:
            if exclude_config_ids and last_exc:
                logger.error(f"[YOUTUBE_API] Todas as chaves ativas falharam. Último erro: {last_exc}")
            raise e

        config_id = getattr(config, "id", None)
        masked_key = YouTubeApiManager.mask_api_key(api_key)

        for attempt in range(max_retries_per_key):
            try:
                url = YouTubeService.BASE_URL + endpoint
                req_params = {"key": api_key, **params}

                response = requests.get(url, params=req_params, timeout=15)

                if response.ok:
                    cost = ENDPOINT_COSTS.get(operation, 1)
                    YouTubeApiManager.record_usage(db, config_id, operation, cost, success=True)
                    return response.json(), (config_id or 0)

                # Check if API_KEY_INVALID
                if _is_invalid_key_error(response.status_code, response.text):
                    logger.warning(
                        f"[YOUTUBE_API] API key {masked_key} (ID {config_id}) retornou API_KEY_INVALID ({response.status_code}). Marcando como ERROR no DB e tentando próxima chave imediatamente."
                    )
                    if config_id and config_id > 0:
                        cfg = db.query(YouTubeApiConfig).filter(YouTubeApiConfig.id == config_id).first()
                        if cfg:
                            cfg.status = "ERROR"
                            cfg.error_message = f"API_KEY_INVALID: Chave de API inválida ou revogada (HTTP {response.status_code})"
                            cfg.updated_at = utc_now()
                            db.commit()
                    last_exc = requests.HTTPError(f"API_KEY_INVALID ({response.status_code})", response=response)
                    break  # Never retry same invalid key 3x; break to fallback to next key immediately

                # Check if QUOTA_EXCEEDED
                if _is_quota_exceeded_error(response.status_code, response.text):
                    logger.warning(
                        f"[YOUTUBE_API] API key {masked_key} (ID {config_id}) atingiu quota (403 quotaExceeded). Marcando como QUOTA_EXCEEDED e tentando próxima chave."
                    )
                    if config_id and config_id > 0:
                        cfg = db.query(YouTubeApiConfig).filter(YouTubeApiConfig.id == config_id).first()
                        if cfg:
                            cfg.status = "QUOTA_EXCEEDED"
                            cfg.error_message = "Cota diária esgotada (403 quotaExceeded)"
                            cfg.updated_at = utc_now()
                            db.commit()
                    last_exc = YouTubeQuotaExceededException(f"Quota exceeded on config {config_id}")
                    break  # Break to fallback to next key

                # Other HTTP 4xx (e.g. 404)
                if 400 <= response.status_code < 500 and response.status_code != 429:
                    error_msg = f"HTTP {response.status_code}: {response.text}"
                    YouTubeApiManager.record_usage(db, config_id, operation, ENDPOINT_COSTS.get(operation, 1), success=False, error_message=error_msg)
                    response.raise_for_status()

                # Transient 5xx or 429
                last_exc = requests.HTTPError(f"HTTP {response.status_code}: {response.text}", response=response)

            except (requests.Timeout, requests.ConnectionError) as net_err:
                last_exc = net_err
                logger.warning(f"[YOUTUBE_API] Falha de rede temporária na tentativa {attempt + 1}/{max_retries_per_key}: {str(net_err)}")

            if attempt + 1 < max_retries_per_key:
                time.sleep(base_delay * (2 ** attempt))

        if config_id is not None:
            exclude_config_ids.append(config_id)
        elif 0 not in exclude_config_ids:
            exclude_config_ids.append(0)


class YouTubeService:
    BASE_URL = "https://www.googleapis.com/youtube/v3"

    # Cache entry templates
    _CACHE_CHANNEL_PREFIX = "channel:"
    _CACHE_CHANNEL_KEY_PREFIX = "channel:"
    _CACHE_PLAYLIST_PREFIX = "playlist:"
    _CACHE_VIDEO_PREFIX = "video:"

    @classmethod
    def get_quota_used_today(cls, db: Optional[Session] = None) -> int:
        if db:
            return YouTubeApiManager.get_today_usage_total(db)
        return YouTubeApiManager._estimated_quota_used_today if hasattr(YouTubeApiManager, "_estimated_quota_used_today") else 0

    def __init__(self, api_key: Optional[str] = None, db: Optional[Session] = None):
        self.api_key = api_key or qualification_config.YOUTUBE_API_KEY or os.getenv("YOUTUBE_API_KEY", "")
        self.db = db
        self.config_id = None

    def _ensure_api_key(self):
        if self.db:
            try:
                cfg, key = YouTubeApiManager.select_active_config(self.db)
                self.api_key = key
                self.config_id = cfg.id if cfg else None
                return
            except Exception as e:
                logger.warning(f"[YOUTUBE_MANAGER] Manager resolution notice: {str(e)}")

        if not self.api_key:
            env_key = qualification_config.YOUTUBE_API_KEY or os.getenv("YOUTUBE_API_KEY", "")
            if env_key and not YouTubeApiManager.is_dummy_or_placeholder_key(env_key):
                self.api_key = env_key
            else:
                raise ValueError("Nenhuma YouTube API key válida configurada")

    def fetch_channels_batch(self, channel_ids: List[str], force: bool = False) -> Dict[str, Dict[str, Any]]:
        """
        Fetches channel details in batch using channels.list.
        Supports true YouTube channel IDs (UC...) as well as handles (UC_HDL_... or @handle).
        Returns a dict mapping original_channel_id -> channel_data.
        """
        if not channel_ids:
            return {}

        self._ensure_api_key()
        results: Dict[str, Dict[str, Any]] = {}
        # Cache check (per id, with original input key)
        pending: List[str] = []
        for cid in channel_ids:
            if not force:
                cached = _cache_get(self._CACHE_CHANNEL_PREFIX + cid)
                if cached is not None:
                    results[cid] = cached
                    continue
            pending.append(cid)
        if not pending:
            return results

        standard_ids: List[str] = []
        handle_map: Dict[str, List[str]] = {}

        for cid in pending:
            if cid.startswith("UC_HDL_"):
                h = cid.replace("UC_HDL_", "")
                handle_map.setdefault(h, []).append(cid)
            elif cid.startswith("@"):
                h = cid.replace("@", "")
                handle_map.setdefault(h, []).append(cid)
            elif len(cid) == 24 and cid.startswith("UC"):
                standard_ids.append(cid)
            else:
                handle_map.setdefault(cid, []).append(cid)

        # 1. Standard IDs in batches of 50
        if standard_ids:
            for i in range(0, len(standard_ids), 50):
                chunk = standard_ids[i:i + 50]
                ids_param = ",".join(chunk)
                if not self.db:
                    url = f"{self.BASE_URL}/channels"
                    params = {
                        "part": "snippet,contentDetails,statistics",
                        "id": ids_param,
                        "key": self.api_key,
                    }
                    response = requests.get(url, params=params, timeout=10)
                    response.raise_for_status()
                    data = response.json()
                else:
                    data, used_config_id = _call_with_retry(
                        self.db,
                        "/channels",
                        "channels.list",
                        {"part": "snippet,contentDetails,statistics", "id": ids_param},
                    )
                    self.config_id = used_config_id

                for item in data.get("items", []):
                    parsed = self._parse_channel_item(item)
                    _cache_set(self._CACHE_CHANNEL_PREFIX + parsed["channel_id"], parsed)
                    for orig in chunk:
                        _cache_set(self._CACHE_CHANNEL_PREFIX + orig, parsed)
                    results[parsed["channel_id"]] = parsed
                    for orig in chunk:
                        results[orig] = parsed

        # 2. Handle-based channels via forHandle
        for handle, orig_cids in handle_map.items():
            if not self.db:
                url = f"{self.BASE_URL}/channels"
                params = {
                    "part": "snippet,contentDetails,statistics",
                    "forHandle": handle,
                    "key": self.api_key,
                }
                response = requests.get(url, params=params, timeout=10)
                response.raise_for_status()
                data = response.json()
            else:
                data, used_config_id = _call_with_retry(
                    self.db,
                    "/channels",
                    "channels.list (handle)",
                    {"part": "snippet,contentDetails,statistics", "forHandle": handle},
                )
                self.config_id = used_config_id

            items = data.get("items", [])
            if items:
                parsed = self._parse_channel_item(items[0])
                _cache_set(self._CACHE_CHANNEL_PREFIX + parsed["channel_id"], parsed)
                for orig in orig_cids:
                    _cache_set(self._CACHE_CHANNEL_PREFIX + orig, parsed)
                results[parsed["channel_id"]] = parsed
                for orig in orig_cids:
                    results[orig] = parsed

        return results

    def _parse_channel_item(self, item: Dict[str, Any]) -> Dict[str, Any]:
        cid = item.get("id")
        snippet = item.get("snippet", {})
        content_details = item.get("contentDetails", {})
        statistics = item.get("statistics", {})

        uploads_playlist_id = content_details.get("relatedPlaylists", {}).get("uploads")
        if not uploads_playlist_id and cid and len(cid) >= 3 and cid.startswith("UC"):
            uploads_playlist_id = "UU" + cid[2:]

        return {
            "channel_id": cid,
            "title": snippet.get("title", ""),
            "custom_url": snippet.get("customUrl", ""),
            "description": snippet.get("description", ""),
            "published_at": snippet.get("publishedAt"),
            "country": snippet.get("country"),
            "thumbnail": snippet.get("thumbnails", {}).get("default", {}).get("url"),
            "uploads_playlist_id": uploads_playlist_id,
            "subscribers": int(statistics.get("subscriberCount", 0)) if statistics.get("subscriberCount") is not None else 0,
            "total_views": int(statistics.get("viewCount", 0)) if statistics.get("viewCount") is not None else 0,
            "total_videos": int(statistics.get("videoCount", 0)) if statistics.get("videoCount") is not None else 0,
        }

    def fetch_recent_video_ids_from_playlist(
        self, uploads_playlist_id: str, max_results: int = 3, force: bool = False
    ) -> List[str]:
        """
        Fetches up to max_results video IDs from the uploads playlist using playlistItems.list.
        Uses cache (5 min TTL) unless force=True. Cost recorded centrally.
        """
        if not uploads_playlist_id:
            return []

        cache_key = f"{self._CACHE_PLAYLIST_PREFIX}{uploads_playlist_id}:{max_results}"
        if not force:
            cached = _cache_get(cache_key)
            if cached is not None:
                return cached

        self._ensure_api_key()
        if not self.db:
            # Without DB we cannot record usage or fall back across configs.
            url = f"{self.BASE_URL}/playlistItems"
            params = {
                "part": "contentDetails",
                "playlistId": uploads_playlist_id,
                "maxResults": max_results,
                "key": self.api_key,
            }
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
        else:
            data, used_config_id = _call_with_retry(
                self.db,
                "/playlistItems",
                "playlistItems.list",
                {
                    "part": "contentDetails",
                    "playlistId": uploads_playlist_id,
                    "maxResults": max_results,
                },
            )
            self.config_id = used_config_id

        video_ids = [
            item.get("contentDetails", {}).get("videoId")
            for item in data.get("items", [])
            if item.get("contentDetails", {}).get("videoId")
        ]
        _cache_set(cache_key, video_ids)
        return video_ids

    def fetch_videos_batch(self, video_ids: List[str], force: bool = False) -> Dict[str, Dict[str, Any]]:
        """
        Fetches detailed metadata for a batch of videos using videos.list.
        Honors cache unless force=True. Cost recorded centrally.
        """
        if not video_ids:
            return {}

        self._ensure_api_key()
        results: Dict[str, Dict[str, Any]] = {}

        # Serve cache hits first
        pending: List[str] = []
        if force:
            pending = list(video_ids)
        else:
            for vid in video_ids:
                cached = _cache_get(self._CACHE_VIDEO_PREFIX + vid)
                if cached is not None:
                    results[vid] = cached
                else:
                    pending.append(vid)

        for i in range(0, len(pending), 50):
            chunk = pending[i:i + 50]
            ids_param = ",".join(chunk)

            if not self.db:
                url = f"{self.BASE_URL}/videos"
                params = {
                    "part": "snippet,statistics,contentDetails",
                    "id": ids_param,
                    "key": self.api_key,
                }
                response = requests.get(url, params=params, timeout=10)
                response.raise_for_status()
                data = response.json()
            else:
                data, used_config_id = _call_with_retry(
                    self.db,
                    "/videos",
                    "videos.list",
                    {
                        "part": "snippet,statistics,contentDetails",
                        "id": ids_param,
                    },
                )
                self.config_id = used_config_id

            for item in data.get("items", []):
                vid = item.get("id")
                snippet = item.get("snippet", {})
                statistics = item.get("statistics", {})
                content_details = item.get("contentDetails", {})
                parsed = {
                    "video_id": vid,
                    "title": snippet.get("title", ""),
                    "description": snippet.get("description", ""),
                    "published_at": snippet.get("publishedAt"),
                    "tags": snippet.get("tags", []),
                    "view_count": int(statistics.get("viewCount", 0)) if statistics.get("viewCount") is not None else 0,
                    "like_count": int(statistics.get("likeCount", 0)) if statistics.get("likeCount") is not None else 0,
                    "comment_count": int(statistics.get("commentCount", 0)) if statistics.get("commentCount") is not None else 0,
                    "duration": content_details.get("duration", ""),
                }
                results[vid] = parsed
                _cache_set(self._CACHE_VIDEO_PREFIX + vid, parsed)

        return results
