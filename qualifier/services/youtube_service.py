import requests
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
from qualifier.config.qualification_config import qualification_config

logger = logging.getLogger("qualifier.youtube")

class YouTubeQuotaExceededException(Exception):
    pass

class YouTubeService:
    BASE_URL = "https://www.googleapis.com/youtube/v3"
    _estimated_quota_used_today = 0
    _last_quota_reset_day = None

    @classmethod
    def _track_quota(cls, units: int):
        current_day = datetime.now(timezone.utc).date()
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
        self.api_key = api_key or qualification_config.YOUTUBE_API_KEY

    def _check_quota_available(self):
        if self._estimated_quota_used_today >= qualification_config.DAILY_QUOTA_LIMIT:
            raise YouTubeQuotaExceededException("Daily YouTube API quota limit reached.")

    def fetch_channels_batch(self, channel_ids: List[str]) -> Dict[str, Dict[str, Any]]:
        """
        Fetches channel details in batch using channels.list (max 50 IDs per request).
        Returns a dict mapping channel_id -> channel_data.
        """
        if not channel_ids:
            return {}

        self._check_quota_available()
        results: Dict[str, Dict[str, Any]] = {}
        
        # Batch up to 50
        for i in range(0, len(channel_ids), 50):
            chunk = channel_ids[i:i + 50]
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
                    cid = item.get("id")
                    snippet = item.get("snippet", {})
                    content_details = item.get("contentDetails", {})
                    statistics = item.get("statistics", {})

                    uploads_playlist_id = content_details.get("relatedPlaylists", {}).get("uploads")

                    results[cid] = {
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
            except YouTubeQuotaExceededException:
                raise
            except Exception as e:
                logger.error(f"[YOUTUBE] Error fetching channels batch: {str(e)}")
                raise

        return results

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
                raise YouTubeQuotaExceededException("YouTube API quota exceeded on playlistItems.")
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
            logger.error(f"[YOUTUBE] Error fetching playlist {uploads_playlist_id}: {str(e)}")
            return []

    def fetch_videos_batch(self, video_ids: List[str]) -> Dict[str, Dict[str, Any]]:
        """
        Fetches video details in batch using videos.list (max 50 IDs per request).
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
                "part": "snippet,contentDetails,statistics",
                "id": ids_param,
                "key": self.api_key
            }

            try:
                self._track_quota(1)
                response = requests.get(url, params=params, timeout=10)
                if response.status_code == 403:
                    raise YouTubeQuotaExceededException("YouTube API quota exceeded on videos.list.")
                response.raise_for_status()
                data = response.json()

                for item in data.get("items", []):
                    vid = item.get("id")
                    snippet = item.get("snippet", {})
                    content_details = item.get("contentDetails", {})
                    statistics = item.get("statistics", {})

                    results[vid] = {
                        "video_id": vid,
                        "title": snippet.get("title", ""),
                        "description": snippet.get("description", ""),
                        "published_at": snippet.get("publishedAt"),
                        "tags": snippet.get("tags", []),
                        "duration": content_details.get("duration", ""),
                        "view_count": int(statistics.get("viewCount", 0)) if statistics.get("viewCount") is not None else 0,
                        "like_count": int(statistics.get("likeCount", 0)) if statistics.get("likeCount") is not None else 0,
                        "comment_count": int(statistics.get("commentCount", 0)) if statistics.get("commentCount") is not None else 0,
                    }
            except YouTubeQuotaExceededException:
                raise
            except Exception as e:
                logger.error(f"[YOUTUBE] Error fetching videos batch: {str(e)}")
                raise

        return results
