import pytest
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

os.environ["DATABASE_URL"] = "sqlite:///./test_prospect_os.db"
os.environ["SECRET_KEY"] = "test-prospect-os-key-2026"

from fastapi.testclient import TestClient
from backend.main import app
from backend.database.connection import engine, Base
from backend.seed import seed

client = TestClient(app)

@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    seed()
    yield
    Base.metadata.drop_all(bind=engine)
    if os.path.exists("./test_prospect_os.db"):
        try:
            os.remove("./test_prospect_os.db")
        except:
            pass

def test_rbac_matrix_and_protected_routes():
    # Login ADMIN
    admin_res = client.post("/auth/login", json={"email": "carlos@prospector.com", "password": "123"})
    assert admin_res.status_code == 200
    admin_token = admin_res.json()["access_token"]
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    # Login USER
    user_res = client.post("/auth/login", json={"email": "maria@prospector.com", "password": "123"})
    assert user_res.status_code == 200
    user_token = user_res.json()["access_token"]
    user_headers = {"Authorization": f"Bearer {user_token}"}

    # 1. Canais Coletados List: ADMIN -> 200 OK, USER -> 403 Forbidden
    res_ch_admin = client.get("/channels/list", headers=admin_headers)
    assert res_ch_admin.status_code == 200
    assert "channels" in res_ch_admin.json()

    res_ch_user = client.get("/channels/list", headers=user_headers)
    assert res_ch_user.status_code == 403

    # 2. Users Management: ADMIN -> 200 OK, USER -> 403 Forbidden
    res_users_admin = client.get("/users", headers=admin_headers)
    assert res_users_admin.status_code == 200

    res_users_user = client.get("/users", headers=user_headers)
    assert res_users_user.status_code == 403

    # 3. Qualification: ADMIN -> 200 OK, USER -> 403 Forbidden
    res_qual_admin = client.get("/qualification/status-overview", headers=admin_headers)
    assert res_qual_admin.status_code == 200

    res_qual_user = client.get("/qualification/status-overview", headers=user_headers)
    assert res_qual_user.status_code == 403

    # 4. APIs Management: ADMIN -> 200 OK, USER -> 403 Forbidden
    res_apis_admin = client.get("/youtube-apis", headers=admin_headers)
    assert res_apis_admin.status_code == 200

    res_apis_user = client.get("/youtube-apis", headers=user_headers)
    assert res_apis_user.status_code == 403

def test_notifications_lifecycle_and_single_goal_trigger():
    # Login Carlos
    carlos_login = client.post("/auth/login", json={"email": "carlos@prospector.com", "password": "123"})
    carlos_token = carlos_login.json()["access_token"]
    carlos_headers = {"Authorization": f"Bearer {carlos_token}"}

    # 1. Start session -> triggers USER_START_SESSION notification
    start_res = client.post("/work-sessions/start", json={
        "daily_target": 2,
        "target_hours": 8.0,
        "cycle_type": "CUSTOM"
    }, headers=carlos_headers)
    assert start_res.status_code == 200

    # Verify notification created
    notifs = client.get("/notifications", headers=carlos_headers).json()
    assert len(notifs) >= 1
    assert any(n["type"] == "USER_START_SESSION" for n in notifs)

    # 2. Collect channel 1
    ch1 = client.post("/channels", json={
        "channel_id": "UC_TEST_NOTIF_001",
        "channel_name": "Test Notif Channel 1",
        "channel_url": "https://youtube.com/channel/UC_TEST_NOTIF_001"
    }, headers=carlos_headers)
    assert ch1.status_code == 200

    # 3. Collect channel 2 -> Reaches goal (daily_target = 2) -> triggers USER_REACHED_GOAL
    ch2 = client.post("/channels", json={
        "channel_id": "UC_TEST_NOTIF_002",
        "channel_name": "Test Notif Channel 2",
        "channel_url": "https://youtube.com/channel/UC_TEST_NOTIF_002"
    }, headers=carlos_headers)
    assert ch2.status_code == 200

    # 4. Collect channel 3 -> Exceeds goal, MUST NOT create duplicate USER_REACHED_GOAL
    ch3 = client.post("/channels", json={
        "channel_id": "UC_TEST_NOTIF_003",
        "channel_name": "Test Notif Channel 3",
        "channel_url": "https://youtube.com/channel/UC_TEST_NOTIF_003"
    }, headers=carlos_headers)
    assert ch3.status_code == 200

    notifs_after = client.get("/notifications", headers=carlos_headers).json()
    goal_notifs = [n for n in notifs_after if n["type"] == "USER_REACHED_GOAL"]
    assert len(goal_notifs) == 1, "Goal notification must trigger exactly ONCE per cycle"

    # 5. Finish session -> triggers USER_COMPLETE_CYCLE
    finish_res = client.post("/work-sessions/finish", headers=carlos_headers)
    assert finish_res.status_code == 200

    notifs_final = client.get("/notifications", headers=carlos_headers).json()
    cycle_notifs = [n for n in notifs_final if n["type"] == "USER_COMPLETE_CYCLE"]
    assert len(cycle_notifs) >= 1

def test_member_profile_stats_and_averages():
    # Login Carlos
    carlos_login = client.post("/auth/login", json={"email": "carlos@prospector.com", "password": "123"})
    carlos_token = carlos_login.json()["access_token"]
    carlos_headers = {"Authorization": f"Bearer {carlos_token}"}

    # Fetch profile stats
    profile_res = client.get("/profiles/me", headers=carlos_headers)
    assert profile_res.status_code == 200
    stats = profile_res.json()

    assert stats["name"] == "Carlos Silva"
    assert "total_hours_worked" in stats
    assert "total_channels_collected" in stats
    assert "daily_avg_hours" in stats
    assert "daily_avg_channels" in stats
    assert "avg_channels_per_hour" in stats
    assert "chart_7d" in stats
    assert len(stats["chart_7d"]) == 7

def test_music_provider_and_spotify_status():
    carlos_login = client.post("/auth/login", json={"email": "carlos@prospector.com", "password": "123"})
    carlos_token = carlos_login.json()["access_token"]
    carlos_headers = {"Authorization": f"Bearer {carlos_token}"}

    music_res = client.get("/music/status", headers=carlos_headers)
    assert music_res.status_code == 200
    data = music_res.json()

    assert "spotify" in data
    assert "youtube_music" in data
    assert data["youtube_music"]["status"] == "EM_BREVE"
