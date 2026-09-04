import pytest
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.main import app
from backend.database.connection import Base, get_db
from backend.database.models import User, WorkSession, Channel, CollectionEvent, utc_now
from backend.security.auth import get_password_hash, create_access_token

@pytest.fixture(scope="module")
def client_and_db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    db = TestingSessionLocal()
    # Create operator user
    operator = User(
        name="Carlos Operador",
        email="carlos.local@prospector.com",
        password_hash=get_password_hash("password123"),
        role="USER",
        active=True
    )
    # Create admin user
    admin = User(
        name="Admin User",
        email="admin.local@prospector.com",
        password_hash=get_password_hash("admin123"),
        role="ADMIN",
        active=True
    )
    db.add_all([operator, admin])
    db.commit()
    db.refresh(operator)
    db.refresh(admin)

    operator_token = create_access_token(data={"sub": str(operator.id), "role": operator.role, "user_id": operator.id})
    admin_token = create_access_token(data={"sub": str(admin.id), "role": admin.role, "user_id": admin.id})

    test_client = TestClient(app)

    yield {
        "client": test_client,
        "db": db,
        "operator": operator,
        "admin": admin,
        "operator_headers": {"Authorization": f"Bearer {operator_token}"},
        "admin_headers": {"Authorization": f"Bearer {admin_token}"}
    }

    app.dependency_overrides.clear()


def test_extension_info_endpoint(client_and_db):
    client = client_and_db["client"]
    res = client.get("/api/system/extension-info")
    assert res.status_code == 200
    data = res.json()
    assert "version" in data
    assert data["download_url"] == "/static/prospect-os-extension.zip"
    assert "instructions" in data
    assert len(data["instructions"]) > 0


def test_cannot_collect_channel_without_active_session(client_and_db):
    client = client_and_db["client"]
    headers = client_and_db["operator_headers"]

    # Attempt to collect without starting a session
    payload = {
        "channel_id": "UC_TEST_NO_SESSION_123",
        "channel_name": "Canal Sem Sessao",
        "channel_url": "https://www.youtube.com/channel/UC_TEST_NO_SESSION_123"
    }
    res = client.post("/api/channels", json=payload, headers=headers)
    assert res.status_code == 409
    assert "Inicie seu turno de trabalho" in res.json()["detail"]


def test_start_session_and_pause_resume_calculations(client_and_db):
    client = client_and_db["client"]
    headers = client_and_db["operator_headers"]

    # 1. Start Session
    start_payload = {
        "daily_target": 160,
        "target_hours": 8.0,
        "cycle_type": "8H"
    }
    res = client.post("/api/work-sessions/start", json=start_payload, headers=headers)
    assert res.status_code == 200
    session_data = res.json()
    assert session_data["status"] == "ACTIVE"
    assert session_data["collected_count"] == 0
    assert session_data["daily_target"] == 160
    session_id = session_data["id"]

    # 2. Pause Session
    pause_res = client.post("/api/work-sessions/pause", headers=headers)
    assert pause_res.status_code == 200
    paused_data = pause_res.json()
    assert paused_data["status"] == "PAUSED"

    # 3. Resume Session
    resume_res = client.post("/api/work-sessions/resume", headers=headers)
    assert resume_res.status_code == 200
    resumed_data = resume_res.json()
    assert resumed_data["status"] == "ACTIVE"


def test_consolidated_finish_with_batch_channels_and_dedupe(client_and_db):
    client = client_and_db["client"]
    headers = client_and_db["operator_headers"]
    db = client_and_db["db"]

    # Pre-populate a channel in the DB to test dedupe inside the finish batch
    existing_cid = "UC_ALREADY_IN_DB_999"
    pre_channel = Channel(
        channel_id=existing_cid,
        channel_name="Canal Pre Existente",
        channel_url=f"https://www.youtube.com/channel/{existing_cid}",
        first_collected_by_id=client_and_db["admin"].id,
        first_collected_at=utc_now()
    )
    db.add(pre_channel)
    db.commit()

    # Get current active session and simulate 1 hour elapsed in DB
    curr = client.get("/api/work-sessions/current", headers=headers).json()
    session_id = curr["id"]
    db_session = db.query(WorkSession).filter(WorkSession.id == session_id).first()
    db_session.started_at = utc_now() - timedelta(hours=1, minutes=5)
    db_session.last_resumed_at = utc_now() - timedelta(hours=1)
    db.commit()

    # Prepare finish batch containing 3 new channels and 1 pre-existing duplicate channel
    batch_channels = [
        {
            "channel_id": "UC_BATCH_NEW_001",
            "channel_name": "Canal Batch 1",
            "channel_url": "https://www.youtube.com/channel/UC_BATCH_NEW_001",
            "source": "youtube_search"
        },
        {
            "channel_id": "UC_BATCH_NEW_002",
            "channel_name": "Canal Batch 2",
            "channel_url": "https://www.youtube.com/channel/UC_BATCH_NEW_002",
            "source": "youtube_search"
        },
        {
            "channel_id": "UC_BATCH_NEW_003",
            "channel_name": "Canal Batch 3",
            "channel_url": "https://www.youtube.com/channel/UC_BATCH_NEW_003",
            "source": "youtube_search"
        },
        {
            "channel_id": existing_cid,
            "channel_name": "Canal Duplicado",
            "channel_url": f"https://www.youtube.com/channel/{existing_cid}",
            "source": "youtube_search"
        }
    ]

    finish_payload = {
        "session_id": session_id,
        "active_seconds": 3600, # 1 hour
        "channels": batch_channels
    }

    # Consolidated Finish Call
    res = client.post("/api/work-sessions/finish", json=finish_payload, headers=headers)
    assert res.status_code == 200
    data = res.json()

    assert data["status"] == "FINISHED"
    assert data["inserted_count"] == 3
    assert data["already_exists_count"] == 1
    assert data["collected_count"] == 3
    assert data["active_seconds"] >= 3600


def test_idempotent_retry_of_finish_session(client_and_db):
    client = client_and_db["client"]
    headers = client_and_db["operator_headers"]

    # Retry the exact same finish payload for the session just finished
    finish_payload = {
        "active_seconds": 3600,
        "channels": [
            {
                "channel_id": "UC_BATCH_NEW_001",
                "channel_name": "Canal Batch 1",
                "channel_url": "https://www.youtube.com/channel/UC_BATCH_NEW_001"
            }
        ]
    }

    # Second call must succeed idempotently without raising error or re-inserting duplicates
    res = client.post("/api/work-sessions/finish", json=finish_payload, headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "FINISHED"
    assert data["inserted_count"] == 0


def test_cannot_mutate_finished_session_with_new_channel(client_and_db):
    client = client_and_db["client"]
    headers = client_and_db["operator_headers"]
    db = client_and_db["db"]

    # Attempt to sneak in channel D into an already FINISHED session
    finish_payload = {
        "channels": [
            {
                "channel_id": "UC_BATCH_NEW_001", # Existing
                "channel_name": "Canal Batch 1",
                "channel_url": "https://www.youtube.com/channel/UC_BATCH_NEW_001"
            },
            {
                "channel_id": "UC_BATCH_SNEAK_004", # New channel attempted post-finish
                "channel_name": "Canal Malicioso Post Fim",
                "channel_url": "https://www.youtube.com/channel/UC_BATCH_SNEAK_004"
            }
        ]
    }

    res = client.post("/api/work-sessions/finish", json=finish_payload, headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "FINISHED"
    assert data["inserted_count"] == 0 # Must NOT insert D

    # Verify channel D was never written to DB
    sneak_channel = db.query(Channel).filter(Channel.channel_id == "UC_BATCH_SNEAK_004").first()
    assert sneak_channel is None


def test_active_time_tampering_is_clamped_to_server_wallclock(client_and_db):
    client = client_and_db["client"]
    headers = client_and_db["operator_headers"]
    db = client_and_db["db"]

    # Start a brand new session (only 10 seconds ago)
    start_payload = {"daily_target": 100, "target_hours": 8.0, "cycle_type": "8H"}
    res = client.post("/api/work-sessions/start", json=start_payload, headers=headers)
    assert res.status_code == 200
    session_id = res.json()["id"]

    # Set started_at to exactly 60 seconds ago in DB
    db_session = db.query(WorkSession).filter(WorkSession.id == session_id).first()
    db_session.started_at = utc_now() - timedelta(seconds=60)
    db_session.last_resumed_at = utc_now() - timedelta(seconds=60)
    db.commit()

    # Attempt to spoof 999999999 active seconds
    tampered_payload = {
        "session_id": session_id,
        "active_seconds": 999999999,
        "channels": []
    }
    finish_res = client.post("/api/work-sessions/finish", json=tampered_payload, headers=headers)
    assert finish_res.status_code == 200
    data = finish_res.json()

    # Must be clamped around 60 seconds, NEVER 999999999
    assert data["active_seconds"] <= 70
    assert data["active_seconds"] < 1000


def test_cross_user_session_finish_rejected(client_and_db):
    client = client_and_db["client"]
    op_headers = client_and_db["operator_headers"]
    admin_headers = client_and_db["admin_headers"]

    # Admin starts a session
    res = client.post("/api/work-sessions/start", json={"daily_target": 50, "target_hours": 4.0}, headers=admin_headers)
    assert res.status_code == 200
    admin_session_id = res.json()["id"]

    # Operator attempts to finish Admin's session_id
    tamper_payload = {
        "session_id": admin_session_id,
        "channels": [
            {
                "channel_id": "UC_OP_SPOOF_001",
                "channel_name": "Canal Spoof",
                "channel_url": "https://www.youtube.com/channel/UC_OP_SPOOF_001"
            }
        ]
    }
    op_res = client.post("/api/work-sessions/finish", json=tamper_payload, headers=op_headers)
    assert op_res.status_code == 400
    assert "não pertence ao usuário" in op_res.json()["detail"]


def test_nonexistent_session_id_finish_rejected(client_and_db):
    client = client_and_db["client"]
    op_headers = client_and_db["operator_headers"]

    # Nonexistent session_id
    tamper_payload = {
        "session_id": 99999999,
        "channels": []
    }
    res = client.post("/api/work-sessions/finish", json=tamper_payload, headers=op_headers)
    assert res.status_code == 400
    assert "Sessão não encontrada" in res.json()["detail"]


def test_paused_session_rejects_channels_collected_during_pause(client_and_db):
    client = client_and_db["client"]
    headers = client_and_db["operator_headers"]
    db = client_and_db["db"]

    # Operator starts a session
    client.post("/api/work-sessions/start", json={"daily_target": 80, "target_hours": 6.0}, headers=headers)
    # Operator pauses the session
    client.post("/api/work-sessions/pause", headers=headers)

    # Get the session and set paused_at to 10 minutes ago
    curr = client.get("/api/work-sessions/current", headers=headers).json()
    session_id = curr["id"]
    db_session = db.query(WorkSession).filter(WorkSession.id == session_id).first()
    ten_mins_ago = utc_now() - timedelta(minutes=10)
    db_session.paused_at = ten_mins_ago
    db.commit()

    # Finish while paused, submitting 1 valid channel collected before pause, and 1 invalid channel collected 2 minutes ago (during pause)
    finish_payload = {
        "session_id": session_id,
        "channels": [
            {
                "channel_id": "UC_COLLECTED_BEFORE_PAUSE",
                "channel_name": "Canal Antes da Pausa",
                "channel_url": "https://www.youtube.com/channel/UC_COLLECTED_BEFORE_PAUSE",
                "collected_at": (ten_mins_ago - timedelta(minutes=5)).isoformat()
            },
            {
                "channel_id": "UC_COLLECTED_DURING_PAUSE",
                "channel_name": "Canal Durante Pausa",
                "channel_url": "https://www.youtube.com/channel/UC_COLLECTED_DURING_PAUSE",
                "collected_at": (ten_mins_ago + timedelta(minutes=2)).isoformat()
            }
        ]
    }

    res = client.post("/api/work-sessions/finish", json=finish_payload, headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "FINISHED"
    assert data["inserted_count"] == 1 # Only the one before pause is inserted
    assert any("Canal coletado durante pausa" in err for err in data["errors"])

    # Ensure invalid channel is not in DB
    invalid_ch = db.query(Channel).filter(Channel.channel_id == "UC_COLLECTED_DURING_PAUSE").first()
    assert invalid_ch is None


def test_collection_blocked_after_session_finished(client_and_db):
    client = client_and_db["client"]
    headers = client_and_db["operator_headers"]

    # Since the previous session is FINISHED, direct collect must be rejected
    payload = {
        "channel_id": "UC_AFTER_FINISHED_001",
        "channel_name": "Canal Apos Fim",
        "channel_url": "https://www.youtube.com/channel/UC_AFTER_FINISHED_001"
    }
    res = client.post("/api/channels", json=payload, headers=headers)
    assert res.status_code == 409

