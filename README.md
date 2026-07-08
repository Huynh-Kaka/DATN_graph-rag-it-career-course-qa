# IT Career Goal Advisor — Graph-RAG

Web app tư vấn mục tiêu nghề nghiệp IT theo mô hình **Graph-RAG**: kết hợp **Neo4j** (knowledge graph), **Qdrant** (vector search), **PostgreSQL** (phiên chat) và **Google Gemini** (LLM).

**Repo:** https://github.com/Huynh-Kaka/DATN_graph-rag-it-career-course-qa

> Tài liệu chi tiết (biến môi trường, thí nghiệm D-01/D-02/D-03, lỗi thường gặp): xem **[README_SETUP.md](README_SETUP.md)**

---

## Yêu cầu

| Thành phần | Cách A — Docker (khuyến nghị) | Cách B — Local |
|------------|-------------------------------|----------------|
| Docker Desktop + Compose v2 | ✅ Cần | ❌ |
| Python 3.12+ | ❌ | ✅ Cần |
| Neo4j / Qdrant / PostgreSQL | Tự dựng qua Docker | Tự cài hoặc dùng cloud |
| Gemini API key | ✅ Bắt buộc | ✅ Bắt buộc |
| Node.js | ❌ Không cần | ❌ Không cần |

---

## Các bước chạy dự án

### Bước 1 — Tải mã nguồn

```powershell
git clone https://github.com/Huynh-Kaka/DATN_graph-rag-it-career-course-qa.git
cd DATN_graph-rag-it-career-course-qa
```

### Bước 2 — Tạo file `.env`

File `.env` **không có trên Git**. Bạn tự tạo từ mẫu:

```powershell
Copy-Item .env.example .env
notepad .env
```

**Điền tối thiểu:**

```env
GEMINI_API_KEY=your-gemini-api-key
CHATBOT_LLM_MODE=2
```

- Lấy Gemini API key tại: https://aistudio.google.com/apikey  
- `CHATBOT_LLM_MODE=2` = dùng Gemini trực tiếp (không cần proxy LLM local)

> **Chạy Docker:** không cần sửa `NEO4J_URI`, `QDRANT_URL`, `DATABASE_URL` — `docker-compose.yml` tự trỏ tới các container DB.

---

### Bước 3A — Chạy bằng Docker (khuyến nghị)

#### 3A.1 Dựng toàn bộ hệ thống

```powershell
docker compose up -d --build
```

Docker sẽ khởi động 4 service:

| Service | URL trên máy bạn |
|---------|------------------|
| App (API + giao diện) | http://127.0.0.1:8000 |
| Neo4j Browser | http://localhost:7474 |
| Qdrant | http://localhost:6333 |
| PostgreSQL | `localhost:5432` |

Kiểm tra container:

```powershell
docker compose ps
```

Đợi ~30–60 giây cho lần đầu (`neo4j` và `postgres` cần trạng thái `healthy`).

#### 3A.2 Nạp dữ liệu (chạy một lần)

Graph và vector index **chưa có sẵn** — phải chạy sau khi container đã lên:

```powershell
docker compose exec app python scripts/ingest.py --xlsx-path "data/bộ dữ liệu.xlsx" --batch-size 500 --reset-graph
docker compose exec app python scripts/validate_ingest.py
docker compose exec app python scripts/build_index_corpus.py
docker compose exec app python scripts/index_qdrant.py
```

#### 3A.3 Kiểm tra & mở app

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/health
```

**Kỳ vọng:** `status: "ok"`, `checks.neo4j = "ok"`, `checks.qdrant = "ok"`, `checks.gemini = "configured"`.

Mở trình duyệt:

| Trang | URL |
|-------|-----|
| Trang chủ | http://127.0.0.1:8000/ |
| Chat | http://127.0.0.1:8000/chat.html |
| Form tư vấn | http://127.0.0.1:8000/form.html |
| API docs | http://127.0.0.1:8000/docs |

**Thử nhanh:** vào Chat, gõ `Làm Backend Developer cần học những gì?` → bot trả lời lộ trình kỹ năng và gợi ý khóa học.

---

### Bước 3B — Chạy local (không Docker)

#### 3B.1 Cài dependencies

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

#### 3B.2 Cấu hình `.env` đầy đủ

Ngoài `GEMINI_API_KEY`, điền thêm kết nối DB (local hoặc cloud):

```env
GEMINI_API_KEY=your-gemini-api-key
CHATBOT_LLM_MODE=2
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=your-neo4j-password
QDRANT_URL=http://localhost:6333
QDRANT_API_KEY=
QDRANT_COLLECTION=career_roadmap
DATABASE_URL=postgresql://career:careerpass@localhost:5432/careerdb
```

Neo4j, Qdrant và PostgreSQL phải **đang chạy** trước khi tiếp tục.

#### 3B.3 Nạp dữ liệu (chạy một lần)

```powershell
python scripts/ingest.py --xlsx-path "data/bộ dữ liệu.xlsx" --batch-size 500 --reset-graph
python scripts/validate_ingest.py
python scripts/build_index_corpus.py
python scripts/index_qdrant.py
python scripts/reset_db_v2.py
```

#### 3B.4 Chạy server

```powershell
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Mở http://127.0.0.1:8000/chat.html và thử chat như mục 3A.3.

---

## Kiến trúc tóm tắt

```text
Người dùng (chat.html / form.html)
    → FastAPI (app/main.py)
        → Intent Router (Gemini)
        → Retriever: Qdrant (vector + BM25) + Neo4j (graph) → RRF fusion
        → Response Generator (Gemini) → Validator
    → PostgreSQL (lưu phiên chat, feedback)
```

---

## Cấu trúc thư mục chính

```text
app/              Backend FastAPI (API, RAG, graph, LLM)
frontend/         Giao diện web (HTML/CSS/JS tĩnh)
scripts/          Ingest, index, eval (ingest.py, index_qdrant.py, ...)
data/             Dữ liệu nguồn (bộ dữ liệu.xlsx, corpus, gold eval)
tests/            Pytest (~300+ test)
docker-compose.yml   Docker: app + Neo4j + Qdrant + PostgreSQL
Dockerfile        Image Python 3.12
.env.example      Mẫu cấu hình (copy thành .env)
README_SETUP.md   Hướng dẫn chi tiết đầy đủ
```

---

## Lỗi thường gặp

| Triệu chứng | Cách xử lý |
|-------------|------------|
| `neo4j: unavailable` | Chưa chạy Bước nạp dữ liệu, hoặc sai `NEO4J_*` |
| `qdrant: unavailable` | Chưa chạy `index_qdrant.py` |
| Chat trả lỗi 503 | Kiểm tra `GEMINI_API_KEY` / quota Gemini |
| Không có lịch sử chat | `DATABASE_URL` trống → session in-memory (vẫn chat được) |
| `chatbot_local: unavailable` | Đặt `CHATBOT_LLM_MODE=2` trong `.env` |

Chi tiết thêm: [README_SETUP.md — mục 6](README_SETUP.md#6-các-lỗi-thường-gặp-khi-setup-và-cách-xử-lý)

---

## Thí nghiệm & đánh giá

| Mã | Nội dung | Script |
|----|----------|--------|
| D-01 | Ablation Graph-RAG (4 nhánh fusion) | `scripts/run_quality_ablation.py` |
| D-02 | Đánh giá retrieval (Qdrant + BM25 + RRF) | `scripts/eval_retrieval.py` |
| D-03 | E2E LLM-as-Judge (pipeline đầy đủ) | `scripts/eval_answer_quality.py` |

Hướng dẫn chi tiết: [README_SETUP.md — mục 5](README_SETUP.md#5-thí-nghiệm--đánh-giá-d-01--d-02--d-03)

---

## Tài liệu tham khảo

- [README_SETUP.md](README_SETUP.md) — hướng dẫn cài đặt đầy đủ
- [docs/HUONG_DAN_DEMO.md](docs/HUONG_DAN_DEMO.md) — kịch bản demo
- [docs/HUONG_DAN_THI_NGHIEM_D01_D02_D03.md](docs/HUONG_DAN_THI_NGHIEM_D01_D02_D03.md) — metric thí nghiệm
