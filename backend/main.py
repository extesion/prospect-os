from fastapi import FastAPI, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import text

from backend.config.settings import settings
from backend.database.connection import get_db, engine, Base
from backend.routes import auth, channels, stats, work_sessions
import qualifier.models # Ensures qualification tables are registered with Base
from qualifier.routes.qualification import router as qualification_router
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("youtube_prospector")

# Auto-create tables safely (ignore on read-only serverless if connection fails at startup)
try:
    Base.metadata.create_all(bind=engine)
    with engine.begin() as conn:
        # PostgreSQL column text upgrade
        if "postgresql" in str(engine.url):
            conn.execute(text("""
                DO $$ 
                BEGIN 
                    IF EXISTS (
                        SELECT 1 FROM information_schema.columns 
                        WHERE table_name = 'user_profiles' AND column_name = 'avatar_url' AND data_type = 'character varying'
                    ) THEN 
                        ALTER TABLE user_profiles ALTER COLUMN avatar_url TYPE TEXT;
                        ALTER TABLE user_profiles ALTER COLUMN banner_url TYPE TEXT;
                    END IF;
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns 
                        WHERE table_name = 'users' AND column_name = 'is_deleted'
                    ) THEN 
                        ALTER TABLE users ADD COLUMN is_deleted BOOLEAN DEFAULT FALSE;
                        ALTER TABLE users ADD COLUMN deleted_at TIMESTAMP WITH TIME ZONE;
                    END IF;
                END $$;
            """))
        elif "sqlite" in str(engine.url):
            # SQLite safe column migration
            res = conn.execute(text("PRAGMA table_info(users)")).fetchall()
            col_names = [r[1] for r in res] if res else []
            if "is_deleted" not in col_names:
                conn.execute(text("ALTER TABLE users ADD COLUMN is_deleted BOOLEAN DEFAULT 0"))
            if "deleted_at" not in col_names:
                conn.execute(text("ALTER TABLE users ADD COLUMN deleted_at TIMESTAMP"))
except Exception as e:
    logger.warning(f"Startup DB check: {e}")

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="API Central para Prospecção e Coleta de Canais do YouTube com Prevenção de Duplicidades e Gestão de Produtividade",
    docs_url="/docs",
    redoc_url="/redoc"
)

from backend.routes import auth, channels, stats, work_sessions, users, youtube_apis, notifications, profiles, music, system
from qualifier.routes.qualification import router as qualification_router

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static files for uploads (avatars, banners)
from fastapi.staticfiles import StaticFiles
import os
static_dir = os.path.join(os.path.dirname(__file__), "static")
uploads_dir = os.path.join(static_dir, "uploads")
try:
    os.makedirs(uploads_dir, exist_ok=True)
except Exception:
    pass

if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

# Register routes with /api prefix
app.include_router(auth.router, prefix=settings.API_V1_STR)
app.include_router(channels.router, prefix=settings.API_V1_STR)
app.include_router(stats.router, prefix=settings.API_V1_STR)
app.include_router(work_sessions.router, prefix=settings.API_V1_STR)
app.include_router(qualification_router, prefix=settings.API_V1_STR)
app.include_router(users.router, prefix=settings.API_V1_STR)
app.include_router(youtube_apis.router, prefix=settings.API_V1_STR)
app.include_router(notifications.router, prefix=settings.API_V1_STR)
app.include_router(profiles.router, prefix=settings.API_V1_STR)
app.include_router(music.router, prefix=settings.API_V1_STR)
app.include_router(system.router, prefix=settings.API_V1_STR)

# Also expose without /api prefix for convenience
app.include_router(auth.router)
app.include_router(channels.router)
app.include_router(stats.router)
app.include_router(work_sessions.router)
app.include_router(qualification_router)
app.include_router(users.router)
app.include_router(youtube_apis.router)
app.include_router(notifications.router)
app.include_router(profiles.router)
app.include_router(music.router)
app.include_router(system.router)


@app.get("/health", tags=["Health"])
@app.get("/api/health", tags=["Health"])
def health_check(db: Session = Depends(get_db)):
    """Verifica disponibilidade da API e integridade da conexão com o banco de dados."""
    try:
        db.execute(text("SELECT 1"))
        db_status = "connected"
    except Exception as e:
        logger.error(f"Database connection error in health check: {str(e)}")
        db_status = f"error: {str(e)}"

    return {
        "status": "online" if db_status == "connected" else "degraded",
        "service": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "database": db_status,
        "dashboard_url": settings.DASHBOARD_URL
    }

from fastapi.responses import FileResponse
import os

@app.get("/dashboard", tags=["Dashboard"])
def get_dashboard():
    """Retorna a Dashboard visual da equipe com métricas e tabela de canais."""
    template_path = os.path.join(os.path.dirname(__file__), "templates", "dashboard.html")
    if os.path.exists(template_path):
        return FileResponse(template_path)
    return {"message": "Template dashboard.html não encontrado."}

@app.get("/qualifier", tags=["Qualifier"])
def get_qualifier():
    """Retorna a Interface Web Operacional do Qualificador de Leads."""
    template_path = os.path.join(os.path.dirname(__file__), "templates", "qualifier.html")
    if os.path.exists(template_path):
        return FileResponse(template_path)
    return {"message": "Template qualifier.html não encontrado."}

@app.get("/users", tags=["Users"])
def get_users_page():
    """Retorna a Interface Web de Gestão de Usuários (ADMIN)."""
    template_path = os.path.join(os.path.dirname(__file__), "templates", "users.html")
    if os.path.exists(template_path):
        return FileResponse(template_path)
    return {"message": "Template users.html não encontrado."}

@app.get("/youtube-apis", tags=["YouTube APIs"])
def get_youtube_apis_page():
    """Retorna a Interface Web de Gestão de YouTube Data APIs e Quotas (ADMIN)."""
    template_path = os.path.join(os.path.dirname(__file__), "templates", "youtube_apis.html")
    if os.path.exists(template_path):
        return FileResponse(template_path)
    return {"message": "Template youtube_apis.html não encontrado."}

@app.get("/login", tags=["Authentication"])
def get_login_page():
    """Retorna a Interface de Autenticação Obrigatória do PROSPECT OS."""
    template_path = os.path.join(os.path.dirname(__file__), "templates", "login.html")
    if os.path.exists(template_path):
        return FileResponse(template_path)
    return {"message": "Template login.html não encontrado."}

@app.get("/", tags=["Root"])
def root():
    return {
        "message": "PROSPECT OS API Central is running.",
        "system": "PROSPECT OS — Team Prospecting Operating System",
        "documentation": "/docs",
        "login": "/login",
        "dashboard": "/dashboard",
        "health": "/health"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)

