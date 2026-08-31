import pytest
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

os.environ["DATABASE_URL"] = "sqlite:///./test_work_sessions.db"
os.environ["SECRET_KEY"] = "test-secret-key-12345"

from fastapi.testclient import TestClient
from backend.main import app
from backend.database.connection import engine, Base
from backend.seed import seed

client = TestClient(app)

@pytest.fixture(scope="session", autouse=True)
def setup_database():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    seed()
    yield
    Base.metadata.drop_all(bind=engine)
    if os.path.exists("./test_work_sessions.db"):
        try:
            os.remove("./test_work_sessions.db")
        except:
            pass

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
