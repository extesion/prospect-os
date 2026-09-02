from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import func, desc, and_
import json
import logging

from backend.database.models import (
    User, UserProfile, UserMusicConnection, WorkSession,
    CollectionEvent, Channel, utc_now
)
from backend.services.work_session_service import ensure_utc, format_seconds_hours_mins, format_seconds_hms, WorkSessionService
from backend.schemas.user_profile import UserProfileStats, UserProfileUpdate

logger = logging.getLogger(__name__)

class ProfileService:

    @staticmethod
    def get_or_create_profile(db: Session, user_id: int) -> UserProfile:
        """Recupera ou cria perfil padrão para o usuário."""
        profile = db.query(UserProfile).filter(UserProfile.user_id == user_id).first()
        if not profile:
            profile = UserProfile(
                user_id=user_id,
                avatar_url=None,
                banner_url=None,
                bio="Operador de prospecção",
                custom_status="Focado em resultados",
                show_music_to_team=True,
                created_at=utc_now(),
                updated_at=utc_now()
            )
            db.add(profile)
            db.commit()
            db.refresh(profile)
        return profile

    @staticmethod
    def update_profile(db: Session, user_id: int, data: UserProfileUpdate) -> UserProfile:
        """Atualiza dados do perfil."""
        profile = ProfileService.get_or_create_profile(db, user_id)
        if data.bio is not None:
            profile.bio = data.bio.strip()
        if data.custom_status is not None:
            profile.custom_status = data.custom_status.strip()
        if data.show_music_to_team is not None:
            profile.show_music_to_team = data.show_music_to_team
        profile.updated_at = utc_now()
        db.commit()
        db.refresh(profile)
        return profile

    @staticmethod
    def get_user_full_stats(db: Session, user_id: int) -> Optional[UserProfileStats]:
        """Calcula métricas agregadas e dados de perfil do usuário."""
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return None

        profile = ProfileService.get_or_create_profile(db, user_id)
        now = utc_now()

        # 1. Sessão Atual
        active_sess = (
            db.query(WorkSession)
            .filter(WorkSession.user_id == user_id)
            .filter(WorkSession.status.in_(["ACTIVE", "PAUSED"]))
            .order_by(WorkSession.started_at.desc())
            .first()
        )

        active_sess_dict = None
        work_session_status = "PARADO"
        if active_sess:
            work_session_status = active_sess.status
            res = WorkSessionService.compute_session_response(active_sess, user.name)
            active_sess_dict = res.model_dump()

        # Presence: Ativo se tem sessão ativa ou atualizou recentemente
        presence_status = "online" if active_sess else "offline"

        # 2. Todas as sessões do usuário
        all_sessions = (
            db.query(WorkSession)
            .filter(WorkSession.user_id == user_id)
            .order_by(WorkSession.started_at.asc())
            .all()
        )

        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        week_start = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        total_secs = 0
        secs_today = 0
        secs_week = 0
        secs_month = 0
        
        longest_sess_secs = 0
        completed_cycles = 0
        goals_reached = 0

        # Mapeamento por data (para cálculo de melhor dia e médias reais)
        daily_channels_map: Dict[str, int] = {}
        daily_seconds_map: Dict[str, int] = {}

        for s in all_sessions:
            s_started = ensure_utc(s.started_at)
            if not s_started:
                continue

            date_key = s_started.strftime("%Y-%m-%d")

            # Tempo da sessão
            s_active_secs = s.active_seconds
            if s.status == "ACTIVE":
                s_resumed = ensure_utc(s.last_resumed_at) or now
                elapsed = int((now - s_resumed).total_seconds())
                if elapsed > 0:
                    s_active_secs += elapsed

            total_secs += s_active_secs
            longest_sess_secs = max(longest_sess_secs, s_active_secs)

            if s.status == "FINISHED":
                completed_cycles += 1
            if s.collected_count >= s.daily_target:
                goals_reached += 1

            if s_started >= today_start:
                secs_today += s_active_secs
            if s_started >= week_start:
                secs_week += s_active_secs
            if s_started >= month_start:
                secs_month += s_active_secs

            daily_seconds_map[date_key] = daily_seconds_map.get(date_key, 0) + s_active_secs

        # 3. Canais Coletados
        user_channels = (
            db.query(Channel)
            .filter(Channel.first_collected_by_id == user_id)
            .all()
        )

        total_channels = len(user_channels)
        channels_today = 0
        channels_week = 0
        channels_month = 0

        for ch in user_channels:
            ch_date = ensure_utc(ch.first_collected_at)
            if not ch_date:
                continue
            
            d_str = ch_date.strftime("%Y-%m-%d")
            daily_channels_map[d_str] = daily_channels_map.get(d_str, 0) + 1

            if ch_date >= today_start:
                channels_today += 1
            if ch_date >= week_start:
                channels_week += 1
            if ch_date >= month_start:
                channels_month += 1

        # 4. Médias Matemáticas Exatas baseadas nos dias com atividade real
        all_active_days = set(daily_channels_map.keys()).union(set(daily_seconds_map.keys()))
        active_days_count = len(all_active_days) if all_active_days else 1

        total_hours = total_secs / 3600.0
        daily_avg_hours = round(total_hours / active_days_count, 1) if active_days_count > 0 else 0.0
        daily_avg_channels = round(total_channels / active_days_count, 1) if active_days_count > 0 else 0.0
        avg_channels_per_hour = round(total_channels / total_hours, 1) if total_hours > 0.05 else 0.0

        # Melhor dia de coleta
        best_day_channels = 0
        best_day_date = None
        for d_str, count in daily_channels_map.items():
            if count > best_day_channels:
                best_day_channels = count
                best_day_date = d_str

        # 5. Gerar dados de gráficos para 7, 30 e 90 dias
        def build_chart(days: int) -> List[Dict[str, Any]]:
            data = []
            for i in range(days - 1, -1, -1):
                day_dt = (now - timedelta(days=i)).strftime("%Y-%m-%d")
                d_obj = datetime.strptime(day_dt, "%Y-%m-%d")
                label = d_obj.strftime("%d/%m")
                c_count = daily_channels_map.get(day_dt, 0)
                sec_count = daily_seconds_map.get(day_dt, 0)
                hours_val = round(sec_count / 3600.0, 1)
                data.append({
                    "date": day_dt,
                    "label": label,
                    "channels": c_count,
                    "hours": hours_val
                })
            return data

        chart_7d = build_chart(7)
        chart_30d = build_chart(30)
        chart_90d = build_chart(90)

        # 6. Música Spotify (Now Playing / Mais ouvida da sessão)
        now_playing = None
        most_played = None
        music_conn = db.query(UserMusicConnection).filter(UserMusicConnection.user_id == user_id).first()
        if music_conn and music_conn.is_connected and profile.show_music_to_team:
            if music_conn.is_playing and music_conn.current_track_name:
                now_playing = {
                    "provider": music_conn.provider,
                    "track_name": music_conn.current_track_name,
                    "artist": music_conn.current_artist,
                    "album_art": music_conn.current_album_art,
                    "track_url": music_conn.current_track_url,
                    "is_playing": True
                }
            if music_conn.most_played_track:
                most_played = {
                    "track_name": music_conn.most_played_track,
                    "artist": music_conn.most_played_artist,
                    "play_count": music_conn.most_played_count
                }

        return UserProfileStats(
            user_id=user.id,
            name=user.name,
            email=user.email,
            role=user.role or "USER",
            active=user.active,
            avatar_url=profile.avatar_url,
            banner_url=profile.banner_url,
            bio=profile.bio,
            custom_status=profile.custom_status,
            show_music_to_team=profile.show_music_to_team,
            presence_status=presence_status,
            work_session_status=work_session_status,
            active_session=active_sess_dict,
            total_hours_worked=round(total_hours, 1),
            formatted_total_hours=format_seconds_hours_mins(total_secs),
            hours_today=round(secs_today / 3600.0, 1),
            formatted_hours_today=format_seconds_hours_mins(secs_today),
            hours_this_week=round(secs_week / 3600.0, 1),
            formatted_hours_this_week=format_seconds_hours_mins(secs_week),
            hours_this_month=round(secs_month / 3600.0, 1),
            formatted_hours_this_month=format_seconds_hours_mins(secs_month),
            total_channels_collected=total_channels,
            channels_today=channels_today,
            channels_this_week=channels_week,
            channels_this_month=channels_month,
            active_days_count=active_days_count,
            daily_avg_hours=daily_avg_hours,
            daily_avg_channels=daily_avg_channels,
            avg_channels_per_hour=avg_channels_per_hour,
            best_day_channels=best_day_channels,
            best_day_date=best_day_date,
            longest_session_hours=round(longest_sess_secs / 3600.0, 1),
            formatted_longest_session=format_seconds_hours_mins(longest_sess_secs),
            completed_cycles_count=completed_cycles,
            goals_reached_count=goals_reached,
            chart_7d=chart_7d,
            chart_30d=chart_30d,
            chart_90d=chart_90d,
            now_playing=now_playing,
            most_played_session_track=most_played
        )
