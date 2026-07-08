# IT Career Goal Advisor (Graph-RAG Web)

Du an web Python tu van muc tieu nghe nghiep IT theo mo hinh Graph-RAG:

- Luu quan he ky nang -> vai tro -> roadmap -> tai nguyen trong graph.
- Tim ngu canh lien quan bang vector retrieval.
- Tong hop goi y muc tieu nghe nghiep theo ho so nguoi dung.

## Cong nghe

- FastAPI + Jinja2 (web app)
- Neo4j (knowledge graph)
- Qdrant (vector search)
- LLM provider (OpenAI-compatible API)

## Deploy len Render

Stack production tren Render gom **Web Service (Docker)** + **PostgreSQL** (trong `render.yaml`). Neo4j va Qdrant can hosted rieng (vi du [Neo4j Aura](https://neo4j.com/cloud/aura/), [Qdrant Cloud](https://qdrant.tech/cloud/)).

1. Day code len GitHub/GitLab.
2. Render Dashboard → **New** → **Blueprint** → chon repo (file `render.yaml`).
3. Khi deploy, nhap secret tren Dashboard:
   - `GEMINI_API_KEY`
   - `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD` (Aura: `neo4j+s://...`)
   - `QDRANT_URL`, `QDRANT_API_KEY` (Qdrant Cloud cluster URL + API key)
4. Sau khi Postgres san sang, ingest graph/vector tu may local (khong chay trong container Render):
   ```bash
   python scripts/ingest.py --xlsx-path "data/bộ dữ liệu.xlsx" --batch-size 500
   python scripts/index_qdrant.py
   ```
5. Kiem tra: `https://<ten-dich-vu>.onrender.com/api/health`

Chay local bang Docker (chi app; Neon + Qdrant Cloud + Neo4j Aura qua `.env`):

```bash
docker compose up -d --build
```

Build image rieng (giong Render):

```bash
docker build -t career-graph-rag .
docker run --rm -p 8000:8000 -e PORT=8000 -e GEMINI_API_KEY=... career-graph-rag
```

## Chay nhanh

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Mo trinh duyet:
- `http://127.0.0.1:8000/` (form tu van)
- `http://127.0.0.1:8000/docs` (API docs)

## Cau truc thu muc

- `app/main.py`: khoi tao FastAPI app.
- `app/api/chat_routes.py`: `POST /api/chat` — hoi thoai Graph-RAG (Gen 3).
- `app/api/advisory_routes.py`: `POST /api/advisory/*` — form tu van (Gen 2).
- `app/services/chat_service.py`: orchestrator chat (intent, tight fusion, generator).
- `app/services/advisory_service.py`: luong form + structured advice JSON.
- `app/rag/graph_builder.py`: truy van graph context (form advisory).
- `app/rag/retriever.py`: hybrid retrieval vector + BM25/RRF.
- `frontend/`: `form.html`, `chat.html` (giao dien chinh).
- `scripts/ingest.py`: script nap du lieu mau vao graph/vector.

> `POST /api/advise` (Gen 1 legacy) da go. Dung `/api/advisory` hoac `/api/chat`.

## Bien moi truong (`.env`)

```env
OPENAI_API_KEY=your_key
OPENAI_MODEL=gpt-4o-mini
NEO4J_URI=neo4j+s://your-instance.databases.neo4j.io
NEO4J_USER=neo4j
NEO4J_PASSWORD=your_neo4j_password
QDRANT_URL=https://your-cluster.cloud.qdrant.io
QDRANT_API_KEY=your_qdrant_api_key
QDRANT_COLLECTION=career_roadmap
```

## Qdrant Cloud (vector search)

1. Tạo cluster trên [Qdrant Cloud](https://cloud.qdrant.io/) → **Data** → copy **Cluster URL** và **API Key**.
2. Thêm vào `.env`:
   ```env
   QDRANT_URL=https://xxxxxxxx.us-east-1-0.aws.cloud.qdrant.io
   QDRANT_API_KEY=...
   QDRANT_COLLECTION=career_roadmap
   ```
3. Index corpus lên cluster (chạy trên máy local, cần `GEMINI_API_KEY` / embedding):
   ```bash
   python scripts/validate_graph_coverage.py --min-relation-edges 30
   python scripts/build_index_corpus.py
   python scripts/index_qdrant.py
   ```
4. Kiểm tra: `GET /api/health` → `checks.qdrant` = `"ok"`.

### Re-index Qdrant (maintenance window)

Sau khi mở rộng `competency_relation`, cần **full rebuild** collection (chatbot mất RAG ~5–15 phút):

1. Thông báo downtime cho người dùng.
2. `python scripts/validate_graph_coverage.py --min-relation-edges 30`
3. `python scripts/build_index_corpus.py` (fail-fast nếu graph thiếu cạnh relation)
4. `python scripts/index_qdrant.py` — xóa và tạo lại collection
5. `python scripts/smoke_ablation.py` — xác nhận retrieval + graph

### Biến môi trường `competency_relation`

```env
COMPETENCY_RELATION_ENRICH=1          # enrich pathfinding/course_rec (mặc định bật)
COMPETENCY_RELATION_INTENT_ENABLED=0  # intent riêng — bật khi coverage ≥ 40%
COMPETENCY_RELATION_MIN_COVERAGE=0.40
```

Validate sau ingest: `python scripts/validate_ingest.py` và `python scripts/validate_graph_coverage.py --min-coverage 0.40 --warn-only`

`docker-compose.yml` không còn DB local; app đọc biến môi trường từ `.env`.

## Neo4j Aura (knowledge graph)

1. Tạo instance trên [Neo4j Aura](https://neo4j.com/cloud/aura/).
2. Trong `.env` dùng đúng tên biến (không dùng `NEO4J_USERNAME`):
   ```env
   NEO4J_URI=neo4j+s://xxxxxxxx.databases.neo4j.io
   NEO4J_USER=neo4j
   NEO4J_PASSWORD=...
   ```
3. Nạp graph từ Excel:
   ```bash
   python scripts/ingest.py --xlsx-path "data/bộ dữ liệu.xlsx" --batch-size 500
   ```

## PostgreSQL (chat + profile v2)

```bash
python scripts/reset_db_v2.py
```

Xóa **chỉ dữ liệu** (giữ schema, nhanh khi demo lại):

```bash
python scripts/clear_postgres_data.py --yes
```

Schema: `user_profiles`, `chat_sessions`, `chat_messages`, `advice_results`.  
Form API: `POST /api/advisory/start`

### Chuyển DB local → Neon

1. Tạo project trên [Neon](https://neon.tech), copy **Pooled connection string** (`postgresql://...?sslmode=require`).
2. Gán vào `.env` làm `DATABASE_URL` (app tự đổi sang `postgresql+asyncpg` và bật SSL).
3. Migrate bảng + dữ liệu từ Docker Postgres:

```powershell
.\scripts\migrate_local_to_neon.ps1
```

Chỉ schema trống trên Neon (không có dữ liệu local): `python scripts/reset_db_v2.py` với `DATABASE_URL` Neon.

Chỉ dữ liệu (schema đã có): `.\scripts\migrate_local_to_neon.ps1 -DataOnly`

## Ghi chu

Bo khung nay tap trung vao kien truc va luong xu ly. Ban co the thay prompt, schema du lieu,
hoac bo sung ranking de nang chat luong tu van muc tieu nghe nghiep IT.

## Nap du lieu XLSX vao Neo4j

File du lieu chinh: `data/bộ dữ liệu.xlsx`

```bash
pip install -r requirements.txt
python scripts/ingest.py --xlsx-path "data/bộ dữ liệu.xlsx" --batch-size 500
```

Neu DB cu dung schema cu (`:Competency`, `REQUIRES`, `TEACHES`), nen xoa graph roi nap lai:

```bash
python scripts/ingest.py --xlsx-path "data/bộ dữ liệu.xlsx" --batch-size 500 --reset-graph
```

Script se:
- Tao constraint can thiet; tuy chon `--reset-graph` de xoa toan bo nut/can va constraint cu.
- Upsert nut theo loai (Knowledge, Tool, ProgrammingLanguage, ...), Career, Course, Industry, Taxonomy, ...
- Gan thuoc tinh `color` (hex) dong bo voi `design/neo4j_browser_palette.grass`.
- Quan he career-nang luc: `NEED_KNOW`, `NEED_TOOL`, `NEED_LANG`, ...; course-nang luc: `TEACH_*`.
- In thong ke so dong da ingest.

## Ve bieu do node-link (kieu force graph)

Ban co the tao bieu do lien ket node giong kieu anh minh hoa:

```bash
python scripts/visualize_graph.py
```

Lenh nay tao file `graph_rag_network.html`. Mo file bang trinh duyet de keo/thả, zoom va xem
moi quan he giua cac node (Student -> Role -> Skill -> Roadmap -> Resource + vector chunks).
