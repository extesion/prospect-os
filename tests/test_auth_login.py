from unittest.mock import Mock, patch

from fastapi.testclient import TestClient

from backend.database.connection import SessionLocal
from backend.database.models import User
from backend.main import app
from backend.security.auth import AuthService


client = TestClient(app)


def login(email: str, password: str):
    return client.post("/auth/login", json={"email": email, "password": password})


def set_user_state(email: str, *, active: bool = True, is_deleted: bool = False):
    with SessionLocal() as db:
        user = db.query(User).filter(User.email == email).one()
        user.active = active
        user.is_deleted = is_deleted
        db.commit()


def test_login_valid_user_returns_token_and_user():
    response = login("carlos@prospector.com", "123")

    assert response.status_code == 200
    data = response.json()
    assert data["access_token"]
    assert data["token_type"] == "bearer"
    assert data["user"]["email"] == "carlos@prospector.com"
    assert data["user"]["active"] is True


def test_login_nonexistent_user_returns_401_never_500():
    response = login("missing@prospector.com", "123")

    assert response.status_code == 401


def test_login_wrong_password_returns_401_never_500():
    response = login("carlos@prospector.com", "wrong-password")

    assert response.status_code == 401


def test_login_inactive_user_returns_403_never_500():
    set_user_state("carlos@prospector.com", active=False)

    response = login("carlos@prospector.com", "123")

    assert response.status_code == 403


def test_login_deleted_user_returns_401_never_500():
    set_user_state("carlos@prospector.com", is_deleted=True)

    response = login("carlos@prospector.com", "123")

    assert response.status_code == 401


def test_authenticate_does_not_read_password_hash_when_user_is_none():
    db = Mock()
    db.query.return_value.filter.return_value.first.return_value = None

    with patch("backend.security.auth.verify_password") as verify_password:
        assert AuthService.authenticate(db, "missing@prospector.com", "123") is None

    verify_password.assert_not_called()
