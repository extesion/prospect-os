from datetime import datetime, timezone
from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, ForeignKey, Index, Float, Text
)
from sqlalchemy.orm import relationship
from backend.database.connection import Base

def utc_now():
    return datetime.now(timezone.utc)

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    email = Column(String(150), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(20), default="USER", nullable=False)  # 'ADMIN', 'USER'
    active = Column(Boolean, default=True, nullable=False)
    is_deleted = Column(Boolean, default=False, nullable=False)
    deleted_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    channels = relationship("Channel", back_populates="first_collector", foreign_keys="Channel.first_collected_by_id")
    events = relationship("CollectionEvent", back_populates="user")
    work_sessions = relationship("WorkSession", back_populates="user")


class Channel(Base):
    __tablename__ = "channels"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    channel_id = Column(String(64), unique=True, index=True, nullable=False)
    channel_name = Column(String(255), nullable=False)
    channel_handle = Column(String(100), nullable=True)
    channel_url = Column(String(500), nullable=False)
    source = Column(String(100), default="youtube_search", nullable=False)
    search_term = Column(String(255), nullable=True)
    
    first_collected_by_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    first_collected_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    first_collector = relationship("User", back_populates="channels", foreign_keys=[first_collected_by_id])
    events = relationship("CollectionEvent", back_populates="channel", foreign_keys="CollectionEvent.channel_id", primaryjoin="Channel.channel_id==CollectionEvent.channel_id")

    __table_args__ = (
        Index("idx_channel_id", "channel_id"),
        Index("idx_collected_at", "first_collected_at"),
    )


class CollectionEvent(Base):
    __tablename__ = "collection_events"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    channel_id = Column(String(64), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    work_session_id = Column(Integer, ForeignKey("work_sessions.id", ondelete="SET NULL"), nullable=True)
    event_type = Column(String(50), nullable=False)  # 'COLLECT', 'DUPLICATE_ATTEMPT', 'BULK_COLLECT'
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    user = relationship("User", back_populates="events")
    channel = relationship("Channel", back_populates="events", foreign_keys=[channel_id], primaryjoin="CollectionEvent.channel_id==Channel.channel_id")
    work_session = relationship("WorkSession", back_populates="collection_events")

    __table_args__ = (
        Index("idx_event_channel_user", "channel_id", "user_id"),
        Index("idx_event_created_at", "created_at"),
        Index("idx_event_session", "work_session_id"),
    )


class WorkSession(Base):
    __tablename__ = "work_sessions"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    started_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    ended_at = Column(DateTime(timezone=True), nullable=True)
    paused_at = Column(DateTime(timezone=True), nullable=True)
    last_resumed_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    active_seconds = Column(Integer, default=0, nullable=False)
    status = Column(String(20), default="ACTIVE", nullable=False) # 'ACTIVE', 'PAUSED', 'FINISHED'
    cycle_type = Column(String(50), default="8H", nullable=False) # '8H', '6H', 'CUSTOM'
    daily_target = Column(Integer, default=160, nullable=False)
    target_hours = Column(Float, default=8.0, nullable=False)
    target_per_hour = Column(Float, nullable=False)
    collected_count = Column(Integer, default=0, nullable=False)
    
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    user = relationship("User", back_populates="work_sessions")
    events = relationship("WorkSessionEvent", back_populates="session", cascade="all, delete-orphan")
    collection_events = relationship("CollectionEvent", back_populates="work_session")

    __table_args__ = (
        Index("idx_session_user_status", "user_id", "status"),
        Index("idx_session_started_at", "started_at"),
    )


class WorkSessionEvent(Base):
    __tablename__ = "work_session_events"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    session_id = Column(Integer, ForeignKey("work_sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    event_type = Column(String(20), nullable=False) # 'START', 'PAUSE', 'RESUME', 'FINISH'
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    session = relationship("WorkSession", back_populates="events")

    __table_args__ = (
        Index("idx_wsevent_session", "session_id"),
        Index("idx_wsevent_created_at", "created_at"),
    )


class CycleSetting(Base):
    __tablename__ = "cycle_settings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    default_daily_target = Column(Integer, default=160, nullable=False)
    presets_json = Column(Text, nullable=True)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)


class YouTubeApiConfig(Base):
    __tablename__ = "youtube_api_configs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    api_key = Column(String(255), nullable=False)
    status = Column(String(50), default="ACTIVE", nullable=False) # 'ACTIVE', 'QUOTA_EXCEEDED', 'ERROR', 'INACTIVE'
    daily_limit = Column(Integer, default=10000, nullable=False)
    last_used_at = Column(DateTime(timezone=True), nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    usages = relationship("YouTubeApiUsage", back_populates="api_config", cascade="all, delete-orphan")


class YouTubeApiUsage(Base):
    __tablename__ = "youtube_api_usage"

    id = Column(Integer, primary_key=True, autoincrement=True)
    api_config_id = Column(Integer, ForeignKey("youtube_api_configs.id", ondelete="SET NULL"), nullable=True, index=True)
    endpoint = Column(String(100), nullable=False) # 'channels.list', 'playlistItems.list', 'videos.list'
    units = Column(Integer, default=1, nullable=False)
    requested_at = Column(DateTime(timezone=True), default=utc_now, nullable=False, index=True)
    success = Column(Boolean, default=True, nullable=False)
    error_message = Column(Text, nullable=True)

    api_config = relationship("YouTubeApiConfig", back_populates="usages")

    __table_args__ = (
        Index("idx_yt_usage_requested_at", "requested_at"),
        Index("idx_yt_usage_config", "api_config_id"),
    )


class Notification(Base):
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, autoincrement=True)
    type = Column(String(50), nullable=False)  # 'USER_START_SESSION', 'USER_REACHED_GOAL', 'USER_COMPLETE_CYCLE', 'USER_END_SESSION', 'SYSTEM'
    actor_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    target_user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True) # None = Broadcast to all team
    title = Column(String(200), nullable=False)
    message = Column(Text, nullable=False)
    metadata_json = Column(Text, nullable=True) # JSON with extra payload (channels, rate, cycle_type, etc.)
    read_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False, index=True)

    actor = relationship("User", foreign_keys=[actor_user_id])
    target = relationship("User", foreign_keys=[target_user_id])

    __table_args__ = (
        Index("idx_notifications_created", "created_at"),
        Index("idx_notifications_target", "target_user_id"),
    )


class UserProfile(Base):
    __tablename__ = "user_profiles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False, index=True)
    avatar_url = Column(Text, nullable=True)
    banner_url = Column(Text, nullable=True)
    bio = Column(String(250), nullable=True)
    custom_status = Column(String(100), nullable=True)
    show_music_to_team = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    user = relationship("User", backref="profile", uselist=False)


class UserMusicConnection(Base):
    __tablename__ = "user_music_connections"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False, index=True)
    provider = Column(String(50), default="spotify", nullable=False) # 'spotify', 'youtube_music'
    is_connected = Column(Boolean, default=False, nullable=False)
    access_token = Column(Text, nullable=True)
    refresh_token = Column(Text, nullable=True)
    token_expires_at = Column(DateTime(timezone=True), nullable=True)
    current_track_name = Column(String(255), nullable=True)
    current_artist = Column(String(255), nullable=True)
    current_album_art = Column(String(500), nullable=True)
    current_track_url = Column(String(500), nullable=True)
    is_playing = Column(Boolean, default=False, nullable=False)
    session_tracks_json = Column(Text, nullable=True) # Track history counter during session
    most_played_track = Column(String(255), nullable=True)
    most_played_artist = Column(String(255), nullable=True)
    most_played_count = Column(Integer, default=0, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    user = relationship("User", backref="music_connection", uselist=False)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    actor_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    action = Column(String(100), nullable=False) # 'CREATE_USER', 'UPDATE_USER', 'CHANGE_ROLE', 'RESET_PASSWORD', 'DEACTIVATE_USER'
    target_resource = Column(String(100), nullable=False)
    target_id = Column(String(100), nullable=True)
    details_json = Column(Text, nullable=True)
    ip_address = Column(String(50), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False, index=True)

    actor = relationship("User", foreign_keys=[actor_user_id])

