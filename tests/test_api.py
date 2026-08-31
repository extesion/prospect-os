import pytest
import os
import sys

# Ensure backend can be imported
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Use temporary SQLite for fast isolated test verification
os.environ["DATABASE_URL"] = "sqlite:///./test_prospector.db"
os.environ["SECRET_KEY"] = "test-secret-key-12345"

from fastapi.testclient import TestClient
from backend.main import app
from backend.database.connection import engine, Base
from backend.seed import seed

client = TestClient(app)

@pytest.fixture(scope="session", autouse=True)
def setup_database():
    # Recreate test db and seed users
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    seed()
    yield
    # Cleanup
    Base.metadata.drop_all(bind=engine)
    if os.path.exists("./test_prospector.db"):
        try:
            os.remove("./test_prospector.db")
        except:
            pass

def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "online"
    assert data["database"] == "connected"

def test_auth_login():
    # Login as Carlos
    response = client.post("/auth/login", json={
        "email": "carlos@prospector.com",
        "password": "123"
    })
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["user"]["name"] == "Carlos Silva"

    token = data["access_token"]
    me_resp = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me_resp.status_code == 200
    assert me_resp.json()["email"] == "carlos@prospector.com"

def test_check_empty_channels():
    # Login
    auth_resp = client.post("/auth/login", json={
        "email": "carlos@prospector.com",
        "password": "123"
    })
    token = auth_resp.json()["access_token"]

    # Check non-existent channels
    check_resp = client.post(
        "/channels/check",
        json={"channel_ids": ["UCtest111", "UCtest222"]},
        headers={"Authorization": f"Bearer {token}"}
    )
    assert check_resp.status_code == 200
    data = check_resp.json()["channels"]
    assert data["UCtest111"]["exists"] is False
    assert data["UCtest222"]["exists"] is False

def test_collect_channel_and_duplicate_prevention():
    # 1. Login Carlos
    carlos_token = client.post("/auth/login", json={
        "email": "carlos@prospector.com",
        "password": "123"
    }).json()["access_token"]

    # 2. Login Maria
    maria_token = client.post("/auth/login", json={
        "email": "maria@prospector.com",
        "password": "123"
    }).json()["access_token"]

    # 3. Carlos collects channel UC999AAA
    collect_resp = client.post(
        "/channels",
        json={
            "channel_id": "UC999AAA",
            "channel_name": "Canal de Teste Marketing",
            "channel_handle": "@marketingxyz",
            "channel_url": "https://www.youtube.com/@marketingxyz",
            "source": "youtube_search",
            "search_term": "marketing digital"
        },
        headers={"Authorization": f"Bearer {carlos_token}"}
    )
    assert collect_resp.status_code == 200
    assert collect_resp.json()["success"] is True
    assert collect_resp.json()["already_exists"] is False
    assert collect_resp.json()["channel"]["first_collected_by"]["name"] == "Carlos Silva"

    # 4. Maria tries to collect the exact same channel UC999AAA (concurrency test)
    duplicate_resp = client.post(
        "/channels",
        json={
            "channel_id": "UC999AAA",
            "channel_name": "Canal de Teste Marketing",
            "channel_handle": "@marketingxyz",
            "channel_url": "https://www.youtube.com/@marketingxyz",
            "source": "youtube_search",
            "search_term": "marketing digital"
        },
        headers={"Authorization": f"Bearer {maria_token}"}
    )
    assert duplicate_resp.status_code == 200
    dup_data = duplicate_resp.json()
    assert dup_data["success"] is False
    assert dup_data["already_exists"] is True
    assert "Carlos Silva" in dup_data["message"]

    # 5. Check bulk status
    check_resp = client.post(
        "/channels/check",
        json={"channel_ids": ["UC999AAA", "UCnaoexiste"]},
        headers={"Authorization": f"Bearer {maria_token}"}
    )
    channels_status = check_resp.json()["channels"]
    assert channels_status["UC999AAA"]["exists"] is True
    assert channels_status["UC999AAA"]["collected_by"]["name"] == "Carlos Silva"
    assert channels_status["UCnaoexiste"]["exists"] is False

def test_bulk_collect():
    carlos_token = client.post("/auth/login", json={
        "email": "carlos@prospector.com",
        "password": "123"
    }).json()["access_token"]

    bulk_data = {
        "channels": [
            {
                "channel_id": "UC_BULK_1",
                "channel_name": "Canal Bulk 1",
                "channel_url": "https://www.youtube.com/channel/UC_BULK_1"
            },
            {
                "channel_id": "UC_BULK_2",
                "channel_name": "Canal Bulk 2",
                "channel_url": "https://www.youtube.com/channel/UC_BULK_2"
            },
            {
                "channel_id": "UC999AAA", # Already exists from previous test
                "channel_name": "Canal Já Existente",
                "channel_url": "https://www.youtube.com/@marketingxyz"
            }
        ]
    }

    bulk_resp = client.post(
        "/channels/bulk",
        json=bulk_data,
        headers={"Authorization": f"Bearer {carlos_token}"}
    )
    assert bulk_resp.status_code == 200
    res = bulk_resp.json()
    assert "UC_BULK_1" in res["inserted"]
    assert "UC_BULK_2" in res["inserted"]
    assert "UC999AAA" in res["already_exists"]
    assert len(res["errors"]) == 0

def test_stats():
    carlos_token = client.post("/auth/login", json={
        "email": "carlos@prospector.com",
        "password": "123"
    }).json()["access_token"]

    # My stats
    my_stats = client.get("/stats/me", headers={"Authorization": f"Bearer {carlos_token}"}).json()
    assert my_stats["today_count"] >= 3 # UC999AAA, UC_BULK_1, UC_BULK_2
    assert my_stats["user_name"] == "Carlos Silva"

    # Team stats
    team_stats = client.get("/stats/team", headers={"Authorization": f"Bearer {carlos_token}"}).json()
    assert team_stats["today_count"] >= 3
    assert team_stats["active_users_today"] >= 1
