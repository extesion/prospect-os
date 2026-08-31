import pytest
import os
import sys

# Ensure backend and qualifier can be imported
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi.testclient import TestClient
from backend.main import app
from backend.database.connection import SessionLocal
from backend.database.models import User, YouTubeApiConfig, YouTubeApiUsage
from qualifier.services.youtube_api_manager import YouTubeApiManager
from qualifier.services.keyword_analyzer import KeywordAnalyzer

client = TestClient(app)

def test_rbac_admin_vs_user_protection():
    # 1. Login as USER (maria@prospector.com)
    user_login = client.post("/api/auth/login", json={"email": "maria@prospector.com", "password": "123"})
    assert user_login.status_code == 200
    user_token = user_login.json()["access_token"]
    user_headers = {"Authorization": f"Bearer {user_token}"}

    # 2. Login as ADMIN (carlos@prospector.com)
    admin_login = client.post("/api/auth/login", json={"email": "carlos@prospector.com", "password": "123"})
    assert admin_login.status_code == 200
    admin_token = admin_login.json()["access_token"]
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    # 3. USER tries to access Admin routes -> 403 FORBIDDEN
    res_users = client.get("/api/users", headers=user_headers)
    assert res_users.status_code == 403

    res_apis = client.get("/api/youtube-apis", headers=user_headers)
    assert res_apis.status_code == 403

    # 4. ADMIN accesses Admin routes -> 200 OK
    admin_users_res = client.get("/api/users", headers=admin_headers)
    assert admin_users_res.status_code == 200
    assert len(admin_users_res.json()) >= 4

    # 5. ADMIN creates new user
    create_user_res = client.post(
        "/api/users",
        json={
            "name": "Novo Operador Teste",
            "email": "operador.novo@prospector.com",
            "password": "senha_segura_123",
            "role": "USER",
            "active": True
        },
        headers=admin_headers
    )
    assert create_user_res.status_code == 201
    new_user_data = create_user_res.json()
    assert new_user_data["email"] == "operador.novo@prospector.com"
    assert new_user_data["role"] == "USER"

    # 6. ADMIN edits user (redefining password & role)
    uid = new_user_data["id"]
    edit_res = client.put(
        f"/api/users/{uid}",
        json={"name": "Operador Promovido", "role": "ADMIN", "password": "nova_senha_456"},
        headers=admin_headers
    )
    assert edit_res.status_code == 200
    assert edit_res.json()["name"] == "Operador Promovido"
    assert edit_res.json()["role"] == "ADMIN"

def test_youtube_api_manager_and_endpoints():
    admin_login = client.post("/api/auth/login", json={"email": "carlos@prospector.com", "password": "123"})
    admin_headers = {"Authorization": f"Bearer {admin_login.json()['access_token']}"}

    # 1. Create new YouTube API config
    create_api_res = client.post(
        "/api/youtube-apis",
        json={
            "name": "Projeto Alpha Secundário",
            "api_key": "AIzaSyTestKeyForMultiAccountManagement999",
            "daily_limit": 10000,
            "status": "ACTIVE"
        },
        headers=admin_headers
    )
    assert create_api_res.status_code == 201
    cfg_data = create_api_res.json()
    assert cfg_data["name"] == "Projeto Alpha Secundário"
    # Never reveal raw key
    assert "AIzaSyTestKeyForMultiAccountManagement999" not in cfg_data["masked_key"]
    assert cfg_data["masked_key"].startswith("AIza")

    config_id = cfg_data["id"]

    # 2. Get Overview summary
    overview_res = client.get("/api/youtube-apis", headers=admin_headers)
    assert overview_res.status_code == 200
    ov_data = overview_res.json()
    assert "summary" in ov_data
    assert "apis" in ov_data
    assert ov_data["summary"]["active_apis"] >= 1

    # 3. Test Quota tracking recording
    db = SessionLocal()
    YouTubeApiManager.record_usage(db, config_id, "channels.list", units=1, success=True)
    YouTubeApiManager.record_usage(db, config_id, "videos.list", units=1, success=True)
    usage = YouTubeApiManager.get_today_usage_for_config(db, config_id)
    assert usage == 2
    db.close()

    # 4. Edit API config
    edit_api_res = client.put(
        f"/api/youtube-apis/{config_id}",
        json={"daily_limit": 5000, "status": "ACTIVE"},
        headers=admin_headers
    )
    assert edit_api_res.status_code == 200
    assert edit_api_res.json()["daily_limit"] == 5000

def test_keyword_analyzer_sources_prioritization():
    texts = [
        {"text": "Acesse nossa consultoria e mentorias de negócios.", "source": "channel_description"},
        {"text": "Novos cursos disponíveis e parcerias comerciais no link.", "source": "last_video_description"}
    ]

    found, sources_map = KeywordAnalyzer.extract_keywords_with_sources(texts)
    assert len(found) >= 3
    assert "consultoria" in sources_map
    assert "channel_description" in sources_map["consultoria"]
    assert "parcerias" in sources_map
    assert "last_video_description" in sources_map["parcerias"]
