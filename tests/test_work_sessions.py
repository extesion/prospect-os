import pytest
import os
import sys
from unittest.mock import patch
from sqlalchemy.exc import OperationalError

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

os.environ["DATABASE_URL"] = "sqlite:///./test_work_sessions.db"
os.environ["SECRET_KEY"] = "test-secret-key-12345"
try:
    os.remove("test_work_sessions.db")
except FileNotFoundError:
    pass

from fastapi.testclient import TestClient
from backend.main import app
from backend.database.connection import engine, Base, SessionLocal
from backend.database.models import Channel, CollectionEvent, Notification, WorkSession, WorkSessionEvent
from backend.seed import seed

client = TestClient(app)

@pytest.fixture(autouse=True)
def setup_database():
    Base.metadata.create_all(bind=engine)
    seed()
    db = SessionLocal()
    try:
        db.query(CollectionEvent).delete()
        db.query(WorkSessionEvent).delete()
        db.query(Notification).delete()
        db.query(WorkSession).delete()
        db.query(Channel).delete()
        db.commit()
    finally:
        db.close()
    yield

def test_start_rolls_back_after_first_sql_failure():
    token = client.post("/auth/login", json={"email": "carlos@prospector.com", "password": "123"}).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    with patch("backend.services.notification_service.NotificationService.notify_session_started") as notify:
        notify.side_effect = OperationalError("INSERT INTO notifications", {}, Exception("missing column"))
        failed = client.post("/work-sessions/start", json={"daily_target": 160, "target_hours": 8, "cycle_type": "8H"}, headers=headers)

    assert failed.status_code == 500
    assert failed.json()["detail"] == "Não foi possível iniciar a sessão de trabalho."
    db = SessionLocal()
    try:
        assert db.query(WorkSession).count() == 0
        assert db.query(WorkSessionEvent).count() == 0
    finally:
        db.close()

    # Session fornecida por get_db ficou reutilizável após rollback.
    recovered = client.post("/work-sessions/start", json={"daily_target": 160, "target_hours": 8, "cycle_type": "8H"}, headers=headers)
    assert recovered.status_code == 200


def test_new_session_ignores_historical_channels():
    token = client.post("/auth/login", json={"email": "ana@prospector.com", "password": "123"}).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    from backend.database.connection import SessionLocal
    from backend.database.models import Channel, User, utc_now
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == "ana@prospector.com").one()
        for i in range(5):
            db.add(Channel(channel_id=f"UC_HIST_{i}", channel_name=f"Histórico {i}",
                channel_url=f"https://youtube.com/channel/UC_HIST_{i}",
                first_collected_by_id=user.id, first_collected_at=utc_now()))
        db.commit()
    finally:
        db.close()

    started = client.post("/work-sessions/start", json={"daily_target": 160, "target_hours": 8.0, "cycle_type": "8H"}, headers=headers)
    assert started.status_code == 200
    assert started.json()["collected_count"] == 0

    new_channel = {"channel_id": "UC_NEW_IN_SESSION", "channel_name": "Novo", "channel_url": "https://youtube.com/channel/UC_NEW_IN_SESSION"}
    assert client.post("/channels", json=new_channel, headers=headers).json()["success"] is True
    assert client.get("/work-sessions/current", headers=headers).json()["collected_count"] == 1


def test_start_8h_session():
    carlos_token = client.post("/auth/login", json={
        "email": "carlos@prospector.com",
        "password": "123"
    }).json()["access_token"]

    resp = client.post("/work-sessions/start", json={
        "daily_target": 160,
        "target_hours": 8.0,
        "cycle_type": "8H"
    }, headers={"Authorization": f"Bearer {carlos_token}"})

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ACTIVE"
    assert data["daily_target"] == 160
    assert data["target_hours"] == 8.0
    assert data["target_per_hour"] == 20.0
    assert data["target_per_hour_display"] == 20.0
    assert data["collected_count"] == 0

def test_start_6h_session_math():
    maria_token = client.post("/auth/login", json={
        "email": "maria@prospector.com",
        "password": "123"
    }).json()["access_token"]

    resp = client.post("/work-sessions/start", json={
        "daily_target": 160,
        "target_hours": 6.0,
        "cycle_type": "6H"
    }, headers={"Authorization": f"Bearer {maria_token}"})

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ACTIVE"
    # Mathematical exact check: 160 / 6 = 26.666666666666668
    assert abs(data["target_per_hour"] - (160 / 6)) < 0.001
    assert data["target_per_hour_display"] == 26.7

def test_single_active_session_enforcement():
    carlos_token = client.post("/auth/login", json={
        "email": "carlos@prospector.com",
        "password": "123"
    }).json()["access_token"]

    started = client.post("/work-sessions/start", json={
        "daily_target": 160,
        "target_hours": 8.0,
        "cycle_type": "8H"
    }, headers={"Authorization": f"Bearer {carlos_token}"})
    assert started.status_code == 200

    # Try starting another session while one is active
    resp = client.post("/work-sessions/start", json={
        "daily_target": 200,
        "target_hours": 10.0,
        "cycle_type": "CUSTOM"
    }, headers={"Authorization": f"Bearer {carlos_token}"})

    assert resp.status_code == 200
    # Should return existing session (160 target)
    assert resp.json()["daily_target"] == 160

def test_pause_and_resume_session():
    carlos_token = client.post("/auth/login", json={
        "email": "carlos@prospector.com",
        "password": "123"
    }).json()["access_token"]

    started = client.post("/work-sessions/start", json={
        "daily_target": 160,
        "target_hours": 8.0,
        "cycle_type": "8H"
    }, headers={"Authorization": f"Bearer {carlos_token}"})
    assert started.status_code == 200

    # Pause
    pause_resp = client.post("/work-sessions/pause", headers={"Authorization": f"Bearer {carlos_token}"})
    assert pause_resp.status_code == 200
    assert pause_resp.json()["status"] == "PAUSED"

    # Current session check
    cur_resp = client.get("/work-sessions/current", headers={"Authorization": f"Bearer {carlos_token}"})
    assert cur_resp.status_code == 200
    assert cur_resp.json()["status"] == "PAUSED"

    # Resume
    resume_resp = client.post("/work-sessions/resume", headers={"Authorization": f"Bearer {carlos_token}"})
    assert resume_resp.status_code == 200
    assert resume_resp.json()["status"] == "ACTIVE"

def test_channel_collection_increments_session():
    carlos_token = client.post("/auth/login", json={
        "email": "carlos@prospector.com",
        "password": "123"
    }).json()["access_token"]

    # ACTIVE session is required
    start_resp = client.post("/work-sessions/start", json={"daily_target": 1, "target_hours": 8.0, "cycle_type": "8H"}, headers={"Authorization": f"Bearer {carlos_token}"})
    assert start_resp.status_code == 200
    assert start_resp.json()["status"] == "ACTIVE"

    # Collect a new channel
    collect_resp = client.post("/channels", json={
        "channel_id": "UC_SESSION_TEST_1",
        "channel_name": "Canal Sessao 1",
        "channel_url": "https://youtube.com/channel/UC_SESSION_TEST_1"
    }, headers={"Authorization": f"Bearer {carlos_token}"})
    assert collect_resp.status_code == 200
    assert collect_resp.json()["success"] is True

    # Check work session collected_count
    cur_resp = client.get("/work-sessions/current", headers={"Authorization": f"Bearer {carlos_token}"})
    assert cur_resp.json()["collected_count"] == 1

    # Try duplicate channel -> Should NOT increment
    dup_resp = client.post("/channels", json={
        "channel_id": "UC_SESSION_TEST_1",
        "channel_name": "Canal Sessao 1",
        "channel_url": "https://youtube.com/channel/UC_SESSION_TEST_1"
    }, headers={"Authorization": f"Bearer {carlos_token}"})
    assert dup_resp.json()["already_exists"] is True

    cur_resp2 = client.get("/work-sessions/current", headers={"Authorization": f"Bearer {carlos_token}"})
    assert cur_resp2.json()["collected_count"] == 1 # Still 1

def test_collection_rejected_without_active_session():
    token = client.post("/auth/login", json={"email": "maria@prospector.com", "password": "123"}).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    payload = {"channel_id": "UC_BLOCKED", "channel_name": "Blocked", "channel_url": "https://youtube.com/channel/UC_BLOCKED"}

    rejected = client.post("/channels", json=payload, headers=headers)
    assert rejected.status_code == 409
    assert rejected.json()["detail"] == "Inicie seu turno de trabalho para coletar canais."

    # Exact extension start payload is valid and permits only ACTIVE collection.
    started = client.post("/work-sessions/start", json={"daily_target": 160, "target_hours": 8.0, "cycle_type": "8H"}, headers=headers)
    assert started.status_code == 200
    assert started.json()["status"] == "ACTIVE"
    assert client.post("/work-sessions/pause", headers=headers).status_code == 200
    assert client.post("/channels/bulk", json={"channels": [payload]}, headers=headers).status_code == 409


def test_hours_ranking_strictly_by_active_hours():
    # Ranking endpoint
    ranking_resp = client.get("/work-sessions/ranking?period=today")
    assert ranking_resp.status_code == 200
    ranking = ranking_resp.json()
    assert len(ranking) >= 2

    # Check ordering: ranking[0].total_active_seconds >= ranking[1].total_active_seconds
    for i in range(len(ranking) - 1):
        assert ranking[i]["total_active_seconds"] >= ranking[i+1]["total_active_seconds"]
        assert ranking[i]["rank_position"] == i + 1

def test_team_live_status():
    team_resp = client.get("/work-sessions/team/status")
    assert team_resp.status_code == 200
    data = team_resp.json()
    assert "users_working_count" in data
    assert "formatted_total_hours_today" in data
    assert "members" in data
    assert len(data["members"]) >= 4

def test_finish_session():
    carlos_token = client.post("/auth/login", json={
        "email": "carlos@prospector.com",
        "password": "123"
    }).json()["access_token"]

    started = client.post("/work-sessions/start", json={
        "daily_target": 160,
        "target_hours": 8.0,
        "cycle_type": "8H"
    }, headers={"Authorization": f"Bearer {carlos_token}"})
    assert started.status_code == 200

    finish_resp = client.post("/work-sessions/finish", headers={"Authorization": f"Bearer {carlos_token}"})
    assert finish_resp.status_code == 200
    assert finish_resp.json()["status"] == "FINISHED"

    # Current should now be None
    cur_resp = client.get("/work-sessions/current", headers={"Authorization": f"Bearer {carlos_token}"})
    assert cur_resp.json() is None

def test_cycle_settings():
    settings_resp = client.get("/work-sessions/settings")
    assert settings_resp.status_code == 200
    data = settings_resp.json()
    assert data["default_daily_target"] == 160
    assert len(data["presets"]) >= 3
