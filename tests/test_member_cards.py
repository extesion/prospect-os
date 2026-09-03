from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from backend.database.connection import SessionLocal
from backend.database.models import Channel, User, UserMusicConnection, UserProfile, WorkSession, utc_now
from backend.main import app
from backend.security.auth import get_password_hash


client = TestClient(app)


@pytest.fixture
def member_data():
    db = SessionLocal()
    now = utc_now()
    users = [
        User(name="Online Parado", email="card-idle@test.local", password_hash=get_password_hash("123"), role="USER"),
        User(name="Trabalhando", email="card-active@test.local", password_hash=get_password_hash("123"), role="ADMIN"),
        User(name="Pausado", email="card-paused@test.local", password_hash=get_password_hash("123"), role="USER"),
        User(name="Offline", email="card-offline@test.local", password_hash=get_password_hash("123"), role="USER"),
    ]
    users[0].last_seen_at = now
    users[1].last_seen_at = now - timedelta(seconds=91)
    users[2].last_seen_at = now
    users[3].last_seen_at = now - timedelta(seconds=91)
    db.add_all(users); db.flush()
    db.add_all([
        UserProfile(user_id=users[0].id, avatar_url="/static/avatar.png", banner_url="/static/banner.png", updated_at=now),
        UserProfile(user_id=users[1].id, updated_at=now - timedelta(hours=1)),
        UserProfile(user_id=users[2].id, updated_at=now),
        UserProfile(user_id=users[3].id, updated_at=now - timedelta(hours=1)),
    ])
    active = WorkSession(user_id=users[1].id, started_at=now - timedelta(hours=2), last_resumed_at=now,
                         active_seconds=7200, status="ACTIVE", daily_target=100, target_hours=4,
                         target_per_hour=25, collected_count=40)
    paused = WorkSession(user_id=users[2].id, started_at=now, last_resumed_at=now,
                         active_seconds=3600, status="PAUSED", daily_target=100, target_hours=4,
                         target_per_hour=25, collected_count=20)
    finished = WorkSession(user_id=users[1].id, started_at=now - timedelta(days=1), last_resumed_at=now,
                           active_seconds=3600, status="FINISHED", daily_target=1, target_hours=1,
                           target_per_hour=1, collected_count=1, ended_at=now)
    db.add_all([active, paused, finished]); db.flush()
    db.add_all([Channel(channel_id=f"UC_CARD_{i}", channel_name=f"Card {i}",
                        channel_url=f"https://youtube.test/{i}", first_collected_by_id=users[1].id,
                        first_collected_at=now) for i in range(3)])
    db.commit()
    ids = [u.id for u in users]
    yield ids
    db.query(Channel).filter(Channel.first_collected_by_id.in_(ids)).delete(synchronize_session=False)
    db.query(UserMusicConnection).filter(UserMusicConnection.user_id.in_(ids)).delete(synchronize_session=False)
    db.query(WorkSession).filter(WorkSession.user_id.in_(ids)).delete(synchronize_session=False)
    db.query(UserProfile).filter(UserProfile.user_id.in_(ids)).delete(synchronize_session=False)
    db.query(User).filter(User.id.in_(ids)).delete(synchronize_session=False)
    db.commit(); db.close()


def test_member_cards_complete_profile_presence_and_work_states(member_data):
    response = client.get("/work-sessions/team/status")
    assert response.status_code == 200
    cards = {card["user_id"]: card for card in response.json()["members"]}
    idle, active, paused, offline = (cards[user_id] for user_id in member_data)
    assert (idle["avatar_url"], idle["banner_url"], idle["presence"], idle["session_status"]) == (
        "/static/avatar.png", "/static/banner.png", "online", "IDLE")
    assert (active["presence"], active["session_status"]) == ("offline", "ACTIVE")
    assert (paused["presence"], paused["session_status"]) == ("online", "PAUSED")
    assert (offline["presence"], offline["session_status"]) == ("offline", "IDLE")


def test_heartbeat_marks_authenticated_user_online():
    login = client.post("/auth/login", json={"email": "carlos@prospector.com", "password": "123"})
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    assert client.post("/auth/heartbeat", headers=headers).json() == {"status": "ok"}
    user_id = login.json()["user"]["id"]
    cards = {card["user_id"]: card for card in client.get("/work-sessions/team/status").json()["members"]}
    assert cards[user_id]["presence"] == "online"


def test_profile_and_music_updates_do_not_force_online(member_data):
    db = SessionLocal()
    offline_id = member_data[3]
    profile = db.query(UserProfile).filter(UserProfile.user_id == offline_id).one()
    profile.updated_at = utc_now()
    db.add(UserMusicConnection(user_id=offline_id, is_connected=True, is_playing=True,
                               current_track_name="Fresh track", updated_at=utc_now()))
    db.commit(); db.close()
    card = next(card for card in client.get("/work-sessions/team/status").json()["members"]
                if card["user_id"] == offline_id)
    assert card["presence"] == "offline"
    assert card["music_status"] == "Tocando"


def test_member_cards_aggregates_rates_chart_and_fallbacks(member_data):
    cards = {card["user_id"]: card for card in client.get("/work-sessions/team/status").json()["members"]}
    card = cards[member_data[1]]
    assert card["role"] == "ADMIN"
    assert card["current_rate"] == 20.0
    assert card["required_rate"] == 30.0
    assert card["total_hours_worked"] == 3.0
    assert card["channels_today"] == card["total_channels_collected"] == 3
    assert card["completed_cycles_count"] == card["goals_reached_count"] == 1
    assert len(card["chart_7d"]) == 7 and card["chart_7d"][-1]["channels"] == 3
    assert card["now_playing"] is None and card["music_status"] == "Nada tocando"
    numeric = ["hours_today", "hours_this_week", "hours_this_month", "total_hours_worked",
               "channels_today", "channels_this_week", "channels_this_month", "total_channels_collected",
               "daily_avg_hours", "daily_avg_channels", "avg_channels_per_hour"]
    assert all(card[key] is not None for key in numeric)
