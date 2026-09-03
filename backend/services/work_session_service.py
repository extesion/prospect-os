from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Tuple
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func, and_, or_
import json
import logging

from backend.database.models import User, UserProfile, UserMusicConnection, WorkSession, WorkSessionEvent, CycleSetting, Channel, utc_now
from backend.schemas.work_session import (
    WorkSessionStart, WorkSessionResponse, UserRankingItem,
    TeamStatusItem, TeamSummaryResponse, CyclePresetItem,
    CycleSettingsResponse, CycleSettingsUpdate, SessionHistoryItem
)

logger = logging.getLogger(__name__)

def ensure_utc(dt: Optional[datetime]) -> Optional[datetime]:
    """Garante que o datetime possua timezone UTC (evita conflito naive vs aware no SQLite)"""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)

def format_seconds_hms(seconds: int) -> str:
    """Formata segundos em HH:MM:SS"""
    if seconds < 0:
        seconds = 0
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    return f"{h:02d}:{m:02d}:{s:02d}"

def format_seconds_hours_mins(seconds: int) -> str:
    """Formata segundos em '07h 42min' para ranking e relatórios"""
    if seconds < 0:
        seconds = 0
    h = seconds // 3600
    m = (seconds % 3600) // 60
    return f"{h:02d}h {m:02d}min"

class WorkSessionService:

    @staticmethod
    def compute_session_response(session: WorkSession, user_name: str = "") -> WorkSessionResponse:
        """
        Calcula dinamicamente os valores de tempo real, ritmo e projeções da sessão.
        """
        now = utc_now()
        last_resumed = ensure_utc(session.last_resumed_at) or now
        
        # Calcula active_seconds real
        current_active = session.active_seconds
        if session.status == "ACTIVE":
            elapsed_since_resume = int((now - last_resumed).total_seconds())
            if elapsed_since_resume > 0:
                current_active += elapsed_since_resume

        active_hours = current_active / 3600.0

        # Ritmo atual (canais/h)
        current_rate = round(session.collected_count / active_hours, 1) if active_hours > 0.001 else 0.0

        # Meta por hora configurada
        target_per_hour = session.daily_target / session.target_hours if session.target_hours > 0 else 0.0
        target_per_hour_display = round(target_per_hour, 1)

        # Faltam para a meta
        remaining = max(0, session.daily_target - session.collected_count)

        # Horas restantes do ciclo planejado
        remaining_active_hours = max(0.0, session.target_hours - active_hours)

        # Novo ritmo necessário para bater a meta dentro do ciclo
        if remaining == 0:
            required_rate = 0.0
        elif remaining_active_hours > 0.01:
            required_rate = round(remaining / remaining_active_hours, 1)
        else:
            required_rate = round(float(remaining), 1)

        # Progresso percentual
        progress_pct = round((session.collected_count / session.daily_target) * 100.0, 1) if session.daily_target > 0 else 0.0

        # Projeção de conclusão
        proj_hours = None
        proj_display = None
        if remaining == 0:
            proj_display = "Meta Concluída"
        elif current_rate > 0:
            proj_hours = round(remaining / current_rate, 2)
            total_proj_mins = int(proj_hours * 60)
            ph = total_proj_mins // 60
            pm = total_proj_mins % 60
            proj_display = f"aprox. {ph}h{pm:02d}min" if ph > 0 else f"aprox. {pm}min"

        # Indicador de status de ritmo
        if current_rate >= target_per_hour * 1.05 and current_rate > 0:
            status_indicator = "ABOVE_TARGET"
        elif current_rate >= target_per_hour * 0.95 and current_rate > 0:
            status_indicator = "IN_TARGET"
        else:
            status_indicator = "BELOW_TARGET"

        is_target_completed = session.collected_count >= session.daily_target
        is_cycle_time_exceeded = active_hours > session.target_hours

        name = user_name or (session.user.name if session.user else "Usuário")

        return WorkSessionResponse(
            id=session.id,
            user_id=session.user_id,
            user_name=name,
            started_at=session.started_at,
            ended_at=session.ended_at,
            paused_at=session.paused_at,
            last_resumed_at=session.last_resumed_at,
            active_seconds=session.active_seconds,
            current_active_seconds=current_active,
            formatted_active_time=format_seconds_hms(current_active),
            status=session.status,
            cycle_type=session.cycle_type,
            daily_target=session.daily_target,
            target_hours=session.target_hours,
            target_per_hour=target_per_hour,
            target_per_hour_display=target_per_hour_display,
            collected_count=session.collected_count,
            current_rate=current_rate,
            remaining=remaining,
            remaining_active_hours=round(remaining_active_hours, 2),
            required_rate=required_rate,
            progress_percentage=progress_pct,
            projected_finish_hours=proj_hours,
            projected_finish_display=proj_display,
            status_indicator=status_indicator,
            is_target_completed=is_target_completed,
            is_cycle_time_exceeded=is_cycle_time_exceeded
        )

    @staticmethod
    def start_session(db: Session, user: User, data: WorkSessionStart) -> WorkSessionResponse:
        """
        Inicia uma sessão de trabalho para o usuário.
        Garante que apenas 1 sessão ativa/pausada exista por usuário.
        """
        now = utc_now()

        # Verifica se já existe uma sessão em andamento
        existing = (
            db.query(WorkSession)
            .filter(WorkSession.user_id == user.id)
            .filter(WorkSession.status.in_(["ACTIVE", "PAUSED"]))
            .first()
        )

        if existing:
            # Se já existir e estiver PAUSED, retoma automaticamente
            if existing.status == "PAUSED":
                existing.status = "ACTIVE"
                existing.paused_at = None
                existing.last_resumed_at = now
                event = WorkSessionEvent(
                    session_id=existing.id,
                    user_id=user.id,
                    event_type="RESUME",
                    created_at=now
                )
                db.add(event)
                db.commit()
                db.refresh(existing)
            return WorkSessionService.compute_session_response(existing, user.name)

        # Calcula target_per_hour matematicamente exato
        target_per_hour = data.daily_target / data.target_hours if data.target_hours > 0 else 20.0

        new_session = WorkSession(
            user_id=user.id,
            started_at=now,
            last_resumed_at=now,
            active_seconds=0,
            status="ACTIVE",
            cycle_type=data.cycle_type,
            daily_target=data.daily_target,
            target_hours=data.target_hours,
            target_per_hour=target_per_hour,
            collected_count=0,
            created_at=now,
            updated_at=now
        )
        db.add(new_session)
        db.flush()

        event = WorkSessionEvent(
            session_id=new_session.id,
            user_id=user.id,
            event_type="START",
            created_at=now
        )
        db.add(event)

        # Disparar notificação interna de início de turno
        try:
            from backend.services.notification_service import NotificationService
            start_time_str = now.strftime("%H:%M")
            NotificationService.create_notification(
                db=db,
                notification_type="USER_START_SESSION",
                actor_user_id=user.id,
                title="Turno Iniciado",
                message=f"{user.name} iniciou um turno de trabalho às {start_time_str}.",
                metadata={"session_id": new_session.id, "cycle_type": new_session.cycle_type, "target": new_session.daily_target}
            )
        except Exception as e:
            logger.warning(f"Erro ao disparar notificação de início de turno: {e}")

        db.commit()
        db.refresh(new_session)

        return WorkSessionService.compute_session_response(new_session, user.name)

    @staticmethod
    def pause_session(db: Session, user: User) -> WorkSessionResponse:
        """
        Pausa a contagem de tempo da sessão ativa.
        """
        now = utc_now()
        session = (
            db.query(WorkSession)
            .filter(WorkSession.user_id == user.id)
            .filter(WorkSession.status == "ACTIVE")
            .first()
        )

        if not session:
            # Se já estiver pausada, retorna a pausada
            paused = (
                db.query(WorkSession)
                .filter(WorkSession.user_id == user.id)
                .filter(WorkSession.status == "PAUSED")
                .first()
            )
            if paused:
                return WorkSessionService.compute_session_response(paused, user.name)
            raise ValueError("Nenhuma sessão ativa encontrada para pausar.")

        # Acumula o tempo ativo decorrido
        last_resumed = ensure_utc(session.last_resumed_at) or now
        elapsed = int((now - last_resumed).total_seconds())
        if elapsed > 0:
            session.active_seconds += elapsed

        session.status = "PAUSED"
        session.paused_at = now
        session.updated_at = now

        event = WorkSessionEvent(
            session_id=session.id,
            user_id=user.id,
            event_type="PAUSE",
            created_at=now
        )
        db.add(event)
        db.commit()
        db.refresh(session)

        return WorkSessionService.compute_session_response(session, user.name)

    @staticmethod
    def resume_session(db: Session, user: User) -> WorkSessionResponse:
        """
        Retoma a sessão pausada.
        """
        now = utc_now()
        session = (
            db.query(WorkSession)
            .filter(WorkSession.user_id == user.id)
            .filter(WorkSession.status == "PAUSED")
            .first()
        )

        if not session:
            # Se já estiver ativa, retorna a ativa
            active = (
                db.query(WorkSession)
                .filter(WorkSession.user_id == user.id)
                .filter(WorkSession.status == "ACTIVE")
                .first()
            )
            if active:
                return WorkSessionService.compute_session_response(active, user.name)
            raise ValueError("Nenhuma sessão pausada encontrada para retomar.")

        session.status = "ACTIVE"
        session.paused_at = None
        session.last_resumed_at = now
        session.updated_at = now

        event = WorkSessionEvent(
            session_id=session.id,
            user_id=user.id,
            event_type="RESUME",
            created_at=now
        )
        db.add(event)
        db.commit()
        db.refresh(session)

        return WorkSessionService.compute_session_response(session, user.name)

    @staticmethod
    def finish_session(db: Session, user: User) -> WorkSessionResponse:
        """
        Finaliza a sessão de trabalho e consolida as horas trabalhadas.
        """
        now = utc_now()
        session = (
            db.query(WorkSession)
            .filter(WorkSession.user_id == user.id)
            .filter(WorkSession.status.in_(["ACTIVE", "PAUSED"]))
            .first()
        )

        if not session:
            raise ValueError("Nenhuma sessão em andamento encontrada para finalizar.")

        if session.status == "ACTIVE":
            last_resumed = ensure_utc(session.last_resumed_at) or now
            elapsed = int((now - last_resumed).total_seconds())
            if elapsed > 0:
                session.active_seconds += elapsed

        session.status = "FINISHED"
        session.ended_at = now
        session.updated_at = now

        event = WorkSessionEvent(
            session_id=session.id,
            user_id=user.id,
            event_type="FINISH",
            created_at=now
        )
        db.add(event)

        # Disparar notificação de ciclo finalizado
        try:
            from backend.services.notification_service import NotificationService
            active_hours = session.active_seconds / 3600.0
            avg_rate = round(session.collected_count / active_hours, 1) if active_hours > 0.01 else 0.0
            time_str = format_seconds_hours_mins(session.active_seconds)
            NotificationService.create_notification(
                db=db,
                notification_type="USER_COMPLETE_CYCLE",
                actor_user_id=user.id,
                title="Ciclo Finalizado",
                message=f"🏁 {user.name} finalizou seu ciclo: {session.collected_count} canais em {time_str} ({avg_rate} canais/h).",
                metadata={
                    "session_id": session.id,
                    "collected_count": session.collected_count,
                    "active_seconds": session.active_seconds,
                    "average_rate": avg_rate
                }
            )
        except Exception as e:
            logger.warning(f"Erro ao disparar notificação de fim de ciclo: {e}")

        db.commit()
        db.refresh(session)

        return WorkSessionService.compute_session_response(session, user.name)

    @staticmethod
    def get_current_session(db: Session, user: User) -> Optional[WorkSessionResponse]:
        """
        Recupera a sessão ativa ou pausada atual do usuário.
        """
        session = (
            db.query(WorkSession)
            .filter(WorkSession.user_id == user.id)
            .filter(WorkSession.status.in_(["ACTIVE", "PAUSED"]))
            .order_by(WorkSession.started_at.desc())
            .first()
        )
        if not session:
            return None
        return WorkSessionService.compute_session_response(session, user.name)

    @staticmethod
    def register_channel_collection(db: Session, user_id: int, channel_id: str) -> Optional[int]:
        """
        Incrementa a contagem da sessão ativa do usuário se houver uma em andamento.
        Dispara notificação quando o usuário atinge a meta diária configurada (1x por ciclo).
        Retorna o work_session_id associado.
        """
        session = (
            db.query(WorkSession)
            .filter(WorkSession.user_id == user_id)
            .filter(WorkSession.status == "ACTIVE")
            .first()
        )

        if session:
            prev_count = session.collected_count
            session.collected_count += 1
            session.updated_at = utc_now()
            db.flush()

            # Checar se bateu a meta agora
            if prev_count < session.daily_target and session.collected_count >= session.daily_target:
                try:
                    from backend.services.notification_service import NotificationService
                    user = db.query(User).filter(User.id == user_id).first()
                    u_name = user.name if user else "Operador"
                    NotificationService.create_notification(
                        db=db,
                        notification_type="USER_REACHED_GOAL",
                        actor_user_id=user_id,
                        title="Meta Atingida! 🎯",
                        message=f"🎯 {u_name} atingiu a meta de {session.daily_target} canais!",
                        metadata={
                            "session_id": session.id,
                            "daily_target": session.daily_target,
                            "collected_count": session.collected_count
                        }
                    )
                except Exception as e:
                    logger.warning(f"Erro ao disparar notificação de meta atingida: {e}")

            return session.id
        return None

    @staticmethod
    def get_ranking(db: Session, period: str = "today") -> List[UserRankingItem]:
        """
        Retorna o ranking de membros ordenado EXCLUSIVAMENTE por HORAS TRABALHADAS.
        Ignora usuários excluídos e sessões órfãs.
        """
        now = utc_now()
        if period == "today":
            start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
        elif period == "week":
            start_date = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
        elif period == "month":
            start_date = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        else:
            start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)

        # Usuários ativos e não excluídos
        all_users = db.query(User).filter(User.active == True, User.is_deleted == False).all()
        user_map = {u.id: u for u in all_users}
        valid_user_ids = set(user_map.keys())

        # Consulta todas as sessões dentro do período pertencentes a usuários válidos
        sessions = (
            db.query(WorkSession)
            .filter(WorkSession.started_at >= start_date)
            .filter(WorkSession.user_id.in_(valid_user_ids) if valid_user_ids else False)
            .all()
        )

        profiles = db.query(UserProfile).filter(UserProfile.user_id.in_(valid_user_ids) if valid_user_ids else False).all()
        profile_map = {p.user_id: p for p in profiles}

        user_totals: Dict[int, Dict] = {}
        for u in all_users:
            p = profile_map.get(u.id)
            user_totals[u.id] = {
                "user_id": u.id,
                "user_name": u.name,
                "avatar_url": p.avatar_url if p else None,
                "banner_url": p.banner_url if p else None,
                "total_active_seconds": 0,
                "channels_collected": 0
            }

        for s in sessions:
            uid = s.user_id
            if uid not in user_totals:
                continue

            # Calcula tempo ativo da sessão
            active = s.active_seconds
            if s.status == "ACTIVE":
                last_resumed = ensure_utc(s.last_resumed_at) or now
                elapsed = int((now - last_resumed).total_seconds())
                if elapsed > 0:
                    active += elapsed

            user_totals[uid]["total_active_seconds"] += active
            user_totals[uid]["channels_collected"] += s.collected_count

        # Ordena ESTRITAMENTE por total_active_seconds DESC
        sorted_users = sorted(
            user_totals.values(),
            key=lambda x: x["total_active_seconds"],
            reverse=True
        )

        ranking_list: List[UserRankingItem] = []
        for rank, item in enumerate(sorted_users, start=1):
            ranking_list.append(UserRankingItem(
                rank_position=rank,
                user_id=item["user_id"],
                user_name=item["user_name"],
                avatar_url=item["avatar_url"],
                banner_url=item["banner_url"],
                total_active_seconds=item["total_active_seconds"],
                formatted_hours=format_seconds_hours_mins(item["total_active_seconds"]),
                channels_collected=item["channels_collected"]
            ))

        return ranking_list

    @staticmethod
    def get_team_summary(db: Session) -> TeamSummaryResponse:
        """
        Retorna visão geral da equipe em tempo real (usuários trabalhando, horas totais hoje, média de canais/h).
        Garante que apenas membros ativos e não excluídos façam parte dos cards e métricas.
        """
        now = utc_now()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

        all_users = db.query(User).filter(User.active == True, User.is_deleted == False).all()
        valid_user_ids = {u.id for u in all_users}
        if not valid_user_ids:
            return TeamSummaryResponse(users_working_count=0, total_hours_today_seconds=0,
                formatted_total_hours_today="00h 00min", total_channels_today=0,
                team_average_rate=0.0, members=[])

        profiles = db.query(UserProfile).filter(UserProfile.user_id.in_(valid_user_ids)).all()
        profile_map = {p.user_id: p for p in profiles}
        music_conns = db.query(UserMusicConnection).filter(UserMusicConnection.user_id.in_(valid_user_ids)).all()
        music_map = {m.user_id: m for m in music_conns}
        all_sessions = db.query(WorkSession).filter(WorkSession.user_id.in_(valid_user_ids)).all()
        all_channels = db.query(Channel).filter(Channel.first_collected_by_id.in_(valid_user_ids)).all()

        current_session_map = {}
        sessions_by_user = {uid: [] for uid in valid_user_ids}
        channels_by_user = {uid: [] for uid in valid_user_ids}
        for s in all_sessions:
            sessions_by_user[s.user_id].append(s)
            if s.status in ["ACTIVE", "PAUSED"]:
                old = current_session_map.get(s.user_id)
                if not old or ensure_utc(s.started_at) > ensure_utc(old.started_at):
                    current_session_map[s.user_id] = s
        for channel in all_channels:
            channels_by_user[channel.first_collected_by_id].append(channel)

        week_start = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        chart_start = today_start - timedelta(days=6)
        total_hours_today_seconds = 0
        total_channels_today = sum(1 for c in all_channels if ensure_utc(c.first_collected_at) >= today_start)
        users_working_count = sum(1 for s in current_session_map.values() if s.status == "ACTIVE")
        members: List[TeamStatusItem] = []
        for u in all_users:
            sess, p, m_conn = current_session_map.get(u.id), profile_map.get(u.id), music_map.get(u.id)
            user_sessions, user_channels = sessions_by_user[u.id], channels_by_user[u.id]
            seconds = {"today": 0, "week": 0, "month": 0, "total": 0}
            daily_seconds, daily_channels = {}, {}
            completed_cycles = goals_reached = 0
            for item in user_sessions:
                started = ensure_utc(item.started_at)
                active = item.active_seconds
                if item.status == "ACTIVE":
                    active += max(0, int((now - (ensure_utc(item.last_resumed_at) or now)).total_seconds()))
                seconds["total"] += active
                if started >= today_start: seconds["today"] += active
                if started >= week_start: seconds["week"] += active
                if started >= month_start: seconds["month"] += active
                day = started.strftime("%Y-%m-%d")
                daily_seconds[day] = daily_seconds.get(day, 0) + active
                completed_cycles += item.status == "FINISHED"
                goals_reached += item.collected_count >= item.daily_target
            total_hours_today_seconds += seconds["today"]
            for channel in user_channels:
                collected = ensure_utc(channel.first_collected_at)
                day = collected.strftime("%Y-%m-%d")
                daily_channels[day] = daily_channels.get(day, 0) + 1
            channels_today = sum(1 for c in user_channels if ensure_utc(c.first_collected_at) >= today_start)
            channels_week = sum(1 for c in user_channels if ensure_utc(c.first_collected_at) >= week_start)
            channels_month = sum(1 for c in user_channels if ensure_utc(c.first_collected_at) >= month_start)
            active_days = len(set(daily_seconds) | set(daily_channels)) or 1
            total_hours = seconds["total"] / 3600
            chart = [{"date": (chart_start + timedelta(days=i)).strftime("%Y-%m-%d"),
                      "label": (chart_start + timedelta(days=i)).strftime("%d/%m"),
                      "channels": daily_channels.get((chart_start + timedelta(days=i)).strftime("%Y-%m-%d"), 0)}
                     for i in range(7)]

            last_seen = ensure_utc(u.last_seen_at)
            presence = "online" if last_seen and last_seen >= now - timedelta(seconds=90) else "offline"
            now_playing = None
            if m_conn and m_conn.is_connected and (p is None or p.show_music_to_team) and m_conn.current_track_name:
                now_playing = {"provider": m_conn.provider or "spotify", "track_name": m_conn.current_track_name or "--",
                               "artist": m_conn.current_artist or "--", "album_art": m_conn.current_album_art,
                               "is_playing": bool(m_conn.is_playing)}
            res = WorkSessionService.compute_session_response(sess, u.name) if sess else None
            members.append(TeamStatusItem(
                user_id=u.id, user_name=u.name or "Usuário", role=u.role or "USER",
                avatar_url=p.avatar_url if p else None, banner_url=p.banner_url if p else None,
                presence=presence, session_id=sess.id if sess else None,
                session_status=sess.status if sess else "IDLE",
                active_seconds=res.current_active_seconds if res else 0,
                formatted_time=res.formatted_active_time if res else "00:00:00",
                collected_count=sess.collected_count if sess else 0,
                daily_target=sess.daily_target if sess else 0,
                current_rate=res.current_rate if res else 0.0,
                required_rate=res.required_rate if res else 0.0,
                progress_percentage=res.progress_percentage if res else 0.0,
                projected_finish_display=res.projected_finish_display if res else None,
                hours_today=round(seconds["today"] / 3600, 1), hours_this_week=round(seconds["week"] / 3600, 1),
                hours_this_month=round(seconds["month"] / 3600, 1), total_hours_worked=round(total_hours, 1),
                channels_today=channels_today, channels_this_week=channels_week, channels_this_month=channels_month,
                total_channels_collected=len(user_channels), daily_avg_hours=round(total_hours / active_days, 1),
                daily_avg_channels=round(len(user_channels) / active_days, 1),
                avg_channels_per_hour=round(len(user_channels) / total_hours, 1) if total_hours > .05 else 0.0,
                completed_cycles_count=completed_cycles, goals_reached_count=goals_reached, chart_7d=chart,
                now_playing=now_playing,
                music_status=("Tocando" if now_playing and now_playing["is_playing"] else "Pausado") if now_playing else "Nada tocando"
            ))

        # Calcula média da equipe (canais/h)
        total_active_hours = total_hours_today_seconds / 3600.0
        team_avg_rate = round(total_channels_today / total_active_hours, 1) if total_active_hours > 0.01 else 0.0

        return TeamSummaryResponse(
            users_working_count=users_working_count,
            total_hours_today_seconds=total_hours_today_seconds,
            formatted_total_hours_today=format_seconds_hours_mins(total_hours_today_seconds),
            total_channels_today=total_channels_today,
            team_average_rate=team_avg_rate,
            members=members
        )

    @staticmethod
    def get_history(
        db: Session,
        user_id: Optional[int] = None,
        limit: int = 50,
        offset: int = 0
    ) -> List[SessionHistoryItem]:
        """
        Retorna o histórico detalhado de sessões de trabalho finalizadas ou recentes.
        """
        query = (
            db.query(WorkSession)
            .join(User, WorkSession.user_id == User.id)
            .options(joinedload(WorkSession.user))
            .filter(User.is_deleted == False)
        )
        if user_id:
            query = query.filter(WorkSession.user_id == user_id)

        sessions = query.order_by(WorkSession.started_at.desc()).offset(offset).limit(limit).all()

        history_items: List[SessionHistoryItem] = []
        for s in sessions:
            active_hours = s.active_seconds / 3600.0
            avg_rate = round(s.collected_count / active_hours, 1) if active_hours > 0.01 else 0.0
            started = ensure_utc(s.started_at)
            date_str = started.strftime("%d/%m/%Y") if started else "-"

            history_items.append(SessionHistoryItem(
                id=s.id,
                user_id=s.user_id,
                user_name=s.user.name if s.user else "Usuário",
                date_str=date_str,
                started_at=s.started_at,
                ended_at=s.ended_at,
                active_seconds=s.active_seconds,
                formatted_active_time=format_seconds_hours_mins(s.active_seconds),
                cycle_type=s.cycle_type,
                daily_target=s.daily_target,
                collected_count=s.collected_count,
                average_rate=avg_rate,
                status=s.status
            ))

        return history_items

    @staticmethod
    def get_cycle_settings(db: Session) -> CycleSettingsResponse:
        """
        Recupera configurações de metas e presets de ciclos.
        """
        setting = db.query(CycleSetting).first()
        if not setting:
            default_presets = [
                {"id": "8H", "name": "Ciclo 8 Horas", "hours": 8.0, "target": 160, "rate": 20.0},
                {"id": "6H", "name": "Ciclo 6 Horas", "hours": 6.0, "target": 160, "rate": 26.7},
                {"id": "CUSTOM", "name": "Personalizado", "hours": 8.0, "target": 160, "rate": 20.0}
            ]
            setting = CycleSetting(
                default_daily_target=160,
                presets_json=json.dumps(default_presets),
                updated_at=utc_now()
            )
            db.add(setting)
            db.commit()
            db.refresh(setting)

        try:
            presets_data = json.loads(setting.presets_json) if setting.presets_json else []
        except:
            presets_data = []

        presets = [CyclePresetItem(**p) for p in presets_data]
        return CycleSettingsResponse(
            default_daily_target=setting.default_daily_target,
            presets=presets
        )

    @staticmethod
    def update_cycle_settings(db: Session, data: CycleSettingsUpdate) -> CycleSettingsResponse:
        """
        Atualiza configurações de metas e presets.
        """
        setting = db.query(CycleSetting).first()
        if not setting:
            setting = CycleSetting(
                default_daily_target=data.default_daily_target,
                updated_at=utc_now()
            )
            db.add(setting)
        else:
            setting.default_daily_target = data.default_daily_target
            setting.updated_at = utc_now()

        if data.presets is not None:
            setting.presets_json = json.dumps([p.model_dump() for p in data.presets])

        db.commit()
        db.refresh(setting)
        return WorkSessionService.get_cycle_settings(db)
