import pytest
import os
import sys
import base64

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)

# 1x1 valid PNG
VALID_PNG_BYTES = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==")
# 1x1 valid GIF89a
VALID_GIF_BYTES = base64.b64decode("R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7")

def test_avatar_and_banner_upload_end_to_end():
    # 1. Login Carlos
    login_res = client.post("/auth/login", json={"email": "carlos@prospector.com", "password": "123"})
    assert login_res.status_code == 200
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 2. Upload Avatar (PNG)
    avatar_files = {"file": ("test_avatar.png", VALID_PNG_BYTES, "image/png")}
    av_res = client.post("/profiles/upload/avatar", files=avatar_files, headers=headers)
    assert av_res.status_code == 200
    av_data = av_res.json()
    assert av_data["success"] is True
    assert av_data["asset_type"] == "avatar"
    assert av_data["url"].startswith("data:image/png;base64,")

    # 3. Upload Banner (GIF animado)
    banner_files = {"file": ("test_banner.gif", VALID_GIF_BYTES, "image/gif")}
    bn_res = client.post("/profiles/upload/banner", files=banner_files, headers=headers)
    assert bn_res.status_code == 200
    bn_data = bn_res.json()
    assert bn_data["success"] is True
    assert bn_data["asset_type"] == "banner"
    assert bn_data["url"].startswith("data:image/gif;base64,")

    # 4. Fetch /profiles/me to ensure persistence
    me_profile = client.get("/profiles/me", headers=headers)
    assert me_profile.status_code == 200
    stats = me_profile.json()
    assert stats["name"] == "Carlos Silva"
    assert stats["avatar_url"].startswith("data:image/png;base64,")
    assert stats["banner_url"].startswith("data:image/gif;base64,")

    # 5. Fetch /work-sessions/team/status to verify Member Card has avatar & banner
    team_status = client.get("/work-sessions/team/status", headers=headers)
    assert team_status.status_code == 200
    team_data = team_status.json()
    carlos_member = next((m for m in team_data["members"] if m["user_id"] == stats["user_id"]), None)
    assert carlos_member is not None
    assert carlos_member["avatar_url"] == stats["avatar_url"]
    assert carlos_member["banner_url"] == stats["banner_url"]

    # 6. Fetch /work-sessions/ranking to verify Ranking has avatar & banner
    ranking = client.get("/work-sessions/ranking?period=today", headers=headers).json()
    carlos_rank = next((r for r in ranking if r["user_id"] == stats["user_id"]), None)
    if carlos_rank:
        assert carlos_rank["avatar_url"] == stats["avatar_url"]
        assert carlos_rank["banner_url"] == stats["banner_url"]

def test_upload_invalid_file_type_rejected():
    login_res = client.post("/auth/login", json={"email": "carlos@prospector.com", "password": "123"})
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Plain text file disguised as image
    fake_files = {"file": ("malicious.exe", b"MZThisIsNotAnImage", "image/jpeg")}
    res = client.post("/profiles/upload/avatar", files=fake_files, headers=headers)
    assert res.status_code == 400
    assert "formato de imagem inválido" in res.json()["detail"] or "Tipo de arquivo não permitido" in res.json()["detail"]
