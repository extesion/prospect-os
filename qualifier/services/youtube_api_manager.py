from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timezone
import os
import logging
from sqlalchemy.orm import Session
from sqlalchemy import func

from backend.database.models import YouTubeApiConfig, YouTubeApiUsage, utc_now
from qualifier.config.qualification_config import qualification_config

logger = logging.getLogger(__name__)

class YouTubeQuotaExceededException(Exception):
    pass

class YouTubeApiManager:
    """
    Centralized manager for multi-project/credential YouTube Data API v3 configurations.
    Tracks estimated quota consumption, selects available active configurations,
    and logs request costs without exposing API keys to clients.
    """

    @staticmethod
    def mask_api_key(api_key: str) -> str:
        """Returns masked API key for safe UI display (e.g. AIza************92X)."""
        if not api_key:
            return "—"
        if len(api_key) <= 8:
            return "********"
        return f"{api_key[:4]}************{api_key[-3:]}"

    @classmethod
    def ensure_default_config(cls, db: Session) -> Optional[YouTubeApiConfig]:
        """Ensures at least one default active configuration exists in DB if env key is present."""
        count = db.query(func.count(YouTubeApiConfig.id)).scalar() or 0
        if count == 0:
            key = qualification_config.YOUTUBE_API_KEY or os.getenv("YOUTUBE_API_KEY", "")
            if key:
                default_cfg = YouTubeApiConfig(
                    name="Projeto Principal (Padrão)",
                    api_key=key,
                    status="ACTIVE",
                    daily_limit=qualification_config.DAILY_QUOTA_LIMIT or 10000,
                    created_at=utc_now(),
                    updated_at=utc_now()
                )
                db.add(default_cfg)
                db.commit()
                db.refresh(default_cfg)
                return default_cfg
        return None

    @classmethod
    def get_today_usage_for_config(cls, db: Session, config_id: int) -> int:
        """Computes estimated units consumed today (UTC cycle)."""
        today_midnight = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        total = (
            db.query(func.sum(YouTubeApiUsage.units))
            .filter(
                YouTubeApiUsage.api_config_id == config_id,
                YouTubeApiUsage.requested_at >= today_midnight
            )
            .scalar()
        ) or 0
        return int(total)

    @classmethod
    def get_today_usage_total(cls, db: Session) -> int:
        """Total estimated units consumed today across all configurations."""
        today_midnight = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        total = (
            db.query(func.sum(YouTubeApiUsage.units))
            .filter(YouTubeApiUsage.requested_at >= today_midnight)
            .scalar()
        ) or 0
        return int(total)

    @classmethod
    def get_active_config(cls, db: Session) -> Tuple[Any, str]:
        """
        Selects an available active API configuration that has remaining daily quota.
        Returns a tuple: (YouTubeApiConfig, api_key_str).
        """
        cls.ensure_default_config(db)
        
        active_configs = (
            db.query(YouTubeApiConfig)
            .filter(YouTubeApiConfig.status == "ACTIVE")
            .order_by(YouTubeApiConfig.id.asc())
            .all()
        )

        if not active_configs:
            # Fallback to .env directly if no DB config is active
            env_key = qualification_config.YOUTUBE_API_KEY or os.getenv("YOUTUBE_API_KEY", "")
            if env_key:
                dummy = YouTubeApiConfig(id=0, name="Ambiente .env", api_key=env_key, daily_limit=10000, status="ACTIVE")
                return dummy, env_key
            raise ValueError("Nenhuma chave da YouTube API ativa configurada no sistema.")

        for cfg in active_configs:
            usage_today = cls.get_today_usage_for_config(db, cfg.id)
            if usage_today < cfg.daily_limit:
                return cfg, cfg.api_key
            else:
                # Mark as QUOTA_EXCEEDED for UI clarity
                cfg.status = "QUOTA_EXCEEDED"
                cfg.updated_at = utc_now()
                db.commit()

        # If all active configs exceeded quota, raise quota exception
        raise YouTubeQuotaExceededException("Limite diário de quota atingido em todas as configurações ativas da YouTube API.")

    @classmethod
    def select_active_config(
        cls,
        db: Session,
        prefer_config_id: Optional[int] = None,
        exclude_ids: Optional[List[int]] = None,
    ) -> Tuple[Any, str]:
        """
        Selects next usable active configuration.

        - Honors preferred config id if eligible.
        - Skips ids in exclude_ids (used during fallback to avoid retrying the same key).
        - Marks configs that hit daily limit as QUOTA_EXCEEDED.
        - Falls back to .env key if no DB row is active.
        """
        exclude_ids = exclude_ids or []
        cls.ensure_default_config(db)

        query = (
            db.query(YouTubeApiConfig)
            .filter(YouTubeApiConfig.status == "ACTIVE")
            .order_by(YouTubeApiConfig.id.asc())
        )
        candidates = [c for c in query.all() if c.id not in exclude_ids]

        # Prefer specific id if eligible
        if prefer_config_id is not None:
            for cfg in candidates:
                if cfg.id == prefer_config_id:
                    usage_today = cls.get_today_usage_for_config(db, cfg.id)
                    if usage_today < cfg.daily_limit:
                        return cfg, cfg.api_key
                    break

        for cfg in candidates:
            usage_today = cls.get_today_usage_for_config(db, cfg.id)
            if usage_today < cfg.daily_limit:
                return cfg, cfg.api_key
            cfg.status = "QUOTA_EXCEEDED"
            cfg.updated_at = utc_now()
            db.commit()

        # Fallback to .env directly if no DB config is active
        env_key = qualification_config.YOUTUBE_API_KEY or os.getenv("YOUTUBE_API_KEY", "")
        if env_key:
            dummy = YouTubeApiConfig(
                id=0,
                name="Ambiente .env",
                api_key=env_key,
                daily_limit=10000,
                status="ACTIVE",
            )
            return dummy, env_key
        raise ValueError("Nenhuma chave da YouTube API ativa configurada no sistema.")

    @classmethod
    def record_usage(
        cls,
        db: Session,
        config_id: Optional[int],
        endpoint: str,
        units: int,
        success: bool = True,
        error_message: Optional[str] = None
    ):
        """Records API call usage and updates config timestamp."""
        now = utc_now()
        try:
            usage = YouTubeApiUsage(
                api_config_id=config_id if config_id and config_id > 0 else None,
                endpoint=endpoint,
                units=units,
                requested_at=now,
                success=success,
                error_message=error_message
            )
            db.add(usage)

            if config_id and config_id > 0:
                cfg = db.query(YouTubeApiConfig).filter(YouTubeApiConfig.id == config_id).first()
                if cfg:
                    cfg.last_used_at = now
                    if not success and error_message and ("quotaExceeded" in error_message or "403" in error_message):
                        cfg.status = "QUOTA_EXCEEDED"
                        cfg.error_message = error_message
                    elif not success:
                        cfg.error_message = error_message

            db.commit()
        except Exception as e:
            logger.error(f"[YOUTUBE_USAGE] Failed to record usage: {str(e)}")
            db.rollback()

    @classmethod
    def get_dashboard_summary(cls, db: Session) -> Dict[str, Any]:
        """Consolidates metrics, status bars, and configs for Admin dashboard."""
        cls.ensure_default_config(db)
        
        configs = db.query(YouTubeApiConfig).order_by(YouTubeApiConfig.id.asc()).all()
        today_midnight = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

        total_usage_all = 0
        total_limit_all = 0
        active_count = 0
        unavailable_count = 0

        config_items = []
        for cfg in configs:
            usage = cls.get_today_usage_for_config(db, cfg.id)
            total_usage_all += usage
            if cfg.status == "ACTIVE":
                total_limit_all += cfg.daily_limit
                active_count += 1
            else:
                unavailable_count += 1

            pct = round((usage / max(1, cfg.daily_limit)) * 100, 1)
            
            # Status label and category
            status_text = "NORMAL"
            status_color = "emerald"
            if pct >= 100:
                status_text = "LIMITE ATINGIDO"
                status_color = "rose"
            elif pct >= 90:
                status_text = "CRÍTICO"
                status_color = "orange"
            elif pct >= 70:
                status_text = "ATENÇÃO"
                status_color = "amber"

            config_items.append({
                "id": cfg.id,
                "name": cfg.name,
                "masked_key": cls.mask_api_key(cfg.api_key),
                "status": cfg.status,
                "daily_limit": cfg.daily_limit,
                "usage_today": usage,
                "available_today": max(0, cfg.daily_limit - usage),
                "percentage": pct,
                "status_text": status_text,
                "status_color": status_color,
                "last_used_at": cfg.last_used_at.strftime("%d/%m/%Y %H:%M") if cfg.last_used_at else None,
                "error_message": cfg.error_message,
                "created_at": cfg.created_at.strftime("%d/%m/%Y") if cfg.created_at else None
            })

        return {
            "summary": {
                "total_usage_today": total_usage_all,
                "total_limit_active": total_limit_all,
                "total_available_active": max(0, total_limit_all - total_usage_all),
                "active_apis": active_count,
                "unavailable_apis": unavailable_count,
                "reset_cycle": "Meia-noite UTC (00:00 UTC)"
            },
            "apis": config_items
        }

Tuple_Config_Key = Any
