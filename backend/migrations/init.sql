-- YouTube Prospector - PostgreSQL Database Initialization Script

-- 1. Users table
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(150) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    active BOOLEAN DEFAULT TRUE NOT NULL,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP NOT NULL
);

-- Index on email
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);

-- 2. Channels table
CREATE TABLE IF NOT EXISTS channels (
    id BIGSERIAL PRIMARY KEY,
    channel_id VARCHAR(64) UNIQUE NOT NULL,
    channel_name VARCHAR(255) NOT NULL,
    channel_handle VARCHAR(100),
    channel_url VARCHAR(500) NOT NULL,
    source VARCHAR(100) DEFAULT 'youtube_search' NOT NULL,
    search_term VARCHAR(255),
    first_collected_by_id INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    first_collected_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP NOT NULL,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP NOT NULL
);

-- Unique index and query indexes
CREATE UNIQUE INDEX IF NOT EXISTS idx_channels_channel_id ON channels(channel_id);
CREATE INDEX IF NOT EXISTS idx_channels_collected_at ON channels(first_collected_at);
CREATE INDEX IF NOT EXISTS idx_channels_collector ON channels(first_collected_by_id);

-- 3. Collection events table (audit / team productivity)
CREATE TABLE IF NOT EXISTS collection_events (
    id BIGSERIAL PRIMARY KEY,
    channel_id VARCHAR(64) NOT NULL,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    event_type VARCHAR(50) NOT NULL, -- 'COLLECT', 'DUPLICATE_ATTEMPT', 'BULK_COLLECT'
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_events_channel_user ON collection_events(channel_id, user_id);
CREATE INDEX IF NOT EXISTS idx_events_created_at ON collection_events(created_at);
