from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from backend.database.connection import SessionLocal, get_db
from backend.database.models import User
from backend.main import app
from backend.security.auth import create_access_token, get_current_user


client = TestClient(app)
EMAIL = "carlos@prospector.com"


def token_for(user_id: int) -> str:
    return create_access_token({"sub": str(user_id)})


def seeded_user():
    with SessionLocal() as db:
        user = db.query(User).filter(User.email == EMAIL).one()
        return user.id, user.last_seen_at


def post(token: str):
    return client.post("/auth/heartbeat", headers={"Authorization": f"Bearer {token}"})


def test_active_authenticated_user_returns_200_and_updates_last_seen_at():
    user_id, previous = seeded_user()

    response = post(token_for(user_id))

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    with SessionLocal() as db:
        current = db.get(User, user_id).last_seen_at
        assert current is not None
        assert previous is None or current > previous


@pytest.mark.parametrize("state", ["missing", "deleted", "inactive"])
def test_unavailable_user_returns_401(state):
    user_id, _ = seeded_user()
    if state == "missing":
        assert post(token_for(999999999)).status_code == 401
        return

    with SessionLocal() as db:
        user = db.get(User, user_id)
        user.is_deleted = state == "deleted"
        user.active = state != "inactive"
        db.commit()
    try:
        assert post(token_for(user_id)).status_code == 401
    finally:
        with SessionLocal() as db:
            user = db.get(User, user_id)
            user.is_deleted = False
            user.active = True
            db.commit()


def test_sql_error_rolls_back_and_returns_sanitized_response():
    db = Mock()
    db.commit.side_effect = RuntimeError("database detail must stay server-side")
    user = Mock(id=123, last_seen_at=None)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user
    try:
        response = client.post("/auth/heartbeat")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 500
    assert response.json() == {"detail": "Erro interno ao registrar presença."}
    assert "database detail" not in response.text
    db.rollback.assert_called_once_with()


# Successful query and update against metadata-created schema prove all mapped columns exist.
def test_heartbeat_works_with_compatible_schema():
    user_id, _ = seeded_user()
    assert post(token_for(user_id)).status_code == 200
