from datetime import datetime, timezone
import logging

from pydantic import BaseModel
from dotenv import load_dotenv
import os

load_dotenv(override=True)

_logger = logging.getLogger(__name__)


def _env(key: str, default: str = "") -> str:
    value = os.getenv(key, default) or ""
    return value.strip().strip('"').strip("'")


def _env_bool(key: str, default: str = "0") -> bool:
    return _env(key, default).lower() in ("1", "true", "yes", "on")


def _env_float(key: str, default: str) -> float:
    return float(_env(key, default) or default)


def _clamp_retrieval_int(key: str, default: int, lo: int, hi: int) -> int:
    """E-03: clamp RRF hyperparameters to safe tuning range."""
    raw = _env(key, str(default))
    try:
        val = int(raw or default)
    except ValueError:
        _logger.warning("%s=%r invalid — using default %s", key, raw, default)
        return default
    if val < lo or val > hi:
        _logger.warning(
            "%s=%s out of range [%s,%s] — clamped",
            key,
            val,
            lo,
            hi,
        )
        return max(lo, min(hi, val))
    return val


def _env_llm_mode(key: str, default: str = "2") -> int:
    """1 = ưu tiên API local (Gemini 3.5 qua proxy); 2 = chỉ Gemini 2.5 trực tiếp."""
    raw = _env(key, default) or default
    try:
        mode = int(raw)
    except ValueError:
        mode = 2
    return mode if mode in (1, 2) else 2


def _env_datetime(key: str) -> datetime | None:
    """ISO-8601 UTC, e.g. 2025-06-01T00:00:00Z. Empty = no filter."""
    raw = _env(key)
    if not raw:
        return None
    normalized = raw.replace("Z", "+00:00")
    dt = datetime.fromisoformat(normalized)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _normalize_database_url(url: str) -> str:
    """Render/Heroku Postgres trả postgresql:// — SQLAlchemy async cần +asyncpg."""
    if not url:
        return url
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://") :]
    if url.startswith("postgresql://") and "+asyncpg" not in url.split("://", 1)[0]:
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url


class Settings(BaseModel):
    log_level: str = _env("LOG_LEVEL", "INFO")
    gemini_api_key: str = _env("GEMINI_API_KEY")
    # D-03: LLM-as-judge — provider gemini | openai | groq | local (mặc định gemini).
    judge_provider: str = _env("JUDGE_PROVIDER", "gemini").lower()
    judge_gemini_api_key: str = _env("JUDGE_GEMINI_API_KEY") or _env("GEMINI_API_KEY")
    judge_gemini_model: str = _env("JUDGE_GEMINI_MODEL", "gemini-2.0-flash-lite")
    judge_openai_api_key: str = _env("JUDGE_OPENAI_API_KEY") or _env("OPENAI_API_KEY")
    judge_openai_model: str = _env("JUDGE_OPENAI_MODEL") or _env("OPENAI_MODEL", "gpt-4o-mini")
    judge_groq_api_key: str = _env("JUDGE_GROQ_API_KEY") or _env("GROQ_API_KEY")
    judge_groq_model: str = _env("JUDGE_GROQ_MODEL", "llama-3.1-8b-instant")
    judge_groq_base_url: str = _env("JUDGE_GROQ_BASE_URL", "https://api.groq.com/openai/v1")
    judge_request_delay_seconds: float = _env_float("JUDGE_REQUEST_DELAY_SECONDS", "2.5")
    judge_local_model: str = _env("JUDGE_LOCAL_MODEL") or _env(
        "CHATBOT_LOCAL_MODEL", "gemini-3.5-flash-thinking@think=2"
    )
    gemini_model: str = _env("GEMINI_MODEL", "gemini-2.5-flash-lite")
    gemini_fallback_models: str = _env(
        "GEMINI_FALLBACK_MODELS",
        "gemini-flash-lite-latest,gemini-2.5-flash,gemini-2.0-flash-lite",
    )

    router_model: str = _env("ROUTER_MODEL") or _env("GEMINI_MODEL", "gemini-2.5-flash-lite")
    router_fallback_models: str = _env("ROUTER_FALLBACK_MODELS") or _env(
        "GEMINI_FALLBACK_MODELS",
        "gemini-flash-lite-latest,gemini-2.5-flash,gemini-2.0-flash-lite",
    )
    router_temperature: float = _env_float("ROUTER_TEMPERATURE", "0.15")
    router_career_fuzzy_threshold: float = _env_float("ROUTER_CAREER_FUZZY_THRESHOLD", "80")

    generator_model: str = _env("GENERATOR_MODEL") or _env("GEMINI_MODEL", "gemini-2.5-flash-lite")
    generator_fallback_models: str = _env("GENERATOR_FALLBACK_MODELS") or _env(
        "GEMINI_FALLBACK_MODELS",
        "gemini-flash-lite-latest,gemini-2.5-flash,gemini-2.0-flash-lite",
    )
    generator_temperature: float = _env_float("GENERATOR_TEMPERATURE", "0.7")

    # auto | gemini | local — auto = USE_LOCAL_GENERATOR cho pathfinding/course_rec
    generator_backend: str = _env("GENERATOR_BACKEND", "auto")
    use_local_generator: bool = _env_bool("USE_LOCAL_GENERATOR", "0")
    ollama_base_url: str = _env("OLLAMA_BASE_URL", "http://localhost:11434")
    ollama_model_pathfinding: str = _env("OLLAMA_MODEL_PATHFINDING", "career-pathfinding")
    ollama_model_course_rec: str = _env("OLLAMA_MODEL_COURSE_REC", "career-course-rec")
    ollama_timeout_seconds: float = _env_float("OLLAMA_TIMEOUT_SECONDS", "120")

    openai_api_key: str = _env("OPENAI_API_KEY")
    openai_model: str = _env("OPENAI_MODEL", "gpt-4o-mini")

    # CHATBOT_LLM_MODE: 1 = local Gemini 3.5 trước (fallback Gemini 2.5); 2 = chỉ Gemini 2.5
    chatbot_llm_mode: int = _env_llm_mode("CHATBOT_LLM_MODE", "2")
    # API OpenAI-compatible local (gemini_2api) — dùng khi CHATBOT_LLM_MODE=1
    chatbot_local_base_url: str = _env("CHATBOT_LOCAL_BASE_URL", "")
    chatbot_local_api_key: str = _env("CHATBOT_LOCAL_API_KEY", "sk-chatbot-local")
    chatbot_local_model: str = _env(
        "CHATBOT_LOCAL_MODEL", "gemini-3.5-flash-thinking@think=2"
    )
    chatbot_local_timeout_seconds: float = _env_float("CHATBOT_LOCAL_TIMEOUT_SECONDS", "120")

    embedding_provider: str = _env("EMBEDDING_PROVIDER", "gemini")
    embedding_model: str = _env(
        "EMBEDDING_MODEL", "gemini-embedding-001"
    )
    embedding_api_key: str = _env("EMBEDDING_API_KEY") or _env("GEMINI_API_KEY")
    embedding_dimensions: int = int(_env("EMBEDDING_DIMENSIONS", "768") or "768")

    neo4j_uri: str = _env("NEO4J_URI", "bolt://localhost:7687")
    neo4j_user: str = _env("NEO4J_USER", "neo4j")
    neo4j_password: str = _env("NEO4J_PASSWORD", "neo4j_password")
    qdrant_url: str = _env("QDRANT_URL", "http://localhost:6333")
    qdrant_api_key: str = _env("QDRANT_API_KEY")
    qdrant_collection: str = _env("QDRANT_COLLECTION", "career_roadmap")

    # A-03: cộng điểm RRF khi vector doc nằm trong subgraph Neo4j (graph-aware rerank).
    retrieval_graph_boost: float = _env_float("RETRIEVAL_GRAPH_BOOST", "0.15")

    # E-03: RRF fusion pool (safe range documented in .env.example).
    retrieval_rrf_k: int = _clamp_retrieval_int("RETRIEVAL_RRF_K", 60, 20, 80)
    retrieval_rrf_pool_size: int = _clamp_retrieval_int(
        "RETRIEVAL_RRF_POOL_SIZE", 60, 30, 80
    )
    retrieval_max_edge_in_top_k: int = _clamp_retrieval_int(
        "RETRIEVAL_MAX_EDGE_IN_TOP_K", 2, 0, 5
    )

    # B-02: eval fail-fast khi Qdrant/embedding lỗi; production mặc định fallback.
    retrieval_strict: bool = _env_bool("RETRIEVAL_STRICT", "0")

    # competency_relation feature flags (plan v3)
    competency_relation_enrich: bool = _env_bool("COMPETENCY_RELATION_ENRICH", "1")
    competency_relation_min_coverage: float = _env_float(
        "COMPETENCY_RELATION_MIN_COVERAGE", "0.40"
    )
    competency_relation_intent_enabled: bool = _env_bool(
        "COMPETENCY_RELATION_INTENT_ENABLED", "1"
    )

    generator_confidence_threshold: float = _env_float("GENERATOR_CONFIDENCE_THRESHOLD", "0.45")

    generator_retry_max_attempts: int = int(_env("GENERATOR_RETRY_MAX_ATTEMPTS", "2") or "2")
    generator_retry_backoff_seconds: float = _env_float("GENERATOR_RETRY_BACKOFF_SECONDS", "2.0")

    database_url: str = _normalize_database_url(_env("DATABASE_URL", ""))
    database_echo: bool = _env_bool("DATABASE_ECHO", "0")

    # Sidebar / list_sessions: chỉ hiện phiên có created_at >= mốc (bỏ qua phiên test/cũ).
    session_filter_after: datetime | None = _env_datetime("SESSION_FILTER_AFTER")


settings = Settings()
