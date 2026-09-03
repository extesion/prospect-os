import pytest
import os
import sys
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

# Ensure backend can be imported
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Use temporary SQLite for fast isolated test verification
os.environ["DATABASE_URL"] = "sqlite:///./test_prospector.db"
os.environ["SECRET_KEY"] = "test-secret-key-12345"

from fastapi.testclient import TestClient
from backend.main import app
from backend.database.connection import engine, Base, SessionLocal
from backend.seed import seed
from backend.database.models import Channel, User

from qualifier.services.link_extractor import LinkExtractor
from qualifier.services.email_extractor import EmailExtractor
from qualifier.services.whatsapp_detector import WhatsAppDetector
from qualifier.services.keyword_analyzer import KeywordAnalyzer
from qualifier.services.niche_detector import NicheDetector
from qualifier.services.commercial_signal_detector import CommercialSignalDetector
from qualifier.services.scoring_engine import ScoringEngine
from qualifier.services.qualification_service import QualificationService
from qualifier.services.youtube_service import YouTubeService, YouTubeQuotaExceededException
from qualifier.models.qualification_result import QualificationResult
from qualifier.models.qualification_job import QualificationJob
from qualifier.worker import QualificationWorker

client = TestClient(app)

@pytest.fixture(scope="session", autouse=True)
def setup_database():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    seed()
    yield
    Base.metadata.drop_all(bind=engine)
    if os.path.exists("./test_prospector.db"):
        try:
            os.remove("./test_prospector.db")
        except:
            pass

def get_auth_token():
    auth_resp = client.post("/auth/login", json={"email": "carlos@prospector.com", "password": "123"})
    return auth_resp.json()["access_token"]


# ============================================================================
# 1. LINK & SOCIAL EXTRACTION TESTS
# ============================================================================

def test_link_extractor_comprehensive():
    texts = [
        {
            "text": "Acesse nosso site oficial: https://meunegocio.com/inicio?utm_source=youtube&ref=123 e nos siga no Instagram https://instagram.com/meunegociooficial",
            "source": "channel_description"
        },
        {
            "text": "Compre o curso na Kiwify: https://kiwify.app/abc1234 ou veja todos os links no https://linktr.ee/meunegocio",
            "source": "video_1"
        },
        {
            "text": "Converse pelo WhatsApp https://wa.me/5511999998888 ou no TikTok https://tiktok.com/@meunegocio e LinkedIn https://linkedin.com/in/meunegocio",
            "source": "video_2"
        }
    ]

    res = LinkExtractor.extract_links_from_texts(texts)

    assert res["website"] == "https://meunegocio.com/inicio"  # Tracking params removed
    assert res["instagram"] == "https://instagram.com/meunegociooficial"
    assert res["tiktok"] == "https://tiktok.com/@meunegocio"
    assert res["linkedin"] == "https://linkedin.com/in/meunegocio"
    assert res["whatsapp_link"] == "https://wa.me/5511999998888"

    assert len(res["link_aggregators"]) == 1
    assert res["link_aggregators"][0]["platform"] == "linktree"

    assert len(res["sales_platforms"]) == 1
    assert res["sales_platforms"][0]["platform"] == "kiwify"


# ============================================================================
# 2. EMAIL EXTRACTION TESTS
# ============================================================================

def test_email_extractor():
    texts = [
        {"text": "Para parcerias e orçamentos: comercial@empresa.com.br ou contato@empresa.com.br", "source": "channel_description"},
        {"text": "Email de suporte: suporte@empresa.com.br e imagem teste@2x.png", "source": "video_1"}
    ]

    res = EmailExtractor.extract_emails(texts)
    # comercial@ should be prioritized over generic
    assert res["email"] in ["comercial@empresa.com.br", "contato@empresa.com.br"]
    assert res["email_source"] == "channel_description"

    # Test no email
    no_email_res = EmailExtractor.extract_emails([{"text": "Sem email aqui!", "source": "v1"}])
    assert no_email_res["email"] is None


# ============================================================================
# 3. WHATSAPP DETECTOR TESTS
# ============================================================================

def test_whatsapp_detector():
    # Link format
    t1 = [{"text": "Chame no zap: https://wa.me/5511988887777", "source": "channel_desc"}]
    res1 = WhatsAppDetector.detect_whatsapp(t1)
    assert res1["whatsapp"] == "5511988887777"

    # Context format
    t2 = [{"text": "Contato Comercial / WhatsApp: (11) 97777-6666", "source": "video_1"}]
    res2 = WhatsAppDetector.detect_whatsapp(t2)
    assert "977776666" in res2["whatsapp"] or "11977776666" in res2["whatsapp"]


# ============================================================================
# 4. KEYWORDS & NICHE DETECTION TESTS
# ============================================================================

def test_keyword_and_niche_detector():
    texts = [
        {"text": "Canal oficial sobre marketing digital, tráfego pago, lançamentos e consultoria de vendas.", "source": "channel_desc"},
        {"text": "Inscreva-se no curso de tráfego pago com desconto no link da bio! Faça seu orçamento.", "source": "video_1"}
    ]

    keywords = KeywordAnalyzer.extract_keywords(texts)
    matched_kws = [k["keyword"] for k in keywords]
    assert "marketing" in matched_kws or "consultoria" in matched_kws or "curso" in matched_kws

    niche, confidence = NicheDetector.detect_niche(texts, channel_name="Agência de Marketing Digital")
    assert niche == "marketing"
    assert confidence > 0.3


# ============================================================================
# 5. COMMERCIAL SIGNALS TESTS
# ============================================================================

def test_commercial_signal_detector():
    links = {
        "website": "https://agencia.com",
        "website_source": "channel_desc",
        "sales_platforms": [{"platform": "hotmart", "url": "https://hotmart.com/x", "source": "video_1"}],
        "link_aggregators": []
    }
    email = {"email": "contato@agencia.com", "email_source": "channel_desc"}
    whatsapp = {"whatsapp": "5511999998888", "whatsapp_source": "video_1"}
    keywords = [
        {"keyword": "consultoria", "source": "channel_desc", "context": "...consultoria de vendas..."},
        {"keyword": "curso", "source": "video_1", "context": "...curso completo..."}
    ]

    signals = CommercialSignalDetector.detect_signals(links, email, whatsapp, keywords, [])
    sig_types = [s["type"] for s in signals]

    assert "own_website" in sig_types
    assert "commercial_email" in sig_types
    assert "whatsapp_contact" in sig_types
    assert "course_sale" in sig_types or "sales_platform" in sig_types
    assert "consulting_service" in sig_types


# ============================================================================
# 6. SCORING ENGINE & PENALTIES TESTS
# ============================================================================

def test_scoring_engine_qualified():
    # Strong lead: email, website, whatsapp, instagram, recent (2 days), commercial signals
    res = ScoringEngine.calculate_score(
        email="contato@empresa.com",
        website="https://empresa.com",
        whatsapp="5511999998888",
        instagram="https://instagram.com/empresa",
        days_since_last_video=2,
        estimated_posting_frequency_days=4.0,
        commercial_signals=[{"type": "course_sale", "source": "v1", "value": "curso"}],
        keywords_found=[{"keyword": "consultoria", "source": "desc", "context": "..."}],
        link_aggregators=[{"platform": "linktree", "url": "https://linktr.ee/empresa"}],
        sales_platforms=[{"platform": "kiwify", "url": "https://kiwify.app/x"}],
        has_any_external_links=True
    )

    assert res["score"] >= 70
    assert res["status"] == "QUALIFIED"
    assert res["score_breakdown"]["email"] == 20
    assert res["score_breakdown"]["website"] == 15
    assert "Canal qualificado" in res["qualification_reason"]

def test_scoring_engine_inactivity_penalty():
    # Inactive > 180 days with no contacts
    res = ScoringEngine.calculate_score(
        email=None,
        website=None,
        whatsapp=None,
        instagram=None,
        days_since_last_video=200,
        estimated_posting_frequency_days=None,
        commercial_signals=[],
        keywords_found=[],
        link_aggregators=[],
        sales_platforms=[],
        has_any_external_links=False
    )

    assert res["score"] <= 39
    assert res["status"] == "REJECTED"
    assert res["score_breakdown"]["inactivity_penalty"] == -25
    assert res["score_breakdown"]["no_contact_penalty"] == -10


# ============================================================================
# 7. END-TO-END QUALIFICATION SERVICE WITH MOCKED YOUTUBE API
# ============================================================================

def test_qualification_service_and_worker():
    db = SessionLocal()
    try:
        user = db.query(User).first()
        now = datetime.now(timezone.utc)

        # Create test channel in DB
        ch = Channel(
            channel_id="UC_QUAL_TEST_01",
            channel_name="Tech e Negócios Pro",
            channel_handle="@technegocios",
            channel_url="https://youtube.com/@technegocios",
            first_collected_by_id=user.id,
            first_collected_at=now,
            created_at=now,
            updated_at=now
        )
        db.add(ch)
        db.commit()

        # Enqueue job
        job = QualificationService.enqueue_channel(db, "UC_QUAL_TEST_01", priority=1)
        assert job.status == "PENDING"

        # Mock YouTubeService responses
        mock_yt = MagicMock(spec=YouTubeService)
        mock_yt.fetch_channels_batch.return_value = {
            "UC_QUAL_TEST_01": {
                "channel_id": "UC_QUAL_TEST_01",
                "title": "Tech e Negócios Pro",
                "description": "Canal sobre tecnologia, software e inteligência artificial. Contato comercial: contato@techpro.com e site https://techpro.io",
                "published_at": "2022-01-01T00:00:00Z",
                "country": "BR",
                "uploads_playlist_id": "UU_QUAL_TEST_01",
                "subscribers": 50000,
                "total_views": 1500000,
                "total_videos": 120
            }
        }
        mock_yt.fetch_recent_video_ids_from_playlist.return_value = ["VID_01", "VID_02"]
        mock_yt.fetch_videos_batch.return_value = {
            "VID_01": {
                "video_id": "VID_01",
                "title": "Como criar sua Agência de IA em 2026",
                "description": "Veja o curso completo em https://kiwify.app/ia-pro e fale no WhatsApp (11) 98888-7777",
                "published_at": (now - timedelta(days=3)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "tags": ["ia", "inteligencia artificial", "marketing", "negocios"],
                "duration": "PT15M",
                "view_count": 12000,
                "like_count": 800,
                "comment_count": 120
            },
            "VID_02": {
                "video_id": "VID_02",
                "title": "Ferramentas essenciais de IA",
                "description": "Mais dicas no Instagram https://instagram.com/techpro e consultoria sob medida.",
                "published_at": (now - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "tags": ["tecnologia", "produtividade"],
                "duration": "PT10M",
                "view_count": 8000,
                "like_count": 500,
                "comment_count": 40
            }
        }

        worker = QualificationWorker(youtube_service=mock_yt)
        res = worker.process_batch(db, limit=10)

        assert res["completed"] == 1
        assert res["failed"] == 0

        # Verify persisted QualificationResult
        qual_res = db.query(QualificationResult).filter(QualificationResult.channel_id == "UC_QUAL_TEST_01").first()
        assert qual_res is not None
        assert qual_res.qualification_status == "QUALIFIED"
        assert qual_res.email == "contato@techpro.com"
        assert qual_res.website == "https://techpro.io"
        assert qual_res.days_since_last_video == 3
        assert qual_res.subscribers == 50000
        assert len(qual_res.analyzed_videos) == 2
        db.refresh(job)
        assert job.status == "QUALIFIED"
        assert 0 <= qual_res.score <= 100
        assert qual_res.score_breakdown
        assert any(k["source"] == "channel_description" for k in qual_res.keywords_found)

    finally:
        db.close()


def test_activity_boundaries_and_retry_error_states():
    for days, expected in [(30, "ACTIVE"), (31, "LOW_ACTIVITY"), (90, "LOW_ACTIVITY"), (91, "INACTIVE")]:
        assert QualificationService._classify_activity(days) == expected

    job = QualificationJob(channel_id="UC_RETRY", status="PROCESSING", attempts=0, max_attempts=2)
    worker = QualificationWorker(youtube_service=MagicMock(spec=YouTubeService))
    worker._handle_retry(job, "temporary")
    assert job.status == "RETRY" and job.next_retry_at and job.error_message == "temporary"
    worker._handle_retry(job, "persistent")
    assert job.status == "ERROR" and job.finished_at


def test_queue_pause_invalid_channel_and_no_double_enqueue():
    db = SessionLocal()
    try:
        with pytest.raises(ValueError):
            QualificationService.enqueue_channel(db, "UC_DOES_NOT_EXIST")
        existing = db.query(Channel).first()
        job = QualificationService.enqueue_channel(db, existing.channel_id)
        job.status = "PROCESSING"
        db.commit()
        same = QualificationService.enqueue_channel(db, existing.channel_id)
        assert same.id == job.id and same.status == "PROCESSING"

        from qualifier.config.qualification_config import qualification_config
        qualification_config.QUEUE_PAUSED = True
        assert QualificationWorker(youtube_service=MagicMock(spec=YouTubeService)).process_batch(db)["processed"] == 0
        qualification_config.QUEUE_PAUSED = False
    finally:
        db.close()


# ============================================================================
# 8. API ENDPOINTS TESTS
# ============================================================================

def test_qualification_api_endpoints():
    token = get_auth_token()
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Get queue
    queue_resp = client.get("/api/qualification/queue", headers=headers)
    assert queue_resp.status_code == 200
    assert isinstance(queue_resp.json(), list)

    # 2. Get stats
    stats_resp = client.get("/api/qualification/stats", headers=headers)
    assert stats_resp.status_code == 200
    s_data = stats_resp.json()
    assert "total_qualified" in s_data
    assert "pending_jobs" in s_data

    # 3. Get / Update Config
    cfg_resp = client.get("/api/qualification/config", headers=headers)
    assert cfg_resp.status_code == 200
    assert cfg_resp.json()["DAILY_QUOTA_LIMIT"] >= 1000

    update_cfg_resp = client.put("/api/qualification/config", json={"videos_to_analyze": 3, "score_qualified_threshold": 70}, headers=headers)
    assert update_cfg_resp.status_code == 200

    # 4. Get channel qualification result (from previous test)
    qual_resp = client.get("/api/qualification/UC_QUAL_TEST_01", headers=headers)
    assert qual_resp.status_code == 200
    q_data = qual_resp.json()
    assert q_data["channel_id"] == "UC_QUAL_TEST_01"
    assert q_data["qualification_status"] == "QUALIFIED"
    assert q_data["score"] >= 70

    # 5. Get email template data
    email_data_resp = client.get("/api/qualification/UC_QUAL_TEST_01/email-data", headers=headers)
    assert email_data_resp.status_code == 200
    e_data = email_data_resp.json()
    assert e_data["channel_name"] == "Tech e Negócios Pro"
    assert e_data["email"] == "contato@techpro.com"
    assert e_data["website"] == "https://techpro.io"

    # 6. Retry endpoint
    retry_resp = client.post("/api/qualification/UC_QUAL_TEST_01/retry", headers=headers)
    assert retry_resp.status_code == 200
    assert retry_resp.json()["status"] == "PENDING"

    # 7. Backfill endpoint
    backfill_resp = client.post("/api/qualification/backfill", headers=headers)
    assert backfill_resp.status_code == 200
    assert "enqueued_count" in backfill_resp.json()

    # 8. Web UI Endpoint
    ui_resp = client.get("/qualifier")
    assert ui_resp.status_code == 200
    assert "QUALIFICADOR DE LEADS" in ui_resp.text

    # 9. Status Overview Endpoint
    overview_resp = client.get("/api/qualification/status-overview", headers=headers)
    assert overview_resp.status_code == 200
    ov_data = overview_resp.json()
    assert ov_data["connections"]["local_processor"] == "online"
    assert "stats" in ov_data

    # 10. Leads List with Filters
    leads_resp = client.get("/api/qualification/leads?page=1&page_size=50", headers=headers)
    assert leads_resp.status_code == 200
    l_data = leads_resp.json()
    assert l_data["total"] >= 1
    assert len(l_data["leads"]) >= 1

    # 11. Modal Detail Endpoint
    detail_resp = client.get("/api/qualification/leads/UC_QUAL_TEST_01/detail", headers=headers)
    assert detail_resp.status_code == 200
    d_data = detail_resp.json()
    assert d_data["channel"]["channel_name"] == "Tech e Negócios Pro"
    assert d_data["qualification"]["score"] >= 70
