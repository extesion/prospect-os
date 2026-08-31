from fastapi import FastAPI, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import text

from backend.config.settings import settings
from backend.database.connection import get_db, engine, Base
from backend.routes import auth, channels, stats, work_sessions
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("youtube_prospector")

# Auto-create tables if not exists
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="API Central para Prospecção e Coleta de Canais do YouTube com Prevenção de Duplicidades e Gestão de Produtividade",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routes
app.include_router(auth.router, prefix=settings.API_V1_STR)
app.include_router(channels.router, prefix=settings.API_V1_STR)
app.include_router(stats.router, prefix=settings.API_V1_STR)
app.include_router(work_sessions.router, prefix=settings.API_V1_STR)

# Also expose without /api prefix for convenience
app.include_router(auth.router)
app.include_router(channels.router)
app.include_router(stats.router)
app.include_router(work_sessions.router)


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

@app.get("/", tags=["Root"])
def root():
    return {
        "message": "YouTube Prospector API Central is running.",
        "documentation": "/docs",
        "dashboard": "/dashboard",
        "health": "/health"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)

