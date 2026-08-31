import os
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
import requests
import logging
from sqlalchemy.orm import Session

from qualifier.config.qualification_config import qualification_config
from qualifier.services.youtube_api_manager import YouTubeApiManager, YouTubeQuotaExceededException

logger = logging.getLogger(__name__)

class YouTubeService:
    BASE_URL = "https://www.googleapis.com/youtube/v3"

    @classmethod
    def get_quota_used_today(cls) -> int:
        return YouTubeApiManager._estimated_quota_used_today if hasattr(YouTubeApiManager, '_estimated_quota_used_today') else 0

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

    def fetch_channels_batch(self, channel_ids: List[str]) -> Dict[str, Dict[str, Any]]:
        """
        Fetches channel details in batch using channels.list.
        Supports true YouTube channel IDs (UC...) as well as handles (UC_HDL_... or @handle).
        Returns a dict mapping original_channel_id -> channel_data.
        """
        if not channel_ids:
            return {}

        self._ensure_api_key()
        results: Dict[str, Dict[str, Any]] = {}

        standard_ids = []
        handle_map = {}

        for cid in channel_ids:
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
                
                url = f"{self.BASE_URL}/channels"
                params = {
                    "part": "snippet,contentDetails,statistics",
                    "id": ids_param,
                    "key": self.api_key
                }

                try:
                    response = requests.get(url, params=params, timeout=10)
                    
                    if response.status_code == 403:
                        err_msg = response.text
                        if self.db:
                            YouTubeApiManager.record_usage(self.db, self.config_id, "channels.list", 1, success=False, error_message=err_msg)
                        raise YouTubeQuotaExceededException(f"YouTube API error 403: {err_msg}")

                    response.raise_for_status()
                    data = response.json()
                    
                    if self.db:
                        YouTubeApiManager.record_usage(self.db, self.config_id, "channels.list", 1, success=True)

                    for item in data.get("items", []):
                        real_cid = item.get("id")
                        parsed_data = self._parse_channel_item(item)
                        results[real_cid] = parsed_data

                except YouTubeQuotaExceededException:
                    raise
                except Exception as e:
                    if self.db:
                        YouTubeApiManager.record_usage(self.db, self.config_id, "channels.list", 1, success=False, error_message=str(e))
                    logger.error(f"[YOUTUBE] Error fetching channels batch: {str(e)}")
                    raise

        # 2. Handle-based channels via forHandle
        for handle, orig_cids in handle_map.items():
            url = f"{self.BASE_URL}/channels"
            params = {
                "part": "snippet,contentDetails,statistics",
                "forHandle": handle,
                "key": self.api_key
            }

            try:
                response = requests.get(url, params=params, timeout=10)
                
                if response.status_code == 403:
                    err_msg = response.text
                    if self.db:
                        YouTubeApiManager.record_usage(self.db, self.config_id, "channels.list (handle)", 1, success=False, error_message=err_msg)
                    raise YouTubeQuotaExceededException(f"YouTube API error 403 on handle {handle}: {err_msg}")

                if response.status_code == 200:
                    data = response.json()
                    items = data.get("items", [])
                    if items:
                        parsed_data = self._parse_channel_item(items[0])
                        results[parsed_data["channel_id"]] = parsed_data
                        for orig_cid in orig_cids:
                            results[orig_cid] = parsed_data
                    
                    if self.db:
                        YouTubeApiManager.record_usage(self.db, self.config_id, "channels.list (handle)", 1, success=True)

            except YouTubeQuotaExceededException:
                raise
            except Exception as e:
                if self.db:
                    YouTubeApiManager.record_usage(self.db, self.config_id, "channels.list (handle)", 1, success=False, error_message=str(e))
                logger.warning(f"[YOUTUBE] Could not resolve handle {handle}: {str(e)}")

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

    def fetch_recent_video_ids_from_playlist(self, uploads_playlist_id: str, max_results: int = 3) -> List[str]:
        """
        Fetches up to max_results video IDs from the uploads playlist using playlistItems.list.
        """
        if not uploads_playlist_id:
            return []

        self._ensure_api_key()
        url = f"{self.BASE_URL}/playlistItems"
        params = {
            "part": "contentDetails",
            "playlistId": uploads_playlist_id,
            "maxResults": max_results,
            "key": self.api_key
        }

        try:
            response = requests.get(url, params=params, timeout=10)
            if response.status_code == 403:
                if self.db:
                    YouTubeApiManager.record_usage(self.db, self.config_id, "playlistItems.list", 1, success=False, error_message=response.text)
                raise YouTubeQuotaExceededException("YouTube API quota exceeded in playlistItems (HTTP 403).")
            
            response.raise_for_status()
            data = response.json()

            if self.db:
                YouTubeApiManager.record_usage(self.db, self.config_id, "playlistItems.list", 1, success=True)

            video_ids = []
            for item in data.get("items", []):
                vid = item.get("contentDetails", {}).get("videoId")
                if vid:
                    video_ids.append(vid)
            return video_ids
        except YouTubeQuotaExceededException:
            raise
        except Exception as e:
            if self.db:
                YouTubeApiManager.record_usage(self.db, self.config_id, "playlistItems.list", 1, success=False, error_message=str(e))
            logger.error(f"[YOUTUBE] Error fetching playlist items: {str(e)}")
            return []

    def fetch_videos_batch(self, video_ids: List[str]) -> Dict[str, Dict[str, Any]]:
        """
        Fetches detailed metadata for a batch of videos using videos.list.
        Returns a dict mapping video_id -> video_data.
        """
        if not video_ids:
            return {}

        self._ensure_api_key()
        results: Dict[str, Dict[str, Any]] = {}

        for i in range(0, len(video_ids), 50):
            chunk = video_ids[i:i + 50]
            ids_param = ",".join(chunk)

            url = f"{self.BASE_URL}/videos"
            params = {
                "part": "snippet,statistics,contentDetails",
                "id": ids_param,
                "key": self.api_key
            }

            try:
                response = requests.get(url, params=params, timeout=10)
                if response.status_code == 403:
                    if self.db:
                        YouTubeApiManager.record_usage(self.db, self.config_id, "videos.list", 1, success=False, error_message=response.text)
                    raise YouTubeQuotaExceededException("YouTube API quota exceeded in videos.list (HTTP 403).")
                
                response.raise_for_status()
                data = response.json()

                if self.db:
                    YouTubeApiManager.record_usage(self.db, self.config_id, "videos.list", 1, success=True)

                for item in data.get("items", []):
                    vid = item.get("id")
                    snippet = item.get("snippet", {})
                    statistics = item.get("statistics", {})
                    content_details = item.get("contentDetails", {})

                    results[vid] = {
                        "video_id": vid,
                        "title": snippet.get("title", ""),
                        "description": snippet.get("description", ""),
                        "published_at": snippet.get("publishedAt"),
                        "tags": snippet.get("tags", []),
                        "view_count": int(statistics.get("viewCount", 0)) if statistics.get("viewCount") is not None else 0,
                        "like_count": int(statistics.get("likeCount", 0)) if statistics.get("likeCount") is not None else 0,
                        "comment_count": int(statistics.get("commentCount", 0)) if statistics.get("commentCount") is not None else 0,
                        "duration": content_details.get("duration", "")
                    }
            except YouTubeQuotaExceededException:
                raise
            except Exception as e:
                if self.db:
                    YouTubeApiManager.record_usage(self.db, self.config_id, "videos.list", 1, success=False, error_message=str(e))
                logger.error(f"[YOUTUBE] Error fetching videos batch: {str(e)}")
                raise

        return results
