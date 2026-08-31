import os
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
import requests
import logging

from qualifier.config.qualification_config import qualification_config

logger = logging.getLogger(__name__)

class YouTubeQuotaExceededException(Exception):
    pass

class YouTubeService:
    BASE_URL = "https://www.googleapis.com/youtube/v3"
    
    _estimated_quota_used_today: int = 0
    _last_quota_reset_day: Optional[int] = None

    @classmethod
    def _track_quota(cls, units: int = 1):
        current_day = datetime.now(timezone.utc).day
        if cls._last_quota_reset_day != current_day:
            cls._estimated_quota_used_today = 0
            cls._last_quota_reset_day = current_day

        cls._estimated_quota_used_today += units
        if cls._estimated_quota_used_today >= qualification_config.DAILY_QUOTA_LIMIT:
            logger.warning(f"[QUOTA_LIMIT] Daily quota limit reached: {cls._estimated_quota_used_today}/{qualification_config.DAILY_QUOTA_LIMIT}")

    @classmethod
    def get_quota_used_today(cls) -> int:
        return cls._estimated_quota_used_today

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or qualification_config.YOUTUBE_API_KEY or os.getenv("YOUTUBE_API_KEY", "")

    def _check_quota_available(self):
        if not self.api_key:
            self.api_key = qualification_config.YOUTUBE_API_KEY or os.getenv("YOUTUBE_API_KEY", "")
            if not self.api_key:
                raise ValueError("Chave da YouTube API (YOUTUBE_API_KEY) não configurada.")

        if self._estimated_quota_used_today >= qualification_config.DAILY_QUOTA_LIMIT:
            raise YouTubeQuotaExceededException("Daily YouTube API quota limit reached.")

    def fetch_channels_batch(self, channel_ids: List[str]) -> Dict[str, Dict[str, Any]]:
        """
        Fetches channel details in batch using channels.list.
        Supports true YouTube channel IDs (UC...) as well as handles (UC_HDL_... or @handle).
        Returns a dict mapping original_channel_id -> channel_data.
        """
        if not channel_ids:
            return {}

        self._check_quota_available()
        results: Dict[str, Dict[str, Any]] = {}

        standard_ids = []
        handle_map = {} # handle -> list of original_channel_ids

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
                # Treat any other custom string as handle
                handle_map.setdefault(cid, []).append(cid)

        # 1. Fetch standard IDs in batches of 50
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
                    self._track_quota(1)
                    response = requests.get(url, params=params, timeout=10)
                    
                    if response.status_code == 403:
                        err_json = response.json().get("error", {})
                        reasons = [e.get("reason") for e in err_json.get("errors", [])]
                        if "quotaExceeded" in reasons or "rateLimitExceeded" in reasons:
                            raise YouTubeQuotaExceededException("YouTube API quota exceeded (HTTP 403).")
                        raise Exception(f"YouTube API error 403: {err_json.get('message')}")
                    
                    response.raise_for_status()
                    data = response.json()
                    
                    for item in data.get("items", []):
                        real_cid = item.get("id")
                        parsed_data = self._parse_channel_item(item)
                        results[real_cid] = parsed_data

                except YouTubeQuotaExceededException:
                    raise
                except Exception as e:
                    logger.error(f"[YOUTUBE] Error fetching standard channels batch: {str(e)}")
                    raise

        # 2. Fetch handle-based channels via forHandle
        for handle, orig_cids in handle_map.items():
            url = f"{self.BASE_URL}/channels"
            params = {
                "part": "snippet,contentDetails,statistics",
                "forHandle": handle,
                "key": self.api_key
            }

            try:
                self._track_quota(1)
                response = requests.get(url, params=params, timeout=10)
                
                if response.status_code == 403:
                    err_json = response.json().get("error", {})
                    reasons = [e.get("reason") for e in err_json.get("errors", [])]
                    if "quotaExceeded" in reasons or "rateLimitExceeded" in reasons:
                        raise YouTubeQuotaExceededException("YouTube API quota exceeded (HTTP 403).")
                    raise Exception(f"YouTube API error 403: {err_json.get('message')}")

                if response.status_code == 200:
                    data = response.json()
                    items = data.get("items", [])
                    if items:
                        parsed_data = self._parse_channel_item(items[0])
                        # Map both real_id and each original_cid to the parsed data
                        results[parsed_data["channel_id"]] = parsed_data
                        for orig_cid in orig_cids:
                            results[orig_cid] = parsed_data

            except YouTubeQuotaExceededException:
                raise
            except Exception as e:
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

        self._check_quota_available()
        url = f"{self.BASE_URL}/playlistItems"
        params = {
            "part": "contentDetails",
            "playlistId": uploads_playlist_id,
            "maxResults": max_results,
            "key": self.api_key
        }

        try:
            self._track_quota(1)
            response = requests.get(url, params=params, timeout=10)
            if response.status_code == 403:
                raise YouTubeQuotaExceededException("YouTube API quota exceeded in playlistItems (HTTP 403).")
            response.raise_for_status()
            data = response.json()

            video_ids = []
            for item in data.get("items", []):
                vid = item.get("contentDetails", {}).get("videoId")
                if vid:
                    video_ids.append(vid)
            return video_ids
        except YouTubeQuotaExceededException:
            raise
        except Exception as e:
            logger.error(f"[YOUTUBE] Error fetching playlist items: {str(e)}")
            return []

    def fetch_videos_batch(self, video_ids: List[str]) -> Dict[str, Dict[str, Any]]:
        """
        Fetches detailed metadata for a batch of videos using videos.list.
        Returns a dict mapping video_id -> video_data.
        """
        if not video_ids:
            return {}

        self._check_quota_available()
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
                self._track_quota(1)
                response = requests.get(url, params=params, timeout=10)
                if response.status_code == 403:
                    raise YouTubeQuotaExceededException("YouTube API quota exceeded in videos.list (HTTP 403).")
                response.raise_for_status()
                data = response.json()

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
                logger.error(f"[YOUTUBE] Error fetching videos batch: {str(e)}")
                raise

        return results
