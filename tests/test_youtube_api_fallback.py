import pytest
import os
import sys
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.database.connection import engine, Base, SessionLocal
from backend.database.models import YouTubeApiConfig, YouTubeApiUsage, Channel, User, utc_now
from qualifier.services.youtube_api_manager import YouTubeApiManager, YouTubeQuotaExceededException
from qualifier.services.youtube_service import YouTubeService, _call_with_retry
from qualifier.worker import QualificationWorker
from qualifier.models.qualification_job import QualificationJob
from qualifier.models.qualification_result import QualificationResult


def test_youtube_api_key_fallback_and_invalidation():
    db = SessionLocal()
    try:
        # Clean up any existing api configs
        db.query(YouTubeApiUsage).delete()
        db.query(YouTubeApiConfig).delete()
        db.commit()

        # Add 2 configs: Config 1 (invalid key) and Config 2 (valid key)
        cfg1 = YouTubeApiConfig(
            name="Key 1 (Invalid)",
            api_key="AIzaSyInvalidKey1234567890",
            status="ACTIVE",
            daily_limit=10000
        )
        cfg2 = YouTubeApiConfig(
            name="Key 2 (Valid Fallback)",
            api_key="AIzaSyValidKey9876543210",
            status="ACTIVE",
            daily_limit=10000
        )
        db.add_all([cfg1, cfg2])
        db.commit()
        db.refresh(cfg1)
        db.refresh(cfg2)

        # Mock requests.get: when key is cfg1.api_key -> return 400 API_KEY_INVALID
        # when key is cfg2.api_key -> return 200 with channel data
        def mock_requests_get(url, params=None, timeout=None):
            req_key = params.get("key") if params else None
            mock_resp = MagicMock()
            if req_key == cfg1.api_key:
                mock_resp.ok = False
                mock_resp.status_code = 400
                mock_resp.text = '{"error": {"code": 400, "message": "API key not valid. Please pass a valid API key.", "status": "INVALID_ARGUMENT", "errors": [{"reason": "API_KEY_INVALID"}]}}'
                return mock_resp
            elif req_key == cfg2.api_key:
                mock_resp.ok = True
                mock_resp.status_code = 200
                mock_resp.json.return_value = {"items": [{"id": "UC_TEST", "snippet": {"title": "Test Channel"}}]}
                return mock_resp
            mock_resp.ok = False
            mock_resp.status_code = 404
            mock_resp.text = "Not found"
            return mock_resp

        with patch("requests.get", side_effect=mock_requests_get) as mock_get:
            res_data, used_cfg_id = _call_with_retry(
                db=db,
                endpoint="/channels",
                operation="channels.list",
                params={"id": "UC_TEST"},
                max_retries_per_key=3
            )

            # 1. Returned data is from the successful key
            assert res_data["items"][0]["id"] == "UC_TEST"
            assert used_cfg_id == cfg2.id

            # 2. Key 1 was marked as ERROR in DB
            db.refresh(cfg1)
            assert cfg1.status == "ERROR"
            assert "API_KEY_INVALID" in cfg1.error_message

            # 3. Key 1 was called only once (not repeated 3x!)
            key1_calls = [c for c in mock_get.call_args_list if c[1]["params"].get("key") == cfg1.api_key]
            assert len(key1_calls) == 1

            # 4. Quota was recorded ONLY for Key 2, NOT for Key 1
            usages = db.query(YouTubeApiUsage).all()
            assert len(usages) == 1
            assert usages[0].api_config_id == cfg2.id
            assert usages[0].success == True
            assert usages[0].units == 1

    finally:
        db.close()


def test_no_valid_keys_raises_clear_error():
    db = SessionLocal()
    try:
        db.query(YouTubeApiUsage).delete()
        db.query(YouTubeApiConfig).delete()
        db.commit()

        # Add single invalid key
        cfg = YouTubeApiConfig(
            name="Key Invalid Only",
            api_key="AIzaSyBadKeyOnly12345",
            status="ACTIVE",
            daily_limit=10000
        )
        db.add(cfg)
        db.commit()

        def mock_bad_get(url, params=None, timeout=None):
            mock_resp = MagicMock()
            mock_resp.ok = False
            mock_resp.status_code = 400
            mock_resp.text = '{"error": {"code": 400, "message": "API key not valid", "errors": [{"reason": "keyInvalid"}]}}'
            return mock_resp

        with patch("requests.get", side_effect=mock_bad_get):
            with pytest.raises(ValueError, match="Nenhuma YouTube API key válida configurada"):
                _call_with_retry(
                    db=db,
                    endpoint="/channels",
                    operation="channels.list",
                    params={"id": "UC_TEST"}
                )

        db.refresh(cfg)
        assert cfg.status == "ERROR"
    finally:
        db.close()


def test_secrets_are_masked_in_manager():
    assert YouTubeApiManager.mask_api_key("AIzaSyB1234567890abcdefXYZ") == "AIza************XYZ"
    assert YouTubeApiManager.mask_api_key("short") == "********"
    assert YouTubeApiManager.mask_api_key("") == "—"
