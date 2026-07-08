# CODEBASE MAP — IT Career Goal Advisor (Graph-RAG)

> Tài liệu bản đồ codebase cho dự án tại `d:\Doantotnghiep`.
> Mục đích: giúp dev và AI agent nắm nhanh kiến trúc + vai trò từng file mà **không phải đọc lại toàn bộ source**, tiết kiệm token.
> Toàn bộ nội dung dưới đây được **xác minh trực tiếp từ code** (không phỏng đoán). Bỏ qua `__pycache__`, `.pytest_cache`, `.pyc`, `files.zip`.

---

## Mục lục

1. [Tổng quan kiến trúc](#1-tổng-quan-kiến-trúc)
2. [Bản đồ từng file](#2-bản-đồ-từng-file)
   - [2.1 `app/` (root)](#21-app-root)
   - [2.2 `app/api/`](#22-appapi)
   - [2.3 `app/core/`](#23-appcore)
   - [2.4 `app/db/`](#24-appdb)
   - [2.5 `app/graph/` (+ `queries/`)](#25-appgraph--queries)
   - [2.6 `app/intent/`](#26-appintent)
   - [2.7 `app/rag/`](#27-apprag)
   - [2.8 `app/generator/`](#28-appgenerator)
   - [2.9 `app/services/`](#29-appservices)
   - [2.10 `app/session/`](#210-appsession)
   - [2.11 `app/advice/` & `app/response/`](#211-appadvice--appresponse)
   - [2.12 `app/utils/`](#212-apputils)
   - [2.13 `app/eval/`](#213-appeval)
3. [Công cụ Database](#3-công-cụ-database)
4. [Các công cụ khác (RAG, Graph, LLM, Intent, Session, Scripts, Data)](#4-các-công-cụ-khác)
5. [Cấu hình & môi trường](#5-cấu-hình--môi-trường)
6. [Tests](#6-tests)

---

## 1. Tổng quan kiến trúc

**Hệ thống làm gì:** Chatbot **tư vấn hướng nghiệp IT** dùng kiến trúc **Graph-RAG (tight fusion)**. Người dùng hỏi về lộ trình nghề (pathfinding), khóa học (course recommendation), liên kết môn học–nghề (subject_career), hoặc điền form để nhận tư vấn có cấu trúc. Hệ thống kết hợp **knowledge graph (Neo4j)** làm ground-truth, **hybrid retrieval (Qdrant + BM25Okapi + RRF + graph-aware boost)** làm bằng chứng bổ sung, và **LLM (Gemini, tùy chọn Ollama local)** để sinh câu trả lời tự nhiên.

**Các tầng/module chính:**

| Tầng | Thư mục | Vai trò |
|---|---|---|
| API (FastAPI) | `app/api/` | Expose endpoint chat/advisory/intent/health |
| Orchestration | `app/services/` | Điều phối luồng: intent → graph → rag → generator |
| Intent routing | `app/intent/` | Phân loại ý định bằng Gemini (JSON) + fuzzy career matching |
| Knowledge Graph | `app/graph/` | Truy vấn Neo4j: pathfinding, course rec, skills gap |
| RAG | `app/rag/` | Query expansion, vector search (Qdrant), hybrid rerank, fusion |
| Generation | `app/generator/` | Sinh reply (Gemini/Ollama), prompt, validator chống hallucination |
| Session | `app/session/` | Trạng thái phiên (Postgres-backed hoặc in-memory) |
| Persistence | `app/db/` | PostgreSQL (SQLAlchemy async + asyncpg): profile/session/message/feedback/advice |
| DTO phản hồi | `app/response/`, `app/advice/` | Structured reply cho frontend + JSON schema tư vấn |

**Luồng xử lý chính (một lượt chat — async):**

```
POST /api/chat
  └─ ChatService.handle_message(message, session_id)
       ├─ 1. Session: get_or_create(session_id)  → SessionState (Postgres hoặc in-memory)
       ├─ 2. Intent: build_router_user_message → IntentRouterService.route()
       │        → GeminiRouterClient.classify() (JSON, temp thấp) → parse_route_json()
       │        → fuzzy chuẩn hóa career (CareerMatcher) → maybe_adjust_outcome() → apply_route_to_state()
       ├─ 3. Phân nhánh intent (_answer_from_intent):
       │        • subject_career → GraphRepository.subject_to_careers (IN_SUBJECT multi-hop)
       │                       → format_subject_career_reply (không qua LLM chính)
       │        • pathfinding / course_rec → VectorRetriever.retrieve_docs TRƯỚC (A-01)
       │                       → map_hits_to_graph_nodes → graph_seed_ids
       │                       → GraphRepository.pathfinding / course_recommendation (seed boost Cypher)
       │                       → extract_relevant_ids_from_graph → graph-aware rerank (A-03)
       │                       + ExemplarRetriever + FusionService.aggregate(graph_seed_ids=...)
       │                       → ResponseGenerator (Gemini/Ollama + gate confidence)
       │        • roadmap_followup → RoadmapFollowupService.build (advice + typed gap
       │                       + courses_for_career_skills multi-hop A-02, một query Neo4j)
       │        • competency_slot_fill → CompetencyTypeOrchestrator (7 nhóm, apply_skills_gap_typed)
       │        • slot_fill → generator.slot_fill (hỏi ngược thu thập slot)
       ├─ 4. structured_from_* → StructuredReply + plain_text fallback
       └─ 5. _finalize_llm_meta (gắn generator_backend + llm_router) → save(state) → trả response
```

**Luồng form tư vấn (riêng):** `POST /api/advisory/start` → `AdvisoryService.submit_advisory_form` → tạo profile + session → `GraphContextBuilder` lấy context Neo4j → gọi **Gemini structured output** (`response_schema = ADVICE_RESULT_JSON_SCHEMA`) → lưu `advice_results`.

**Stack đã xác minh:**
- **Graph DB:** Neo4j (driver đồng bộ `neo4j.GraphDatabase`, bolt/neo4j+s) — ⚠️ chưa async (E-02).
- **Relational DB:** PostgreSQL (Neon) qua SQLAlchemy async + `asyncpg`.
- **Vector store:** Qdrant (collection `career_roadmap`).
- **LLM mặc định:** Google **Gemini** (`gemini-2.5-flash-lite`) qua SDK `google.genai`; tùy chọn **Ollama local** cho pathfinding/course_rec.
- **Embedding:** Gemini `gemini-embedding-001` (768 chiều), có thể chuyển OpenAI.
- **Web framework:** FastAPI (+ static frontend mount).

---

## 2. Bản đồ từng file

> Định dạng mỗi file: **Mục đích** → **Class/function chính** → **Phụ thuộc / được gọi bởi**.

### 2.1 `app/` (root)

#### `app/main.py`
- **Mục đích:** Điểm khởi tạo FastAPI app. Gọi `setup_logging` trước khi tạo app; đăng ký 4 router; init/close PostgreSQL trong `lifespan`; mount static frontend.
- **Chính:** `setup_logging(settings.log_level)` (E-01), `lifespan()` (init/close DB), `app = FastAPI(...)`, `include_router(advisory/chat/health/intent)`, mount `StaticFiles` từ thư mục `frontend/`.
- **Phụ thuộc:** `app.api.*`, `app.core.logging_config`, `app.db.engine` (`init_database`, `close_database`). Là entrypoint khi chạy `uvicorn app.main:app`.

### 2.2 `app/api/`

Tất cả module khai báo `router = APIRouter(...)`, gắn vào app qua `app.include_router(...)`.

#### `app/api/chat_routes.py`
- **Mục đích:** Router chat chính (`prefix="/api"`). Hội thoại, quản lý session, lịch sử, greeting, feedback. Lazy-init singleton `ChatService` + `FeedbackRepository`.
- **Chính:** Models `ChatRequest`, `ChatResponse` (reply, action, structured, evidence, generator_backend, llm_router…), `FeedbackRequest`. Endpoints: **`GET /api/chat/greeting`**, **`GET /api/session/{id}`**, **`GET /api/session/{id}/messages`**, **`GET /api/sessions`**, **`POST /api/chat`** → `handle_message()`, **`POST /api/chat/messages/{message_id}/feedback`** (yêu cầu `database_enabled()`, rating ∈ {-1,+1}).
- **Phụ thuộc:** `app.services.chat_service.ChatService`, `app.db.feedback_repository`, `app.db.engine.database_enabled`. Gọi bởi frontend chat.

#### `app/api/advisory_routes.py`
- **Mục đích:** Router form khởi tạo tư vấn (`prefix="/api/advisory"`). Nhận hồ sơ (background, role, skills, goals, weekly_time…), validate enum, tạo profile+session+advice, tìm/gợi ý role từ Neo4j.
- **Chính:** `AdvisoryStartRequest(BaseModel)` (+ `@field_validator`), helpers `_parse_background/_parse_role/_parse_weekly_time` (raise 422), `get_advisory_service()`. Endpoints: **`POST /api/advisory/start`** → `start_advisory()`; **`GET /api/advisory/session/{id}/advice`** → cache advice; **`GET /api/advisory/roles/search`** → `search_roles()`.
- **Phụ thuộc:** `app.services.advisory_service.AdvisoryService`, `app.db.enums`. Gọi bởi form frontend.

#### `app/api/intent_routes.py`
- **Mục đích:** Router phân loại ý định độc lập (debug) (`prefix="/api"`). Chạy intent router theo ngữ cảnh phiên, cập nhật state, trả route.
- **Chính:** `RouteRequest(BaseModel)`; **`POST /api/route`** → `route_intent()`.
- **Phụ thuộc:** `app.intent.router.IntentRouterService`, `app.session.context`, `app.session.repository.create_session_repository`.

#### `app/api/health_routes.py`
- **Mục đích:** Health check (`prefix="/api"`) — kiểm tra Neo4j, PostgreSQL, Gemini, Ollama, local generator, Qdrant.
- **Chính:** **`GET /api/health`** → `health_check()` trả `{"status": "ok"|"degraded", "checks": {...}}` (critical khi neo4j ok + gemini configured).
- **Phụ thuộc:** `app.core.config.settings`, `app.db.engine`, `app.graph.neo4j_client.Neo4jClient`, `app.rag.qdrant_client.qdrant_http_headers`, `app.services.generator_backend.generator_status`, `httpx`.

### 2.3 `app/core/`

#### `app/core/config.py`
- **Mục đích:** Cấu hình tập trung qua pydantic `Settings`, đọc từ `.env` (`load_dotenv(override=True)`). Chuẩn hóa `DATABASE_URL` thành `postgresql+asyncpg://`.
- **Chính:** `Settings(BaseModel)` (toàn bộ env: Gemini/router/generator, Ollama, OpenAI, embedding, Neo4j, Qdrant, retrieval, judge, database…), helpers `_env/_env_bool/_env_float`, `_normalize_database_url()`. Export singleton `settings`.
- **Phụ thuộc:** Được import gần như toàn bộ codebase. Xem chi tiết ở [mục 5](#5-cấu-hình--môi-trường).

#### `app/core/logging_config.py`
- **Mục đích:** Cấu hình logging chuẩn cho toàn app (E-01) — thay ghi file debug ad-hoc.
- **Chính:** `setup_logging(log_level)` — set level root logger + `StreamHandler` stdout, format `%(asctime)s %(levelname)s [%(name)s] %(message)s`.
- **Phụ thuộc:** stdlib `logging`. Gọi từ `app/main.py` với `settings.log_level` (`LOG_LEVEL`, mặc định `INFO`).

### 2.4 `app/db/`

> PostgreSQL qua **SQLAlchemy async + asyncpg**. Chi tiết DB ở [mục 3](#3-công-cụ-database).

| File | Mục đích | Class/function chính |
|---|---|---|
| `engine.py` | Quản lý engine/session async, xử lý SSL Neon, init/close | `_prepare_asyncpg_url`, `database_enabled`, `get_engine`, `get_session_factory`, `session_scope`, `init_database`, `close_database` |
| `base.py` | Declarative Base ORM | `Base(DeclarativeBase)` |
| `models.py` | 5 ORM models + 4 enum wrappers (UUID/JSONB/ARRAY) | `UserProfileModel`, `ChatSessionModel`, `ChatMessageModel`, `MessageFeedbackModel`, `AdviceResultModel` |
| `repository.py` | Persistence phiên/tin nhắn chat; ORM ⇄ `SessionState` | `ChatSessionRepository` (`get_or_create`, `save`, `append_message`, `list_messages`, `list_sessions`), helpers `_orm_to_state`/`_state_to_orm` |
| `profile_repository.py` | CRUD hồ sơ, liên kết session↔profile, lưu/đọc advice | `ProfileRepository` (`create_profile`, `get_profile`, `create_session_for_profile`, `link_session_profile`, `save_advice`, `get_latest_advice`), `load_profile_for_session` |
| `profile_snapshot.py` | DTO dataclass tách ORM để đưa vào prompt | `ProfileSnapshot` (`.target_role_label`, `.to_prompt_dict`) |
| `feedback_repository.py` | Feedback message (UPSERT), review, lấy dữ liệu approved | `FeedbackRepository` (`save_feedback` on-conflict, `update_review_status`, `list_pending_review`, `get_feedback_for_message`, `list_approved_messages`) |
| `enums.py` | Enum domain + nhãn hiển thị VN | `UserBackground`, `TargetRole`, `WeeklyTime`, `ReviewStatus`; maps `ROLE_DISPLAY`, `BACKGROUND_DISPLAY`, `WEEKLY_TIME_DISPLAY`, `WEEKLY_TIME_FROM_FORM` |
| `__init__.py` | Public API lifecycle | re-export `init_database`, `close_database`, `database_enabled` |

### 2.5 `app/graph/` (+ `queries/`)

> Neo4j knowledge graph. Sơ đồ quan hệ ở cuối [mục 4](#4-các-công-cụ-khác).

#### `app/graph/neo4j_client.py`
- **Mục đích:** Quản lý kết nối Neo4j (driver đồng bộ, fail-safe nếu không kết nối).
- **Chính:** `Neo4jClient` (`.available`, `.session()` raise nếu chưa kết nối, `.close()`, staticmethod `competency_labels()` → 7 nhãn), const `_COMPETENCY_LABELS`.
- **Phụ thuộc:** `neo4j`, `settings`. Dùng bởi `repository.py`, `queries/*`.

#### `app/graph/repository.py`
- **Mục đích:** Facade gom pathfinding + course_rec + multi-hop + subject_career + tìm nghề; áp skills-gap theo `item_code`.
- **Chính:** `GraphRepository` (`pathfinding`, `pathfinding_by_type`, `course_recommendation`, `course_recommendation_by_type`, `courses_for_career_skills` A-02, `subject_to_careers` C-03, `search_careers` dùng `difflib`, `close`). Mọi truy vấn graph chính nhận tham số `seed_*_codes` từ tight fusion (A-01).
- **Phụ thuộc:** `neo4j_client`, `queries.*`, `skills_gap`, `models`, `app.rag.aliases.subject_search_terms`. Export qua `__init__.py`; dùng bởi services.

#### `app/graph/skills_gap.py`
- **Mục đích:** Phân tích khoảng cách kỹ năng = yêu cầu nghề − known_skills; so khớp theo **`item_code`** (C-02).
- **Chính:** `FORM_SKILL_ALIASES`, `normalize_skill_token`, `expand_known_skill_codes`, `apply_skills_gap_to_result`, `apply_skills_gap_typed`, `merge_typed_gap_results`, `build_gap_skill_names`, `pathfinding_from_typed_gap`, protocol `GraphRepositoryLike`. **`apply_skills_gap`** deprecated (chỉ equivalence test).
- **Phụ thuộc:** `models`, `app.session.competency_types`, `app.session.store`, `app.utils.skill_normalize`. Gọi bởi `repository.py`, competency flow, roadmap_followup.

#### `app/graph/formatters.py`
- **Mục đích:** Format kết quả graph → Markdown tiếng Việt.
- **Chính:** `format_pathfinding(result, state)`, `format_course_rec(result)`.
- **Phụ thuộc:** `models`, `app.session.store`. Gọi bởi generator (formatter tĩnh).

#### `app/graph/models.py`
- **Mục đích:** Pydantic DTO cho kết quả graph.
- **Chính:** `CompetencyItem` (+ `priority`, `code`, `is_seed`), `PathfindingResult`, `CourseItem` (+ `coverage_level`, `is_seed`), `CourseRecResult`, `SkillCoursesBlock`, `CareerSkillCoursesResult` (A-02 multi-hop).
- **Phụ thuộc:** `pydantic`. Dùng khắp graph layer.

#### `app/graph/queries/pathfinding.py`
- **Mục đích:** Cypher tìm competency mà `Career` yêu cầu (qua `NEED_*`) → `PathfindingResult`. C-01: `ORDER BY priority_group ASC`; A-01: seed boost.
- **Chính:** const `_CYPHER`, `_CYPHER_BY_REL`; `fetch_pathfinding`, `fetch_pathfinding_by_type`, `_parse_skills`.
- **Phụ thuộc:** `models`, `neo4j_client`. Gọi bởi `repository.py`.

#### `app/graph/queries/course_rec.py`
- **Mục đích:** Cypher gợi ý `Course` dạy 1 competency (qua `TEACH_*`), fuzzy resolve tên + chống khớp ngắn sai. C-01: `ORDER BY coverage_level DESC`; A-01: seed boost.
- **Chính:** const Cypher `_CYPHER_BY_CODE`/`_CYPHER_LIST_COMPETENCIES`/`_CYPHER_COURSES_MATCH`/`_CYPHER_COURSES_BY_REL`; `fetch_course_recommendations`, `fetch_courses_by_type`, `_resolve_via_fuzzy` (rapidfuzz), `_competency_search_terms`, `_is_spurious_short_match`, `_parse_courses`.
- **Phụ thuộc:** `rapidfuzz`, `models`, `neo4j_client`, `settings`. Gọi bởi `repository.py`.

#### `app/graph/queries/career_multihop.py`
- **Mục đích:** A-02 — một Cypher gộp `Career -[NEED_*]-> Competency <-[TEACH_*]- Course` (thay vòng lặp N query course_rec). **BUILT_ON fallback:** nếu không có TEACH trực tiếp → gọi `fetch_course_recommendations` (prerequisite courses).

#### `app/graph/relation_registry.py`
- **Mục đích:** Loader `data/relation_types.yaml` — direction, topo ordering, validate Excel row.
- **Chính:** `RelationRegistry`, `get_relation_registry()`, `get_direction`, `ordering_rel_types`, `validate_excel_row`.

#### `app/graph/competency_resolve.py`
- **Mục đích:** Fuzzy resolve competency + type hint disambiguation (exact → alias → WRatio + type boost).

#### `app/graph/queries/competency_relation.py`
- **Mục đích:** Query cạnh `competency_relation` (BUILT_ON, VALIDATES, …) theo anchor type từ registry.
- **Chính:** `fetch_competency_relations`, `fetch_built_on_prerequisites`, `batch_fetch_prerequisites` (UNWIND enrich pathfinding).

#### `data/relation_types.yaml` + `data/competency_relation_supplement.jsonl`
- Registry 6 loại quan hệ + supplement JSONL merge vào ingest (REQUIRES softskill, REQUIRES_KNOWLEDGE methodology).
- **Chính:** const `_CYPHER_MULTIHOP`; `fetch_courses_for_career_skills(client, career, skill_names, ...)` → `CareerSkillCoursesResult`; sắp xếp theo `priority_group` ASC, `coverage_level` DESC, seed boost.
- **Phụ thuộc:** `models`, `neo4j_client`, `course_rec._parse_courses`. Gọi bởi `repository.courses_for_career_skills`, `roadmap_followup`.

#### `app/graph/queries/subject_career.py`
- **Mục đích:** C-03 — multi-hop học thuật `(Course)-[:IN_SUBJECT]->(Subject)` → competency → career (schema ingest thực tế).
- **Chính:** const `_CYPHER_SUBJECT_TO_CAREERS`; `fetch_subject_to_careers(client, search_terms, subject_codes, limit)`.
- **Phụ thuộc:** `neo4j_client`. Gọi bởi `repository.subject_to_careers`.

#### `app/graph/subject_career_case_study.py`
- **Mục đích:** C-03 — format chuỗi Subject→Course→Competency→Career và case study OOP cho báo cáo/log.
- **Chính:** `OOP_CASE_STUDY_DOC`, `format_subject_career_chain`, `format_subject_career_reply`, `log_case_study_sample`.
- **Phụ thuộc:** stdlib. Gọi bởi `chat_service._answer_subject_career`.

#### `app/graph/queries/__init__.py` & `app/graph/__init__.py`
- `queries/__init__.py`: re-export `fetch_courses_for_career_skills`, `fetch_course_recommendations`, `fetch_courses_by_type`, `fetch_pathfinding`, `fetch_pathfinding_by_type`.
- `graph/__init__.py`: re-export `GraphRepository`.

### 2.6 `app/intent/`

> Intent classification dùng **Gemini** (JSON output) + fuzzy career matching + heuristic subject_career. **6 intent:** `slot_fill`, `pathfinding`, `course_rec`, `roadmap_followup`, `competency_slot_fill`, `subject_career`. Domain `in`/`out`, confidence `high`/`low`.

#### `app/intent/parser.py`
- **Mục đích:** Parse JSON thô từ Gemini → `IntentRouteResult`; route mặc định khi lỗi.
- **Chính:** `strip_json_fence`, `parse_route_json`, `fallback_route`, helpers `_nullable_str`/`_require_literal`.
- **Phụ thuộc:** `models`. Gọi bởi `router.py`.

#### `app/intent/router.py`
- **Mục đích:** Service trung tâm điều phối intent: heuristic C-03 (`_try_subject_career_route`), gọi Gemini, parse, hậu xử lý (fuzzy career, domain/confidence/missing slots) → `RouteOutcome`.
- **Chính:** `IntentRouterService` (`route`, `_try_subject_career_route`, `_post_process`, `_sanitize_missing_slots`, `_should_stop_for_missing_slots`, `_missing_slots_prompt`, `close`).
- **Phụ thuộc:** `career_matcher`, `career_registry`, `models`, `parser`, `prompt`, `templates`, `app.services.gemini_router_client`. Gọi bởi `chat_service.py`, `intent_routes.py`.

#### `app/intent/prompt.py`
- **Mục đích:** Dựng system/user prompt (VN) cho bộ phân loại intent.
- **Chính:** `build_router_system_prompt(career_names)` (luật phân loại, ưu tiên intent, schema JSON), `build_router_user_prompt(message, session_context)`.
- **Phụ thuộc:** stdlib. Gọi bởi `router.py`.

#### `app/intent/models.py`
- **Mục đích:** Kiểu dữ liệu (Pydantic + Literal) cho intent routing.
- **Chính:** `Domain`, `Intent` (6 giá trị, gồm `subject_career`), `Confidence`, `IntentEntities` (+ `subject`), `IntentRouteResult`, `RouteOutcome`.
- **Phụ thuộc:** `pydantic`. Import rộng rãi (parser, router, templates, session, chat_service).

#### `app/intent/career_matcher.py`
- **Mục đích:** Chuẩn hóa (fuzzy + alias) tên nghề tự do → tên `Career` có trong Neo4j.
- **Chính:** `CareerMatcher.resolve(raw)` (alias → abbrev → exact → fuzzy `WRatio`, ngưỡng `router_career_fuzzy_threshold`).
- **Phụ thuộc:** `rapidfuzz`, `settings`, `app.rag.aliases`. Gọi bởi `router.py`.

#### `app/intent/career_registry.py`
- **Mục đích:** Nạp & cache danh sách tên `Career` từ Neo4j.
- **Chính:** `CareerRegistry` (`list_careers(force_reload)`, `close`).
- **Phụ thuộc:** `neo4j`, `settings`. Gọi bởi `router.py`.

#### `app/intent/templates.py`
- **Mục đích:** Câu trả lời mẫu VN (greeting, out-of-domain, low-confidence, gợi ý form).
- **Chính:** const `CHAT_GREETING`, `OUT_OF_DOMAIN_MESSAGE`; hàm `out_of_domain_message`, `greeting_message`, `suggest_form_message`, `low_confidence_message`, `profile_received_message`.
- **Phụ thuộc:** `app.intent.models.Intent`. Gọi bởi `router.py`, `chat_service.py`.

#### `app/intent/__init__.py`
- Re-export `IntentRouteResult`, `IntentRouterService`, `RouteOutcome`.

### 2.7 `app/rag/`

> Hybrid retrieval: **Vector (Qdrant) + BM25Okapi (rank_bm25) + RRF fusion + graph-aware boost (A-03)**. Tokenizer tiếng Việt: **underthesea** (B-03, fallback regex). Embedding mặc định Gemini.

#### `app/rag/retriever.py`
- **Mục đích:** Lớp truy hồi chính: Qdrant vector search (qua `qdrant_search`) + BM25Okapi corpus + RRF (B-01) + graph-aware boost (A-03); fallback mẫu khi lỗi (trừ khi `RETRIEVAL_STRICT=1`).
- **Chính:** `RetrieverUnavailableError` (B-02), `RetrievedDoc` (dataclass), `VectorRetriever` (`retrieve`, `retrieve_docs`, `_vector_search`, `_hybrid_rerank`, `_apply_graph_boost`, `set_bm25_corpus`, `reload_bm25_corpus`, `_fallback_samples`), module-level `_tokenize` (underthesea + unidecode), `_rrf_fuse`, `_get_bm25_engine`, const `RRF_K=60`, `RRF_POOL_SIZE=60`.
- **Phụ thuộc:** `settings`, `embeddings.EmbeddingClient`, `qdrant_client`, `qdrant_search.search_vectors`, `query_expand.expand_query_vi`, `rank_bm25.BM25Okapi`. Gọi bởi `chat_service`, `fusion`, scripts eval/ablation.

#### `app/rag/query_expand.py`
- **Mục đích:** Mở rộng câu hỏi VN bằng canonical EN + alias/keyword (nghề/kỹ năng/soft skill/môn) trước khi embed.
- **Chính:** `expand_query_vi(message)`.
- **Phụ thuộc:** `app.rag.aliases`. Gọi bởi `retriever.py`.

#### `app/rag/aliases.py`
- **Mục đích:** "Từ điển miền" — nạp `domain_aliases.json`, resolve text tự do (VN/abbrev) → canonical cho 4 loại entity, map subject→competency; heuristic C-03.
- **Chính:** `load_aliases` (lru_cache), `resolve_abbrev_career`, `resolve_*_alias`, `resolve_all_*_aliases`, `resolve_alias_any`, `resolve_alias_all`, `competencies_from_subject`, `subject_search_terms`, `looks_like_subject_career_question`, `all_keywords_for_*`, `keywords_block`, `get_*_entry`, `_scan_all_matches`.
- **Phụ thuộc:** stdlib only. Gọi bởi `query_expand`, `corpus_builder`, `paraphrase`, `intent.career_matcher`, `competency_orchestrator`.

#### `app/rag/embeddings.py`
- **Mục đích:** Wrapper sinh embedding qua Gemini hoặc OpenAI; cờ `available`.
- **Chính:** `EmbeddingClient` (`.available`, `.embed`, `_embed_openai` `text-embedding-3-small`, `_embed_gemini` `gemini-embedding-001` 768d).
- **Phụ thuộc:** `settings` (lazy `openai`/`google.genai`). Gọi bởi `retriever`, `exemplar`, scripts.

#### `app/rag/qdrant_client.py`
- **Mục đích:** Factory tạo `QdrantClient` (local/Cloud) + headers auth.
- **Chính:** `create_qdrant_client(timeout)`, `qdrant_http_headers()`.
- **Phụ thuộc:** `settings`. Gọi bởi `retriever`, `health_routes`, `index_qdrant`.

#### `app/rag/qdrant_search.py`
- **Mục đích:** Adapter tìm kiếm Qdrant — tương thích `query_points` (API mới) và `search` (API cũ), tránh rơi fallback khi client chỉ hỗ trợ một API.
- **Chính:** `QdrantHit` (dataclass), `search_vectors(client, collection_name, query_vector, limit, query_filter)`.
- **Phụ thuộc:** `qdrant_client.models.Filter`. Gọi bởi `retriever._vector_search`.

#### `app/rag/corpus_builder.py`
- **Mục đích:** Sinh "index text" VN giàu từ khóa cho course/career/competency để nạp Qdrant + BM25.
- **Chính:** `build_course_index_text`, `build_career_index_text`, `build_competency_index_text`, `_load_enriched`.
- **Phụ thuộc:** `app.rag.aliases`. Gọi bởi `build_index_corpus`, test.

#### `app/rag/confidence.py`
- **Mục đích:** Tính điểm tin cậy heuristic [0,1] để quyết định dùng LLM hay formatter tĩnh.
- **Chính:** `compute_confidence(found, n_competencies, parse_fallback, route_confidence)`.
- **Phụ thuộc:** none. Gọi bởi `response_generator` (ngưỡng `GENERATOR_CONFIDENCE_THRESHOLD=0.45`).

#### `app/rag/fusion.py`
- **Mục đích:** Gộp graph ground-truth (Neo4j) + vector snippets + LLM draft → `context_block` + `evidence`; tight fusion A-01/A-03.
- **Chính:** `map_hits_to_graph_nodes(hits)` → `{career_codes, competency_codes, course_codes}`; `extract_relevant_ids_from_graph(graph_payload)` (A-03 rerank); `FusionService.aggregate(..., graph_seed_ids=...)`, `FusionService.build_evidence(...)`.
- **Phụ thuộc:** `retriever.RetrievedDoc`. Gọi bởi `chat_service`, `ablation_pipeline`, test.

#### `app/rag/exemplar.py`
- **Mục đích:** Few-shot retrieval — lấy 2–3 lượt chat đã approved gần query nhất (cosine) làm ví dụ cho LLM.
- **Chính:** `ExemplarRetriever.fetch_examples(query, top_k)`, `_cosine`.
- **Phụ thuộc:** `db.engine.database_enabled`, `db.feedback_repository`, `embeddings`. Gọi bởi `chat_service`.

#### `app/rag/paraphrase.py`
- **Mục đích:** Sinh biến thể câu hỏi (pathfinding/course_rec) từ alias cho data SFT + render keyword block.
- **Chính:** `pathfinding_questions`, `course_rec_questions`, `user_prompt_keywords_block`.
- **Phụ thuộc:** `aliases`. Gọi bởi `export_chat_dataset`, `build_synthetic_ft_data`.

#### `app/rag/graph_builder.py`
- **Mục đích:** Truy vấn Neo4j lấy "context đồ thị" cho 1 vai trò (skills `NEED_*`, courses `TEACH_*`, industry); có stub khi mất kết nối. Dùng bởi luồng form advisory.
- **Chính:** const `_CYPHER_CONTEXT`/`_CYPHER_LIST_CAREERS`; `GraphContextBuilder` (`get_graph_context`, `close`), `_format_graph_row`, `_stub_context`.
- **Phụ thuộc:** `settings`, `neo4j`. Gọi bởi `advisory_service`.

### 2.8 `app/generator/`

> Lưu ý: **không tồn tại** `app/generator/generator_backend.py`. Logic chọn backend nằm ở `app/services/generator_backend.py`.

#### `app/generator/response_generator.py`
- **Mục đích:** Sinh reply chat (slot_fill/pathfinding/course_rec). Ưu tiên: Local FT → Gemini → formatter tĩnh; có gate confidence + lọc citation ảo.
- **Chính:** `ResponseGenerator` (`slot_fill`, `pathfinding`, `course_rec`, `_generate_text`, `last_generator_backend`), `_prepend_context`.
- **Phụ thuộc:** `prompts`, `validator`, `graph.formatters`, `graph.models`, `intent.models`, `rag.confidence`, `settings`, `gemini_generator_client`, `generator_backend`, `local_generator_client`, `session.store`. Gọi bởi `chat_service`.

#### `app/generator/advisory_prompt.py`
- **Mục đích:** Prompt cho luồng form tư vấn + format kết quả JSON advice thành tin nhắn.
- **Chính:** `build_advisory_system_prompt`, `build_advisory_user_prompt(profile, graph_context)`, `format_advice_reply(structured)`.
- **Phụ thuộc:** `db.enums`, `db.profile_snapshot`. Gọi bởi `advisory_service`.

#### `app/generator/prompts.py`
- **Mục đích:** System prompts + builder user-prompt cho 3 intent chat, grounding nghiêm ngặt (chỉ dùng Neo4j/hồ sơ).
- **Chính:** const `_GROUNDING`, `SLOT_FILL_SYSTEM`, `PATHFINDING_SYSTEM`, `COURSE_REC_SYSTEM`; `build_slot_fill_user_prompt`, `build_pathfinding_user_prompt`, `build_course_rec_user_prompt`, `_profile_block`.
- **Phụ thuộc:** `db.enums`, `intent.models`, `session.context`, `session.store`. Gọi bởi `response_generator`.

#### `app/generator/validator.py`
- **Mục đích:** Hậu kiểm output LLM — xóa citation khóa học ảo `[Course: CODE]` không có trong graph snapshot.
- **Chính:** `extract_course_codes_from_snapshot`, `validate_and_strip_hallucinated_citations`, const `_COURSE_CITE_RE`.
- **Phụ thuộc:** stdlib. Gọi bởi `response_generator`.

#### `app/generator/__init__.py`
- Re-export `ResponseGenerator`.

### 2.9 `app/services/`

#### `app/services/chat_service.py`
- **Mục đích:** **Orchestrator trung tâm** luồng chat (intent → vector seeds → graph → rag fusion → generator + vòng đời session).
- **Chính:** `ChatService` (`handle_message`, `_process_turn`, `_answer_from_intent`, `_answer_subject_career`, `greeting`, `get_session/get_history/list_sessions`, `_finalize_llm_meta`, helpers `_enrich_route`/`_wants_it_advice`/`_competency_flow_not_started`), const `_WANTS_IT_ADVICE`. Luồng pathfinding/course_rec: `retrieve_docs` → `map_hits_to_graph_nodes` → graph query với seeds → fusion.
- **Phụ thuộc:** hầu hết các tầng (`db.profile_repository`, `generator.response_generator`, `graph.repository`, `graph.subject_career_case_study`, `intent.*`, `rag.exemplar/fusion/retriever`, `response.structured`, `services.competency_orchestrator/roadmap_followup`, `session.*`). Gọi bởi `chat_routes.py`.

#### `app/services/advisory_service.py`
- **Mục đích:** Luồng form tư vấn: tạo profile/session, sinh tư vấn **structured JSON** bằng Gemini (`response_schema`), cache advice.
- **Chính:** `AdvisoryService` (`submit_advisory_form`, `get_cached_advice`, `search_careers`, `_generate_and_store_advice`, `_call_structured_llm` gọi thẳng Gemini SDK, `_fallback_advice`), `_fallback_roadmap`.
- **Phụ thuộc:** `advice.schema.ADVICE_RESULT_JSON_SCHEMA`, `db.*`, `generator.advisory_prompt`, `graph.repository/skills_gap`, `rag.graph_builder`, `response.structured`, `gemini_generator_client`, `session.repository`, `google.genai`. Gọi bởi `advisory_routes.py`.

#### `app/services/competency_orchestrator.py`
- **Mục đích:** Điều phối thu thập năng lực theo 7 nhóm tuần tự (LANG→…→CERT): hỏi từng nhóm, parse kỹ năng (aliases), bỏ qua nhóm rỗng, tổng hợp gap + gợi ý khóa học.
- **Chính:** `OrchestratorTurn` (dataclass), `CompetencyTypeOrchestrator` (`should_handle`, `handle_turn`, `start_collection`, `_skip_empty_types`, `_prompt_for_type`, `_extract_skills_from_message`, `_handle_gap_summary`, `_build_gap_summary`, `_courses_for_missing`), const `_SKIP_RE`.
- **Phụ thuộc:** `graph.models/repository/skills_gap`, `rag.aliases`, `session.competency_types/store`. Gọi bởi `chat_service`.

#### `app/services/roadmap_followup.py`
- **Mục đích:** Intent `roadmap_followup` — gộp advice đã lưu + skills gap typed (Neo4j) + khóa học theo skill thiếu → `StructuredReply`.
- **Chính:** `RoadmapFollowupService` (`build`, `_fetch_courses_for_skills` dùng `courses_for_career_skills` A-02 một query, `_merge_known_codes`, `_merge_gap_labels`, `_pick_summary`), const `_MAX_COURSE_SKILLS=6`, `_MAX_COURSES_PER_SKILL=4`.
- **Phụ thuộc:** `db.profile_repository`, `graph.models/repository`, `response.structured`, `session.store`, `utils.skill_normalize`. Gọi bởi `chat_service`.

#### `app/services/generator_backend.py`
- **Mục đích:** **Logic chọn backend sinh** (Gemini vs Ollama local) theo intent + cấu hình + fallback. Điểm quyết định trung tâm.
- **Chính:** `GeneratorIntent(Enum)` (SLOT_FILL/PATHFINDING/COURSE_REC), `resolve_backend_for_intent(intent)`, `generate_reply(...)` → `(text, backend_used)`, `generator_status(...)`.
- **Quy tắc:** `slot_fill` → luôn `gemini`; `GENERATOR_BACKEND=gemini/local` → tương ứng; `auto` → `local` nếu `USE_LOCAL_GENERATOR=1`, ngược lại `gemini`. Fallback: local lỗi → `gemini_fallback`.
- **Phụ thuộc:** `settings`, `gemini_generator_client`, `local_generator_client`. Gọi bởi `response_generator`, `health_routes`.

#### `app/services/gemini_router_client.py`
- **Mục đích:** Client Gemini cho **Intent Router** — temp thấp, output JSON.
- **Chính:** `GeminiRouterClient.classify(system_prompt, user_message)`, `_router_models_to_try`, quota/404 helpers.
- **Phụ thuộc:** `google.genai`, `settings`. Gọi bởi `intent.router`.

#### `app/services/gemini_generator_client.py`
- **Mục đích:** Client Gemini cho **Response Generator** — temp cao (0.7) cho văn bản tự nhiên.
- **Chính:** `GeminiGeneratorClient` (`.available`, `.generate`, `_generator_models_to_try`).
- **Phụ thuộc:** `google.genai`, `settings`. Gọi bởi `response_generator`, `generator_backend`, `advisory_service` (dùng `._client` trực tiếp cho `response_schema`).

#### `app/services/local_generator_client.py`
- **Mục đích:** Client gọi **Ollama HTTP API** (local LLM), cùng "bề mặt" `generate()` như Gemini.
- **Chính:** `LocalGeneratorClient` (`.available` ping `/api/tags`, `.generate(... intent)` POST `/api/chat`, chọn model theo intent).
- **Phụ thuộc:** `httpx`, `settings`. Gọi bởi `response_generator`, `generator_backend`.

### 2.10 `app/session/`

> Session state: **Postgres-backed** (`ChatSessionRepository`) khi có `DATABASE_URL`, ngược lại **in-memory** (`MemorySessionStore`). Factory: `create_session_repository()`.

| File | Mục đích | Class/function chính |
|---|---|---|
| `store.py` | `SessionState` — cấu trúc trạng thái phiên trung tâm (career, competency, luồng 7 bước, profile, messages, route) | `SessionState` (`merge_route`, `append_message`, `current_competency_type`, `reset_competency_flow`, `record_known_for_type`, `all_known_skills`, `to_public_dict`) |
| `memory_store.py` | Backend lưu phiên in-memory (fallback) | `MemorySessionStore` (`get_or_create`, `save`, `append_message`, `list_messages`, `list_sessions`) |
| `context.py` | Ghép ngữ cảnh phiên vào prompt router + áp route về state | `build_router_user_message`, `build_history_block`, `apply_route_to_state`, `infer_followup_intent`, `extract_competency_hint`, `_session_context_block` |
| `followup.py` | Điều chỉnh `RouteOutcome` theo ngữ cảnh (ép roadmap_followup/competency_slot_fill/course_rec) | `maybe_adjust_outcome`, `infer_roadmap_followup`, `_apply_forced_intent`, const `_ROADMAP_FOLLOWUP` |
| `models.py` | `ChatTurn` — một lượt hội thoại | `ChatTurn` (dataclass: role, content) |
| `competency_types.py` | Thứ tự 7 nhóm năng lực + map sang quan hệ Neo4j | `Phase`, `COMPETENCY_TYPE_ORDER` (CT_LANG..CT_CERT), `CT_TO_NEED_REL`, `CT_TO_TEACH_REL`, `CT_TO_LABEL`, `need_rel_for_type`, `teach_rel_for_type`, `type_label` |
| `repository.py` | Protocol + factory chọn backend lưu phiên | `SessionRepository` (Protocol), `create_session_repository()` |
| `__init__.py` | Re-export | `SessionState`, `apply_route_to_state`, `build_router_user_message` |

### 2.11 `app/advice/` & `app/response/`

#### `app/advice/schema.py`
- **Mục đích:** JSON Schema cho structured output tư vấn (dùng làm `response_schema` của Gemini).
- **Chính:** `ADVICE_RESULT_JSON_SCHEMA` (fields: `skills_gap` {missing, weak}, `roadmap` [{month, topics, milestone}], `recommended_courses`, `estimated_months`, `summary_vi`).
- **Phụ thuộc:** none. Gọi bởi `advisory_service`. `__init__.py` re-export.

#### `app/response/structured.py`
- **Mục đích:** Structured reply cho frontend (cards/timeline/chips) + chuyển đổi từ graph/advice + plain-text fallback. C-01: badge ưu tiên/bao phủ trên chip.
- **Chính:** `SectionType`, `StructuredSection`, `StructuredReply` (`.model_dump_public`), `plain_text_from_structured`, `priority_badge`, `coverage_badge`, `course_item_to_chip`, `structured_from_pathfinding`, `structured_from_advice`, `structured_from_course_rec`, `_labels_from_form_codes`, `_display_normalize_skill_labels`.
- **Phụ thuộc:** `pydantic`, lazy `graph.skills_gap.FORM_SKILL_ALIASES`. Gọi bởi `chat_service`, `advisory_service`, `roadmap_followup`.

### 2.12 `app/utils/`

#### `app/utils/skill_normalize.py`
- **Mục đích:** Chuẩn hóa nhãn kỹ năng để **so khớp/dedupe** (bỏ tiền tố `platform:`/`tool:`/…, NFKD, lower).
- **Chính:** `normalize_skill_label`, `normalize_skill_set`, const `_PREFIX_RE`.
- **Phụ thuộc:** `re`, `unicodedata`. Gọi bởi skills_gap, roadmap_followup, structured, test.

#### `app/utils/__init__.py`
- Chỉ docstring `"""Shared utilities."""` — đánh dấu package.

### 2.13 `app/eval/`

> Module đánh giá thực nghiệm (nhóm D nangcap.txt) — pure Python + tích hợp pipeline ablation/judge.

#### `app/eval/retrieval_metrics.py`
- **Mục đích:** IR metrics cho eval retrieval (D-02) — không phụ thuộc ranx/numpy.
- **Chính:** `precision_at_k`, `recall_at_k`, `reciprocal_rank`, `dcg_at_k`, `ndcg_at_k`, `RetrievalMetricRow`, `aggregate_query_metrics`.
- **Phụ thuộc:** stdlib. Gọi bởi `scripts/eval_retrieval.py`, test.

#### `app/eval/quality_metrics.py`
- **Mục đích:** Chấm chất lượng ablation (D-01) — faithfulness, skill accuracy, hallucination rate, cosine similarity (generative mode).
- **Chính:** `QualityScores`, `skill_recall`, `compute_quality_scores`, `embedding_text_similarity`, `classify_error_tags`, `build_gold_reference_text`, `average_scores`, helpers entity extraction.
- **Phụ thuộc:** `app.generator.validator`, `app.utils.skill_normalize`. Gọi bởi `ablation_pipeline`, `run_quality_ablation`, test.

#### `app/eval/ablation_pipeline.py`
- **Mục đích:** Pipeline ablation D-01 — 4 fusion mode + 2 eval mode.
- **Chính:** `FusionMode` (`vector_only`, `graph_only`, `late_fusion`, `tight_fusion`), `EvalRunMode` (`static`, `generative`), `AblationPipeline`, `AblationCaseResult`, `MODE_LABELS`; tích hợp `map_hits_to_graph_nodes`, formatter tĩnh hoặc LLM generative.
- **Phụ thuộc:** `graph.repository`, `rag.fusion/retriever`, `generator.response_generator`, `quality_metrics`. Gọi bởi `scripts/run_quality_ablation.py`, test.

#### `app/eval/error_analysis.py`
- **Mục đích:** Phân tích lỗi chéo cấu hình ablation (D-01) — ma trận per-case, so sánh mode thắng/thua.
- **Chính:** `build_per_case_matrix`, `compare_mode_wins`, `build_error_analysis_report`.
- **Phụ thuộc:** `ablation_pipeline.FusionMode`, `quality_metrics`. Gọi bởi `run_quality_ablation.py` (JSON report).

#### `app/eval/llm_judge.py`
- **Mục đích:** LLM-as-a-Judge end-to-end (D-03) — chấm faithfulness/skill_completeness/no_hallucination.
- **Chính:** `JudgeScores`, `JUDGE_SYSTEM_PROMPT`, `create_judge_client()`, clients Gemini/OpenAI/Groq, `judge_model_label`.
- **Phụ thuộc:** `settings` (JUDGE_* env). Gọi bởi `scripts/eval_answer_quality.py`, test.

#### `app/eval/__init__.py`
- Package marker cho eval utilities.

---

## 3. Công cụ Database

Hệ thống dùng **3 datastore song song**:

### 3.1 Neo4j (Knowledge Graph) — graph DB chính
- **Kết nối:** `app/graph/neo4j_client.py` — driver **đồng bộ** `neo4j.GraphDatabase.driver(settings.neo4j_uri, auth=(user, password))`. Mặc định `bolt://localhost:7687`, production `neo4j+s://...aura...`. **⚠️ Chưa chuyển async driver (E-02 chưa làm)** — dùng `session.run(...)` trong luồng async FastAPI. Có `verify_connectivity()`, lỗi → `available=False` (degrade gracefully).
- **Các file liên quan:** `app/graph/neo4j_client.py`, `app/graph/repository.py`, `app/graph/queries/pathfinding.py`, `app/graph/queries/course_rec.py`, `app/graph/queries/career_multihop.py`, `app/graph/queries/subject_career.py`, `app/rag/graph_builder.py`, `app/intent/career_registry.py`.
- **Sơ đồ graph (suy ra từ Cypher):**
  - **Nodes:** `Career`, `Industry`, `Course`, `Organization`, `Level`, `Subtitle`, **`Subject`**, và **7 nhãn competency**: `ProgrammingLanguage`, `Framework`, `Platform`, `Tool`, `Knowledge`, `Softskill`, `Certification` (mỗi competency có `item_code`, `item_name`).
  - **Relationships:** `(Career)-[:NEED_* {priority_group}]->(competency)`, `(Career)-[:IN_INDUSTRY]->(Industry)`, `(Course)-[:TEACH_* {coverage_level}]->(competency)`, `(Course)-[:IN_SUBJECT]->(Subject)` (C-03), `(Course)-[:PROVIDED_BY]->(Organization)`, `(Course)-[:AT_LEVEL]->(Level)`, `(Course)-[:HAS_SUBTITLE]->(Subtitle)`.
- **Cypher chính:** `_CYPHER`/`_CYPHER_BY_REL` (pathfinding `NEED_*`), `_CYPHER_BY_CODE`/`_CYPHER_COURSES_MATCH`/`_CYPHER_COURSES_BY_REL`/`_CYPHER_LIST_COMPETENCIES` (course rec `TEACH_*`), query liệt kê `Career` trong `repository.search_careers`.
- **Nạp dữ liệu:** `scripts/ingest.py` (từ Excel) → tạo node + quan hệ `NEED_*`/`TEACH_*`.

### 3.2 PostgreSQL (Neon) — relational DB
- **Kết nối:** `app/db/engine.py` — **SQLAlchemy async + asyncpg** (`create_async_engine`, `async_sessionmaker(class_=AsyncSession)`). URL chuẩn hóa thành `postgresql+asyncpg://` trong `config._normalize_database_url`. Xử lý SSL cho Neon (`*.neon.tech`) và loại tham số libpq (`sslmode`, `channel_binding`) không hợp lệ với asyncpg. `init_database()` chạy `Base.metadata.create_all` lúc startup (cảnh báo, không crash nếu mất kết nối).
- **Các file liên quan:** `app/db/engine.py`, `base.py`, `models.py`, `repository.py`, `profile_repository.py`, `profile_snapshot.py`, `feedback_repository.py`, `enums.py`.
- **5 bảng chính (khớp 1-1 với ORM):**

| Bảng | Mục đích | Ghi chú |
|---|---|---|
| `user_profiles` | Hồ sơ người dùng (background, role, `known_skills text[]`, weekly_time, `goals text[]`, profile_completed) | PK uuid `gen_random_uuid()` |
| `chat_sessions` | Trạng thái phiên (career, competency, `known_by_type jsonb`, `phase`, `missing_slots jsonb`, `last_route jsonb`, FK profile) | trigger `set_updated_at` |
| `chat_messages` | Lịch sử tin nhắn (role CHECK user/assistant/system, content, intent, domain, `route jsonb`) | FK session CASCADE |
| `message_feedback` | Đánh giá (`rating` CHECK ∈ {-1,1}, comment, review_status, reviewer) | `message_id` **UNIQUE** |
| `advice_results` | Kết quả tư vấn (`skills_gap`/`roadmap`/`recommended_courses` jsonb, estimated_months, raw_response) | FK session CASCADE |

- **4 ENUM types:** `user_background`, `target_role`, `weekly_time`, `review_status`.
- **Schema files (`design/`):**
  - `design/postgres_chat_schema_v2.sql` — **schema chính thức** (DROP + tạo lại 4 enum + 5 bảng + trigger `set_updated_at` + index).
  - `design/postgres_chat_schema.sql` — v1 **deprecated** (placeholder trỏ sang v2).
  - `design/migrations/003_chat_sessions_competency_flow.sql` — migration **idempotent** thêm `competency_type_index`, `known_by_type`, `phase` vào `chat_sessions`.
- **Quản lý schema:** `scripts/reset_db_v2.py` (drop + recreate), `scripts/migrate_add_feedback.py` (thêm bảng feedback).

### 3.3 Qdrant (Vector store)
- **Kết nối:** `app/rag/qdrant_client.py` — `create_qdrant_client()` (local `http://localhost:6333` hoặc Qdrant Cloud qua `QDRANT_API_KEY`), collection mặc định `career_roadmap`.
- **Nạp:** `scripts/index_qdrant.py` (embed `data/index_corpus.jsonl` → upsert points + sidecar BM25).

---

## 4. Các công cụ khác

### 4.1 RAG tools (`app/rag/`)
- **Hybrid retrieval (B-01, đã xác minh):** Vector top-60 (Qdrant qua `qdrant_search`) + **BM25Okapi** top-60 (`rank_bm25`, corpus `data/bm25_corpus.json`) → **RRF** (`RRF_K=60`, `1/(k+rank)`). **⚠️ Chưa có env `RETRIEVAL_VECTOR_WEIGHT`/`BM25_WEIGHT` (E-03)** — trọng số RRF cố định trong code.
- **Graph-aware rerank (A-03):** `_apply_graph_boost` cộng `RETRIEVAL_GRAPH_BOOST` (mặc định 0.15) khi `canonical_id`/`course_code` khớp subgraph Neo4j (`extract_relevant_ids_from_graph`).
- **Tokenizer (B-03):** `_tokenize` dùng **underthesea** `word_tokenize(format="text")` + unidecode; fallback regex nếu thiếu thư viện.
- **Tight fusion (A-01):** `map_hits_to_graph_nodes` → `graph_seed_ids` truyền vào Cypher (boost, không lọc cứng).
- **Query expansion:** `expand_query_vi` bơm canonical EN + alias VN.
- **Fusion:** `FusionService.aggregate` gộp graph + vector + LLM draft → `context_block` + `evidence` (truy vết `career_ids`, `course_codes`, `chunk_ids`, `graph_seed_ids`).
- **Embedding:** Gemini `gemini-embedding-001` (768d) mặc định; OpenAI `text-embedding-3-small` tùy chọn.
- **Few-shot:** `ExemplarRetriever` lấy lượt chat approved gần nhất (cosine).
- **Strict mode (B-02):** `RETRIEVAL_STRICT=1` → raise `RetrieverUnavailableError` thay fallback; `eval_retrieval.py` bật sẵn.
- **Fallback production:** nếu Qdrant/embedder không sẵn sàng và `RETRIEVAL_STRICT=0` → 3 doc mẫu hard-code (`_fallback_samples`).

### 4.2 Graph queries (`app/graph/`)
- **Pathfinding:** `fetch_pathfinding` / `fetch_pathfinding_by_type` — competency nghề cần qua `NEED_*`; ORDER BY `priority_group` ASC (C-01).
- **Course rec:** `fetch_course_recommendations` / `fetch_courses_by_type` — khóa học qua `TEACH_*`, ORDER BY `coverage_level` DESC (C-01); fuzzy resolve (rapidfuzz) + chống khớp ngắn sai.
- **Multi-hop (A-02):** `fetch_courses_for_career_skills` — Career→Competency→Course một query; dùng trong `roadmap_followup`.
- **Subject→Career (C-03):** `fetch_subject_to_careers` qua `(Course)-[:IN_SUBJECT]->(Subject)`.
- **Skills gap (C-02):** `apply_skills_gap_typed` / `apply_skills_gap_to_result` / `merge_typed_gap_results` — so khớp theo `item_code`; `apply_skills_gap` deprecated.

### 4.3 LLM / Generator
- **Backend mặc định = Gemini** (vì `GENERATOR_BACKEND=auto` + `USE_LOCAL_GENERATOR=0`). SDK `google.genai`.
- **Có 3 client Gemini riêng** (cùng pattern `_models_to_try` + xử lý quota/404):
  - `GeminiRouterClient` (intent, JSON, temp 0.15)
  - `GeminiGeneratorClient` (chat reply, temp 0.7)
  - `advisory_service` dùng `GeminiGeneratorClient._client` trực tiếp cho structured output (`response_schema`)
- **Ollama local** (`LocalGeneratorClient`, HTTP `/api/chat`): chỉ dùng cho `pathfinding`/`course_rec` khi `USE_LOCAL_GENERATOR=1` + server chạy. Model: `career-pathfinding`, `career-course-rec`.
- **Gate confidence + chống hallucination:** `compute_confidence < 0.45` → formatter tĩnh; `validate_and_strip_hallucinated_citations` xóa `[Course: CODE]` ảo.

### 4.4 Intent parsing/routing (`app/intent/`)
- LLM Gemini phân loại JSON → 6 intent (+ heuristic `subject_career` trước LLM) + domain in/out + confidence high/low; fuzzy chuẩn hóa career (`CareerMatcher`, ngưỡng 80) dựa danh sách `Career` từ Neo4j (`CareerRegistry`).

### 4.5 Session management (`app/session/`)
- `SessionState` lưu qua Postgres (`ChatSessionRepository`) hoặc in-memory fallback; luồng thu thập 7 nhóm năng lực (`competency_types.py`), điều chỉnh intent theo ngữ cảnh (`followup.py`, `context.py`).

### 4.6 Scripts (`scripts/`)

| Script | Mục đích | Lệnh chạy |
|---|---|---|
| `ingest.py` | Nạp Excel (`data/bộ dữ liệu.xlsx`) vào Neo4j: tạo node + constraint + quan hệ `NEED_*`/`TEACH_*` | `python scripts/ingest.py [--reset-graph]` |
| `index_qdrant.py` | Embed `data/index_corpus.jsonl` → tạo lại collection Qdrant + upsert + sidecar `bm25_corpus.json` | `python scripts/index_qdrant.py` |
| `build_index_corpus.py` | Trích career/competency/course từ Neo4j (+ aliases + enrich) → JSONL corpus | `python scripts/build_index_corpus.py --out data/index_corpus.jsonl` |
| `build_synthetic_ft_data.py` | Sinh data fine-tune tổng hợp (paraphrase) cho pathfinding/course_rec, chia train/val | `python scripts/build_synthetic_ft_data.py --out-dir data --per-career 4` |
| `validate_ft_jsonl.py` | Kiểm tra hợp lệ JSONL fine-tune trước khi train | `python scripts/validate_ft_jsonl.py data/ft_..._train.jsonl` |
| `export_chat_dataset.py` | Xuất chat đã duyệt từ Postgres → JSONL fine-tune (tách theo intent) | `python scripts/export_chat_dataset.py --out-dir data [--approved-only]` |
| `eval_retrieval.py` | Đánh giá retrieval (D-02): Recall@k, Precision@k, MRR, nDCG@k trên `retrieval_gold.jsonl`; bật `RETRIEVAL_STRICT=1`; xuất CSV | `python scripts/eval_retrieval.py --k 5,10` |
| `run_quality_ablation.py` | Ablation D-01: 4 fusion mode × static/generative eval; significance tests (scipy Wilcoxon); JSON error analysis | `python scripts/run_quality_ablation.py --eval-mode generative --json-out results.json` |
| `build_answer_gold.py` | Sinh/bổ sung gold set cho ablation D-01 | `python scripts/build_answer_gold.py` |
| `eval_answer_quality.py` | Đánh giá E2E (D-03): ChatService + LLM judge (Groq/Gemini/OpenAI) trên `answer_quality_gold.jsonl` | `python scripts/eval_answer_quality.py --limit 10` |
| `run_ablation.py` | Ablation latency cũ (full vs bỏ vector vs +local), đo latency + intent | `python scripts/run_ablation.py --message "..."` |
| `visualize_graph.py` | Dựng đồ thị demo Graph-RAG → HTML pyvis | `python scripts/visualize_graph.py` |
| `check_llm_setup.py` | Kiểm tra cấu hình Gemini/Ollama/embedding | `python scripts/check_llm_setup.py` |
| `reset_db_v2.py` | Drop + tạo lại schema v2 từ SQLAlchemy metadata | `python scripts/reset_db_v2.py` |
| `migrate_add_feedback.py` | Migration thêm bảng `message_feedback` + enum + index | `python scripts/migrate_add_feedback.py` |
| `add_competency_type_labels.py` | Thêm secondary label cho node `:CompetencyType` (APOC/Cypher) | `python scripts/add_competency_type_labels.py` |
| `mark_review.py` | CLI duyệt feedback (list-pending/approve/reject) | `python scripts/mark_review.py list-pending` |
| `active_learning_queue.py` | Xuất message cần gán nhãn (confidence thấp/feedback xấu) | `python scripts/active_learning_queue.py --limit 20` |
| `enrich_descriptions.py` | Làm giàu mô tả khóa học bằng Gemini → cache `data/enriched_descriptions.json` | `python scripts/enrich_descriptions.py --limit 50` |
| `patch_career_competency_excel.py` | Xóa dòng mapping career–competency sai trong Excel nguồn | `python scripts/patch_career_competency_excel.py` |
| `generate_mapping_architecture.py` | Vẽ sơ đồ kiến trúc mapping XLSX→Neo4j (Pillow) → PNG | `python scripts/generate_mapping_architecture.py` |
| `test_chat_scenarios.py` | Kiểm thử E2E luồng chat qua `ChatService` | `python scripts/test_chat_scenarios.py` |

> Hầu hết script `load_dotenv(PROJECT_ROOT/".env")` + chèn `PROJECT_ROOT` vào `sys.path`, nên cũng chạy được dạng module: `python -m scripts.<name>`.

### 4.7 Data files quan trọng (`data/`)

| File | Định dạng | Nội dung / vai trò |
|---|---|---|
| `bm25_corpus.json` | JSON array (~669 record) | Corpus lexical phụ cho hybrid rerank: `{doc_id, title, payload{doc_type, text...}}` |
| `domain_aliases.json` | JSON (5 khối: careers/competencies/soft_skills/subjects/abbrev_to_career) | File alias **mặc định** mà `load_aliases()` nạp đầu tiên |
| `domain_aliases_upgraded.json` | Cùng schema | File alias dự phòng (chỉ dùng khi thiếu file gốc / qua env `DOMAIN_ALIASES_PATH`) |
| `index_corpus.jsonl` | JSONL (~670 dòng) | Corpus nguồn để index vào Qdrant: `{doc_type, canonical_id, title, point_id, index_text, payload}` |
| `data/eval/retrieval_gold.jsonl` | JSONL (231 dòng) | Gold set đánh giá retrieval: `{query, doc_type, gold_ids, gold_field}` |
| `data/eval/retrieval_results.csv` | CSV | Kết quả chạy `eval_retrieval.py` |
| `data/eval/answer_gold.jsonl` | JSONL | Gold set ablation D-01 (pathfinding/course_rec cases) |
| `data/eval/answer_quality_gold.jsonl` | JSONL | Gold set LLM judge D-03 |
| `data/eval/answer_quality_results.csv` | CSV | Kết quả chạy `eval_answer_quality.py` |

---

## 5. Cấu hình & môi trường

Nguồn: `app/core/config.py` (singleton `settings`) + `.env.example`. `load_dotenv(override=True)`.

| Biến môi trường | Mặc định | Vai trò |
|---|---|---|
| `LOG_LEVEL` | `INFO` | Mức log root logger (E-01): DEBUG/INFO/WARNING/ERROR/CRITICAL |
| `GEMINI_API_KEY` | — | API key Google Gemini (bắt buộc cho LLM) |
| `GEMINI_MODEL` | `gemini-2.5-flash-lite` | Model Gemini chính |
| `GEMINI_FALLBACK_MODELS` | `gemini-flash-lite-latest,gemini-2.5-flash,gemini-2.0-flash-lite` | Chuỗi fallback |
| `ROUTER_MODEL` / `ROUTER_TEMPERATURE` | (kế thừa GEMINI_MODEL) / `0.15` | Model + temp cho intent router |
| `ROUTER_CAREER_FUZZY_THRESHOLD` | `80` | Ngưỡng fuzzy match career (rapidfuzz) |
| `GENERATOR_MODEL` / `GENERATOR_TEMPERATURE` | (kế thừa) / `0.7` | Model + temp cho response generator |
| `GENERATOR_BACKEND` | `auto` | `auto`/`gemini`/`local` — chọn backend sinh |
| `USE_LOCAL_GENERATOR` | `0` | Khi `auto`: bật Ollama local cho pathfinding/course_rec |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Endpoint Ollama |
| `OLLAMA_MODEL_PATHFINDING` / `OLLAMA_MODEL_COURSE_REC` | `career-pathfinding` / `career-course-rec` | Model Ollama theo intent |
| `OLLAMA_TIMEOUT_SECONDS` | `120` | Timeout Ollama |
| `GENERATOR_CONFIDENCE_THRESHOLD` | `0.45` | Dưới ngưỡng → formatter tĩnh thay LLM |
| `OPENAI_API_KEY` / `OPENAI_MODEL` | — / `gpt-4o-mini` | OpenAI (tùy chọn) |
| `EMBEDDING_PROVIDER` | `gemini` | `gemini`/`openai` |
| `EMBEDDING_MODEL` | `gemini-embedding-001` | Model embedding |
| `EMBEDDING_DIMENSIONS` | `768` | Số chiều embedding |
| `NEO4J_URI` / `NEO4J_USER` / `NEO4J_PASSWORD` | `bolt://localhost:7687` / `neo4j` / — | Kết nối Neo4j (production: `neo4j+s://...aura...`) |
| `QDRANT_URL` / `QDRANT_API_KEY` / `QDRANT_COLLECTION` | `http://localhost:6333` / — / `career_roadmap` | Kết nối Qdrant |
| `RETRIEVAL_GRAPH_BOOST` | `0.15` | Điểm cộng graph-aware rerank (A-03) |
| `RETRIEVAL_STRICT` | `0` | `1` = fail-fast khi Qdrant/embedding lỗi (B-02); eval bật sẵn |
| `JUDGE_PROVIDER` | `groq` | LLM judge D-03: `gemini`/`openai`/`groq` |
| `JUDGE_GROQ_API_KEY` / `GROQ_API_KEY` | — | API Groq cho judge (free tier) |
| `JUDGE_GROQ_MODEL` | `llama-3.1-8b-instant` | Model Groq judge |
| `JUDGE_GEMINI_API_KEY` / `JUDGE_GEMINI_MODEL` | — / (kế thừa GEMINI) | Judge qua Gemini |
| `JUDGE_OPENAI_API_KEY` / `JUDGE_OPENAI_MODEL` | — / `gpt-4o-mini` | Judge qua OpenAI |
| `JUDGE_REQUEST_DELAY_SECONDS` | `2.5` | Delay giữa các lần gọi judge (tránh rate limit) |
| `DATABASE_URL` | — | PostgreSQL (Neon); tự chuẩn hóa thành `postgresql+asyncpg://`. Trống → session in-memory |
| `DATABASE_ECHO` | `false` | Log SQL của SQLAlchemy |

> **Chưa có trong config (E-03):** `RETRIEVAL_VECTOR_WEIGHT`, `BM25_WEIGHT` — trọng số hybrid vẫn hard-code RRF trong `retriever.py`.

---

## 6. Tests

**Tổng:** 214 tests (`pytest tests/` — sau khi gỡ Gen 1, 2026-06).

| File | Tests gì |
|---|---|
| `test_ablation_d01.py` | Pipeline ablation D-01: fusion modes, static/generative eval |
| `test_ablation_pipeline.py` | `AblationPipeline` core, seed map, quality scores |
| `test_aliases.py` | Phân giải alias VN → nhãn chuẩn (career/competency/soft skill/subject) + mở rộng truy vấn |
| `test_aliases_multi.py` | Phân giải nhiều alias trong một câu + competency từ subject (OOP) |
| `test_career_matcher.py` | Fuzzy match tên nghề qua `CareerMatcher.resolve` |
| `test_career_multihop.py` | A-02 `fetch_courses_for_career_skills` parse/sort multi-hop |
| `test_competency_orchestrator.py` | Orchestrator bỏ qua loại năng lực rỗng + đặt đúng loại hiện tại |
| `test_confidence.py` | `compute_confidence`: cao khi found, thấp khi not-found/fallback |
| `test_corpus_builder.py` | Dựng index text course/competency (từ khóa + enrich alias subject) |
| `test_course_rec_matching.py` | Trích term năng lực (CBAP) + loại match ngắn giả (spurious "C") |
| `test_eval_answer_quality.py` | Script D-03 wiring (mock judge) |
| `test_eval_retrieval.py` | Script D-02 metrics aggregation |
| `test_fusion.py` | `FusionService.aggregate`, `map_hits_to_graph_nodes`, evidence |
| `test_generator_backend.py` | Chọn backend theo intent/cấu hình (slot_fill luôn Gemini) |
| `test_generator_prompts.py` | User prompt pathfinding/slot_fill chứa JSON Neo4j + known_skills |
| `test_graph_aware_rerank.py` | A-03 `_apply_graph_boost`, `RETRIEVAL_GRAPH_BOOST` |
| `test_graph_formatters.py` | Format pathfinding (nhóm theo kind) + course_rec |
| `test_intent_parser.py` | Bóc fence JSON, parse route JSON (gồm subject_career), fallback mặc định |
| `test_llm_judge.py` | Parse JSON judge, client factory |
| `test_local_generator.py` | `LocalGeneratorClient` gọi Ollama qua httpx (mock) |
| `test_logging_config.py` | E-01 `setup_logging` (2 test: level mapping) |
| `test_memory_session_store.py` | `MemorySessionStore` async: tạo phiên, append/lưu/đọc tin nhắn |
| `test_pathfinding_by_type.py` | `fetch_pathfinding_by_type` parse kết quả Neo4j theo loại quan hệ |
| `test_priority_ranking.py` | C-01 ORDER BY priority_group / coverage_level |
| `test_qdrant_search.py` | Adapter `query_points` vs legacy `search` |
| `test_quality_metrics.py` | D-01 faithfulness, skill recall, cosine similarity |
| `test_retrieval_metrics.py` | D-02 Precision/MRR/nDCG pure Python |
| `test_retrieval_strict.py` | B-02 `RETRIEVAL_STRICT` + `RetrieverUnavailableError` |
| `test_retriever_rrf.py` | B-01 BM25Okapi + RRF fusion |
| `test_roadmap_followup.py` | Gộp nhãn skills-gap, multi-hop courses, priority badges |
| `test_session_competency.py` | Trạng thái phiên năng lực: defaults, record known theo loại, reset flow |
| `test_session_context.py` | Ngữ cảnh phiên: router message, suy luận follow-up, điều chỉnh outcome |
| `test_skill_normalize.py` | Chuẩn hóa nhãn kỹ năng (bỏ tiền tố, trim, lower) + `normalize_skill_set` |
| `test_skills_gap.py` | Mở rộng alias kỹ năng + tách competency known/missing |
| `test_skills_gap_equivalence.py` | C-02 deprecated `apply_skills_gap` vs `apply_skills_gap_typed` |
| `test_skills_gap_typed.py` | Skills-gap theo từng loại (typed) per-block + gộp kết quả |
| `test_subject_career.py` | C-03 intent, Cypher IN_SUBJECT, format chain/reply |
| `test_tight_fusion.py` | A-01 vector hits → graph seed IDs → Cypher params |
| `test_tokenize_vi.py` | B-03 underthesea tokenizer + fallback |
| `test_validator.py` | Loại citation khóa học bịa (`[Course: ...]`) không có trong graph snapshot |

---

*Tài liệu này nên được cập nhật khi cấu trúc thay đổi đáng kể (thêm module/tầng/datastore mới).*
