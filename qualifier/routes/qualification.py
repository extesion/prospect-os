from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func

from backend.database.connection import get_db
from backend.database.models import Channel, User
from backend.security.auth import get_current_user
from qualifier.models.qualification_result import QualificationResult
from qualifier.models.qualification_job import QualificationJob
from qualifier.schemas.qualification_schema import (
    QualificationResultResponse,
    QualificationJobResponse,
    QualificationStatsResponse,
    EmailTemplateDataResponse,
    ConfigUpdateRequest
)
from qualifier.config.qualification_config import qualification_config
from qualifier.services.qualification_service import QualificationService
from qualifier.services.youtube_service import YouTubeService
from qualifier.worker import QualificationWorker

router = APIRouter(prefix="/qualification", tags=["Qualification"])

@router.get("/queue", response_model=List[QualificationJobResponse])
def get_qualification_queue(
    status_filter: Optional[str] = Query(None, description="Filter by status (PENDING, PROCESSING, RETRY, FAILED, COMPLETED)"),
    limit: int = Query(50, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Retorna a fila de jobs de qualificação."""
    query = db.query(QualificationJob)
    if status_filter:
        query = query.filter(QualificationJob.status == status_filter.upper())
    jobs = query.order_by(QualificationJob.created_at.desc()).limit(limit).all()
    return jobs

@router.post("/run")
def run_qualification_batch(
    batch_size: int = Query(50, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Executa o processamento de um lote de jobs pendentes da fila."""
    worker = QualificationWorker()
    result = worker.process_batch(db, limit=batch_size)
    return result

@router.post("/{channel_id}/run")
def qualify_channel_now(
    channel_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Qualifica imediatamente um canal específico."""
    # Ensure job exists
    job = QualificationService.enqueue_channel(db, channel_id, priority=10)
    
    worker = QualificationWorker()
    worker.process_batch(db, limit=1)

    result = (
        db.query(QualificationResult)
        .options(joinedload(QualificationResult.analyzed_videos))
        .filter(QualificationResult.channel_id == channel_id)
        .first()
    )
    if not result:
        # Check job error
        db.refresh(job)
        if job.status == "FAILED":
            raise HTTPException(status_code=400, detail=f"Falha na qualificação: {job.error_message}")
        return {"message": "Job enfileirado para processamento", "job_status": job.status}

    return result

@router.post("/{channel_id}/retry")
def retry_qualification_job(
    channel_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Reinicia um job com erro para que possa ser reprocessado."""
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
def get_qualification_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Retorna métricas consolidadas de qualificação e uso de quota."""
    total_qualified = db.query(func.count(QualificationResult.id)).filter(QualificationResult.qualification_status == "QUALIFIED").scalar() or 0
    total_review = db.query(func.count(QualificationResult.id)).filter(QualificationResult.qualification_status == "REVIEW").scalar() or 0
    total_rejected = db.query(func.count(QualificationResult.id)).filter(QualificationResult.qualification_status == "REJECTED").scalar() or 0
    total_failed = db.query(func.count(QualificationResult.id)).filter(QualificationResult.qualification_status == "FAILED").scalar() or 0

    pending_jobs = db.query(func.count(QualificationJob.id)).filter(QualificationJob.status == "PENDING").scalar() or 0
    processing_jobs = db.query(func.count(QualificationJob.id)).filter(QualificationJob.status == "PROCESSING").scalar() or 0
    completed_jobs = db.query(func.count(QualificationJob.id)).filter(QualificationJob.status == "COMPLETED").scalar() or 0
    retry_jobs = db.query(func.count(QualificationJob.id)).filter(QualificationJob.status == "RETRY").scalar() or 0
    failed_jobs = db.query(func.count(QualificationJob.id)).filter(QualificationJob.status == "FAILED").scalar() or 0

    return QualificationStatsResponse(
        total_qualified=total_qualified,
        total_review=total_review,
        total_rejected=total_rejected,
        total_failed=total_failed,
        pending_jobs=pending_jobs,
        processing_jobs=processing_jobs,
        completed_jobs=completed_jobs,
        retry_jobs=retry_jobs,
        failed_jobs=failed_jobs,
        estimated_quota_used_today=YouTubeService.get_quota_used_today(),
        daily_quota_limit=qualification_config.DAILY_QUOTA_LIMIT
    )

@router.post("/backfill")
def backfill_channels(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Enfileira todos os canais do banco de dados que ainda não possuem qualificação."""
    count = QualificationService.backfill_unqualified_channels(db)
    return {"message": f"{count} canais enfileirados para qualificação.", "enqueued_count": count}

@router.get("/config")
def get_qualification_config(
    current_user: User = Depends(get_current_user)
):
    """Retorna as configurações atuais de qualificação e scoring."""
    return qualification_config.model_dump()

@router.put("/config")
def update_qualification_config(
    body: ConfigUpdateRequest,
    current_user: User = Depends(get_current_user)
):
    """Atualiza configurações de scoring, limites e thresholds."""
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
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Retorna as variáveis preparadas para substituição no template de e-mail."""
    data = QualificationService.get_email_template_data(db, channel_id)
    if not data:
        raise HTTPException(status_code=404, detail="Dados do canal não encontrados.")
    return data

@router.get("/{channel_id}", response_model=QualificationResultResponse)
def get_channel_qualification(
    channel_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Retorna o resultado detalhado de qualificação de um canal."""
    result = (
        db.query(QualificationResult)
        .options(joinedload(QualificationResult.analyzed_videos))
        .filter(QualificationResult.channel_id == channel_id)
        .first()
    )
    if not result:
        raise HTTPException(status_code=404, detail="Qualificação não encontrada para este canal.")
    return result
