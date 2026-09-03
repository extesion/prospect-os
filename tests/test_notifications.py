import pytest
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi.testclient import TestClient
from backend.main import app
from backend.database.connection import SessionLocal
from backend.database.models import Notification, WorkSession, WorkSessionEvent, CollectionEvent, Channel

client = TestClient(app)


@pytest.fixture(autouse=True)
def clean_state():
    """Limpa notificacoes, sessoes e canais antes de cada teste de notificacao."""
    db = SessionLocal()
    try:
        db.query(Notification).delete()
        db.query(CollectionEvent).delete()
        db.query(Channel).delete()
        db.query(WorkSessionEvent).delete()
        db.query(WorkSession).delete()
        db.commit()
    finally:
        db.close()
    yield


def _login(email: str) -> str:
    resp = client.post("/auth/login", json={"email": email, "password": "123"})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def _h(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _start(token: str) -> dict:
    resp = client.post("/work-sessions/start", json={
        "daily_target": 160, "target_hours": 8.0, "cycle_type": "8H"
    }, headers=_h(token))
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_list_requires_auth():
    assert client.get("/notifications").status_code == 401


def test_unread_count_requires_auth():
    assert client.get("/notifications/unread-count").status_code == 401


def test_session_started_notifies_others():
    carlos = _login("carlos@prospector.com")
    maria = _login("maria@prospector.com")
    _start(carlos)
    types = [n["type"] for n in client.get("/notifications", headers=_h(maria)).json()]
    assert "SESSION_STARTED" in types


def test_session_started_no_dup_on_retry():
    carlos = _login("carlos@prospector.com")
    maria = _login("maria@prospector.com")
    _start(carlos)
    _start(carlos)  # retry -> mesma sessao
    notifs = [n for n in client.get("/notifications", headers=_h(maria)).json() if n["type"] == "SESSION_STARTED"]
    assert len(notifs) == 1


def test_session_started_actor_not_notified():
    carlos = _login("carlos@prospector.com")
    _start(carlos)

def test_cycle_completed_fires_once():
    carlos = _login("carlos@prospector.com")
    _start(carlos)
    assert client.post("/work-sessions/finish", headers=_h(carlos)).status_code == 200
    notifs = [n for n in client.get("/notifications", headers=_h(carlos)).json() if n["type"] == "CYCLE_COMPLETED"]
    assert len(notifs) == 1


def test_cycle_completed_no_dup_second_finish():
    carlos = _login("carlos@prospector.com")
    _start(carlos)
    client.post("/work-sessions/finish", headers=_h(carlos))
    client.post("/work-sessions/finish", headers=_h(carlos))  # 400, sem sessao ativa
    notifs = [n for n in client.get("/notifications", headers=_h(carlos)).json() if n["type"] == "CYCLE_COMPLETED"]
    assert len(notifs) == 1


def test_user_sees_only_own():
    carlos = _login("carlos@prospector.com")
    maria = _login("maria@prospector.com")
    _start(carlos)
    maria_ids = {n["id"] for n in client.get("/notifications", headers=_h(maria)).json()}
    carlos_ids = {n["id"] for n in client.get("/notifications", headers=_h(carlos)).json()}
    assert maria_ids.isdisjoint(carlos_ids)


def test_unread_count():
    carlos = _login("carlos@prospector.com")
    maria = _login("maria@prospector.com")
    _start(carlos)
    r = client.get("/notifications/unread-count", headers=_h(maria))
    assert r.status_code == 200
    assert r.json()["unread_count"] >= 1


def test_mark_one_as_read():
    carlos = _login("carlos@prospector.com")
    maria = _login("maria@prospector.com")
    _start(carlos)
    notifs = client.get("/notifications", headers=_h(maria)).json()
    nid = notifs[0]["id"]
    resp = client.post(f"/notifications/{nid}/read", headers=_h(maria))
    assert resp.json()["success"] is True
    count_after = client.get("/notifications/unread-count", headers=_h(maria)).json()["unread_count"]
    assert count_after == len(notifs) - 1


def test_mark_all_as_read():
    carlos = _login("carlos@prospector.com")
    joao = _login("joao@prospector.com")
    _start(carlos)
    resp = client.post("/notifications/read-all", headers=_h(joao))
    assert resp.json()["success"] is True
    assert resp.json()["marked_count"] >= 1
    assert client.get("/notifications/unread-count", headers=_h(joao)).json()["unread_count"] == 0


def test_mark_read_ownership():
    """Joao nao pode marcar notif da Maria como lida."""
    carlos = _login("carlos@prospector.com")
    maria = _login("maria@prospector.com")
    joao = _login("joao@prospector.com")
    _start(carlos)
    maria_notifs = client.get("/notifications", headers=_h(maria)).json()
    nid = maria_notifs[0]["id"]
    resp = client.post(f"/notifications/{nid}/read", headers=_h(joao))
    assert resp.json()["success"] is False


def test_deleted_user_no_notification():
    """Usuario deletado nao recebe novas notificacoes."""
    admin = _login("carlos@prospector.com")
    users_resp = client.get("/users", headers=_h(admin))
    ana = next((u for u in users_resp.json() if "ana" in u["email"]), None)
    assert ana is not None
    assert client.delete(f"/users/{ana['id']}", headers=_h(admin)).status_code == 200

    # Carlos inicia sessao apos exclusao de Ana
    _start(admin)

    from backend.database.connection import SessionLocal
    from backend.database.models import Notification
    db = SessionLocal()
    try:
        count = db.query(Notification).filter(
            Notification.target_user_id == ana["id"],
            Notification.type == "SESSION_STARTED"
        ).count()
        assert count == 0
    finally:
        db.close()


def test_goal_reached_fires_once():
    carlos = _login("carlos@prospector.com")
    _start(carlos)
    for i in range(160):
        client.post("/channels", json={
            "channel_id": f"UC_GR_{i}", "channel_name": f"C{i}",
            "channel_url": f"https://youtube.com/channel/UC_GR_{i}"
        }, headers=_h(carlos))
    notifs = [n for n in client.get("/notifications", headers=_h(carlos)).json() if n["type"] == "GOAL_REACHED"]
    assert len(notifs) == 1


def test_goal_reached_no_dup_on_extra():
    carlos = _login("carlos@prospector.com")
    _start(carlos)
    for i in range(165):
        client.post("/channels", json={
            "channel_id": f"UC_EX_{i}", "channel_name": f"C{i}",
            "channel_url": f"https://youtube.com/channel/UC_EX_{i}"
        }, headers=_h(carlos))
    notifs = [n for n in client.get("/notifications", headers=_h(carlos)).json() if n["type"] == "GOAL_REACHED"]
    assert len(notifs) == 1
