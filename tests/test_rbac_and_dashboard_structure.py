import pytest
import os
import sys

# Ensure backend can be imported
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient
from datetime import datetime, timezone

TEST_DB_FILE = "./test_rbac_isolated.db"
if os.path.exists(TEST_DB_FILE):
    try:
        os.remove(TEST_DB_FILE)
    except:
        pass

test_engine = create_engine(f"sqlite:///{TEST_DB_FILE}", connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

from backend.database.models import Base, User, Channel, WorkSession, UserProfile, CollectionEvent, WorkSessionEvent
from backend.database.connection import get_db
from backend.main import app
from backend.security.auth import get_password_hash, create_access_token

def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db

client = TestClient(app)

@pytest.fixture(autouse=True)
def setup_and_clean_db():
    Base.metadata.create_all(bind=test_engine)
    db = TestingSessionLocal()
    db.query(WorkSessionEvent).delete()
    db.query(CollectionEvent).delete()
    db.query(Channel).delete()
    db.query(WorkSession).delete()
    db.query(UserProfile).delete()
    db.query(User).delete()
    db.commit()
    db.close()
    yield
    db = TestingSessionLocal()
    db.query(WorkSessionEvent).delete()
    db.query(CollectionEvent).delete()
    db.query(Channel).delete()
    db.query(WorkSession).delete()
    db.query(UserProfile).delete()
    db.query(User).delete()
    db.commit()
    db.close()

def create_test_user(email: str, name: str, role: str = "USER", password: str = "pass123", is_admin: bool = False, active: bool = True):
    db = TestingSessionLocal()
    user = User(
        email=email.lower().strip(),
        name=name,
        password_hash=get_password_hash(password),
        role=role.upper(),
        active=active,
        is_deleted=False
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    db.close()
    return user

def get_auth_headers(user: User):
    token = create_access_token(
        data={"sub": str(user.id), "email": user.email, "name": user.name, "role": user.role or "USER"}
    )
    return {"Authorization": f"Bearer {token}"}

def test_rbac_user_forbidden_endpoints():
    admin = create_test_user("admin1@test.com", "Admin 1", role="ADMIN")
    user = create_test_user("user1@test.com", "User 1", role="USER")
    user_headers = get_auth_headers(user)

    # 1. /work-sessions/history
    res = client.get("/api/work-sessions/history", headers=user_headers)
    assert res.status_code == 403

    # 2. /work-sessions/settings (PUT)
    res = client.put("/api/work-sessions/settings", json={"default_daily_target": 200}, headers=user_headers)
    assert res.status_code == 403

    # 3. /users (GET)
    res = client.get("/api/users", headers=user_headers)
    assert res.status_code == 403

    # 4. /channels/list
    res = client.get("/api/channels/list", headers=user_headers)
    assert res.status_code == 403

    # 5. /admin/system/reset
    res = client.post("/api/admin/system/reset", json={"system_password": "883800", "confirmation": "RESETAR"}, headers=user_headers)
    assert res.status_code == 403

def test_rbac_user_allowed_endpoints():
    user = create_test_user("user2@test.com", "User 2", role="USER")
    user_headers = get_auth_headers(user)

    # Overview & Team status
    res = client.get("/api/work-sessions/team/status", headers=user_headers)
    assert res.status_code == 200

    # Ranking
    res = client.get("/api/work-sessions/ranking?period=today", headers=user_headers)
    assert res.status_code == 200

    # Profile me
    res = client.get("/api/auth/me", headers=user_headers)
    assert res.status_code == 200
    assert res.json()["email"] == "user2@test.com"

def test_admin_promotion_requires_system_password():
    admin = create_test_user("admin_chief@test.com", "Admin Chief", role="ADMIN")
    admin_headers = get_auth_headers(admin)

    # 1. Create ADMIN without system password -> 403
    res = client.post("/api/users", json={
        "name": "New Admin",
        "email": "newadmin@test.com",
        "password": "123",
        "role": "ADMIN",
        "active": True
    }, headers=admin_headers)
    assert res.status_code == 403
    assert "Senha do sistema" in res.json()["detail"]

    # 2. Create ADMIN with wrong system password -> 403
    res = client.post("/api/users", json={
        "name": "New Admin",
        "email": "newadmin@test.com",
        "password": "123",
        "role": "ADMIN",
        "active": True,
        "system_password": "wrongpassword"
    }, headers=admin_headers)
    assert res.status_code == 403

    # 3. Create ADMIN with correct system password (883800) -> 201
    res = client.post("/api/users", json={
        "name": "New Admin",
        "email": "newadmin@test.com",
        "password": "123",
        "role": "ADMIN",
        "active": True,
        "system_password": "883800"
    }, headers=admin_headers)
    assert res.status_code == 201
    assert res.json()["role"] == "ADMIN"

    # 4. Promote USER to ADMIN with correct system password -> 200
    normal_user = create_test_user("regular@test.com", "Regular User", role="USER")
    res = client.put(f"/api/users/{normal_user.id}", json={
        "role": "ADMIN",
        "system_password": "883800"
    }, headers=admin_headers)
    assert res.status_code == 200
    assert res.json()["role"] == "ADMIN"

def test_last_admin_protection():
    admin = create_test_user("sole_admin@test.com", "Sole Admin", role="ADMIN")
    admin_headers = get_auth_headers(admin)

    # 1. Attempt to demote sole admin to USER -> 400
    res = client.put(f"/api/users/{admin.id}", json={"role": "USER"}, headers=admin_headers)
    assert res.status_code == 400
    assert "pelo menos um administrador" in res.json()["detail"]

    # 2. Attempt to deactivate sole admin -> 400
    res = client.put(f"/api/users/{admin.id}", json={"active": False}, headers=admin_headers)
    assert res.status_code == 400
    assert "pelo menos um administrador" in res.json()["detail"]

    # 3. Attempt to delete sole admin -> 400
    res = client.delete(f"/api/users/{admin.id}", headers=admin_headers)
    assert res.status_code == 400
    assert "pelo menos um administrador" in res.json()["detail"]

def test_soft_delete_and_exclusion_from_ranking_and_overview():
    admin = create_test_user("admin_del@test.com", "Admin Del", role="ADMIN")
    target_user = create_test_user("delete_me@test.com", "Delete Me", role="USER")
    admin_headers = get_auth_headers(admin)

    # Add work session for target_user
    db = TestingSessionLocal()
    session = WorkSession(
        user_id=target_user.id,
        status="ACTIVE",
        cycle_type="8h",
        daily_target=160,
        target_hours=8.0,
        target_per_hour=20.0,
        active_seconds=3600,
        collected_count=50,
        started_at=datetime.now(timezone.utc)
    )
    db.add(session)
    db.commit()
    db.close()

    # Verify user appears in team status before deletion
    res = client.get("/api/work-sessions/team/status", headers=admin_headers)
    members_before = [m["user_id"] for m in res.json()["members"]]
    assert target_user.id in members_before

    # Delete target_user
    res = client.delete(f"/api/users/{target_user.id}", headers=admin_headers)
    assert res.status_code == 200

    # Verify target_user is excluded from user list
    res = client.get("/api/users", headers=admin_headers)
    user_ids = [u["id"] for u in res.json()]
    assert target_user.id not in user_ids

    # Verify target_user is excluded from live status
    res = client.get("/api/work-sessions/team/status", headers=admin_headers)
    members_after = [m["user_id"] for m in res.json()["members"]]
    assert target_user.id not in members_after

    # Verify target_user is excluded from ranking
    res = client.get("/api/work-sessions/ranking?period=today", headers=admin_headers)
    ranking_ids = [r["user_id"] for r in res.json()]
    assert target_user.id not in ranking_ids

    # Verify deleted user cannot login
    res = client.post("/api/auth/login", json={"email": "delete_me@test.com", "password": "pass123"})
    assert res.status_code == 401

def test_system_reset_flow():
    admin = create_test_user("admin_reset@test.com", "Admin Reset", role="ADMIN")
    user = create_test_user("user_keep@test.com", "User Keep", role="USER")
    admin_headers = get_auth_headers(admin)

    # Insert operational data (channels, sessions)
    db = TestingSessionLocal()
    ch = Channel(
        channel_id="UC_TEST_123",
        channel_name="Test Channel",
        channel_url="https://youtube.com/test",
        source="EXTENSION",
        first_collected_by_id=user.id,
        first_collected_at=datetime.now(timezone.utc)
    )
    db.add(ch)
    sess = WorkSession(
        user_id=user.id,
        status="FINISHED",
        cycle_type="8h",
        daily_target=160,
        target_hours=8.0,
        target_per_hour=20.0,
        active_seconds=7200,
        collected_count=20,
        started_at=datetime.now(timezone.utc)
    )
    db.add(sess)
    db.commit()
    db.close()

    # Reset with wrong password -> 403
    res = client.post("/api/admin/system/reset", json={
        "system_password": "wrong",
        "confirmation": "RESETAR"
    }, headers=admin_headers)
    assert res.status_code == 403

    # Reset with wrong confirmation text -> 400
    res = client.post("/api/admin/system/reset", json={
        "system_password": "883800",
        "confirmation": "resetar"
    }, headers=admin_headers)
    assert res.status_code == 400

    # Successful reset with correct password and confirmation
    res = client.post("/api/admin/system/reset", json={
        "system_password": "883800",
        "confirmation": "RESETAR"
    }, headers=admin_headers)
    assert res.status_code == 200
    assert res.json()["success"] is True

    # Verify operational tables are empty
    db = TestingSessionLocal()
    assert db.query(Channel).count() == 0
    assert db.query(WorkSession).count() == 0

    # Verify users are preserved
    assert db.query(User).filter(User.email == "admin_reset@test.com").count() == 1
    assert db.query(User).filter(User.email == "user_keep@test.com").count() == 1
    db.close()
