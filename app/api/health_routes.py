from __future__ import annotations

from fastapi import APIRouter

from app.core.config import settings
from app.db.engine import database_enabled
from app.db.engine import get_engine
from sqlalchemy import text

from app.graph.neo4j_client import Neo4jClient
from app.rag.qdrant_client import qdrant_http_headers
from app.services.chat_completion_gateway import ChatCompletionGateway
from app.services.generator_backend import generator_status

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health")
async def health_check():
    """Kiểm tra nhanh các dịch vụ (Bước 5 — vận hành)."""
    checks: dict[str, str] = {}

    neo = Neo4jClient()
    checks["neo4j"] = "ok" if neo.available else "unavailable"
    neo.close()

    if database_enabled():
        try:
            engine = get_engine()
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            checks["postgres"] = "ok"
        except Exception as exc:
            checks["postgres"] = f"error: {exc}"
    else:
        checks["postgres"] = "disabled (in-memory session)"

    gw = ChatCompletionGateway()
    checks["chatbot_llm_mode"] = str(settings.chatbot_llm_mode)
    if gw.prefer_local and gw.local_configured:
        try:
            import httpx

            url = settings.chatbot_local_base_url.rstrip("/") + "/models"
            async with httpx.AsyncClient(timeout=2.0) as client:
                r = await client.get(
                    url,
                    headers={
                        "Authorization": f"Bearer {settings.chatbot_local_api_key or 'sk-chatbot-local'}"
                    },
                )
                checks["chatbot_local"] = (
                    "ok" if r.status_code == 200 else f"http {r.status_code}"
                )
        except Exception as exc:
            checks["chatbot_local"] = f"unavailable: {exc}"
    elif gw.prefer_local:
        checks["chatbot_local"] = "disabled (set CHATBOT_LOCAL_BASE_URL)"
    else:
        checks["chatbot_local"] = "skipped (CHATBOT_LLM_MODE=2)"

    checks["gemini"] = "configured" if settings.gemini_api_key else "missing GEMINI_API_KEY"

    if settings.use_local_generator:
        try:
            import httpx

            url = settings.ollama_base_url.rstrip("/") + "/api/tags"
            async with httpx.AsyncClient(timeout=2.0) as client:
                r = await client.get(url)
                checks["ollama"] = "ok" if r.status_code == 200 else f"http {r.status_code}"
        except Exception as exc:
            checks["ollama"] = f"unavailable: {exc}"
    else:
        checks["ollama"] = "disabled"

    checks["local_generator"] = (
        "enabled" if settings.use_local_generator else "disabled (USE_LOCAL_GENERATOR=0)"
    )
    checks["generator"] = generator_status()

    try:
        import httpx

        url = settings.qdrant_url.rstrip("/") + "/readyz"
        async with httpx.AsyncClient(timeout=2.0) as client:
            r = await client.get(url, headers=qdrant_http_headers())
            checks["qdrant"] = "ok" if r.status_code == 200 else f"http {r.status_code}"
    except Exception as exc:
        checks["qdrant"] = f"unavailable: {exc}"

    llm_ok = (
        checks["gemini"] == "configured"
        or checks.get("chatbot_local") == "ok"
    )
    critical = checks["neo4j"] == "ok" and llm_ok
    return {
        "status": "ok" if critical else "degraded",
        "checks": checks,
    }
