# Hướng dẫn cài đặt & chạy dự án — IT Career Goal Advisor (Graph-RAG)

> Tài liệu này giúp bạn clone repo về và chạy được dự án ngay. Toàn bộ lệnh viết cho **Windows PowerShell** (kèm biến thể Linux/macOS khi cần).
>
> ⚠️ **CẢNH BÁO BẢO MẬT QUAN TRỌNG:** File `.env` hiện đang nằm trong thư mục dự án và **chứa secret thật** (Gemini API key, mật khẩu Neo4j, Qdrant API key, connection string Neon PostgreSQL, Groq key). Nếu repo đã/đang được push lên Git, hãy **thu hồi (rotate) toàn bộ các key này ngay** và đảm bảo `.env` nằm trong `.gitignore`. Tài liệu này chỉ dùng **placeholder** — không sao chép giá trị secret thật.

---

## 1. Tổng quan dự án

**IT Career Goal Advisor** là một web app tư vấn mục tiêu nghề nghiệp IT theo mô hình **Graph-RAG (Retrieval-Augmented Generation)**. Hệ thống kết hợp:

- **Knowledge Graph (Neo4j)**: lưu quan hệ `Career → Competency (Knowledge/Tool/Language/Framework...) → Course → Subject` qua các cạnh `NEED_*`, `TEACH_*`, `IN_SUBJECT`...
- **Vector search (Qdrant)**: tìm ngữ cảnh liên quan bằng embedding (Gemini `gemini-embedding-001`, 768 chiều) + **BM25** (sidecar), hợp nhất bằng **RRF fusion** và **graph-aware rerank**.
- **LLM (Google Gemini / proxy local / Ollama fine-tune)**: định tuyến ý định (Intent Router — Bước 1) và sinh câu trả lời (Response Generator — Bước 4), có Validator loại bỏ trích dẫn ảo.
- **PostgreSQL (Neon)**: lưu hồ sơ người dùng, phiên chat, tin nhắn, kết quả tư vấn và feedback (HITL 👍/👎). Nếu không cấu hình `DATABASE_URL`, hệ thống chạy session **in-memory**.

### Kiến trúc tổng thể

| Tầng | Thành phần | Công nghệ |
|------|------------|-----------|
| Frontend | `frontend/` (HTML/CSS/JS tĩnh) | Vanilla JS, phục vụ tĩnh bởi FastAPI (`StaticFiles`) |
| Backend API | `app/` (FastAPI) | FastAPI + Uvicorn + SQLAlchemy async |
| Graph DB | Knowledge graph | Neo4j (Aura hoặc local bolt) |
| Vector DB | Vector + BM25 retrieval | Qdrant Cloud |
| Relational DB | Session / profile / feedback | PostgreSQL (Neon) |
| LLM | Router + Generator + Judge | Gemini API, proxy OpenAI-compatible local (tùy chọn), Ollama fine-tune (tùy chọn) |

### Sơ đồ luồng xử lý chính

```mermaid
flowchart TD
    U[Người dùng<br/>chat.html / form.html] -->|POST /api/chat| API[FastAPI app.main:app]
    API --> CS[ChatService<br/>orchestrator]
    CS --> IR[Intent Router - Bước 1<br/>Gemini / proxy local]
    IR -->|intent + slots| RET[Retriever - Bước 2/3<br/>tight fusion]

    subgraph Retrieval
        RET --> VEC[Qdrant<br/>vector + BM25]
        RET --> GRAPH[Neo4j<br/>subgraph NEED_/TEACH_]
        VEC --> RRF[RRF fusion +<br/>graph-aware rerank]
        GRAPH --> RRF
    end

    RRF --> GEN[Response Generator - Bước 4<br/>Gemini / Ollama]
    GEN --> VAL[Validator<br/>loại citation ảo]
    VAL --> RESP[Structured response<br/>cards + evidence]
    RESP --> API
    API -->|persist| PG[(PostgreSQL / Neon<br/>session, message, feedback)]
    API --> U
```

Ngoài luồng chat, còn có **luồng Form tư vấn** (`POST /api/advisory/start`) dùng Gemini structured output để sinh advice JSON (skills thiếu / đã có / khóa học gợi ý) rồi chuyển sang chat.

---

## 2. Danh sách file/thư mục quan trọng ảnh hưởng vận hành

| File / thư mục | Vai trò | Thiếu/sai gây lỗi gì |
|----------------|---------|----------------------|
| `app/main.py` | Entry point FastAPI: khởi tạo app, include 4 router, mount frontend tĩnh, lifespan init/close PostgreSQL | Sai import router → app không khởi động |
| `backend/main.py` | Alias `from app.main import app` — dùng cho Docker (`uvicorn main:app`) | Docker entrypoint không tìm thấy app |
| `app/core/config.py` | `Settings` đọc **toàn bộ** biến môi trường từ `.env` (`load_dotenv(override=True)`), có default + clamp | Biến sai kiểu/khoảng → cảnh báo log, dùng default |
| `app/core/logging_config.py` | Cấu hình logging theo `LOG_LEVEL` | Không nghiêm trọng |
| `app/db/engine.py` | Tạo async engine SQLAlchemy, chuẩn hóa `postgresql://` → `postgresql+asyncpg://`, bật SSL cho Neon | `DATABASE_URL` sai → không persist (fallback in-memory) |
| `app/graph/neo4j_client.py` | Kết nối Neo4j (dùng `NEO4J_URI/USER/PASSWORD`) | Sai credentials → `/api/health` báo `neo4j: unavailable`, chat mất graph context |
| `app/rag/qdrant_client.py` | Client Qdrant + headers API key | Sai `QDRANT_URL/API_KEY` → retrieval vector fail |
| `app/rag/embeddings.py` | Sinh embedding (Gemini) cho index + query | Thiếu `GEMINI_API_KEY`/`EMBEDDING_API_KEY` → không embed được |
| `app/rag/retriever.py` | Hybrid retrieval vector + BM25 + RRF fusion | Trung tâm chất lượng RAG |
| `app/services/chat_service.py` | Orchestrator chat: intent → tight fusion → generator | Lỗi ở đây làm hỏng toàn bộ luồng chat |
| `app/services/advisory_service.py` | Luồng form + structured advice JSON | Ảnh hưởng luồng form |
| `app/services/chat_completion_gateway.py` | Gateway LLM: chọn proxy local (mode 1) hay Gemini trực tiếp (mode 2) | Cấu hình `CHATBOT_LLM_MODE` sai → gọi LLM thất bại |
| `app/api/*.py` | Các router: `health_routes`, `chat_routes`, `advisory_routes`, `intent_routes` (đều prefix `/api`) | Thiếu → mất endpoint tương ứng |
| `requirements.txt` | Dependencies Python | Thiếu package → import error khi chạy |
| `.env` | Chứa secret & cấu hình runtime (KHÔNG commit) | Thiếu → dùng default (local bolt/Qdrant), nhiều dịch vụ unavailable |
| `.env.example` | Mẫu biến môi trường (copy thành `.env`) | Tham chiếu để tạo `.env` |
| `Dockerfile` / `docker-compose.yml` / `render.yaml` | Đóng gói & deploy (image `python:3.12-slim`, chạy `uvicorn main:app`) | Sai → build/deploy fail |
| `scripts/ingest.py` | Nạp knowledge graph từ Excel vào Neo4j | Chưa chạy → graph rỗng, chat không có dữ liệu |
| `scripts/build_index_corpus.py` + `scripts/index_qdrant.py` | Build corpus & index lên Qdrant (+ BM25 sidecar) | Chưa chạy → retrieval vector rỗng |
| `scripts/reset_db_v2.py` | Tạo/tái tạo schema PostgreSQL v2 | Chưa chạy → bảng chưa có (app cũng tự `create_all` khi khởi động) |
| `data/bộ dữ liệu.xlsx` | **Nguồn dữ liệu graph chính** cho `ingest.py` | Thiếu → không ingest được graph |
| `data/index_corpus.jsonl`, `data/bm25_corpus.json`, `data/domain_aliases.json`, `data/enriched_descriptions.json` | Dữ liệu corpus/alias cho retrieval (Docker copy trực tiếp) | Thiếu → index/alias fail |
| `frontend/chat.html`, `form.html`, `index.html` + `js/`, `css/` | Giao diện web (fetch dùng `API_BASE=''` — cùng origin) | Thiếu → không có UI |

---

## 3. Biến môi trường & cấu hình cần thiết

Tạo file `.env` ở thư mục gốc bằng cách copy `.env.example`:

```powershell
Copy-Item .env.example .env
```

```bash
# Linux/macOS
cp .env.example .env
```

Sau đó điền các giá trị. Bảng dưới liệt kê **toàn bộ** biến (đối chiếu `.env.example` với `app/core/config.py`). Cột **Bắt buộc** = ✅ nghĩa là cần để hệ thống hoạt động cơ bản.

### 3.1. Nhóm bắt buộc / quan trọng

| Biến | Mô tả | Ví dụ (placeholder) | Bắt buộc |
|------|-------|---------------------|:--------:|
| `GEMINI_API_KEY` | Key Google Gemini (LLM + embedding). Lấy tại https://aistudio.google.com/apikey | `your-gemini-api-key` | ✅ |
| `NEO4J_URI` | URI Neo4j (Aura `neo4j+s://...` hoặc local `bolt://localhost:7687`) | `neo4j+s://xxxxxxxx.databases.neo4j.io` | ✅ |
| `NEO4J_USER` | User Neo4j | `neo4j` | ✅ |
| `NEO4J_PASSWORD` | Mật khẩu Neo4j | `your-neo4j-password` | ✅ |
| `QDRANT_URL` | URL cluster Qdrant (Cloud) hoặc `http://localhost:6333` | `https://xxxx.aws.cloud.qdrant.io` | ✅ |
| `QDRANT_API_KEY` | API key Qdrant Cloud (bỏ trống nếu Qdrant local không auth) | `your-qdrant-api-key` | ⚠️ (Cloud) |
| `QDRANT_COLLECTION` | Tên collection vector | `career_roadmap` | ✅ |
| `DATABASE_URL` | Connection string PostgreSQL/Neon (`?sslmode=require`). Để trống = session in-memory | `postgresql://USER:PASS@ep-xxx-pooler.region.aws.neon.tech/neondb?sslmode=require` | ⭕ (khuyến nghị) |

### 3.2. Cấu hình LLM (Router / Generator / Chat mode)

| Biến | Mô tả | Ví dụ / mặc định | Bắt buộc |
|------|-------|------------------|:--------:|
| `GEMINI_MODEL` | Model Gemini chính | `gemini-2.5-flash-lite` | ⭕ |
| `GEMINI_FALLBACK_MODELS` | Danh sách model fallback (phẩy) | `gemini-flash-lite-latest,gemini-2.5-flash` | ⭕ |
| `CHATBOT_LLM_MODE` | `1` = ưu tiên API local (proxy Gemini 3.5) rồi fallback Gemini; `2` = chỉ Gemini trực tiếp | `2` (an toàn nhất khi setup mới) | ⭕ |
| `CHATBOT_LOCAL_BASE_URL` | Base URL proxy OpenAI-compatible local (bắt buộc khi mode=1) | `http://localhost:8081/v1` | ⚠️ (mode 1) |
| `CHATBOT_LOCAL_API_KEY` | API key proxy local | `sk-chatbot-local` | ⭕ |
| `CHATBOT_LOCAL_MODEL` | Tên model proxy local | `gemini-3.5-flash-thinking@think=2` | ⭕ |
| `CHATBOT_LOCAL_TIMEOUT_SECONDS` | Timeout mỗi call proxy local | `60` (mặc định code `120`) | ⭕ |
| `ROUTER_MODEL` / `ROUTER_FALLBACK_MODELS` | Model cho Intent Router (trống = dùng `GEMINI_MODEL`) | trống | ⭕ |
| `ROUTER_TEMPERATURE` | Nhiệt độ router | `0.15` | ⭕ |
| `ROUTER_CAREER_FUZZY_THRESHOLD` | Ngưỡng fuzzy match tên nghề | `80` | ⭕ |
| `GENERATOR_MODEL` / `GENERATOR_FALLBACK_MODELS` | Model cho Generator (trống = dùng `GEMINI_MODEL`) | trống | ⭕ |
| `GENERATOR_TEMPERATURE` | Nhiệt độ generator | `0.7` | ⭕ |
| `GENERATOR_CONFIDENCE_THRESHOLD` | Ngưỡng confidence trả lời | `0.45` | ⭕ |
| `GENERATOR_RETRY_MAX_ATTEMPTS` | Số lần retry khi LLM lỗi tạm (503/timeout) | `2` | ⭕ |
| `GENERATOR_RETRY_BACKOFF_SECONDS` | Thời gian chờ giữa các lần retry | `2` | ⭕ |
| `OPENAI_API_KEY` / `OPENAI_MODEL` | OpenAI (tùy chọn) | trống / `gpt-4o-mini` | ⭕ |

### 3.3. Generator local (Ollama fine-tune — tùy chọn)

| Biến | Mô tả | Ví dụ / mặc định | Bắt buộc |
|------|-------|------------------|:--------:|
| `GENERATOR_BACKEND` | `auto` \| `gemini` \| `local` | `auto` | ⭕ |
| `USE_LOCAL_GENERATOR` | `1` = dùng Ollama fine-tune cho pathfinding/course_rec | `0` | ⭕ |
| `OLLAMA_BASE_URL` | URL Ollama | `http://localhost:11434` | ⚠️ (khi bật) |
| `OLLAMA_MODEL_PATHFINDING` | Model Ollama cho pathfinding | `career-pathfinding` | ⭕ |
| `OLLAMA_MODEL_COURSE_REC` | Model Ollama cho course_rec | `career-course-rec` | ⭕ |
| `OLLAMA_TIMEOUT_SECONDS` | Timeout Ollama | `60` (mặc định code `120`) | ⭕ |

### 3.4. Embedding

| Biến | Mô tả | Ví dụ / mặc định | Bắt buộc |
|------|-------|------------------|:--------:|
| `EMBEDDING_PROVIDER` | Provider embedding | `gemini` | ⭕ |
| `EMBEDDING_MODEL` | Model embedding | `gemini-embedding-001` | ⭕ |
| `EMBEDDING_API_KEY` | Key embedding (trống = dùng `GEMINI_API_KEY`) | trống | ⭕ |
| `EMBEDDING_DIMENSIONS` | Số chiều vector (phải khớp collection Qdrant) | `768` | ✅ (khớp) |

### 3.5. Retrieval / RRF fusion (đều có clamp an toàn trong code)

| Biến | Mô tả | Ví dụ / mặc định | Bắt buộc |
|------|-------|------------------|:--------:|
| `RETRIEVAL_GRAPH_BOOST` | Điểm cộng graph-aware rerank | `0.15` | ⭕ |
| `RETRIEVAL_RRF_K` | Hằng số RRF (clamp 20–80) | `60` | ⭕ |
| `RETRIEVAL_RRF_POOL_SIZE` | Pool size RRF (clamp 30–80) | `60` | ⭕ |
| `RETRIEVAL_MAX_EDGE_IN_TOP_K` | Số edge doc tối đa trong top-k (0–5) | `2` | ⭕ |
| `RETRIEVAL_STRICT` | `1` = eval fail-fast khi Qdrant/embedding lỗi; `0` = fallback (production) | `0` | ⭕ |

### 3.6. competency_relation (feature flag)

| Biến | Mô tả | Ví dụ / mặc định | Bắt buộc |
|------|-------|------------------|:--------:|
| `COMPETENCY_RELATION_ENRICH` | Enrich pathfinding/course_rec | `1` | ⭕ |
| `COMPETENCY_RELATION_INTENT_ENABLED` | Bật intent riêng (khi coverage ≥ 40%) | `1` | ⭕ |
| `COMPETENCY_RELATION_MIN_COVERAGE` | Ngưỡng coverage tối thiểu | `0.40` | ⭕ |
| `COMPETENCY_RELATION_ROUTE_THRESHOLD` | Ngưỡng scoring router | `3.0` | ⭕ |

### 3.7. LLM-as-Judge (chỉ cho eval — không cần để chạy app)

| Biến | Mô tả | Ví dụ / mặc định | Bắt buộc |
|------|-------|------------------|:--------:|
| `JUDGE_PROVIDER` | `gemini` \| `openai` \| `groq` \| `local` | `local` | ⭕ (eval) |
| `JUDGE_LOCAL_MODEL` | Model judge local (trống = `CHATBOT_LOCAL_MODEL`) | trống | ⭕ |
| `GROQ_API_KEY` / `JUDGE_GROQ_API_KEY` | Key Groq (https://console.groq.com/keys) | `your-groq-key` | ⭕ |
| `JUDGE_GROQ_MODEL` | Model Groq judge | `llama-3.1-8b-instant` | ⭕ |
| `JUDGE_GROQ_BASE_URL` | Base URL Groq | `https://api.groq.com/openai/v1` | ⭕ |
| `JUDGE_OPENAI_API_KEY` / `JUDGE_OPENAI_MODEL` | Judge OpenAI | trống / `gpt-4o-mini` | ⭕ |
| `JUDGE_GEMINI_API_KEY` / `JUDGE_GEMINI_MODEL` | Judge Gemini (trống = `GEMINI_API_KEY`) | trống / `gemini-2.5-flash-lite` | ⭕ |
| `JUDGE_REQUEST_DELAY_SECONDS` | Delay giữa các request judge (tránh rate limit) | `2.5` | ⭕ |

### 3.8. Khác

| Biến | Mô tả | Ví dụ / mặc định | Bắt buộc |
|------|-------|------------------|:--------:|
| `LOG_LEVEL` | `DEBUG`\|`INFO`\|`WARNING`\|`ERROR`\|`CRITICAL` | `INFO` | ⭕ |
| `DATABASE_ECHO` | Log SQL của SQLAlchemy | `false` | ⭕ |
| `SESSION_FILTER_AFTER` | Chỉ hiện phiên chat có `created_at >=` mốc (ISO-8601 UTC). Trống = không lọc | `2026-06-25T00:00:00Z` | ⭕ |

> ⚠️ **Biến dùng trong code nhưng KHÔNG có trong `.env.example`:**
> - `DOMAIN_ALIASES_PATH` — dùng ở `app/rag/aliases.py` để override đường dẫn file alias domain. Có default (`data/domain_aliases.json`) nên **không bắt buộc**, nhưng nên bổ sung vào `.env.example` để đầy đủ. Nếu muốn dùng file alias khác, khai báo biến này.

---

## 4. Các bước cài đặt và chạy dự án từ đầu

### 4.1. Yêu cầu hệ thống

| Thành phần | Phiên bản | Ghi chú |
|-----------|-----------|---------|
| **Python** | **3.12+** | Dockerfile dùng `python:3.12-slim`; docs yêu cầu 3.12+ |
| **Node.js** | ❌ Không cần | Frontend là HTML/CSS/JS tĩnh, phục vụ bởi FastAPI |
| **Docker** | Docker Desktop / Engine + Compose v2 | **Khuyến nghị (DOCKER-first)** — dựng cả app + Neo4j + Qdrant + PostgreSQL bằng 1 lệnh (xem mục 4.6) |
| **Neo4j** | Aura, local, hoặc **Docker** | Cần cho knowledge graph (DOCKER-first: tự dựng qua compose) |
| **Qdrant** | Cloud, local, hoặc **Docker** | Cần cho vector search (DOCKER-first: tự dựng qua compose) |
| **PostgreSQL** | Neon, local, hoặc **Docker** | Session/profile/feedback (DOCKER-first: tự dựng qua compose; không có → in-memory) |
| **Ollama** | Tùy chọn | Chỉ khi `USE_LOCAL_GENERATOR=1` |

### 4.2. Cài đặt dependencies (Python)

```powershell
# Windows PowerShell — tại thư mục gốc D:\Doantotnghiep
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

```bash
# Linux/macOS
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

> Gói `underthesea` (tách từ tiếng Việt cho BM25) khá nặng; nếu cài lỗi, code vẫn có fallback regex nên có thể bỏ qua tạm thời.

### 4.3. Tạo `.env`

```powershell
Copy-Item .env.example .env
# Mở .env và điền GEMINI_API_KEY, NEO4J_*, QDRANT_*, (tùy chọn) DATABASE_URL
```

### 4.4. Khởi tạo dữ liệu (chạy một lần)

**a) Nạp knowledge graph vào Neo4j** (cần `data/bộ dữ liệu.xlsx` và `NEO4J_*` trong `.env`):

```powershell
python scripts/ingest.py --xlsx-path "data/bộ dữ liệu.xlsx" --batch-size 500
# Nếu graph cũ dùng schema cũ → nạp lại sạch:
python scripts/ingest.py --xlsx-path "data/bộ dữ liệu.xlsx" --batch-size 500 --reset-graph
```

Kiểm tra sau ingest:

```powershell
python scripts/validate_ingest.py
python scripts/validate_graph_coverage.py --min-relation-edges 30
```

**b) Index corpus lên Qdrant** (cần `GEMINI_API_KEY` để embed + `QDRANT_*`):

```powershell
python scripts/build_index_corpus.py
python scripts/index_qdrant.py
```

**c) Tạo schema PostgreSQL** (nếu dùng `DATABASE_URL`):

```powershell
python scripts/reset_db_v2.py
```

> Ghi chú: app cũng tự chạy `Base.metadata.create_all` khi khởi động (`init_database` trong `app/db/engine.py`), nên bước (c) chủ yếu để reset sạch. Xóa **chỉ dữ liệu** (giữ schema): `python scripts/clear_postgres_data.py --yes`.

### 4.5. Chạy backend + frontend

Frontend được FastAPI phục vụ tĩnh, nên chỉ cần chạy backend:

```powershell
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
# hoặc dùng script có sẵn:
.\scripts\run_dev.ps1
```

Các trang:

| Trang | URL |
|-------|-----|
| Landing | http://127.0.0.1:8000/ |
| Chat | http://127.0.0.1:8000/chat.html |
| Form tư vấn | http://127.0.0.1:8000/form.html |
| API docs (Swagger) | http://127.0.0.1:8000/docs |
| Health check | http://127.0.0.1:8000/api/health |

### 4.6. Chạy bằng Docker — DOCKER-FIRST (khuyến nghị) 🐳

Cách này dựng **toàn bộ hệ thống bằng Docker**: app FastAPI + **Neo4j** + **Qdrant** + **PostgreSQL** — không cần cài Python/DB thủ công. Đây là cách nhanh và nhất quán nhất để chạy dự án.

**File liên quan:** `docker-compose.yml`, `Dockerfile`, `.dockerignore` (đã có ở thư mục gốc).

#### a) Chuẩn bị `.env`

```powershell
Copy-Item .env.example .env
# Chỉ BẮT BUỘC điền GEMINI_API_KEY (dùng cho LLM + embedding).
# KHÔNG cần sửa NEO4J_URI / QDRANT_URL / DATABASE_URL cho Docker:
#   compose TỰ ĐỘNG ghi đè chúng để trỏ tới các service neo4j / qdrant / postgres.
```

> Mật khẩu DB local (tùy chọn) trong `.env`: `NEO4J_LOCAL_PASSWORD`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`. Bỏ trống sẽ dùng default dev (`neo4jpassword`, `career/careerpass/careerdb`).

#### b) Dựng và chạy tất cả service

```powershell
docker compose up -d --build
```

Các service & cổng:

| Service | Image | Cổng (host → container) | Ghi chú |
|---------|-------|-------------------------|---------|
| `app` | build từ `Dockerfile` (`python:3.12-slim`, chạy `uvicorn main:app`) | `8000 → 8000` | API + frontend tĩnh |
| `neo4j` | `neo4j:5-community` | `7474 → 7474` (Browser), `7687 → 7687` (Bolt) | Bật sẵn plugin **APOC**, volume giữ dữ liệu |
| `qdrant` | `qdrant/qdrant` | `6333 → 6333` (REST), `6334 → 6334` (gRPC) | Volume `qdrant_data` |
| `postgres` | `postgres:16` | `5432 → 5432` | Volume `postgres_data` |

> Nếu cổng `5432` (hoặc `7474/7687/6333`) đang bị chiếm bởi DB cài sẵn trên máy, đổi vế trái mapping trong `docker-compose.yml`, ví dụ `"5433:5432"` (chỉ đổi cổng host — app trong mạng Docker vẫn nối `postgres:5432`).

#### c) Kiểm tra container & health

```powershell
docker compose ps            # trạng thái + (healthy) của từng container
docker compose logs -f app   # log realtime của app (Ctrl+C để thoát)
```

`app` chỉ khởi động sau khi `neo4j` và `postgres` **healthy** (khai báo `depends_on` + `healthcheck`). Đợi ~30–60s cho lần đầu.

#### d) Khởi tạo dữ liệu **BÊN TRONG container app** (chạy một lần)

Script `ingest.py`, `build_index_corpus.py`, `index_qdrant.py` đã được đóng gói vào image cùng `data/`. Chạy qua `docker compose exec`:

```powershell
# 1) Nạp knowledge graph vào Neo4j (dùng data/bộ dữ liệu.xlsx trong image)
docker compose exec app python scripts/ingest.py --xlsx-path "data/bộ dữ liệu.xlsx" --batch-size 500 --reset-graph

# 2) Kiểm tra ingest
docker compose exec app python scripts/validate_ingest.py

# 3) Build corpus + index lên Qdrant (cần GEMINI_API_KEY để embed)
docker compose exec app python scripts/build_index_corpus.py
docker compose exec app python scripts/index_qdrant.py

# 4) (tùy chọn) tạo/reset schema PostgreSQL — app cũng tự create_all khi khởi động
docker compose exec app python scripts/reset_db_v2.py
```

> Vì `.env` **không** được nạp vào image (đã loại trong `.dockerignore`), các script chạy trong container sẽ dùng đúng biến môi trường của service `app` (host DB = tên service), không bị `.env` cloud ghi đè.

#### e) Reset dữ liệu

```powershell
# Chỉ xóa dữ liệu bảng Postgres (giữ schema)
docker compose exec app python scripts/clear_postgres_data.py --yes
# Nạp lại graph sạch
docker compose exec app python scripts/ingest.py --xlsx-path "data/bộ dữ liệu.xlsx" --batch-size 500 --reset-graph
# Xóa SẠCH toàn bộ (cả volume DB) rồi dựng lại từ đầu:
docker compose down -v ; docker compose up -d --build
```

#### f) Health check API & xem log

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/health   # PowerShell
# curl http://127.0.0.1:8000/api/health              # nếu có curl
docker compose logs -f neo4j qdrant postgres          # log các DB
```

Kỳ vọng `checks.neo4j = "ok"`, `checks.qdrant = "ok"`, `checks.postgres = "ok"`, `checks.gemini = "configured"`. Truy cập UI tại http://127.0.0.1:8000/ , Neo4j Browser tại http://localhost:7474 (user `neo4j`, mật khẩu = `NEO4J_LOCAL_PASSWORD`).

#### g) Mapping biến môi trường khi chạy Docker (host = tên service, KHÔNG phải localhost)

`docker-compose.yml` ghi đè các biến sau cho service `app` (thắng giá trị trong `.env`):

| Biến | Giá trị trong Docker | Ý nghĩa |
|------|----------------------|---------|
| `NEO4J_URI` | `bolt://neo4j:7687` | Trỏ tới service `neo4j` (không phải `localhost`) |
| `NEO4J_USER` / `NEO4J_PASSWORD` | `neo4j` / `${NEO4J_LOCAL_PASSWORD}` | Khớp `NEO4J_AUTH` của service neo4j |
| `QDRANT_URL` | `http://qdrant:6333` | Trỏ tới service `qdrant` |
| `QDRANT_API_KEY` | *(rỗng)* | Qdrant local không cần auth |
| `DATABASE_URL` | `postgresql://<user>:<pass>@postgres:5432/<db>` | Trỏ tới service `postgres`, **không** dùng `sslmode=require` |

Các biến còn lại (`GEMINI_API_KEY`, `EMBEDDING_*`, `CHATBOT_*`, `GENERATOR_*`, `QDRANT_COLLECTION`...) đọc từ `.env` qua `env_file`.

#### h) Biến thể: chỉ chạy app trong Docker, DB dùng cloud

Nếu muốn dùng Neo4j Aura + Qdrant Cloud + Neon (không dựng DB local), chỉ build & chạy service `app` với DB cloud khai trong `.env`:

```powershell
docker build -t career-graph-rag .
docker run --rm -p 8000:8000 --env-file .env career-graph-rag
```

> Cách này bỏ qua các override trong compose nên `NEO4J_URI/QDRANT_URL/DATABASE_URL` lấy trực tiếp từ `.env` (giá trị cloud).

### 4.7. Dịch vụ phụ (tùy chọn)

- **Ollama** (khi `USE_LOCAL_GENERATOR=1`): cài Ollama, `ollama serve`, rồi tạo model từ `colab_LLM/Modelfile.pathfinding` và `colab_LLM/Modelfile.course_rec`:
  ```powershell
  ollama create career-pathfinding -f colab_LLM/Modelfile.pathfinding
  ollama create career-course-rec  -f colab_LLM/Modelfile.course_rec
  ```
- **Proxy LLM local (`CHATBOT_LLM_MODE=1`)**: cần một API OpenAI-compatible chạy tại `CHATBOT_LOCAL_BASE_URL` (ví dụ notebook `colab_LLM/main_fixed.ipynb`). Nếu **không có proxy**, đặt `CHATBOT_LLM_MODE=2` để dùng thẳng Gemini.

### 4.8. Kiểm tra đã chạy đúng (health check)

```powershell
curl http://127.0.0.1:8000/api/health
# PowerShell thuần: Invoke-RestMethod http://127.0.0.1:8000/api/health
```

Kỳ vọng JSON: `status: "ok"` (hoặc `degraded`), với `checks.neo4j = "ok"`, `checks.qdrant = "ok"`, `checks.gemini = "configured"`. Chỉ số `critical` = Neo4j ok **và** (Gemini configured hoặc chatbot_local ok).

Test nhanh trên chat: gõ `Làm Backend Developer cần học những gì?` → kỳ vọng trả về lộ trình kỹ năng (intent `pathfinding`). Xem thêm kịch bản mẫu trong `docs/HUONG_DAN_DEMO.md`.

### 4.9. Chạy test

```powershell
python -m pytest tests/ -q --tb=short
```

Kỳ vọng ≥ 300 test pass (theo `docs/HUONG_DAN_KIEM_TRA_LAI.md`). Một số test eval/retrieval cần Neo4j/Qdrant có dữ liệu; test unit thuần thì không.

---

## 5. Thí nghiệm & Đánh giá (D-01 / D-02 / D-03)

Đề tài dùng **bộ metric tùy biến** (không dùng RAGAS nguyên bản) theo ba trục đánh giá bổ sung cho nhau. Tài liệu chi tiết: **`docs/HUONG_DAN_THI_NGHIEM_D01_D02_D03.md`** (giải thích metric + gợi ý phản biện) và **`docs/HUONG_DAN_KIEM_TRA_LAI.md`** (playbook tái lập). Số liệu chi tiết ở `ket_qua_thuc_nghiem.md`.

| Mã | Tên | Tầng đo | Tập gold | Script chính |
|----|-----|---------|----------|--------------|
| **D-01** | Ablation chất lượng Graph-RAG | Context fusion + grounding (4 nhánh fusion) | 80 case (`data/eval/answer_gold_v2.jsonl`) | `scripts/run_quality_ablation.py` |
| **D-02** | Đánh giá retrieval | Truy hồi hybrid Qdrant + BM25 + RRF | 248 query (`data/eval/retrieval_gold.jsonl`) | `scripts/eval_retrieval.py` |
| **D-03** | Đánh giá E2E LLM-as-a-Judge | Pipeline đầy đủ (router → Graph-RAG → generator) | 52 case (`data/eval/answer_quality_gold.jsonl`) | `scripts/eval_answer_quality.py` |

> **Điều kiện tiên quyết cho cả 3 bài:** đã ingest Neo4j + index Qdrant (mục 4.4) và cấu hình `.env` (`NEO4J_*`, `QDRANT_*`, `GEMINI_API_KEY`; D-03 cần thêm judge — khuyến nghị `JUDGE_PROVIDER=local`).

### 5.1. D-01 — Ablation chất lượng Graph-RAG

**Mục tiêu:** so sánh 4 cấu hình fusion (**vector_only / graph_only / late_fusion / tight_fusion**) trên cùng tập gold để chứng minh tight fusion (cấu hình đề tài) tốt hơn RAG vector thuần. Pipeline **không** đi qua intent router (cô lập ảnh hưởng fusion). Hai chế độ chấm: `static` (formatter tĩnh, mặc định) và `generative` (LLM sinh + cosine với gold).

**Lệnh chạy (PowerShell):**

```powershell
# Profile v4 (mặc định, 3 lớp metric — dùng cho báo cáo luận văn)
python scripts/run_quality_ablation.py --metrics-profile v4 --gold data/eval/answer_gold_v2.jsonl --json-out results/ablation_d01_v4.json

# Profile v3 (legacy — một bảng)
python scripts/validate_gold.py data/eval/answer_gold.jsonl
python scripts/run_quality_ablation.py --eval-mode static --metrics-profile v3
python scripts/run_quality_ablation.py --gold data/eval/answer_gold_independent.jsonl --metrics-profile v3 --json-out results/ablation_d01_v3_independent.json

# Chế độ generative (LLM sinh — chậm, giới hạn số case để thử)
python scripts/run_quality_ablation.py --eval-mode generative --limit 5
```

```bash
# Linux/macOS — thay dấu backtick (nếu có) bằng \ ; lệnh trên một dòng không cần đổi
python scripts/run_quality_ablation.py --metrics-profile v4 --gold data/eval/answer_gold_v2.jsonl --json-out results/ablation_d01_v4.json
```

**Kết quả sinh ra:** `results/ablation_d01_v4.json` (+ `.tex`), `results/ablation_d01_v3_static.json` (+ `.tex`). So sánh nhiều lần chạy: `python scripts/compare_ablation_runs.py`.

**Chỉ số chính:** `answer_entity_f1`, `ontology_f1`, `graph_entity_grounding`, `off_graph_mention_rate` (hàm `skill_f1()` trong `app/eval/quality_metrics.py`).

**Pytest liên quan:**

```powershell
python -m pytest tests/test_ablation_d01.py tests/test_ablation_pipeline.py tests/test_quality_metrics.py -v
```

### 5.2. D-02 — Đánh giá retrieval

**Mục tiêu:** đo tầng truy hồi (Qdrant + BM25 + RRF + graph-aware rerank) **độc lập với LLM generator**. Thiết lập chuẩn: `k = 5`, N = 248, `RETRIEVAL_STRICT=1` (script tự set).

**Lệnh chạy (PowerShell):**

```powershell
python scripts/eval_retrieval.py --k 5 --output-csv data/eval/retrieval_results.csv
python scripts/analyze_gold_triviality.py
```

**Kết quả sinh ra:** `data/eval/retrieval_results.csv`.

**Chỉ số chính:** HitRate@5, RecallFull@5, MAP@5, MRR, nDCG@5.
**KPI tham chiếu (v2.1):** HitRate@5 overall ≥ 58%; RecallFull@5 competency ≥ 45%.

**Pytest liên quan:**

```powershell
python -m pytest tests/test_eval_retrieval.py tests/test_retrieval_metrics.py tests/test_retrieval_metrics_graded.py tests/test_retrieval_strict.py -v
```

### 5.3. D-03 — Đánh giá E2E (LLM-as-a-Judge)

**Mục tiêu:** chạy **pipeline đầy đủ** qua `ChatService` (intent router → orchestrator → Graph-RAG → generator) rồi để một LLM trọng tài riêng (Judge) chấm faithfulness / skill completeness / no-hallucination. Mỗi lượt gắn nhãn `valid_run` / `route_mismatch` / `infra_error` — chỉ `valid_run` vào aggregate.

**Lệnh chạy (PowerShell):**

```powershell
# 0) Smoke judge trước (bắt buộc) — kiểm tra provider judge hoạt động
python scripts/smoke_judge.py

# 1) Chạy E2E full 52 case (khuyến nghị JUDGE_PROVIDER=local để tránh 413/503)
$env:JUDGE_PROVIDER="local"
python scripts/eval_answer_quality.py `
  --gold data/eval/answer_quality_gold.jsonl `
  --output-csv data/eval/answer_quality_results.csv `
  --report-json results/eval_summary.json `
  --run-label v2.2-D2 `
  --delay 2.5

# 2) Tổng hợp so với baseline
python scripts/summarize_eval_results.py `
  --report-json results/eval_summary.json `
  --baseline results/baseline_pre_router_v22.json `
  --out results/verification_summary_v22.json
```

```bash
# Linux/macOS
JUDGE_PROVIDER=local python scripts/eval_answer_quality.py \
  --gold data/eval/answer_quality_gold.jsonl \
  --output-csv data/eval/answer_quality_results.csv \
  --report-json results/eval_summary.json \
  --run-label v2.2-D2 --delay 2.5
```

Cohort rút gọn: `data/eval/answer_quality_gold_v21_38.jsonl` (38 case), `..._baseline14.jsonl` (regression nhanh ~5 phút), `..._v22_new14.jsonl`.

**Kết quả sinh ra:** `results/eval_summary.json`, `data/eval/answer_quality_results.csv`, `results/post_fix_v21_38.*`, `results/baseline_pre_router_v22.*`.

**Chỉ số chính:** Faithfulness, Skill completeness, No-hallucination rate, Valid citation rate, valid_run/route_mismatch/infra_error rate.

**Pytest liên quan:**

```powershell
python -m pytest tests/test_eval_answer_quality.py tests/test_eval_route_validity.py tests/test_llm_judge.py tests/test_build_answer_quality_gold.py -v
```

### 5.4. Chạy gộp một lệnh (verification playbook)

```powershell
.\scripts\run_full_verification.ps1
# Chỉ baseline:        .\scripts\run_full_verification.ps1 -BaselineOnly
# Chỉ D1 38 case:      .\scripts\run_full_verification.ps1 -PostFix38 -SkipBuildGold
```

Script này gom pytest → build/validate gold → D-02 retrieval → D-03 E2E. Chi tiết từng bước và ngưỡng KPI: `docs/HUONG_DAN_KIEM_TRA_LAI.md`.

---

## 6. Các lỗi thường gặp khi setup và cách xử lý

> Dựa trên ghi chú thực tế trong `docs/HUONG_DAN_DEMO.md`, `docs/HUONG_DAN_KIEM_TRA_LAI.md`, `ket_qua_thuc_nghiem.md` và cách xử lý lỗi trong code.

| Triệu chứng | Nguyên nhân | Cách xử lý |
|-------------|-------------|------------|
| `/api/health` → `neo4j: unavailable` | Sai `NEO4J_URI/USER/PASSWORD`, dùng `neo4j+s://` cho Aura hay `bolt://` cho local | Kiểm tra credentials; **dùng đúng tên biến `NEO4J_USER`** (không phải `NEO4J_USERNAME`) |
| `/api/health` → `qdrant: unavailable` / `http 4xx` | Sai `QDRANT_URL/API_KEY` hoặc chưa index | Kiểm tra cluster URL + API key; chạy `build_index_corpus.py` + `index_qdrant.py` |
| Course card trống / chat thiếu dữ liệu | Chưa ingest graph hoặc chưa index Qdrant | Chạy `scripts/ingest.py` rồi `scripts/index_qdrant.py`; kiểm tra `/api/health` |
| Bubble đỏ / lỗi **503** / quota khi chat | LLM (Gemini) 503 hoặc hết quota | Bấm **Thử lại** trên UI; kiểm tra `GEMINI_API_KEY`; code tự retry theo `GENERATOR_RETRY_*` và fallback model |
| Judge lỗi **413** (payload too large) khi eval `skills_gap` | Context/request quá lớn với judge Groq (ghi nhận ở 3 case `sg_be_02`, `sg_ds_02`, `sg_cloud_02`) | Dùng `JUDGE_PROVIDER=local`; **delay lớn hơn KHÔNG khắc phục** (là lỗi kích thước, không phải rate limit) |
| Không có lịch sử chat ở sidebar | `DATABASE_URL` chưa cấu hình → session in-memory | Cấu hình `DATABASE_URL` (Neon) rồi `python scripts/reset_db_v2.py`; vẫn chat được nếu không cần persist |
| PostgreSQL kết nối lỗi khi khởi động | Connection string sai / thiếu SSL | Neon cần `?sslmode=require`; code tự đổi sang `postgresql+asyncpg` và bật SSL. App vẫn chạy (fallback in-memory) và log warning |
| `chatbot_local: unavailable` ở health | `CHATBOT_LLM_MODE=1` nhưng proxy local (`CHATBOT_LOCAL_BASE_URL`) không chạy | Bật proxy tại `localhost:8081`, hoặc đặt `CHATBOT_LLM_MODE=2` để dùng Gemini trực tiếp |
| Retrieval trả kết quả lệch chiều / lỗi vector | `EMBEDDING_DIMENSIONS` không khớp collection Qdrant | Đảm bảo `EMBEDDING_DIMENSIONS=768` khớp lúc tạo collection; re-index nếu đổi model |
| Trả lời lệch intent | Câu hỏi mơ hồ / thiếu ngữ cảnh | Tạo chat mới, hỏi rõ (có tên nghề / công nghệ) |
| Cài `underthesea` lỗi | Package nặng, phụ thuộc build | Bỏ qua tạm — BM25 có fallback regex tách từ |
| `RESOURCE_EXHAUSTED` khi index Qdrant | Gemini embedding rate limit | Chạy lại `index_qdrant.py`; giảm tốc độ / thử lại sau |

---

## 7. Cấu trúc thư mục dự án

```text
Doantotnghiep/
├── app/                        # Backend FastAPI (source chính)
│   ├── main.py                 # Entry point: khởi tạo app, include router, mount frontend
│   ├── api/                    # Router HTTP: health, chat, advisory, intent (prefix /api)
│   ├── core/                   # config.py (Settings/env), logging_config.py
│   ├── db/                     # engine async, models, repository (PostgreSQL)
│   ├── graph/                  # Neo4j client, queries, formatters, subject↔career
│   ├── rag/                    # retriever, embeddings, qdrant_client, fusion (RRF), BM25, aliases
│   ├── intent/                 # Intent Router (Bước 1): parser, router, career matcher
│   ├── generator/              # Response Generator (Bước 4): prompts, validator
│   ├── services/               # Orchestrator: chat_service, advisory_service, gateway LLM
│   ├── session/                # Quản lý phiên (store, memory, context, follow-up)
│   ├── response/               # Shape API + structured cards
│   ├── advice/                 # Schema advice JSON (form)
│   └── eval/                   # Metric eval: retrieval, quality, ablation, LLM judge
├── backend/
│   └── main.py                 # Alias app cho Docker (uvicorn main:app)
├── frontend/                   # UI tĩnh (phục vụ bởi FastAPI)
│   ├── index.html, chat.html, form.html
│   ├── css/  (index/chat/form.css)
│   └── js/   (chat.js, form.js, theme.js)  # fetch dùng API_BASE=''
├── scripts/                    # Script vận hành & eval
│   ├── ingest.py               # Nạp graph từ Excel vào Neo4j
│   ├── build_index_corpus.py + index_qdrant.py   # Build & index Qdrant + BM25
│   ├── reset_db_v2.py, clear_postgres_data.py     # Quản lý schema/dữ liệu Postgres
│   ├── validate_*.py           # Kiểm tra ingest / graph coverage / gold
│   ├── eval_*.py, run_*.py     # Đánh giá chất lượng / retrieval / ablation
│   ├── run_dev.ps1             # Khởi động uvicorn (Windows)
│   └── docker-entrypoint.sh    # Entrypoint container
├── data/                       # Dữ liệu nguồn
│   ├── bộ dữ liệu.xlsx          # Nguồn graph chính cho ingest
│   ├── index_corpus.jsonl, bm25_corpus.json       # Corpus retrieval
│   ├── domain_aliases.json, enriched_descriptions.json
│   ├── ft_*.jsonl              # Dataset fine-tune Ollama
│   └── eval/                   # Gold set cho eval
├── tests/                      # ~70+ file pytest (unit + eval)
├── colab_LLM/                  # Modelfile Ollama + notebook proxy LLM local
├── docs/                       # HUONG_DAN_DEMO, HUONG_DAN_KIEM_TRA_LAI, llm_placement...
├── design/                     # Sơ đồ (mermaid, excalidraw) chương 3
├── logs/, results/             # Log & kết quả eval
├── lib/                        # Thư viện JS tĩnh (vis, tom-select) cho visualize graph
├── .env.example                # Mẫu biến môi trường (copy thành .env)
├── .env                        # ⚠️ Secret thật — KHÔNG commit
├── requirements.txt            # Dependencies Python
├── Dockerfile, docker-compose.yml, render.yaml    # Đóng gói & deploy
└── README.md                   # README gốc (deploy Render, Qdrant/Neo4j/Neon)
```

---

### Tham chiếu nhanh

- Kịch bản demo trên web: `docs/HUONG_DAN_DEMO.md`
- Thí nghiệm D-01/D-02/D-03 (metric + phản biện): `docs/HUONG_DAN_THI_NGHIEM_D01_D02_D03.md`
- Tái lập kết quả thực nghiệm (pytest, gold, E2E eval): `docs/HUONG_DAN_KIEM_TRA_LAI.md`
- Vị trí đặt LLM (router/generator/judge): `docs/llm_placement.md`
- Deploy Render + hướng dẫn Qdrant/Neo4j/Neon: `README.md`
