from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.advisory_routes import router as advisory_router
from app.api.chat_routes import router as chat_router
from app.api.health_routes import router as health_router
from app.api.intent_routes import router as intent_router
from app.core.config import settings
from app.core.logging_config import setup_logging
from app.db.engine import close_database, init_database

setup_logging(settings.log_level)

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_database()
    yield
    await close_database()


# lifespan: init PostgreSQL (DATABASE_URL, Docker port 5433)
app = FastAPI(
    title="IT Career Goal Advisor - Graph RAG",
    lifespan=lifespan,
)
app.include_router(advisory_router)
app.include_router(chat_router)
app.include_router(health_router)
app.include_router(intent_router)

if FRONTEND_DIR.is_dir():
    app.mount(
        "/",
        StaticFiles(directory=str(FRONTEND_DIR), html=True),
        name="frontend",
    )
