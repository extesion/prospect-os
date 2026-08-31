import time
import logging
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_

from backend.database.connection import SessionLocal
from backend.database.models import utc_now
from qualifier.models.qualification_job import QualificationJob
from qualifier.models.qualification_result import QualificationResult
from qualifier.config.qualification_config import qualification_config
from qualifier.services.youtube_service import YouTubeService, YouTubeQuotaExceededException
from qualifier.services.qualification_service import QualificationService

logger = logging.getLogger("qualifier.worker")

RETRY_BACKOFF_MINUTES = [5, 15, 60]

class QualificationWorker:

    def __init__(self, youtube_service: Optional[YouTubeService] = None):
        self.yt_service = youtube_service or YouTubeService()

    def fetch_pending_jobs(self, db: Session, limit: int = 50) -> List[QualificationJob]:
        """
        Fetches pending or retry-ready jobs ordered by priority descending and created_at ascending.
        """
        now = utc_now()
        jobs = (
            db.query(QualificationJob)
            .filter(
                or_(
                    QualificationJob.status == "PENDING",
                    and_(
                        QualificationJob.status == "RETRY",
                        or_(
                            QualificationJob.next_retry_at == None,
                            QualificationJob.next_retry_at <= now
                        )
                    )
                )
            )
            .order_by(QualificationJob.priority.desc(), QualificationJob.created_at.asc())
            .limit(limit)
            .all()
        )
        return jobs

    def process_batch(self, db: Session, limit: int = 50) -> Dict[str, Any]:
        """
        Processes a batch of pending qualification jobs efficiently.
        """
        jobs = self.fetch_pending_jobs(db, limit=limit)
        if not jobs:
            return {"processed": 0, "completed": 0, "failed": 0, "retried": 0, "message": "No pending jobs"}

        now = utc_now()
        job_map: Dict[str, QualificationJob] = {}

        # 1. Atomically mark selected jobs as PROCESSING
        for job in jobs:
            job.status = "PROCESSING"
            job.started_at = now
            job.updated_at = now
            job_map[job.channel_id] = job
        db.commit()

        channel_ids = list(job_map.keys())
        logger.info(f"[QUALIFICATION] Starting batch of {len(channel_ids)} channels: {channel_ids[:5]}...")

        # 2. Check cache for channels already analyzed recently
        channels_to_fetch_api: List[str] = []
        cache_valid_threshold = now - timedelta(days=qualification_config.REQUALIFICATION_INTERVAL_DAYS)

        completed_count = 0
        failed_count = 0
        retried_count = 0

        for cid in channel_ids:
            existing_result = db.query(QualificationResult).filter(QualificationResult.channel_id == cid).first()
            if existing_result and existing_result.youtube_data_updated_at and existing_result.youtube_data_updated_at > cache_valid_threshold:
                # Can reuse cached data and complete job
                job = job_map[cid]
                job.status = "COMPLETED"
                job.finished_at = utc_now()
                job.updated_at = utc_now()
                completed_count += 1
                logger.info(f"[QUALIFICATION] channel={cid} status=COMPLETED (cached)")
            else:
                channels_to_fetch_api.append(cid)

        if not channels_to_fetch_api:
            db.commit()
            return {
                "processed": len(channel_ids),
                "completed": completed_count,
                "failed": 0,
                "retried": 0,
                "message": "All jobs resolved from cache"
            }

        # 3. Call YouTube API for channels details in batch
        try:
            channels_api_data = self.yt_service.fetch_channels_batch(channels_to_fetch_api)
        except YouTubeQuotaExceededException as qe:
            logger.error(f"[ERROR] Quota exceeded during batch channel fetch: {str(qe)}")
            # Mark remaining as RETRY
            for cid in channels_to_fetch_api:
                job = job_map[cid]
                self._handle_retry(job, "Quota exceeded")
                retried_count += 1
            db.commit()
            return {"processed": len(channel_ids), "completed": completed_count, "failed": failed_count, "retried": retried_count, "error": "quota_exceeded"}
        except Exception as e:
            logger.error(f"[ERROR] Error fetching channels batch: {str(e)}")
            for cid in channels_to_fetch_api:
                job = job_map[cid]
                self._handle_retry(job, str(e))
                retried_count += 1
            db.commit()
            return {"processed": len(channel_ids), "completed": completed_count, "failed": failed_count, "retried": retried_count, "error": str(e)}

        # 4. For found channels, collect recent video IDs via playlistItems
        channel_video_ids_map: Dict[str, List[str]] = {}
        all_video_ids_to_fetch: List[str] = []

        for cid in channels_to_fetch_api:
            job = job_map[cid]
            ch_data = channels_api_data.get(cid)

            if not ch_data:
                # Permanent error: channel not found or deleted on YouTube
                job.status = "FAILED"
                job.error_message = "Canal não encontrado ou excluído no YouTube (404/Empty)."
                job.finished_at = utc_now()
                job.updated_at = utc_now()
                failed_count += 1
                logger.warning(f"[ERROR] channel={cid} reason=channel_not_found status=FAILED")
                continue

            uploads_playlist_id = ch_data.get("uploads_playlist_id")
            if uploads_playlist_id:
                try:
                    v_ids = self.yt_service.fetch_recent_video_ids_from_playlist(
                        uploads_playlist_id,
                        max_results=qualification_config.VIDEOS_TO_ANALYZE
                    )
                    channel_video_ids_map[cid] = v_ids
                    all_video_ids_to_fetch.extend(v_ids)
                except YouTubeQuotaExceededException:
                    logger.error(f"[ERROR] Quota exceeded on playlist fetch for channel={cid}")
                    self._handle_retry(job, "Quota exceeded on playlist fetch")
                    retried_count += 1
                    continue
                except Exception as e:
                    logger.warning(f"[WARNING] Could not fetch playlist for channel={cid}: {str(e)}")
                    channel_video_ids_map[cid] = []
            else:
                channel_video_ids_map[cid] = []

        # 5. Fetch all video details in batch
        videos_api_data: Dict[str, Dict[str, Any]] = {}
        if all_video_ids_to_fetch:
            try:
                videos_api_data = self.yt_service.fetch_videos_batch(all_video_ids_to_fetch)
            except YouTubeQuotaExceededException:
                logger.error("[ERROR] Quota exceeded during batch video fetch")
            except Exception as e:
                logger.warning(f"[WARNING] Error fetching videos batch: {str(e)}")

        # 6. Analyze and store each channel
        for cid, ch_data in channels_api_data.items():
            job = job_map[cid]
            if job.status != "PROCESSING":
                continue

            v_ids = channel_video_ids_map.get(cid, [])
            recent_videos = [videos_api_data[vid] for vid in v_ids if vid in videos_api_data]

            try:
                qual_result = QualificationService.analyze_and_store_qualification(
                    db=db,
                    channel_data=ch_data,
                    recent_videos=recent_videos
                )
                job.status = "COMPLETED"
                job.error_message = None
                job.finished_at = utc_now()
                job.updated_at = utc_now()
                completed_count += 1
                logger.info(f"[QUALIFICATION] channel={cid} score={qual_result.score} status={qual_result.qualification_status}")
            except Exception as e:
                logger.error(f"[ERROR] Failed local analysis for channel={cid}: {str(e)}")
                self._handle_retry(job, f"Analysis error: {str(e)}")
                retried_count += 1

        db.commit()
        return {
            "processed": len(channel_ids),
            "completed": completed_count,
            "failed": failed_count,
            "retried": retried_count
        }

    def _handle_retry(self, job: QualificationJob, error_msg: str):
        job.attempts += 1
        job.error_message = error_msg
        job.updated_at = utc_now()

        if job.attempts >= job.max_attempts:
            job.status = "FAILED"
            job.finished_at = utc_now()
        else:
            job.status = "RETRY"
            backoff_idx = min(job.attempts - 1, len(RETRY_BACKOFF_MINUTES) - 1)
            backoff_minutes = RETRY_BACKOFF_MINUTES[backoff_idx]
            job.next_retry_at = utc_now() + timedelta(minutes=backoff_minutes)

    def start_worker_loop(self, poll_interval_seconds: int = 10):
        """Continuous background worker loop."""
        logger.info(f"[WORKER] Starting Qualification Worker daemon (poll={poll_interval_seconds}s)...")
        while True:
            try:
                with SessionLocal() as db:
                    res = self.process_batch(db, limit=qualification_config.BATCH_SIZE)
                    if res.get("processed", 0) > 0:
                        logger.info(f"[WORKER] Batch result: {res}")
            except Exception as e:
                logger.error(f"[WORKER] Unexpected error in worker loop: {str(e)}")

            time.sleep(poll_interval_seconds)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    worker = QualificationWorker()
    worker.start_worker_loop(poll_interval_seconds=10)
