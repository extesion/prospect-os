-- PostgreSQL only. Idempotent full-schema reconciliation from SQLAlchemy metadata.
BEGIN;

CREATE TABLE IF NOT EXISTS cycle_settings (
	id SERIAL NOT NULL, 
	default_daily_target INTEGER NOT NULL, 
	presets_json TEXT, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id)
);

CREATE TABLE IF NOT EXISTS qualification_jobs (
	id SERIAL NOT NULL, 
	channel_id VARCHAR(64) NOT NULL, 
	status VARCHAR(20) NOT NULL, 
	attempts INTEGER NOT NULL, 
	max_attempts INTEGER NOT NULL, 
	priority INTEGER NOT NULL, 
	next_retry_at TIMESTAMP WITH TIME ZONE, 
	started_at TIMESTAMP WITH TIME ZONE, 
	finished_at TIMESTAMP WITH TIME ZONE, 
	error_message TEXT, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id)
);

CREATE TABLE IF NOT EXISTS qualification_queue_state (
	id SERIAL NOT NULL, 
	paused BOOLEAN NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id)
);

CREATE TABLE IF NOT EXISTS qualification_results (
	id SERIAL NOT NULL, 
	channel_id VARCHAR(64) NOT NULL, 
	qualification_status VARCHAR(20) NOT NULL, 
	score INTEGER NOT NULL, 
	detected_niche VARCHAR(100), 
	niche_confidence FLOAT NOT NULL, 
	activity_status VARCHAR(20) NOT NULL, 
	days_since_last_video INTEGER, 
	last_video_date TIMESTAMP WITH TIME ZONE, 
	last_video_title VARCHAR(500), 
	estimated_posting_frequency_days FLOAT, 
	channel_description_analyzed BOOLEAN, 
	last_video_description_analyzed BOOLEAN, 
	subscribers BIGINT NOT NULL, 
	total_views BIGINT NOT NULL, 
	total_videos INTEGER NOT NULL, 
	channel_created_at TIMESTAMP WITH TIME ZONE, 
	country VARCHAR(10), 
	uploads_playlist_id VARCHAR(100), 
	email VARCHAR(255), 
	email_source VARCHAR(100), 
	whatsapp VARCHAR(100), 
	whatsapp_source VARCHAR(100), 
	website VARCHAR(500), 
	instagram VARCHAR(500), 
	tiktok VARCHAR(500), 
	twitter VARCHAR(500), 
	facebook VARCHAR(500), 
	linkedin VARCHAR(500), 
	link_aggregators JSON, 
	sales_platforms JSON, 
	commercial_signals JSON, 
	keywords_found JSON, 
	keywords_sources JSON, 
	score_breakdown JSON, 
	qualification_config_snapshot JSON, 
	qualification_config_version INTEGER, 
	qualification_reason TEXT, 
	qualification_version VARCHAR(20) NOT NULL, 
	youtube_data_updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	qualified_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id)
);

CREATE TABLE IF NOT EXISTS users (
	id SERIAL NOT NULL, 
	name VARCHAR(100) NOT NULL, 
	email VARCHAR(150) NOT NULL, 
	password_hash VARCHAR(255) NOT NULL, 
	role VARCHAR(20) NOT NULL, 
	active BOOLEAN NOT NULL, 
	is_deleted BOOLEAN NOT NULL, 
	deleted_at TIMESTAMP WITH TIME ZONE, 
	last_seen_at TIMESTAMP WITH TIME ZONE, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id)
);

CREATE TABLE IF NOT EXISTS youtube_api_configs (
	id SERIAL NOT NULL, 
	name VARCHAR(100) NOT NULL, 
	api_key VARCHAR(255) NOT NULL, 
	status VARCHAR(50) NOT NULL, 
	daily_limit INTEGER NOT NULL, 
	last_used_at TIMESTAMP WITH TIME ZONE, 
	error_message TEXT, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id)
);

CREATE TABLE IF NOT EXISTS analyzed_videos (
	id SERIAL NOT NULL, 
	qualification_result_id INTEGER NOT NULL, 
	channel_id VARCHAR(64) NOT NULL, 
	video_id VARCHAR(64) NOT NULL, 
	title VARCHAR(500) NOT NULL, 
	description TEXT, 
	published_at TIMESTAMP WITH TIME ZONE, 
	view_count BIGINT NOT NULL, 
	like_count INTEGER NOT NULL, 
	comment_count INTEGER NOT NULL, 
	duration VARCHAR(50), 
	tags JSON, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(qualification_result_id) REFERENCES qualification_results (id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS audit_logs (
	id SERIAL NOT NULL, 
	actor_user_id INTEGER, 
	action VARCHAR(100) NOT NULL, 
	target_resource VARCHAR(100) NOT NULL, 
	target_id VARCHAR(100), 
	details_json TEXT, 
	ip_address VARCHAR(50), 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(actor_user_id) REFERENCES users (id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS channels (
	id SERIAL NOT NULL, 
	channel_id VARCHAR(64) NOT NULL, 
	channel_name VARCHAR(255) NOT NULL, 
	channel_handle VARCHAR(100), 
	channel_url VARCHAR(500) NOT NULL, 
	source VARCHAR(100) NOT NULL, 
	search_term VARCHAR(255), 
	first_collected_by_id INTEGER NOT NULL, 
	first_collected_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(first_collected_by_id) REFERENCES users (id)
);

CREATE TABLE IF NOT EXISTS notifications (
	id SERIAL NOT NULL, 
	type VARCHAR(50) NOT NULL, 
	actor_user_id INTEGER, 
	target_user_id INTEGER NOT NULL, 
	title VARCHAR(200) NOT NULL, 
	message TEXT NOT NULL, 
	metadata_json TEXT, 
	dedupe_key VARCHAR(200), 
	read_at TIMESTAMP WITH TIME ZONE, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(actor_user_id) REFERENCES users (id) ON DELETE SET NULL, 
	FOREIGN KEY(target_user_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS qualification_config (
	id INTEGER NOT NULL, 
	version INTEGER NOT NULL, 
	config_json JSON NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_by_id INTEGER, 
	PRIMARY KEY (id), 
	FOREIGN KEY(updated_by_id) REFERENCES users (id)
);

CREATE TABLE IF NOT EXISTS user_music_connections (
	id SERIAL NOT NULL, 
	user_id INTEGER NOT NULL, 
	provider VARCHAR(50) NOT NULL, 
	is_connected BOOLEAN NOT NULL, 
	access_token TEXT, 
	refresh_token TEXT, 
	token_expires_at TIMESTAMP WITH TIME ZONE, 
	current_track_id VARCHAR(255), 
	current_track_name VARCHAR(255), 
	current_artist VARCHAR(255), 
	current_album_art VARCHAR(500), 
	current_track_url VARCHAR(500), 
	position_ms INTEGER NOT NULL, 
	duration_ms INTEGER NOT NULL, 
	captured_at TIMESTAMP WITH TIME ZONE, 
	is_playing BOOLEAN NOT NULL, 
	session_tracks_json TEXT, 
	most_played_track VARCHAR(255), 
	most_played_artist VARCHAR(255), 
	most_played_count INTEGER NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS user_profiles (
	id SERIAL NOT NULL, 
	user_id INTEGER NOT NULL, 
	avatar_url TEXT, 
	banner_url TEXT, 
	bio VARCHAR(250), 
	custom_status VARCHAR(100), 
	show_music_to_team BOOLEAN NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS work_sessions (
	id SERIAL NOT NULL, 
	user_id INTEGER NOT NULL, 
	started_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	ended_at TIMESTAMP WITH TIME ZONE, 
	paused_at TIMESTAMP WITH TIME ZONE, 
	last_resumed_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	active_seconds INTEGER NOT NULL, 
	status VARCHAR(20) NOT NULL, 
	cycle_type VARCHAR(50) NOT NULL, 
	daily_target INTEGER NOT NULL, 
	target_hours FLOAT NOT NULL, 
	target_per_hour FLOAT NOT NULL, 
	collected_count INTEGER NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id)
);

CREATE TABLE IF NOT EXISTS youtube_api_usage (
	id SERIAL NOT NULL, 
	api_config_id INTEGER, 
	endpoint VARCHAR(100) NOT NULL, 
	units INTEGER NOT NULL, 
	requested_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	success BOOLEAN NOT NULL, 
	error_message TEXT, 
	PRIMARY KEY (id), 
	FOREIGN KEY(api_config_id) REFERENCES youtube_api_configs (id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS collection_events (
	id SERIAL NOT NULL, 
	channel_id VARCHAR(64) NOT NULL, 
	user_id INTEGER NOT NULL, 
	work_session_id INTEGER, 
	event_type VARCHAR(50) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id), 
	FOREIGN KEY(work_session_id) REFERENCES work_sessions (id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS work_session_events (
	id SERIAL NOT NULL, 
	session_id INTEGER NOT NULL, 
	user_id INTEGER NOT NULL, 
	event_type VARCHAR(20) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(session_id) REFERENCES work_sessions (id) ON DELETE CASCADE, 
	FOREIGN KEY(user_id) REFERENCES users (id)
);

-- Reconcile existing cycle_settings.
ALTER TABLE cycle_settings ADD COLUMN IF NOT EXISTS default_daily_target INTEGER NOT NULL DEFAULT 160;
ALTER TABLE cycle_settings ADD COLUMN IF NOT EXISTS presets_json TEXT;
ALTER TABLE cycle_settings ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP;
ALTER TABLE cycle_settings ALTER COLUMN updated_at DROP DEFAULT;

-- Reconcile existing qualification_jobs.
ALTER TABLE qualification_jobs ADD COLUMN IF NOT EXISTS channel_id VARCHAR(64) NOT NULL DEFAULT '';
ALTER TABLE qualification_jobs ALTER COLUMN channel_id DROP DEFAULT;
ALTER TABLE qualification_jobs ADD COLUMN IF NOT EXISTS status VARCHAR(20) NOT NULL DEFAULT 'PENDING';
ALTER TABLE qualification_jobs ADD COLUMN IF NOT EXISTS attempts INTEGER NOT NULL DEFAULT 0;
ALTER TABLE qualification_jobs ADD COLUMN IF NOT EXISTS max_attempts INTEGER NOT NULL DEFAULT 3;
ALTER TABLE qualification_jobs ADD COLUMN IF NOT EXISTS priority INTEGER NOT NULL DEFAULT 0;
ALTER TABLE qualification_jobs ADD COLUMN IF NOT EXISTS next_retry_at TIMESTAMP WITH TIME ZONE;
ALTER TABLE qualification_jobs ADD COLUMN IF NOT EXISTS started_at TIMESTAMP WITH TIME ZONE;
ALTER TABLE qualification_jobs ADD COLUMN IF NOT EXISTS finished_at TIMESTAMP WITH TIME ZONE;
ALTER TABLE qualification_jobs ADD COLUMN IF NOT EXISTS error_message TEXT;
ALTER TABLE qualification_jobs ADD COLUMN IF NOT EXISTS created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP;
ALTER TABLE qualification_jobs ALTER COLUMN created_at DROP DEFAULT;
ALTER TABLE qualification_jobs ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP;
ALTER TABLE qualification_jobs ALTER COLUMN updated_at DROP DEFAULT;

-- Reconcile existing qualification_queue_state.
ALTER TABLE qualification_queue_state ADD COLUMN IF NOT EXISTS paused BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE qualification_queue_state ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP;
ALTER TABLE qualification_queue_state ALTER COLUMN updated_at DROP DEFAULT;

-- Reconcile existing qualification_results.
ALTER TABLE qualification_results ADD COLUMN IF NOT EXISTS channel_id VARCHAR(64) NOT NULL DEFAULT '';
ALTER TABLE qualification_results ALTER COLUMN channel_id DROP DEFAULT;
ALTER TABLE qualification_results ADD COLUMN IF NOT EXISTS qualification_status VARCHAR(20) NOT NULL DEFAULT '';
ALTER TABLE qualification_results ALTER COLUMN qualification_status DROP DEFAULT;
ALTER TABLE qualification_results ADD COLUMN IF NOT EXISTS score INTEGER NOT NULL DEFAULT 0;
ALTER TABLE qualification_results ADD COLUMN IF NOT EXISTS detected_niche VARCHAR(100);
ALTER TABLE qualification_results ADD COLUMN IF NOT EXISTS niche_confidence FLOAT NOT NULL DEFAULT 0.0;
ALTER TABLE qualification_results ADD COLUMN IF NOT EXISTS activity_status VARCHAR(20) NOT NULL DEFAULT 'INACTIVE';
ALTER TABLE qualification_results ADD COLUMN IF NOT EXISTS days_since_last_video INTEGER;
ALTER TABLE qualification_results ADD COLUMN IF NOT EXISTS last_video_date TIMESTAMP WITH TIME ZONE;
ALTER TABLE qualification_results ADD COLUMN IF NOT EXISTS last_video_title VARCHAR(500);
ALTER TABLE qualification_results ADD COLUMN IF NOT EXISTS estimated_posting_frequency_days FLOAT;
ALTER TABLE qualification_results ADD COLUMN IF NOT EXISTS channel_description_analyzed BOOLEAN;
ALTER TABLE qualification_results ADD COLUMN IF NOT EXISTS last_video_description_analyzed BOOLEAN;
ALTER TABLE qualification_results ADD COLUMN IF NOT EXISTS subscribers BIGINT NOT NULL DEFAULT 0;
ALTER TABLE qualification_results ADD COLUMN IF NOT EXISTS total_views BIGINT NOT NULL DEFAULT 0;
ALTER TABLE qualification_results ADD COLUMN IF NOT EXISTS total_videos INTEGER NOT NULL DEFAULT 0;
ALTER TABLE qualification_results ADD COLUMN IF NOT EXISTS channel_created_at TIMESTAMP WITH TIME ZONE;
ALTER TABLE qualification_results ADD COLUMN IF NOT EXISTS country VARCHAR(10);
ALTER TABLE qualification_results ADD COLUMN IF NOT EXISTS uploads_playlist_id VARCHAR(100);
ALTER TABLE qualification_results ADD COLUMN IF NOT EXISTS email VARCHAR(255);
ALTER TABLE qualification_results ADD COLUMN IF NOT EXISTS email_source VARCHAR(100);
ALTER TABLE qualification_results ADD COLUMN IF NOT EXISTS whatsapp VARCHAR(100);
ALTER TABLE qualification_results ADD COLUMN IF NOT EXISTS whatsapp_source VARCHAR(100);
ALTER TABLE qualification_results ADD COLUMN IF NOT EXISTS website VARCHAR(500);
ALTER TABLE qualification_results ADD COLUMN IF NOT EXISTS instagram VARCHAR(500);
ALTER TABLE qualification_results ADD COLUMN IF NOT EXISTS tiktok VARCHAR(500);
ALTER TABLE qualification_results ADD COLUMN IF NOT EXISTS twitter VARCHAR(500);
ALTER TABLE qualification_results ADD COLUMN IF NOT EXISTS facebook VARCHAR(500);
ALTER TABLE qualification_results ADD COLUMN IF NOT EXISTS linkedin VARCHAR(500);
ALTER TABLE qualification_results ADD COLUMN IF NOT EXISTS link_aggregators JSON;
ALTER TABLE qualification_results ADD COLUMN IF NOT EXISTS sales_platforms JSON;
ALTER TABLE qualification_results ADD COLUMN IF NOT EXISTS commercial_signals JSON;
ALTER TABLE qualification_results ADD COLUMN IF NOT EXISTS keywords_found JSON;
ALTER TABLE qualification_results ADD COLUMN IF NOT EXISTS keywords_sources JSON;
ALTER TABLE qualification_results ADD COLUMN IF NOT EXISTS score_breakdown JSON;
ALTER TABLE qualification_results ADD COLUMN IF NOT EXISTS qualification_config_snapshot JSON;
ALTER TABLE qualification_results ADD COLUMN IF NOT EXISTS qualification_config_version INTEGER;
ALTER TABLE qualification_results ADD COLUMN IF NOT EXISTS qualification_reason TEXT;
ALTER TABLE qualification_results ADD COLUMN IF NOT EXISTS qualification_version VARCHAR(20) NOT NULL DEFAULT 'v1';
ALTER TABLE qualification_results ADD COLUMN IF NOT EXISTS youtube_data_updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP;
ALTER TABLE qualification_results ALTER COLUMN youtube_data_updated_at DROP DEFAULT;
ALTER TABLE qualification_results ADD COLUMN IF NOT EXISTS created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP;
ALTER TABLE qualification_results ALTER COLUMN created_at DROP DEFAULT;
ALTER TABLE qualification_results ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP;
ALTER TABLE qualification_results ALTER COLUMN updated_at DROP DEFAULT;
ALTER TABLE qualification_results ADD COLUMN IF NOT EXISTS qualified_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP;
ALTER TABLE qualification_results ALTER COLUMN qualified_at DROP DEFAULT;

-- Reconcile existing users.
ALTER TABLE users ADD COLUMN IF NOT EXISTS name VARCHAR(100) NOT NULL DEFAULT '';
ALTER TABLE users ALTER COLUMN name DROP DEFAULT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS email VARCHAR(150) NOT NULL DEFAULT '';
ALTER TABLE users ALTER COLUMN email DROP DEFAULT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS password_hash VARCHAR(255) NOT NULL DEFAULT '';
ALTER TABLE users ALTER COLUMN password_hash DROP DEFAULT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS role VARCHAR(20) NOT NULL DEFAULT 'USER';
ALTER TABLE users ADD COLUMN IF NOT EXISTS active BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE users ADD COLUMN IF NOT EXISTS is_deleted BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE users ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMP WITH TIME ZONE;
ALTER TABLE users ADD COLUMN IF NOT EXISTS last_seen_at TIMESTAMP WITH TIME ZONE;
ALTER TABLE users ADD COLUMN IF NOT EXISTS created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP;
ALTER TABLE users ALTER COLUMN created_at DROP DEFAULT;

-- Reconcile existing youtube_api_configs.
ALTER TABLE youtube_api_configs ADD COLUMN IF NOT EXISTS name VARCHAR(100) NOT NULL DEFAULT '';
ALTER TABLE youtube_api_configs ALTER COLUMN name DROP DEFAULT;
ALTER TABLE youtube_api_configs ADD COLUMN IF NOT EXISTS api_key VARCHAR(255) NOT NULL DEFAULT '';
ALTER TABLE youtube_api_configs ALTER COLUMN api_key DROP DEFAULT;
ALTER TABLE youtube_api_configs ADD COLUMN IF NOT EXISTS status VARCHAR(50) NOT NULL DEFAULT 'ACTIVE';
ALTER TABLE youtube_api_configs ADD COLUMN IF NOT EXISTS daily_limit INTEGER NOT NULL DEFAULT 10000;
ALTER TABLE youtube_api_configs ADD COLUMN IF NOT EXISTS last_used_at TIMESTAMP WITH TIME ZONE;
ALTER TABLE youtube_api_configs ADD COLUMN IF NOT EXISTS error_message TEXT;
ALTER TABLE youtube_api_configs ADD COLUMN IF NOT EXISTS created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP;
ALTER TABLE youtube_api_configs ALTER COLUMN created_at DROP DEFAULT;
ALTER TABLE youtube_api_configs ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP;
ALTER TABLE youtube_api_configs ALTER COLUMN updated_at DROP DEFAULT;

-- Reconcile existing analyzed_videos.
ALTER TABLE analyzed_videos ADD COLUMN IF NOT EXISTS qualification_result_id INTEGER NOT NULL DEFAULT 0;
ALTER TABLE analyzed_videos ALTER COLUMN qualification_result_id DROP DEFAULT;
ALTER TABLE analyzed_videos ADD COLUMN IF NOT EXISTS channel_id VARCHAR(64) NOT NULL DEFAULT '';
ALTER TABLE analyzed_videos ALTER COLUMN channel_id DROP DEFAULT;
ALTER TABLE analyzed_videos ADD COLUMN IF NOT EXISTS video_id VARCHAR(64) NOT NULL DEFAULT '';
ALTER TABLE analyzed_videos ALTER COLUMN video_id DROP DEFAULT;
ALTER TABLE analyzed_videos ADD COLUMN IF NOT EXISTS title VARCHAR(500) NOT NULL DEFAULT '';
ALTER TABLE analyzed_videos ALTER COLUMN title DROP DEFAULT;
ALTER TABLE analyzed_videos ADD COLUMN IF NOT EXISTS description TEXT;
ALTER TABLE analyzed_videos ADD COLUMN IF NOT EXISTS published_at TIMESTAMP WITH TIME ZONE;
ALTER TABLE analyzed_videos ADD COLUMN IF NOT EXISTS view_count BIGINT NOT NULL DEFAULT 0;
ALTER TABLE analyzed_videos ADD COLUMN IF NOT EXISTS like_count INTEGER NOT NULL DEFAULT 0;
ALTER TABLE analyzed_videos ADD COLUMN IF NOT EXISTS comment_count INTEGER NOT NULL DEFAULT 0;
ALTER TABLE analyzed_videos ADD COLUMN IF NOT EXISTS duration VARCHAR(50);
ALTER TABLE analyzed_videos ADD COLUMN IF NOT EXISTS tags JSON;
ALTER TABLE analyzed_videos ADD COLUMN IF NOT EXISTS created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP;
ALTER TABLE analyzed_videos ALTER COLUMN created_at DROP DEFAULT;

-- Reconcile existing audit_logs.
ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS actor_user_id INTEGER;
ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS action VARCHAR(100) NOT NULL DEFAULT '';
ALTER TABLE audit_logs ALTER COLUMN action DROP DEFAULT;
ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS target_resource VARCHAR(100) NOT NULL DEFAULT '';
ALTER TABLE audit_logs ALTER COLUMN target_resource DROP DEFAULT;
ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS target_id VARCHAR(100);
ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS details_json TEXT;
ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS ip_address VARCHAR(50);
ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP;
ALTER TABLE audit_logs ALTER COLUMN created_at DROP DEFAULT;

-- Reconcile existing channels.
ALTER TABLE channels ADD COLUMN IF NOT EXISTS channel_id VARCHAR(64) NOT NULL DEFAULT '';
ALTER TABLE channels ALTER COLUMN channel_id DROP DEFAULT;
ALTER TABLE channels ADD COLUMN IF NOT EXISTS channel_name VARCHAR(255) NOT NULL DEFAULT '';
ALTER TABLE channels ALTER COLUMN channel_name DROP DEFAULT;
ALTER TABLE channels ADD COLUMN IF NOT EXISTS channel_handle VARCHAR(100);
ALTER TABLE channels ADD COLUMN IF NOT EXISTS channel_url VARCHAR(500) NOT NULL DEFAULT '';
ALTER TABLE channels ALTER COLUMN channel_url DROP DEFAULT;
ALTER TABLE channels ADD COLUMN IF NOT EXISTS source VARCHAR(100) NOT NULL DEFAULT 'youtube_search';
ALTER TABLE channels ADD COLUMN IF NOT EXISTS search_term VARCHAR(255);
ALTER TABLE channels ADD COLUMN IF NOT EXISTS first_collected_by_id INTEGER NOT NULL DEFAULT 0;
ALTER TABLE channels ALTER COLUMN first_collected_by_id DROP DEFAULT;
ALTER TABLE channels ADD COLUMN IF NOT EXISTS first_collected_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP;
ALTER TABLE channels ALTER COLUMN first_collected_at DROP DEFAULT;
ALTER TABLE channels ADD COLUMN IF NOT EXISTS created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP;
ALTER TABLE channels ALTER COLUMN created_at DROP DEFAULT;
ALTER TABLE channels ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP;
ALTER TABLE channels ALTER COLUMN updated_at DROP DEFAULT;

-- Reconcile existing notifications.
ALTER TABLE notifications ADD COLUMN IF NOT EXISTS type VARCHAR(50) NOT NULL DEFAULT '';
ALTER TABLE notifications ALTER COLUMN type DROP DEFAULT;
ALTER TABLE notifications ADD COLUMN IF NOT EXISTS actor_user_id INTEGER;
ALTER TABLE notifications ADD COLUMN IF NOT EXISTS target_user_id INTEGER NOT NULL DEFAULT 0;
ALTER TABLE notifications ALTER COLUMN target_user_id DROP DEFAULT;
ALTER TABLE notifications ADD COLUMN IF NOT EXISTS title VARCHAR(200) NOT NULL DEFAULT '';
ALTER TABLE notifications ALTER COLUMN title DROP DEFAULT;
ALTER TABLE notifications ADD COLUMN IF NOT EXISTS message TEXT NOT NULL DEFAULT '';
ALTER TABLE notifications ALTER COLUMN message DROP DEFAULT;
ALTER TABLE notifications ADD COLUMN IF NOT EXISTS metadata_json TEXT;
ALTER TABLE notifications ADD COLUMN IF NOT EXISTS dedupe_key VARCHAR(200);
ALTER TABLE notifications ADD COLUMN IF NOT EXISTS read_at TIMESTAMP WITH TIME ZONE;
ALTER TABLE notifications ADD COLUMN IF NOT EXISTS created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP;
ALTER TABLE notifications ALTER COLUMN created_at DROP DEFAULT;

-- Reconcile existing qualification_config.
ALTER TABLE qualification_config ADD COLUMN IF NOT EXISTS version INTEGER NOT NULL DEFAULT 1;
ALTER TABLE qualification_config ADD COLUMN IF NOT EXISTS config_json JSON NOT NULL DEFAULT '{}'::json;
ALTER TABLE qualification_config ALTER COLUMN config_json DROP DEFAULT;
ALTER TABLE qualification_config ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP;
ALTER TABLE qualification_config ALTER COLUMN updated_at DROP DEFAULT;
ALTER TABLE qualification_config ADD COLUMN IF NOT EXISTS updated_by_id INTEGER;

-- Reconcile existing user_music_connections.
ALTER TABLE user_music_connections ADD COLUMN IF NOT EXISTS user_id INTEGER NOT NULL DEFAULT 0;
ALTER TABLE user_music_connections ALTER COLUMN user_id DROP DEFAULT;
ALTER TABLE user_music_connections ADD COLUMN IF NOT EXISTS provider VARCHAR(50) NOT NULL DEFAULT 'spotify';
ALTER TABLE user_music_connections ADD COLUMN IF NOT EXISTS is_connected BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE user_music_connections ADD COLUMN IF NOT EXISTS access_token TEXT;
ALTER TABLE user_music_connections ADD COLUMN IF NOT EXISTS refresh_token TEXT;
ALTER TABLE user_music_connections ADD COLUMN IF NOT EXISTS token_expires_at TIMESTAMP WITH TIME ZONE;
ALTER TABLE user_music_connections ADD COLUMN IF NOT EXISTS current_track_id VARCHAR(255);
ALTER TABLE user_music_connections ADD COLUMN IF NOT EXISTS current_track_name VARCHAR(255);
ALTER TABLE user_music_connections ADD COLUMN IF NOT EXISTS current_artist VARCHAR(255);
ALTER TABLE user_music_connections ADD COLUMN IF NOT EXISTS current_album_art VARCHAR(500);
ALTER TABLE user_music_connections ADD COLUMN IF NOT EXISTS current_track_url VARCHAR(500);
ALTER TABLE user_music_connections ADD COLUMN IF NOT EXISTS position_ms INTEGER NOT NULL DEFAULT 0;
ALTER TABLE user_music_connections ADD COLUMN IF NOT EXISTS duration_ms INTEGER NOT NULL DEFAULT 0;
ALTER TABLE user_music_connections ADD COLUMN IF NOT EXISTS captured_at TIMESTAMP WITH TIME ZONE;
ALTER TABLE user_music_connections ADD COLUMN IF NOT EXISTS is_playing BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE user_music_connections ADD COLUMN IF NOT EXISTS session_tracks_json TEXT;
ALTER TABLE user_music_connections ADD COLUMN IF NOT EXISTS most_played_track VARCHAR(255);
ALTER TABLE user_music_connections ADD COLUMN IF NOT EXISTS most_played_artist VARCHAR(255);
ALTER TABLE user_music_connections ADD COLUMN IF NOT EXISTS most_played_count INTEGER NOT NULL DEFAULT 0;
ALTER TABLE user_music_connections ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP;
ALTER TABLE user_music_connections ALTER COLUMN updated_at DROP DEFAULT;

-- Reconcile existing user_profiles.
ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS user_id INTEGER NOT NULL DEFAULT 0;
ALTER TABLE user_profiles ALTER COLUMN user_id DROP DEFAULT;
ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS avatar_url TEXT;
ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS banner_url TEXT;
ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS bio VARCHAR(250);
ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS custom_status VARCHAR(100);
ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS show_music_to_team BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP;
ALTER TABLE user_profiles ALTER COLUMN created_at DROP DEFAULT;
ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP;
ALTER TABLE user_profiles ALTER COLUMN updated_at DROP DEFAULT;

-- Reconcile existing work_sessions.
ALTER TABLE work_sessions ADD COLUMN IF NOT EXISTS user_id INTEGER NOT NULL DEFAULT 0;
ALTER TABLE work_sessions ALTER COLUMN user_id DROP DEFAULT;
ALTER TABLE work_sessions ADD COLUMN IF NOT EXISTS started_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP;
ALTER TABLE work_sessions ALTER COLUMN started_at DROP DEFAULT;
ALTER TABLE work_sessions ADD COLUMN IF NOT EXISTS ended_at TIMESTAMP WITH TIME ZONE;
ALTER TABLE work_sessions ADD COLUMN IF NOT EXISTS paused_at TIMESTAMP WITH TIME ZONE;
ALTER TABLE work_sessions ADD COLUMN IF NOT EXISTS last_resumed_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP;
ALTER TABLE work_sessions ALTER COLUMN last_resumed_at DROP DEFAULT;
ALTER TABLE work_sessions ADD COLUMN IF NOT EXISTS active_seconds INTEGER NOT NULL DEFAULT 0;
ALTER TABLE work_sessions ADD COLUMN IF NOT EXISTS status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE';
ALTER TABLE work_sessions ADD COLUMN IF NOT EXISTS cycle_type VARCHAR(50) NOT NULL DEFAULT '8H';
ALTER TABLE work_sessions ADD COLUMN IF NOT EXISTS daily_target INTEGER NOT NULL DEFAULT 160;
ALTER TABLE work_sessions ADD COLUMN IF NOT EXISTS target_hours FLOAT NOT NULL DEFAULT 8.0;
ALTER TABLE work_sessions ADD COLUMN IF NOT EXISTS target_per_hour FLOAT NOT NULL DEFAULT 0;
ALTER TABLE work_sessions ALTER COLUMN target_per_hour DROP DEFAULT;
ALTER TABLE work_sessions ADD COLUMN IF NOT EXISTS collected_count INTEGER NOT NULL DEFAULT 0;
ALTER TABLE work_sessions ADD COLUMN IF NOT EXISTS created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP;
ALTER TABLE work_sessions ALTER COLUMN created_at DROP DEFAULT;
ALTER TABLE work_sessions ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP;
ALTER TABLE work_sessions ALTER COLUMN updated_at DROP DEFAULT;

-- Reconcile existing youtube_api_usage.
ALTER TABLE youtube_api_usage ADD COLUMN IF NOT EXISTS api_config_id INTEGER;
ALTER TABLE youtube_api_usage ADD COLUMN IF NOT EXISTS endpoint VARCHAR(100) NOT NULL DEFAULT '';
ALTER TABLE youtube_api_usage ALTER COLUMN endpoint DROP DEFAULT;
ALTER TABLE youtube_api_usage ADD COLUMN IF NOT EXISTS units INTEGER NOT NULL DEFAULT 1;
ALTER TABLE youtube_api_usage ADD COLUMN IF NOT EXISTS requested_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP;
ALTER TABLE youtube_api_usage ALTER COLUMN requested_at DROP DEFAULT;
ALTER TABLE youtube_api_usage ADD COLUMN IF NOT EXISTS success BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE youtube_api_usage ADD COLUMN IF NOT EXISTS error_message TEXT;

-- Reconcile existing collection_events.
ALTER TABLE collection_events ADD COLUMN IF NOT EXISTS channel_id VARCHAR(64) NOT NULL DEFAULT '';
ALTER TABLE collection_events ALTER COLUMN channel_id DROP DEFAULT;
ALTER TABLE collection_events ADD COLUMN IF NOT EXISTS user_id INTEGER NOT NULL DEFAULT 0;
ALTER TABLE collection_events ALTER COLUMN user_id DROP DEFAULT;
ALTER TABLE collection_events ADD COLUMN IF NOT EXISTS work_session_id INTEGER;
ALTER TABLE collection_events ADD COLUMN IF NOT EXISTS event_type VARCHAR(50) NOT NULL DEFAULT '';
ALTER TABLE collection_events ALTER COLUMN event_type DROP DEFAULT;
ALTER TABLE collection_events ADD COLUMN IF NOT EXISTS created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP;
ALTER TABLE collection_events ALTER COLUMN created_at DROP DEFAULT;

-- Reconcile existing work_session_events.
ALTER TABLE work_session_events ADD COLUMN IF NOT EXISTS session_id INTEGER NOT NULL DEFAULT 0;
ALTER TABLE work_session_events ALTER COLUMN session_id DROP DEFAULT;
ALTER TABLE work_session_events ADD COLUMN IF NOT EXISTS user_id INTEGER NOT NULL DEFAULT 0;
ALTER TABLE work_session_events ALTER COLUMN user_id DROP DEFAULT;
ALTER TABLE work_session_events ADD COLUMN IF NOT EXISTS event_type VARCHAR(20) NOT NULL DEFAULT '';
ALTER TABLE work_session_events ALTER COLUMN event_type DROP DEFAULT;
ALTER TABLE work_session_events ADD COLUMN IF NOT EXISTS created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP;
ALTER TABLE work_session_events ALTER COLUMN created_at DROP DEFAULT;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_analyzed_videos_qualification_result_id' AND conrelid = 'analyzed_videos'::regclass) THEN
        ALTER TABLE analyzed_videos ADD CONSTRAINT fk_analyzed_videos_qualification_result_id FOREIGN KEY (qualification_result_id) REFERENCES qualification_results (id) ON DELETE CASCADE NOT VALID;
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_audit_logs_actor_user_id' AND conrelid = 'audit_logs'::regclass) THEN
        ALTER TABLE audit_logs ADD CONSTRAINT fk_audit_logs_actor_user_id FOREIGN KEY (actor_user_id) REFERENCES users (id) ON DELETE SET NULL NOT VALID;
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_channels_first_collected_by_id' AND conrelid = 'channels'::regclass) THEN
        ALTER TABLE channels ADD CONSTRAINT fk_channels_first_collected_by_id FOREIGN KEY (first_collected_by_id) REFERENCES users (id) NOT VALID;
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_notifications_actor_user_id' AND conrelid = 'notifications'::regclass) THEN
        ALTER TABLE notifications ADD CONSTRAINT fk_notifications_actor_user_id FOREIGN KEY (actor_user_id) REFERENCES users (id) ON DELETE SET NULL NOT VALID;
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_notifications_target_user_id' AND conrelid = 'notifications'::regclass) THEN
        ALTER TABLE notifications ADD CONSTRAINT fk_notifications_target_user_id FOREIGN KEY (target_user_id) REFERENCES users (id) ON DELETE CASCADE NOT VALID;
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_qualification_config_updated_by_id' AND conrelid = 'qualification_config'::regclass) THEN
        ALTER TABLE qualification_config ADD CONSTRAINT fk_qualification_config_updated_by_id FOREIGN KEY (updated_by_id) REFERENCES users (id) NOT VALID;
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_user_music_connections_user_id' AND conrelid = 'user_music_connections'::regclass) THEN
        ALTER TABLE user_music_connections ADD CONSTRAINT fk_user_music_connections_user_id FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE NOT VALID;
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_user_profiles_user_id' AND conrelid = 'user_profiles'::regclass) THEN
        ALTER TABLE user_profiles ADD CONSTRAINT fk_user_profiles_user_id FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE NOT VALID;
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_work_sessions_user_id' AND conrelid = 'work_sessions'::regclass) THEN
        ALTER TABLE work_sessions ADD CONSTRAINT fk_work_sessions_user_id FOREIGN KEY (user_id) REFERENCES users (id) NOT VALID;
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_youtube_api_usage_api_config_id' AND conrelid = 'youtube_api_usage'::regclass) THEN
        ALTER TABLE youtube_api_usage ADD CONSTRAINT fk_youtube_api_usage_api_config_id FOREIGN KEY (api_config_id) REFERENCES youtube_api_configs (id) ON DELETE SET NULL NOT VALID;
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_collection_events_user_id' AND conrelid = 'collection_events'::regclass) THEN
        ALTER TABLE collection_events ADD CONSTRAINT fk_collection_events_user_id FOREIGN KEY (user_id) REFERENCES users (id) NOT VALID;
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_collection_events_work_session_id' AND conrelid = 'collection_events'::regclass) THEN
        ALTER TABLE collection_events ADD CONSTRAINT fk_collection_events_work_session_id FOREIGN KEY (work_session_id) REFERENCES work_sessions (id) ON DELETE SET NULL NOT VALID;
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_work_session_events_session_id' AND conrelid = 'work_session_events'::regclass) THEN
        ALTER TABLE work_session_events ADD CONSTRAINT fk_work_session_events_session_id FOREIGN KEY (session_id) REFERENCES work_sessions (id) ON DELETE CASCADE NOT VALID;
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_work_session_events_user_id' AND conrelid = 'work_session_events'::regclass) THEN
        ALTER TABLE work_session_events ADD CONSTRAINT fk_work_session_events_user_id FOREIGN KEY (user_id) REFERENCES users (id) NOT VALID;
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_job_channel_status ON qualification_jobs (channel_id, status);
CREATE INDEX IF NOT EXISTS idx_job_status_priority ON qualification_jobs (status, priority, created_at);
CREATE INDEX IF NOT EXISTS ix_qualification_jobs_channel_id ON qualification_jobs (channel_id);
CREATE INDEX IF NOT EXISTS ix_qualification_jobs_id ON qualification_jobs (id);
CREATE INDEX IF NOT EXISTS ix_qualification_jobs_priority ON qualification_jobs (priority);
CREATE INDEX IF NOT EXISTS ix_qualification_jobs_status ON qualification_jobs (status);
CREATE INDEX IF NOT EXISTS idx_queue_state ON qualification_queue_state (paused);
CREATE INDEX IF NOT EXISTS idx_qual_niche ON qualification_results (detected_niche);
CREATE INDEX IF NOT EXISTS idx_qual_qualified_at ON qualification_results (qualified_at);
CREATE INDEX IF NOT EXISTS idx_qual_score ON qualification_results (score);
CREATE INDEX IF NOT EXISTS idx_qual_status ON qualification_results (qualification_status);
CREATE UNIQUE INDEX IF NOT EXISTS ix_qualification_results_channel_id ON qualification_results (channel_id);
CREATE INDEX IF NOT EXISTS ix_qualification_results_detected_niche ON qualification_results (detected_niche);
CREATE INDEX IF NOT EXISTS ix_qualification_results_email ON qualification_results (email);
CREATE INDEX IF NOT EXISTS ix_qualification_results_id ON qualification_results (id);
CREATE INDEX IF NOT EXISTS ix_qualification_results_qualification_status ON qualification_results (qualification_status);
CREATE UNIQUE INDEX IF NOT EXISTS ix_users_email ON users (email);
CREATE INDEX IF NOT EXISTS ix_users_id ON users (id);
CREATE INDEX IF NOT EXISTS idx_vid_channel ON analyzed_videos (channel_id);
CREATE INDEX IF NOT EXISTS idx_vid_video_id ON analyzed_videos (video_id);
CREATE INDEX IF NOT EXISTS ix_analyzed_videos_channel_id ON analyzed_videos (channel_id);
CREATE INDEX IF NOT EXISTS ix_analyzed_videos_id ON analyzed_videos (id);
CREATE INDEX IF NOT EXISTS ix_analyzed_videos_qualification_result_id ON analyzed_videos (qualification_result_id);
CREATE INDEX IF NOT EXISTS ix_audit_logs_actor_user_id ON audit_logs (actor_user_id);
CREATE INDEX IF NOT EXISTS ix_audit_logs_created_at ON audit_logs (created_at);
CREATE INDEX IF NOT EXISTS idx_channel_id ON channels (channel_id);
CREATE INDEX IF NOT EXISTS idx_collected_at ON channels (first_collected_at);
CREATE UNIQUE INDEX IF NOT EXISTS ix_channels_channel_id ON channels (channel_id);
CREATE INDEX IF NOT EXISTS ix_channels_id ON channels (id);
CREATE INDEX IF NOT EXISTS idx_notifications_created ON notifications (created_at);
CREATE INDEX IF NOT EXISTS idx_notifications_read ON notifications (target_user_id, read_at);
CREATE INDEX IF NOT EXISTS idx_notifications_target ON notifications (target_user_id);
CREATE INDEX IF NOT EXISTS ix_notifications_actor_user_id ON notifications (actor_user_id);
CREATE INDEX IF NOT EXISTS ix_notifications_created_at ON notifications (created_at);
CREATE UNIQUE INDEX IF NOT EXISTS ix_notifications_dedupe_key ON notifications (dedupe_key);
CREATE INDEX IF NOT EXISTS ix_notifications_target_user_id ON notifications (target_user_id);
CREATE UNIQUE INDEX IF NOT EXISTS ix_user_music_connections_user_id ON user_music_connections (user_id);
CREATE UNIQUE INDEX IF NOT EXISTS ix_user_profiles_user_id ON user_profiles (user_id);
CREATE INDEX IF NOT EXISTS idx_session_started_at ON work_sessions (started_at);
CREATE INDEX IF NOT EXISTS idx_session_user_status ON work_sessions (user_id, status);
CREATE INDEX IF NOT EXISTS ix_work_sessions_id ON work_sessions (id);
CREATE INDEX IF NOT EXISTS ix_work_sessions_user_id ON work_sessions (user_id);
CREATE INDEX IF NOT EXISTS idx_yt_usage_config ON youtube_api_usage (api_config_id);
CREATE INDEX IF NOT EXISTS idx_yt_usage_requested_at ON youtube_api_usage (requested_at);
CREATE INDEX IF NOT EXISTS ix_youtube_api_usage_api_config_id ON youtube_api_usage (api_config_id);
CREATE INDEX IF NOT EXISTS ix_youtube_api_usage_requested_at ON youtube_api_usage (requested_at);
CREATE INDEX IF NOT EXISTS idx_event_channel_user ON collection_events (channel_id, user_id);
CREATE INDEX IF NOT EXISTS idx_event_created_at ON collection_events (created_at);
CREATE INDEX IF NOT EXISTS idx_event_session ON collection_events (work_session_id);
CREATE INDEX IF NOT EXISTS ix_collection_events_channel_id ON collection_events (channel_id);
CREATE INDEX IF NOT EXISTS ix_collection_events_id ON collection_events (id);
CREATE INDEX IF NOT EXISTS idx_wsevent_created_at ON work_session_events (created_at);
CREATE INDEX IF NOT EXISTS idx_wsevent_session ON work_session_events (session_id);
CREATE INDEX IF NOT EXISTS ix_work_session_events_id ON work_session_events (id);
CREATE INDEX IF NOT EXISTS ix_work_session_events_session_id ON work_session_events (session_id);

COMMIT;
