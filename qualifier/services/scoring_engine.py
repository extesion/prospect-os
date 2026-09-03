from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from qualifier.config.qualification_config import qualification_config

class ScoringEngine:

    @staticmethod
    def calculate_score(
        email: Optional[str],
        website: Optional[str],
        whatsapp: Optional[str],
        instagram: Optional[str],
        days_since_last_video: Optional[int],
        estimated_posting_frequency_days: Optional[float],
        commercial_signals: List[Dict[str, str]],
        keywords_found: List[Dict[str, Any]],
        link_aggregators: List[Dict[str, Any]],
        sales_platforms: List[Dict[str, Any]],
        has_any_external_links: bool,
        config=None,
        subscribers: int = 0
    ) -> Dict[str, Any]:
        """
        Calculates normalized qualification score (0-100), breakdown, classification, and reason.
        """
        cfg = config or qualification_config
        breakdown: Dict[str, int] = {}
        reason_points: List[str] = []
        reason_penalties: List[str] = []

        total_score = 0

        # --- POSITIVE POINTS ---

        # 1. Public Email (+20)
        if email:
            points = cfg.SCORE_POINTS_EMAIL
            breakdown["email"] = points
            total_score += points
            reason_points.append("possui e-mail comercial")

        # 2. Own Website (+15)
        if website:
            points = cfg.SCORE_POINTS_WEBSITE
            breakdown["website"] = points
            total_score += points
            reason_points.append("site próprio ativo")

        # 3. WhatsApp (+10)
        if whatsapp:
            points = cfg.SCORE_POINTS_WHATSAPP
            breakdown["whatsapp"] = points
            total_score += points
            reason_points.append("contato WhatsApp direto")

        # 4. Instagram (+5)
        if instagram:
            points = cfg.SCORE_POINTS_INSTAGRAM
            breakdown["instagram"] = points
            total_score += points
            reason_points.append("presença no Instagram")

        # 5. Recent Activity (<= 30 days) (+15)
        if days_since_last_video is not None and days_since_last_video <= cfg.ACTIVE_DAYS_THRESHOLD:
            points = cfg.SCORE_POINTS_ACTIVE_RECENT
            breakdown["recent_activity"] = points
            total_score += points
            reason_points.append(f"canal ativo com vídeo recente há {days_since_last_video} dias")

        # 6. Sales / Product / Service Signals (+15)
        sales_signal_types = {
            "course_sale", "consulting_service", "mentorship_service",
            "agency_service", "store_merch", "product_sale", "sales_platform"
        }
        has_sales_signal = any(
            sig.get("type") in sales_signal_types or sig.get("type", "").startswith("sales_platform")
            for sig in commercial_signals
        ) or bool(sales_platforms)

        if has_sales_signal:
            points = cfg.SCORE_POINTS_SALES_SIGNAL
            breakdown["sales_signals"] = points
            total_score += points
            reason_points.append("sinais claros de venda de produtos ou serviços")

        # 7. Commercial Keywords (+10)
        if keywords_found:
            points = cfg.SCORE_POINTS_COMMERCIAL_KEYWORDS
            breakdown["commercial_keywords"] = points
            total_score += points
            reason_points.append(f"{len(keywords_found)} palavras-chave comerciais detectadas")

        # 8. Link Aggregator (+5)
        if link_aggregators:
            points = cfg.SCORE_POINTS_LINK_AGGREGATOR
            breakdown["link_aggregator"] = points
            total_score += points
            reason_points.append("agregador de links (bio)")

        # 9. Consistent Posting Frequency (+5)
        if estimated_posting_frequency_days is not None and 0 < estimated_posting_frequency_days <= 10:
            points = cfg.SCORE_POINTS_CONSISTENT_POSTING
            breakdown["consistent_posting"] = points
            total_score += points
            reason_points.append(f"frequência de postagem consistente (~1 vídeo a cada {estimated_posting_frequency_days:.0f} dias)")

        # --- PENALTIES ---

        # Inactivity Penalty (> 180 days: -25, > 90 days: -15)
        if days_since_last_video is not None:
            if days_since_last_video > 180:
                penalty = cfg.PENALTY_INACTIVE_180_DAYS
                breakdown["inactivity_penalty"] = penalty
                total_score += penalty
                reason_penalties.append(f"inativo há mais de 180 dias ({days_since_last_video} dias sem publicar)")
            elif days_since_last_video > cfg.LOW_ACTIVITY_DAYS_THRESHOLD:
                penalty = cfg.PENALTY_INACTIVE_90_DAYS
                breakdown["inactivity_penalty"] = penalty
                total_score += penalty
                reason_penalties.append(f"baixa atividade ({days_since_last_video} dias sem publicar)")
        else:
            # Channel without videos
            penalty = cfg.PENALTY_INACTIVE_90_DAYS
            breakdown["no_videos_penalty"] = penalty
            total_score += penalty
            reason_penalties.append("nenhum vídeo público encontrado")

        # No external links (-10)
        if not has_any_external_links:
            penalty = cfg.PENALTY_NO_EXTERNAL_LINKS
            breakdown["no_links_penalty"] = penalty
            total_score += penalty
            reason_penalties.append("nenhum link externo identificado")

        # No contact info at all (-10)
        if not email and not whatsapp:
            penalty = cfg.PENALTY_NO_CONTACT
            breakdown["no_contact_penalty"] = penalty
            total_score += penalty
            reason_penalties.append("sem dados de contato direto (e-mail ou WhatsApp)")

        # No commercial signals (-15)
        if not commercial_signals and not keywords_found and not sales_platforms:
            penalty = cfg.PENALTY_NO_COMMERCIAL_SIGNALS
            breakdown["no_commercial_signals_penalty"] = penalty
            total_score += penalty
            reason_penalties.append("ausência de sinais ou termos comerciais")

        # Admin criteria and weighted score. Defaults retain current behavior.
        enabled = getattr(cfg, "enabled_criteria", {})
        keyword_text = " ".join(str(k.get("keyword", "")).lower() for k in keywords_found)
        _subscribers = subscribers
        hard_fail = (
            (enabled.get("min_subscribers", True) and getattr(cfg, "min_subscribers", 0) and _subscribers < cfg.min_subscribers) or
            (enabled.get("max_subscribers", True) and getattr(cfg, "max_subscribers", None) is not None and _subscribers > cfg.max_subscribers) or
            (enabled.get("max_activity_days", True) and days_since_last_video is not None and days_since_last_video > getattr(cfg, "max_activity_days", 999999)) or
            (enabled.get("require_public_contact", True) and getattr(cfg, "require_public_contact", False) and not (email or whatsapp)) or
            (enabled.get("require_email", True) and getattr(cfg, "require_email", False) and not email) or
            (enabled.get("require_commercial_links", True) and getattr(cfg, "require_commercial_links", False) and not (sales_platforms or commercial_signals)) or
            (enabled.get("negative_keywords", True) and any(k.lower() in keyword_text for k in getattr(cfg, "negative_keywords", [])))
        )
        total_score *= getattr(cfg, "weight_contact", 1.0) if (email or whatsapp) else 1.0
        total_score *= getattr(cfg, "weight_activity", 1.0) if days_since_last_video is not None else 1.0
        total_score *= getattr(cfg, "weight_commercial", 1.0) if (commercial_signals or keywords_found) else 1.0
        if enabled.get("positive_keywords", True) and any(k.lower() in keyword_text for k in getattr(cfg, "positive_keywords", [])):
            total_score *= getattr(cfg, "weight_audience", 1.0)
        final_score = max(0, min(100, round(total_score)))

        # Classification
        if hard_fail:
            status = "REJECTED"
        elif final_score >= getattr(cfg, "qualified_threshold", cfg.SCORE_QUALIFIED_THRESHOLD):
            status = "QUALIFIED"
        elif final_score >= getattr(cfg, "review_threshold", cfg.SCORE_REVIEW_THRESHOLD):
            status = "REVIEW"
        else:
            status = "REJECTED"

        # Generate qualification_reason text
        reason_parts = []
        if reason_points:
            reason_parts.append("Destaques: " + ", ".join(reason_points) + ".")
        if reason_penalties:
            reason_parts.append("Penalidades: " + ", ".join(reason_penalties) + ".")

        if status == "QUALIFIED":
            summary = "Canal qualificado com alto potencial comercial."
        elif status == "REVIEW":
            summary = "Canal em análise intermediária; possui alguns sinais relevantes."
        else:
            summary = "Canal com baixa relevância comercial ou inativo."

        full_reason = f"{summary} {' '.join(reason_parts)}".strip()

        return {
            "score": final_score,
            "status": status,
            "score_breakdown": breakdown,
            "qualification_reason": full_reason
        }

    compute_score = calculate_score

