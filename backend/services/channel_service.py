from datetime import datetime, timezone, time
from typing import List, Dict, Tuple
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.exc import IntegrityError
from sqlalchemy import func

from backend.database.models import Channel, User, CollectionEvent, utc_now
from backend.schemas.channel import (
    ChannelCreate, ChannelBulkCreate, ChannelStatus, CollectorInfo,
    ChannelResponse, ChannelCollectResult, ChannelBulkResponse
)
from backend.schemas.stats import UserStats, TeamStats
import logging

logger = logging.getLogger(__name__)

class ChannelService:

    @staticmethod
    def check_channels(db: Session, channel_ids: List[str]) -> Dict[str, ChannelStatus]:
        """
        Efficiently checks duplicate status for a batch of YouTube Channel IDs.
        """
        if not channel_ids:
            return {}

        # Deduplicate incoming channel_ids list
        unique_ids = list(set(channel_ids))

        # Query all existing channels matching any of the IDs in batch
        existing_channels = (
            db.query(Channel)
            .options(joinedload(Channel.first_collector))
            .filter(Channel.channel_id.in_(unique_ids))
            .all()
        )

        results: Dict[str, ChannelStatus] = {}
        found_map = {ch.channel_id: ch for ch in existing_channels}

        for cid in unique_ids:
            if cid in found_map:
                ch = found_map[cid]
                collector_name = ch.first_collector.name if ch.first_collector else "Desconhecido"
                collector_id = ch.first_collected_by_id
                results[cid] = ChannelStatus(
                    exists=True,
                    collected_by=CollectorInfo(id=collector_id, name=collector_name),
                    collected_at=ch.first_collected_at
                )
            else:
                results[cid] = ChannelStatus(exists=False)

        return results

    @staticmethod
    def collect_single_channel(db: Session, channel_data: ChannelCreate, current_user: User) -> ChannelCollectResult:
        """
        Atomically collects a single YouTube channel, handling race conditions and ensuring uniqueness.
        """
        now = utc_now()
        
        # Quick check
        existing = (
            db.query(Channel)
            .options(joinedload(Channel.first_collector))
            .filter(Channel.channel_id == channel_data.channel_id)
            .first()
        )

        if existing:
            # Register attempt event
            event = CollectionEvent(
                channel_id=existing.channel_id,
                user_id=current_user.id,
                event_type="DUPLICATE_ATTEMPT",
                created_at=now
            )
            db.add(event)
            db.commit()

            collector_name = existing.first_collector.name if existing.first_collector else "Desconhecido"
            return ChannelCollectResult(
                success=False,
                already_exists=True,
                message=f"Canal já cadastrado por {collector_name}.",
                channel=ChannelResponse(
                    id=existing.id,
                    channel_id=existing.channel_id,
                    channel_name=existing.channel_name,
                    channel_handle=existing.channel_handle,
                    channel_url=existing.channel_url,
                    source=existing.source,
                    search_term=existing.search_term,
                    first_collected_by=CollectorInfo(
                        id=existing.first_collected_by_id,
                        name=collector_name
                    ),
                    first_collected_at=existing.first_collected_at,
                    created_at=existing.created_at
                )
            )

        # Attempt atomic insert
        try:
            new_channel = Channel(
                channel_id=channel_data.channel_id,
                channel_name=channel_data.channel_name,
                channel_handle=channel_data.channel_handle,
                channel_url=channel_data.channel_url,
                source=channel_data.source or "youtube_search",
                search_term=channel_data.search_term,
                first_collected_by_id=current_user.id,
                first_collected_at=now,
                created_at=now,
                updated_at=now
            )
            db.add(new_channel)
            
            # Check active work session for productivity tracking
            from backend.services.work_session_service import WorkSessionService
            active_session_id = WorkSessionService.register_channel_collection(db, current_user.id, channel_data.channel_id)

            # Event
            event = CollectionEvent(
                channel_id=channel_data.channel_id,
                user_id=current_user.id,
                work_session_id=active_session_id,
                event_type="COLLECT",
                created_at=now
            )
            db.add(event)

            # Auto-enqueue for qualification
            try:
                from qualifier.models.qualification_job import QualificationJob
                job = QualificationJob(
                    channel_id=channel_data.channel_id,
                    status="PENDING",
                    created_at=now,
                    updated_at=now
                )
                db.add(job)
            except Exception:
                pass

            db.commit()
            db.refresh(new_channel)

            return ChannelCollectResult(
                success=True,
                already_exists=False,
                message="Canal coletado com sucesso!",
                channel=ChannelResponse(
                    id=new_channel.id,
                    channel_id=new_channel.channel_id,
                    channel_name=new_channel.channel_name,
                    channel_handle=new_channel.channel_handle,
                    channel_url=new_channel.channel_url,
                    source=new_channel.source,
                    search_term=new_channel.search_term,
                    first_collected_by=CollectorInfo(
                        id=current_user.id,
                        name=current_user.name
                    ),
                    first_collected_at=new_channel.first_collected_at,
                    created_at=new_channel.created_at
                )
            )
        except IntegrityError:
            # Race condition triggered (another user just collected it a millisecond ago)
            db.rollback()
            existing = (
                db.query(Channel)
                .options(joinedload(Channel.first_collector))
                .filter(Channel.channel_id == channel_data.channel_id)
                .first()
            )
            collector_name = existing.first_collector.name if (existing and existing.first_collector) else "Outro usuário"
            return ChannelCollectResult(
                success=False,
                already_exists=True,
                message=f"Canal já cadastrado por {collector_name}.",
                channel=None
            )

    @staticmethod
    def collect_bulk(db: Session, bulk_data: ChannelBulkCreate, current_user: User) -> ChannelBulkResponse:
        """
        Collects multiple channels in bulk, ignoring already existing channels and ensuring atomicity.
        """
        from backend.services.work_session_service import WorkSessionService
        now = utc_now()
        inserted: List[str] = []
        already_exists: List[str] = []
        errors: List[str] = []

        for item in bulk_data.channels:
            cid = item.channel_id.strip() if item.channel_id else ""
            if not cid:
                continue

            try:
                with db.begin_nested():
                    existing = db.query(Channel.id).filter(Channel.channel_id == cid).first()
                    if existing:
                        already_exists.append(cid)
                        continue

                    c_url = item.channel_url or f"https://www.youtube.com/channel/{cid}"
                    c_name = item.channel_name or item.channel_handle or "Canal YouTube"

                    new_channel = Channel(
                        channel_id=cid,
                        channel_name=c_name,
                        channel_handle=item.channel_handle,
                        channel_url=c_url,
                        source=item.source or "youtube_search",
                        search_term=item.search_term,
                        first_collected_by_id=current_user.id,
                        first_collected_at=now,
                        created_at=now,
                        updated_at=now
                    )
                    db.add(new_channel)
                    
                    active_session_id = WorkSessionService.register_channel_collection(db, current_user.id, cid)

                    event = CollectionEvent(
                        channel_id=cid,
                        user_id=current_user.id,
                        work_session_id=active_session_id,
                        event_type="BULK_COLLECT",
                        created_at=now
                    )
                    db.add(event)

                    try:
                        from qualifier.models.qualification_job import QualificationJob
                        job = QualificationJob(
                            channel_id=cid,
                            status="PENDING",
                            created_at=now,
                            updated_at=now
                        )
                        db.add(job)
                    except Exception:
                        pass

                    inserted.append(cid)
            except IntegrityError:
                already_exists.append(cid)
            except Exception as e:
                logger.error(f"Error inserting channel {cid}: {str(e)}")
                errors.append(f"{cid}: {str(e)}")

        db.commit()
        return ChannelBulkResponse(
            inserted=inserted,
            already_exists=already_exists,
            errors=errors
        )

    @staticmethod
    def get_user_stats(db: Session, user: User) -> UserStats:
        """
        Retrieves today's collection count and all-time collection count for the specified user.
        """
        today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        
        today_count = (
            db.query(func.count(Channel.id))
            .filter(Channel.first_collected_by_id == user.id)
            .filter(Channel.first_collected_at >= today_start)
            .scalar()
        ) or 0

        total_count = (
            db.query(func.count(Channel.id))
            .filter(Channel.first_collected_by_id == user.id)
            .scalar()
        ) or 0

        return UserStats(
            user_id=user.id,
            user_name=user.name,
            today_count=today_count,
            total_count=total_count
        )

    @staticmethod
    def get_team_stats(db: Session) -> TeamStats:
        """
        Retrieves team-wide collection metrics.
        """
        today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

        today_count = (
            db.query(func.count(Channel.id))
            .filter(Channel.first_collected_at >= today_start)
            .scalar()
        ) or 0

        total_count = (
            db.query(func.count(Channel.id))
            .scalar()
        ) or 0

        active_users_today = (
            db.query(func.count(func.distinct(Channel.first_collected_by_id)))
            .filter(Channel.first_collected_at >= today_start)
            .scalar()
        ) or 0

        return TeamStats(
            today_count=today_count,
            total_count=total_count,
            active_users_today=active_users_today
        )
