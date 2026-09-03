import os
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timedelta, timezone
import requests
import logging
import threading
from functools import lru_cache
from sqlalchemy.orm import Session

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


def _get_cached(key: str) -> Optional[tuple]:
    if _YT_CACHE is None:
        return None
    val, expiry = _YT_CACHE.get(key, (None, 0))
    if datetime.now(timezone.utc) < expiry:
        return val
    return None


def _set_cached(key: str, value: Any, ttl_seconds: int = CACHE_TTL_SECONDS) -> None:
    if _YT_CACHE is None:
        _init_cache()
    expiry = datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)
    _YT_CACHE[key] = (value, expiry)


def _clear_cache() -> None:
    with _CACHE_LOCK:
        _YT_CACHE = {}


# -------------------------------------------------------------------------
# Decorator to add retry/backoff around API calls
# -------------------------------------------------------------------------
def _call_with_retry(db: Session, endpoint: str, operation: str, params: Dict[str, Any],
                     max_retries: int = 3, base_delay: float = 1.0) -> Tuple[Dict[str, Any], int]:
    """Executes a tracked YouTube request with retry for temporary failures."""
    import time

    last_exc: Optional[Exception] = None
    for attempt in range(max_retries):
        config, api_key = YouTubeApiManager.get_active_config(db)
        config_id = config.id
        try:
            response = requests.get(
                YouTubeService.BASE_URL + endpoint,
                params={"key": api_key, **params},
                timeout=15,
            )
            if response.ok:
                YouTubeApiManager.record_usage(db, config_id, operation, ENDPOINT_COSTS[operation])
                return response.json(), config_id

            error = f"HTTP {response.status_code}: {response.text}"
            YouTubeApiManager.record_usage(db, config_id, operation, ENDPOINT_COSTS[operation], False, error)
            if 400 <= response.status_code < 500 and response.status_code != 429:
                response.raise_for_status()
            last_exc = requests.HTTPError(error, response=response)
        except requests.RequestException as exc:
            last_exc = exc
            YouTubeApiManager.record_usage(db, config_id, operation, ENDPOINT_COSTS[operation], False, str(exc))

        if attempt + 1 < max_retries:
            time.sleep(base_delay * (2 ** attempt))

    raise YouTubeQuotaExceededException(
        f"Retry exhausted after {max_retries} attempts: {last_exc}"
    ) from last_exc


class YouTubeService:
    BASE_URL = "https://www.googleapis.com/youtube/v3"

    # Cache entry templates
    _CACHE_CHANNEL_KEY_PREFIX = "channel:"
    _CACHE_PLAYLIST_PREFIX = "playlist:"

    @classmethod
    def get_quota_used_today(cls) -> int:
        return YouTubeApiManager._estimated_quota_used_today if hasattr(YouTubeApiManager, "_estimated_quota_used_today") else 0

    def __init__(self, api_key: Optional[str] = None, db: Optional[Session] = None):
        self.api_key = api_key or qualification_config.YOUTUBE_API_KEY or os.getenv("YOUTUBE_API_KEY", "")
        self.db = db
        self.config_id = None

    def _ensure_api_key(self):
        if self.db:
            try:
                cfg, key = YouTubeApiManager.get_active_config(self.db)
                self.api_key = key
                self.config_id = cfg.id if cfg else None
                return
            except Exception as e:
                logger.warning(f"[YOUTUBE_MANAGER] Manager resolution notice: {str(e)}")

        if not self.api_key:
            self.api_key = qualification_config.YOUTUBE_API_KEY or os.getenv("YOUTUBE_API_KEY", "")
            if not self.api_key:
                raise ValueError("Chave da YouTube API (YOUTUBE_API_KEY) não configurada.")

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
