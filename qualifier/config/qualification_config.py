from typing import Dict, List, Any
from pydantic import BaseModel, Field
import os
from pathlib import Path

def get_env_api_key() -> str:
    key = os.getenv("YOUTUBE_API_KEY", "")
    if key:
        return key
    # Search root and parent folders for .env
    current = Path(__file__).resolve().parent
    for p in [current / ".." / ".." / ".env", current / ".." / ".." / "backend" / ".env", Path(".env"), Path("backend/.env")]:
        if p.exists():
            try:
                for line in p.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if line.startswith("YOUTUBE_API_KEY="):
                        val = line.split("=", 1)[1].strip().strip('"').strip("'")
                        if val:
                            os.environ["YOUTUBE_API_KEY"] = val
                            return val
            except Exception:
                pass
    return ""

class QualificationConfig(BaseModel):
    # YouTube API
    YOUTUBE_API_KEY: str = Field(default_factory=get_env_api_key)
    DAILY_QUOTA_LIMIT: int = Field(default=9500)
    VIDEOS_TO_ANALYZE: int = Field(default=3)
    BATCH_SIZE: int = Field(default=50)
    REQUALIFICATION_INTERVAL_DAYS: int = Field(default=30)
    QUALIFICATION_VERSION: str = Field(default="v1")
    QUEUE_PAUSED: bool = Field(default=False)

    # Activity thresholds
    ACTIVE_DAYS_THRESHOLD: int = Field(default=30)
    LOW_ACTIVITY_DAYS_THRESHOLD: int = Field(default=90)

    # Classification score thresholds
    SCORE_QUALIFIED_THRESHOLD: int = Field(default=70)
    SCORE_REVIEW_THRESHOLD: int = Field(default=40)

    # Score weights (Positive)
    SCORE_POINTS_EMAIL: int = Field(default=20)
    SCORE_POINTS_WEBSITE: int = Field(default=15)
    SCORE_POINTS_WHATSAPP: int = Field(default=10)
    SCORE_POINTS_INSTAGRAM: int = Field(default=5)
    SCORE_POINTS_ACTIVE_RECENT: int = Field(default=15)
    SCORE_POINTS_SALES_SIGNAL: int = Field(default=15)
    SCORE_POINTS_COMMERCIAL_KEYWORDS: int = Field(default=10)
    SCORE_POINTS_LINK_AGGREGATOR: int = Field(default=5)
    SCORE_POINTS_CONSISTENT_POSTING: int = Field(default=5)

    # Penalties (Negative)
    PENALTY_INACTIVE_90_DAYS: int = Field(default=-15)
    PENALTY_INACTIVE_180_DAYS: int = Field(default=-25)
    PENALTY_NO_EXTERNAL_LINKS: int = Field(default=-10)
    PENALTY_NO_CONTACT: int = Field(default=-10)
    PENALTY_NO_COMMERCIAL_SIGNALS: int = Field(default=-15)

    # Commercial keywords list
    COMMERCIAL_KEYWORDS: List[str] = [
        "contato", "comercial", "parceria", "parcerias", "patrocínio", "patrocinador",
        "consultoria", "mentoria", "curso", "cursos", "agência", "empresa",
        "serviço", "serviços", "loja", "produto", "produtos", "orçamento",
        "compre", "inscreva-se", "link na bio", "whatsapp", "site", "hotmart",
        "kiwify", "eduzz", "monetizze", "ebook", "treinamento", "assessoria",
        "anuncie", "publicidade", "media kit", "mídia kit", "contrate"
    ]

    # Niches and associated keywords
    NICHES_KEYWORDS_MAP: Dict[str, List[str]] = {
        "marketing": ["marketing", "tráfego pago", "copywriting", "lançamento", "vendas", "social media", "branding", "seo", "afiliado", "growth", "anúncios"],
        "finanças": ["investimentos", "ações", "bolsa de valores", "finanças", "dinheiro", "cripto", "bitcoin", "renda fixa", "dividendos", "economia", "planejamento financeiro"],
        "empreendedorismo": ["empreendedorismo", "negócios", "empresa", "gestão", "liderança", "startup", "b2b", "faturamento", "escalar"],
        "fitness": ["fitness", "musculação", "treino", "dieta", "emagrecimento", "nutrição", "hipertrofia", "academia", "calistenia", "personal trainer"],
        "beleza": ["maquiagem", "skincare", "cabelo", "beleza", "unhas", "estética", "cosméticos", "penteado", "moda"],
        "tecnologia": ["programação", "software", "desenvolvimento", "python", "javascript", "ia", "inteligência artificial", "tech", "hardware", "gadgets", "código"],
        "educação": ["educação", "aula", "enem", "concurso", "idiomas", "inglês", "aprender", "professor", "estudos", "faculdade"],
        "games": ["gameplay", "jogos", "games", "gaming", "playstation", "xbox", "nintendo", "pc gamer", "twitch", "streamer", "walkthrough"],
        "culinária": ["receita", "culinária", "cozinha", "gastronomia", "chef", "comida", "sobremesa", "confeitaria", "prato"],
        "podcast": ["podcast", "entrevista", "cortes", "bate-papo", "talk show", "conversa"],
        "imobiliário": ["imóveis", "imobiliária", "corretor", "apartamento", "casa", "construção", "tour pelo imóvel", "leilão de imóveis"],
        "automotivo": ["carros", "automotivo", "veículos", "motos", "mecânica", "test drive", "automóveis", "aceleração"],
        "moda": ["moda", "look", "roupas", "tendências", "estilo", "outfit", "fashion"],
        "saúde": ["saúde", "médico", "medicina", "psicologia", "terapia", "bem-estar", "saúde mental", "fisioterapia"],
        "entretenimento": ["humor", "comédia", "vlog", "curiosidades", "reação", "react", "desafio", "entretenimento"]
    }

qualification_config = QualificationConfig()
