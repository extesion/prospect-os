BEGIN;

ALTER TABLE users ADD COLUMN IF NOT EXISTS role VARCHAR(20) NOT NULL DEFAULT 'USER';
ALTER TABLE users ADD COLUMN IF NOT EXISTS is_deleted BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE users ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;
ALTER TABLE users ADD COLUMN IF NOT EXISTS last_seen_at TIMESTAMPTZ;

CREATE TABLE IF NOT EXISTS work_sessions (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    started_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    ended_at TIMESTAMPTZ,
    paused_at TIMESTAMPTZ,
    last_resumed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    active_seconds INTEGER NOT NULL DEFAULT 0,
    status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',
    cycle_type VARCHAR(50) NOT NULL DEFAULT '8H',
    daily_target INTEGER NOT NULL DEFAULT 160,
    target_hours DOUBLE PRECISION NOT NULL DEFAULT 8.0,
    target_per_hour DOUBLE PRECISION NOT NULL,
    collected_count INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_work_sessions_user_id ON work_sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_session_user_status ON work_sessions(user_id, status);
CREATE INDEX IF NOT EXISTS idx_session_started_at ON work_sessions(started_at);

CREATE TABLE IF NOT EXISTS work_session_events (
    id SERIAL PRIMARY KEY,
    session_id INTEGER NOT NULL REFERENCES work_sessions(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id),
    event_type VARCHAR(20) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_wsevent_session ON work_session_events(session_id);
CREATE INDEX IF NOT EXISTS idx_wsevent_created_at ON work_session_events(created_at);

CREATE TABLE IF NOT EXISTS notifications (
    id SERIAL PRIMARY KEY,
    type VARCHAR(50) NOT NULL,
    actor_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    target_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title VARCHAR(200) NOT NULL,
    message TEXT NOT NULL,
    metadata_json TEXT,
    dedupe_key VARCHAR(200),
    read_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
ALTER TABLE notifications ADD COLUMN IF NOT EXISTS dedupe_key VARCHAR(200);
CREATE UNIQUE INDEX IF NOT EXISTS ix_notifications_dedupe_key ON notifications(dedupe_key);
CREATE INDEX IF NOT EXISTS idx_notifications_created ON notifications(created_at);
CREATE INDEX IF NOT EXISTS idx_notifications_target ON notifications(target_user_id);
CREATE INDEX IF NOT EXISTS idx_notifications_read ON notifications(target_user_id, read_at);

CREATE TABLE IF NOT EXISTS cycle_settings (
    id SERIAL PRIMARY KEY,
    default_daily_target INTEGER NOT NULL DEFAULT 160,
    presets_json TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

ALTER TABLE collection_events ADD COLUMN IF NOT EXISTS work_session_id INTEGER REFERENCES work_sessions(id) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS idx_event_session ON collection_events(work_session_id);

COMMIT;
