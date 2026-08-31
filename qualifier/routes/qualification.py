import os
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func, or_, and_, desc

from backend.database.connection import get_db
from backend.database.models import Channel, User
from backend.security.auth import get_current_user
from qualifier.models.qualification_result import QualificationResult
from qualifier.models.qualification_job import QualificationJob
from qualifier.models.analyzed_video import AnalyzedVideo
from qualifier.schemas.qualification_schema import (
    QualificationResultResponse,
    QualificationJobResponse,
    QualificationStatsResponse,
    EmailTemplateDataResponse,
    ConfigUpdateRequest,
    LeadItemResponse,
    LeadsPaginationResponse,
    QualifyBatchRequest
)
from qualifier.config.qualification_config import qualification_config
from qualifier.services.qualification_service import QualificationService
from qualifier.services.youtube_service import YouTubeService
from qualifier.worker import QualificationWorker

router = APIRouter(prefix="/qualification", tags=["Qualification"])

# ----------------------------------------------------------------------------
# 1. SERVE WEB INTERFACE
# ----------------------------------------------------------------------------

@router.get("", include_in_schema=False)
@router.get("/", include_in_schema=False)
def serve_qualifier_ui():
    """Retorna a interface web visual do Qualificador de Leads."""
    template_path = os.path.join(os.path.dirname(__file__), "..", "..", "backend", "templates", "qualifier.html")
    template_path = os.path.abspath(template_path)
    if os.path.exists(template_path):
        return FileResponse(template_path)
    return {"message": "Template qualifier.html não encontrado."}


# ----------------------------------------------------------------------------
# 2. STATUS OVERVIEW & STATS
# ----------------------------------------------------------------------------

@router.get("/status-overview")
def get_status_overview(db: Session = Depends(get_db)):
    """Retorna status de conexão (YouTube API, Processador, Banco) e contadores rápidos."""
    yt_api_configured = bool(qualification_config.YOUTUBE_API_KEY and len(qualification_config.YOUTUBE_API_KEY) > 10)
    
    total_channels = db.query(func.count(Channel.id)).scalar() or 0
    total_qualified = db.query(func.count(QualificationResult.id)).filter(QualificationResult.qualification_status == "QUALIFIED").scalar() or 0
    total_review = db.query(func.count(QualificationResult.id)).filter(QualificationResult.qualification_status == "REVIEW").scalar() or 0
    total_rejected = db.query(func.count(QualificationResult.id)).filter(QualificationResult.qualification_status == "REJECTED").scalar() or 0
    total_failed = db.query(func.count(QualificationResult.id)).filter(QualificationResult.qualification_status == "FAILED").scalar() or 0
    
    total_analyzed = db.query(func.count(QualificationResult.id)).scalar() or 0
    total_not_analyzed = max(0, total_channels - total_analyzed)

    total_outreach_ready = (
        db.query(func.count(QualificationResult.id))
        .filter(QualificationResult.score >= qualification_config.SCORE_QUALIFIED_THRESHOLD)
        .filter(QualificationResult.email != None)
        .scalar()
    ) or 0

    pending_jobs = db.query(func.count(QualificationJob.id)).filter(QualificationJob.status == "PENDING").scalar() or 0
    processing_jobs = db.query(func.count(QualificationJob.id)).filter(QualificationJob.status == "PROCESSING").scalar() or 0
    retry_jobs = db.query(func.count(QualificationJob.id)).filter(QualificationJob.status == "RETRY").scalar() or 0

    return {
        "connections": {
            "youtube_api": "connected" if yt_api_configured else "missing_key",
            "local_processor": "online",
            "database": "connected"
        },
        "stats": {
            "total_channels": total_channels,
            "not_analyzed": total_not_analyzed,
            "qualified": total_qualified,
            "review": total_review,
            "rejected": total_rejected,
            "failed": total_failed,
            "outreach_ready": total_outreach_ready,
            "pending_jobs": pending_jobs,
            "processing_jobs": processing_jobs,
            "retry_jobs": retry_jobs,
            "quota_used_today": YouTubeService.get_quota_used_today(),
            "daily_quota_limit": qualification_config.DAILY_QUOTA_LIMIT
        }
    }


# ----------------------------------------------------------------------------
# 3. LEADS LIST WITH ADVANCED FILTERS
# ----------------------------------------------------------------------------

@router.get("/leads", response_model=LeadsPaginationResponse)
def list_leads(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, le=200),
    status_filter: Optional[str] = Query(None, description="TODOS, NOT_ANALYZED, QUALIFIED, REVIEW, REJECTED, OUTREACH_READY, FAILED, PENDING"),
    q: Optional[str] = Query(None, description="Busca por nome, handle ou channel_id"),
    has_email: Optional[bool] = Query(None),
    has_whatsapp: Optional[bool] = Query(None),
    has_website: Optional[bool] = Query(None),
    has_instagram: Optional[bool] = Query(None),
    min_score: Optional[int] = Query(None),
    max_score: Optional[int] = Query(None),
    db: Session = Depends(get_db)
):
    """Retorna listagem consolidada de canais do banco com seus dados de qualificação e filtros."""
    query = (
        db.query(Channel, QualificationResult, QualificationJob)
        .outerjoin(QualificationResult, Channel.channel_id == QualificationResult.channel_id)
        .outerjoin(QualificationJob, Channel.channel_id == QualificationJob.channel_id)
    )

    # Search filter
    if q and q.strip():
        search_term = f"%{q.strip()}%"
        query = query.filter(
            or_(
                Channel.channel_name.ilike(search_term),
                Channel.channel_handle.ilike(search_term),
                Channel.channel_id.ilike(search_term)
            )
        )

    # Status tab filter
    if status_filter:
        sf = status_filter.upper()
        if sf == "NOT_ANALYZED":
            query = query.filter(QualificationResult.id == None)
        elif sf == "QUALIFIED":
            query = query.filter(QualificationResult.qualification_status == "QUALIFIED")
        elif sf == "REVIEW":
            query = query.filter(QualificationResult.qualification_status == "REVIEW")
        elif sf == "REJECTED":
            query = query.filter(QualificationResult.qualification_status == "REJECTED")
        elif sf == "FAILED":
            query = query.filter(
                or_(
                    QualificationResult.qualification_status == "FAILED",
                    QualificationJob.status == "FAILED"
                )
            )
        elif sf == "PENDING":
            query = query.filter(
                or_(
                    QualificationJob.status == "PENDING",
                    QualificationJob.status == "PROCESSING"
                )
            )
        elif sf == "OUTREACH_READY":
            query = query.filter(
                QualificationResult.score >= qualification_config.SCORE_QUALIFIED_THRESHOLD,
                QualificationResult.email != None
            )

    # Boolean flags filters
    if has_email is True:
        query = query.filter(QualificationResult.email != None)
    if has_whatsapp is True:
        query = query.filter(QualificationResult.whatsapp != None)
    if has_website is True:
        query = query.filter(QualificationResult.website != None)
    if has_instagram is True:
        query = query.filter(QualificationResult.instagram != None)

    # Score range filter
    if min_score is not None:
        query = query.filter(QualificationResult.score >= min_score)
    if max_score is not None:
        query = query.filter(QualificationResult.score <= max_score)

    total = query.count()
    offset = (page - 1) * page_size
    rows = query.order_by(Channel.created_at.desc()).offset(offset).limit(page_size).all()

    leads: List[LeadItemResponse] = []
    for ch, qual, job in rows:
        lead_status = "NOT_ANALYZED"
        error_msg = None

        if job and job.status in ("PROCESSING", "PENDING", "RETRY"):
            lead_status = job.status
        elif qual:
            lead_status = qual.qualification_status
        elif job and job.status == "FAILED":
            lead_status = "FAILED"
            error_msg = job.error_message

        outreach_ready = bool(qual and qual.score >= qualification_config.SCORE_QUALIFIED_THRESHOLD and qual.email)

        leads.append(
            LeadItemResponse(
                channel_id=ch.channel_id,
                channel_name=ch.channel_name,
                channel_handle=ch.channel_handle,
                channel_url=ch.channel_url,
                first_collected_at=ch.first_collected_at,
                status=lead_status,
                score=qual.score if qual else None,
                detected_niche=qual.detected_niche if qual else None,
                niche_confidence=qual.niche_confidence if qual else 0.0,
                subscribers=qual.subscribers if qual else 0,
                total_videos=qual.total_videos if qual else 0,
                days_since_last_video=qual.days_since_last_video if qual else None,
                last_video_date=qual.last_video_date if qual else None,
                email=qual.email if qual else None,
                whatsapp=qual.whatsapp if qual else None,
                website=qual.website if qual else None,
                instagram=qual.instagram if qual else None,
                outreach_ready=outreach_ready,
                qualification_reason=qual.qualification_reason if qual else None,
                qualified_at=qual.qualified_at if qual else None,
                error_message=error_msg
            )
        )

    # Stats for counter badges
    total_channels = db.query(func.count(Channel.id)).scalar() or 0
    total_qual = db.query(func.count(QualificationResult.id)).filter(QualificationResult.qualification_status == "QUALIFIED").scalar() or 0
    total_rev = db.query(func.count(QualificationResult.id)).filter(QualificationResult.qualification_status == "REVIEW").scalar() or 0
    total_rej = db.query(func.count(QualificationResult.id)).filter(QualificationResult.qualification_status == "REJECTED").scalar() or 0
    total_analyzed = db.query(func.count(QualificationResult.id)).scalar() or 0
    total_outreach = db.query(func.count(QualificationResult.id)).filter(QualificationResult.score >= qualification_config.SCORE_QUALIFIED_THRESHOLD, QualificationResult.email != None).scalar() or 0

    stats_map = {
        "all": total_channels,
        "not_analyzed": max(0, total_channels - total_analyzed),
        "qualified": total_qual,
        "review": total_rev,
        "rejected": total_rej,
        "outreach_ready": total_outreach
    }

    return LeadsPaginationResponse(
        total=total,
        page=page,
        page_size=page_size,
        leads=leads,
        stats=stats_map
    )


# ----------------------------------------------------------------------------
# 4. ACTION: QUALIFY BATCH (FROM WEB UI)
# ----------------------------------------------------------------------------

@router.post("/qualify-batch")
def qualify_batch_web(
    body: QualifyBatchRequest,
    db: Session = Depends(get_db)
):
    """Executa qualificação de um conjunto selecionado de canais ou de todos os pendentes."""
    channel_ids = body.channel_ids or []
    
    if body.qualify_all_pending or not channel_ids:
        # Enqueue all unqualified
        QualificationService.backfill_unqualified_channels(db)
    else:
        # Enqueue specific channel IDs
        for cid in channel_ids:
            QualificationService.enqueue_channel(db, cid, priority=10)

    # Process batch with local Python worker
    worker = QualificationWorker()
    result = worker.process_batch(db, limit=body.batch_size or 50)
    return result


# ----------------------------------------------------------------------------
# 5. ACTION: QUALIFY SINGLE CHANNEL
# ----------------------------------------------------------------------------

@router.post("/qualify-single/{channel_id}")
def qualify_single_web(
    channel_id: str,
    db: Session = Depends(get_db)
):
    """Qualifica um único canal imediatamente e retorna os dados atualizados."""
    QualificationService.enqueue_channel(db, channel_id, priority=100)
    
    worker = QualificationWorker()
    worker.process_batch(db, limit=1)

    result = (
        db.query(QualificationResult)
        .options(joinedload(QualificationResult.analyzed_videos))
        .filter(QualificationResult.channel_id == channel_id)
        .first()
    )

    if not result:
        job = db.query(QualificationJob).filter(QualificationJob.channel_id == channel_id).first()
        err_msg = job.error_message if job else "Não foi possível qualificar o canal."
        raise HTTPException(status_code=400, detail=err_msg)

    return result


# ----------------------------------------------------------------------------
# 6. DETAIL FOR "VER ANÁLISE" MODAL
# ----------------------------------------------------------------------------

@router.get("/leads/{channel_id}/detail")
def get_lead_detail_for_modal(
    channel_id: str,
    db: Session = Depends(get_db)
):
    """Retorna todos os metadados consolidados para exibição no modal de análise."""
    channel = db.query(Channel).filter(Channel.channel_id == channel_id).first()
    if not channel:
        raise HTTPException(status_code=404, detail="Canal não encontrado no banco de dados.")

    qual = (
        db.query(QualificationResult)
        .options(joinedload(QualificationResult.analyzed_videos))
        .filter(QualificationResult.channel_id == channel_id)
        .first()
    )

    job = db.query(QualificationJob).filter(QualificationJob.channel_id == channel_id).first()

    videos_list = []
    if qual and qual.analyzed_videos:
        for v in qual.analyzed_videos:
            videos_list.append({
                "video_id": v.video_id,
                "title": v.title,
                "description": v.description,
                "published_at": v.published_at.strftime("%d/%m/%Y %H:%M") if v.published_at else None,
                "view_count": v.view_count,
                "like_count": v.like_count,
                "comment_count": v.comment_count,
                "duration": v.duration,
                "tags": v.tags or []
            })

    return {
        "channel": {
            "channel_id": channel.channel_id,
            "channel_name": channel.channel_name,
            "channel_handle": channel.channel_handle,
            "channel_url": channel.channel_url,
            "source": channel.source,
            "search_term": channel.search_term,
            "first_collected_at": channel.first_collected_at.strftime("%d/%m/%Y %H:%M") if channel.first_collected_at else None
        },
        "qualification": {
            "status": qual.qualification_status if qual else ("FAILED" if (job and job.status == "FAILED") else "NOT_ANALYZED"),
            "score": qual.score if qual else None,
            "detected_niche": qual.detected_niche if qual else None,
            "niche_confidence": qual.niche_confidence if qual else 0.0,
            "activity_status": qual.activity_status if qual else "INACTIVE",
            "days_since_last_video": qual.days_since_last_video if qual else None,
            "last_video_date": qual.last_video_date.strftime("%d/%m/%Y") if (qual and qual.last_video_date) else None,
            "estimated_posting_frequency_days": qual.estimated_posting_frequency_days if qual else None,
            "subscribers": qual.subscribers if qual else 0,
            "total_views": qual.total_views if qual else 0,
            "total_videos": qual.total_videos if qual else 0,
            "country": qual.country if qual else None,
            "email": qual.email if qual else None,
            "email_source": qual.email_source if qual else None,
            "whatsapp": qual.whatsapp if qual else None,
            "whatsapp_source": qual.whatsapp_source if qual else None,
            "website": qual.website if qual else None,
            "instagram": qual.instagram if qual else None,
            "tiktok": qual.tiktok if qual else None,
            "twitter": qual.twitter if qual else None,
            "facebook": qual.facebook if qual else None,
            "linkedin": qual.linkedin if qual else None,
            "link_aggregators": qual.link_aggregators if qual else [],
            "sales_platforms": qual.sales_platforms if qual else [],
            "commercial_signals": qual.commercial_signals if qual else [],
            "keywords_found": qual.keywords_found if qual else [],
            "score_breakdown": qual.score_breakdown if qual else {},
            "qualification_reason": qual.qualification_reason if qual else None,
            "qualification_version": qual.qualification_version if qual else "v1",
            "qualified_at": qual.qualified_at.strftime("%d/%m/%Y %H:%M") if (qual and qual.qualified_at) else None,
            "outreach_ready": bool(qual and qual.score >= qualification_config.SCORE_QUALIFIED_THRESHOLD and qual.email),
            "error_message": job.error_message if (job and job.status == "FAILED") else None
        },
        "analyzed_videos": videos_list
    }


# ----------------------------------------------------------------------------
# 7. LEGACY / COMPATIBILITY QUEUE & CONFIG ROUTES
# ----------------------------------------------------------------------------

@router.get("/queue", response_model=List[QualificationJobResponse])
def get_qualification_queue(
    status_filter: Optional[str] = Query(None),
    limit: int = Query(50, le=200),
    db: Session = Depends(get_db)
):
    query = db.query(QualificationJob)
    if status_filter:
        query = query.filter(QualificationJob.status == status_filter.upper())
    return query.order_by(QualificationJob.created_at.desc()).limit(limit).all()

@router.post("/run")
def run_qualification_batch(
    batch_size: int = Query(50, le=100),
    db: Session = Depends(get_db)
):
    worker = QualificationWorker()
    return worker.process_batch(db, limit=batch_size)

@router.post("/{channel_id}/run")
def qualify_channel_now(
    channel_id: str,
    db: Session = Depends(get_db)
):
    job = QualificationService.enqueue_channel(db, channel_id, priority=10)
    worker = QualificationWorker()
    worker.process_batch(db, limit=1)

    result = db.query(QualificationResult).filter(QualificationResult.channel_id == channel_id).first()
    if not result:
        db.refresh(job)
        if job.status == "FAILED":
            raise HTTPException(status_code=400, detail=f"Falha na qualificação: {job.error_message}")
        return {"message": "Job enfileirado para processamento", "job_status": job.status}
    return result

@router.post("/{channel_id}/retry")
def retry_qualification_job(
    channel_id: str,
    db: Session = Depends(get_db)
):
    job = db.query(QualificationJob).filter(QualificationJob.channel_id == channel_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job de qualificação não encontrado.")
    
    job.status = "PENDING"
    job.attempts = 0
    job.next_retry_at = None
    job.error_message = None
    db.commit()
    return {"message": f"Job para o canal {channel_id} reiniciado com sucesso.", "status": "PENDING"}

@router.get("/stats", response_model=QualificationStatsResponse)
def get_qualification_stats(db: Session = Depends(get_db)):
    total_channels = db.query(func.count(Channel.id)).scalar() or 0
    total_qualified = db.query(func.count(QualificationResult.id)).filter(QualificationResult.qualification_status == "QUALIFIED").scalar() or 0
    total_review = db.query(func.count(QualificationResult.id)).filter(QualificationResult.qualification_status == "REVIEW").scalar() or 0
    total_rejected = db.query(func.count(QualificationResult.id)).filter(QualificationResult.qualification_status == "REJECTED").scalar() or 0
    total_failed = db.query(func.count(QualificationResult.id)).filter(QualificationResult.qualification_status == "FAILED").scalar() or 0
    total_analyzed = db.query(func.count(QualificationResult.id)).scalar() or 0
    total_outreach = db.query(func.count(QualificationResult.id)).filter(QualificationResult.score >= qualification_config.SCORE_QUALIFIED_THRESHOLD, QualificationResult.email != None).scalar() or 0

    pending_jobs = db.query(func.count(QualificationJob.id)).filter(QualificationJob.status == "PENDING").scalar() or 0
    processing_jobs = db.query(func.count(QualificationJob.id)).filter(QualificationJob.status == "PROCESSING").scalar() or 0
    completed_jobs = db.query(func.count(QualificationJob.id)).filter(QualificationJob.status == "COMPLETED").scalar() or 0
    retry_jobs = db.query(func.count(QualificationJob.id)).filter(QualificationJob.status == "RETRY").scalar() or 0
    failed_jobs = db.query(func.count(QualificationJob.id)).filter(QualificationJob.status == "FAILED").scalar() or 0

    return QualificationStatsResponse(
        total_channels=total_channels,
        total_not_analyzed=max(0, total_channels - total_analyzed),
        total_qualified=total_qualified,
        total_review=total_review,
        total_rejected=total_rejected,
        total_failed=total_failed,
        total_outreach_ready=total_outreach,
        pending_jobs=pending_jobs,
        processing_jobs=processing_jobs,
        completed_jobs=completed_jobs,
        retry_jobs=retry_jobs,
        failed_jobs=failed_jobs,
        estimated_quota_used_today=YouTubeService.get_quota_used_today(),
        daily_quota_limit=qualification_config.DAILY_QUOTA_LIMIT
    )

@router.post("/backfill")
def backfill_channels(db: Session = Depends(get_db)):
    count = QualificationService.backfill_unqualified_channels(db)
    return {"message": f"{count} canais enfileirados para qualificação.", "enqueued_count": count}

@router.get("/config")
def get_qualification_config():
    return qualification_config.model_dump()

@router.put("/config")
def update_qualification_config(body: ConfigUpdateRequest):
    if body.daily_quota_limit is not None:
        qualification_config.DAILY_QUOTA_LIMIT = body.daily_quota_limit
    if body.videos_to_analyze is not None:
        qualification_config.VIDEOS_TO_ANALYZE = body.videos_to_analyze
    if body.requalification_interval_days is not None:
        qualification_config.REQUALIFICATION_INTERVAL_DAYS = body.requalification_interval_days
    if body.score_qualified_threshold is not None:
        qualification_config.SCORE_QUALIFIED_THRESHOLD = body.score_qualified_threshold
    if body.score_review_threshold is not None:
        qualification_config.SCORE_REVIEW_THRESHOLD = body.score_review_threshold
    if body.active_days_threshold is not None:
        qualification_config.ACTIVE_DAYS_THRESHOLD = body.active_days_threshold
    if body.inactive_days_threshold is not None:
        qualification_config.LOW_ACTIVITY_DAYS_THRESHOLD = body.inactive_days_threshold

    return {"message": "Configurações atualizadas com sucesso", "config": qualification_config.model_dump()}

@router.get("/{channel_id}/email-data", response_model=EmailTemplateDataResponse)
def get_channel_email_template_data(
    channel_id: str,
    db: Session = Depends(get_db)
):
    data = QualificationService.get_email_template_data(db, channel_id)
    if not data:
        raise HTTPException(status_code=404, detail="Dados do canal não encontrados.")
    return data

@router.get("/{channel_id}", response_model=QualificationResultResponse)
def get_channel_qualification(
    channel_id: str,
    db: Session = Depends(get_db)
):
    result = (
        db.query(QualificationResult)
        .options(joinedload(QualificationResult.analyzed_videos))
        .filter(QualificationResult.channel_id == channel_id)
        .first()
    )
    if not result:
        raise HTTPException(status_code=404, detail="Qualificação não encontrada para este canal.")
    return result
