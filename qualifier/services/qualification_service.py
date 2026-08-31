import logging
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy import func

from backend.database.models import Channel, utc_now
from qualifier.models.qualification_result import QualificationResult
from qualifier.models.qualification_job import QualificationJob
from qualifier.models.analyzed_video import AnalyzedVideo
from qualifier.config.qualification_config import qualification_config
from qualifier.services.youtube_service import YouTubeService, YouTubeQuotaExceededException
from qualifier.services.link_extractor import LinkExtractor
from qualifier.services.email_extractor import EmailExtractor
from qualifier.services.whatsapp_detector import WhatsAppDetector
from qualifier.services.keyword_analyzer import KeywordAnalyzer
from qualifier.services.niche_detector import NicheDetector
from qualifier.services.commercial_signal_detector import CommercialSignalDetector
from qualifier.services.scoring_engine import ScoringEngine

logger = logging.getLogger("qualifier.service")

def parse_iso_datetime(dt_str: Optional[str]) -> Optional[datetime]:
    if not dt_str:
        return None
    try:
        # Replace Z with +00:00 for ISO 8601
        cleaned = dt_str.replace("Z", "+00:00")
        return datetime.fromisoformat(cleaned)
    except Exception:
        return None

class QualificationService:

    @staticmethod
    def enqueue_channel(db: Session, channel_id: str, priority: int = 0) -> QualificationJob:
        """Adds or re-activates a qualification job for a channel."""
        now = utc_now()
        existing_job = db.query(QualificationJob).filter(QualificationJob.channel_id == channel_id).first()
        if existing_job:
            existing_job.status = "PENDING"
            existing_job.attempts = 0
            existing_job.priority = priority
            existing_job.error_message = None
            existing_job.started_at = None
            existing_job.finished_at = None
            existing_job.updated_at = now
            db.commit()
            db.refresh(existing_job)
            return existing_job

        new_job = QualificationJob(
            channel_id=channel_id,
            status="PENDING",
            priority=priority,
            created_at=now,
            updated_at=now
        )
        db.add(new_job)
        db.commit()
        db.refresh(new_job)
        return new_job

    @staticmethod
    def backfill_unqualified_channels(db: Session) -> int:
        """Enqueues all channels from the database that do not yet have a qualification result."""
        # Find channels without qualification_result
        unqualified_cids = (
            db.query(Channel.channel_id)
            .outerjoin(QualificationResult, Channel.channel_id == QualificationResult.channel_id)
            .filter(QualificationResult.id == None)
            .all()
        )

        count = 0
        now = utc_now()
        for (cid,) in unqualified_cids:
            existing_job = db.query(QualificationJob.id).filter(
                QualificationJob.channel_id == cid,
                QualificationJob.status.in_(["PENDING", "PROCESSING"])
            ).first()
            if not existing_job:
                job = QualificationJob(channel_id=cid, status="PENDING", created_at=now, updated_at=now)
                db.add(job)
                count += 1

        db.commit()
        return count

    @staticmethod
    def analyze_and_store_qualification(
        db: Session,
        channel_data: Dict[str, Any],
        recent_videos: List[Dict[str, Any]]
    ) -> QualificationResult:
        """
        Executes local analysis pipelines (Regex, Link extraction, Keywords, Niching, Scoring)
        and persists QualificationResult and AnalyzedVideos.
        """
        now = utc_now()
        channel_id = channel_data["channel_id"]
        channel_desc = channel_data.get("description", "")
        channel_title = channel_data.get("title", "")

        # 1. Prepare texts with sources
        texts_with_sources: List[Dict[str, str]] = [
            {"text": channel_desc, "source": "channel_description"}
        ]
        all_tags: List[str] = []

        # Sort recent videos by published_at descending
        sorted_videos = sorted(
            recent_videos,
            key=lambda v: parse_iso_datetime(v.get("published_at")) or datetime.min.replace(tzinfo=timezone.utc),
            reverse=True
        )

        for idx, vid in enumerate(sorted_videos, 1):
            vid_desc = vid.get("description", "")
            source_name = "last_video_description" if idx == 1 else f"video_description_{idx}"
            texts_with_sources.append({"text": vid_desc, "source": source_name})
            for t in (vid.get("tags") or []):
                all_tags.append(t)

        # 2. Extract Links
        extracted_links = LinkExtractor.extract_links_from_texts(texts_with_sources)

        # 3. Extract Email
        extracted_email = EmailExtractor.extract_emails(texts_with_sources)

        # 4. Extract WhatsApp
        extracted_whatsapp = WhatsAppDetector.detect_whatsapp(texts_with_sources, extracted_links)

        # 5. Extract Keywords
        keywords_found, keywords_sources = KeywordAnalyzer.extract_keywords_with_sources(texts_with_sources)

        # 6. Detect Niche
        detected_niche, niche_confidence = NicheDetector.detect_niche(
            texts_with_sources,
            channel_name=channel_title,
            video_tags=all_tags
        )

        # 7. Detect Commercial Signals
        commercial_signals = CommercialSignalDetector.detect_signals(
            extracted_links=extracted_links,
            extracted_email=extracted_email,
            extracted_whatsapp=extracted_whatsapp,
            keywords_found=keywords_found,
            texts_with_sources=texts_with_sources
        )

        # 8. Activity Calculation
        days_since_last_video = None
        last_video_date = None
        last_video_title = None
        estimated_frequency = None
        activity_status = "INACTIVE"

        if sorted_videos:
            most_recent_dt = parse_iso_datetime(sorted_videos[0].get("published_at"))
            last_video_title = sorted_videos[0].get("title")
            if most_recent_dt:
                last_video_date = most_recent_dt
                delta = now - most_recent_dt
                days_since_last_video = max(0, delta.days)

                if days_since_last_video <= qualification_config.ACTIVE_DAYS_THRESHOLD:
                    activity_status = "ACTIVE"
                elif days_since_last_video <= qualification_config.LOW_ACTIVITY_DAYS_THRESHOLD:
                    activity_status = "LOW_ACTIVITY"
                else:
                    activity_status = "INACTIVE"

            if len(sorted_videos) >= 2:
                timestamps = [parse_iso_datetime(v.get("published_at")) for v in sorted_videos if v.get("published_at")]
                valid_ts = [t for t in timestamps if t is not None]
                if len(valid_ts) >= 2:
                    diffs = [(valid_ts[i] - valid_ts[i+1]).total_seconds() / 86400.0 for i in range(len(valid_ts)-1)]
                    positive_diffs = [d for d in diffs if d > 0]
                    if positive_diffs:
                        estimated_frequency = round(sum(positive_diffs) / len(positive_diffs), 1)

        # 9. Compute Score
        has_any_external_links = bool(
            extracted_links.get("website") or
            extracted_links.get("instagram") or
            extracted_links.get("sales_platforms") or
            extracted_links.get("link_aggregators")
        )

        score_res = ScoringEngine.compute_score(
            email=extracted_email.get("email"),
            website=extracted_links.get("website"),
            whatsapp=extracted_whatsapp.get("whatsapp"),
            instagram=extracted_links.get("instagram"),
            days_since_last_video=days_since_last_video,
            estimated_posting_frequency_days=estimated_frequency,
            commercial_signals=commercial_signals,
            keywords_found=keywords_found,
            link_aggregators=extracted_links.get("link_aggregators", []),
            sales_platforms=extracted_links.get("sales_platforms", []),
            has_any_external_links=has_any_external_links
        )

        # 10. Persist or Update QualificationResult
        qual_res = db.query(QualificationResult).filter(QualificationResult.channel_id == channel_id).first()
        if not qual_res:
            qual_res = QualificationResult(channel_id=channel_id, created_at=now)
            db.add(qual_res)

        qual_res.qualification_status = score_res["status"]
        qual_res.score = score_res["score"]
        qual_res.detected_niche = detected_niche
        qual_res.niche_confidence = niche_confidence
        qual_res.activity_status = activity_status
        qual_res.days_since_last_video = days_since_last_video
        qual_res.last_video_date = last_video_date
        qual_res.last_video_title = last_video_title
        qual_res.estimated_posting_frequency_days = estimated_frequency
        
        qual_res.channel_description_analyzed = True
        qual_res.last_video_description_analyzed = len(sorted_videos) > 0

        qual_res.subscribers = channel_data.get("subscribers", 0)
        qual_res.total_views = channel_data.get("total_views", 0)
        qual_res.total_videos = channel_data.get("total_videos", 0)
        qual_res.channel_created_at = parse_iso_datetime(channel_data.get("published_at"))
        qual_res.country = channel_data.get("country")
        qual_res.uploads_playlist_id = channel_data.get("uploads_playlist_id")

        qual_res.email = extracted_email.get("email")
        qual_res.email_source = extracted_email.get("email_source")
        qual_res.whatsapp = extracted_whatsapp.get("whatsapp")
        qual_res.whatsapp_source = extracted_whatsapp.get("whatsapp_source")
        qual_res.website = extracted_links.get("website")
        qual_res.instagram = extracted_links.get("instagram")
        qual_res.tiktok = extracted_links.get("tiktok")
        qual_res.twitter = extracted_links.get("twitter")
        qual_res.facebook = extracted_links.get("facebook")
        qual_res.linkedin = extracted_links.get("linkedin")

        qual_res.link_aggregators = extracted_links.get("link_aggregators")
        qual_res.sales_platforms = extracted_links.get("sales_platforms")
        qual_res.commercial_signals = commercial_signals
        qual_res.keywords_found = keywords_found
        qual_res.keywords_sources = keywords_sources
        qual_res.score_breakdown = score_res["score_breakdown"]
        qual_res.qualification_reason = score_res["qualification_reason"]
        qual_res.qualification_version = qualification_config.QUALIFICATION_VERSION
        qual_res.youtube_data_updated_at = now
        qual_res.updated_at = now
        qual_res.qualified_at = now

        db.flush()

        # 11. Clear and save AnalyzedVideos
        db.query(AnalyzedVideo).filter(AnalyzedVideo.qualification_result_id == qual_res.id).delete()

        for vid in sorted_videos:
            analyzed_vid = AnalyzedVideo(
                qualification_result_id=qual_res.id,
                channel_id=channel_id,
                video_id=vid.get("video_id", ""),
                title=vid.get("title", ""),
                description=vid.get("description", ""),
                published_at=parse_iso_datetime(vid.get("published_at")),
                view_count=vid.get("view_count", 0),
                like_count=vid.get("like_count", 0),
                comment_count=vid.get("comment_count", 0),
                duration=vid.get("duration", ""),
                tags=vid.get("tags", []),
                created_at=now
            )
            db.add(analyzed_vid)

        db.commit()
        db.refresh(qual_res)
        return qual_res

    @staticmethod
    def get_email_template_data(db: Session, channel_id: str) -> Optional[Dict[str, Any]]:
        """
        Prepares structured data ready for email template substitution:
        {{channel_name}}, {{channel_handle}}, {{detected_niche}}, {{subscriber_count}},
        {{last_video_title}}, {{last_video_date}}, {{website}}, {{email}}, {{instagram}}, etc.
        """
        ch = db.query(Channel).filter(Channel.channel_id == channel_id).first()
        qual = db.query(QualificationResult).filter(QualificationResult.channel_id == channel_id).first()

        if not ch and not qual:
            return None

        channel_name = ch.channel_name if ch else "Canal"
        channel_handle = ch.channel_handle if ch else None

        last_vid = None
        if qual and qual.analyzed_videos:
            last_vid = qual.analyzed_videos[0]

        return {
            "channel_id": channel_id,
            "channel_name": channel_name,
            "channel_handle": channel_handle,
            "detected_niche": qual.detected_niche if qual else None,
            "subscriber_count": qual.subscribers if qual else 0,
            "last_video_title": last_vid.title if last_vid else None,
            "last_video_date": qual.last_video_date.strftime("%Y-%m-%d") if (qual and qual.last_video_date) else None,
            "website": qual.website if qual else None,
            "email": qual.email if qual else None,
            "instagram": qual.instagram if qual else None,
            "commercial_signals": [s.get("type", "") for s in (qual.commercial_signals or [])] if qual else [],
            "qualification_reason": qual.qualification_reason if qual else None
        }
