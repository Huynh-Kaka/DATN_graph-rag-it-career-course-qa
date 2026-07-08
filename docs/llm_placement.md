# Vị trí LLM trong hệ thống

## Tóm tắt

| Vai trò | Model | Bật local khi nào |
|---------|--------|-------------------|
| **Intent router** | Gemini (`ROUTER_MODEL`) | Không — luôn API |
| **Sinh câu trả lời chat** (pathfinding, course_rec) | Ollama hoặc Gemini | `USE_LOCAL_GENERATOR=1` + model Ollama |
| **Slot fill** (hỏi thêm slot) | Gemini | Không dùng Ollama |
| **Form tư vấn** (`/api/advisory/start`) | Gemini | Không |
| **Embedding** (Qdrant, exemplar) | Gemini/OpenAI embedding | Không phải chat LLM |

## Cấu hình `.env`

```env
GENERATOR_BACKEND=auto   # auto | gemini | local
USE_LOCAL_GENERATOR=1    # auto: bật nhánh Ollama cho pathfinding/course_rec
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL_PATHFINDING=career-pathfinding
OLLAMA_MODEL_COURSE_REC=career-course-rec
```

- `GENERATOR_BACKEND=gemini` — luôn Gemini cho generator (bỏ qua Ollama).
- `GENERATOR_BACKEND=local` — ưu tiên Ollama; lỗi thì fallback Gemini.
- `GENERATOR_BACKEND=auto` — theo `USE_LOCAL_GENERATOR`.

## Chuỗi fallback (generator)

```text
Local Ollama → Gemini → formatter tĩnh (Neo4j)
```

## Kiểm tra

```powershell
python scripts/check_llm_setup.py
curl http://127.0.0.1:8000/api/health
```

Response chat có thêm `generator_backend` (vd. `local`, `gemini`, `gemini_fallback`, `formatter_static`).

## Ollama (sau Colab)

```powershell
ollama create career-pathfinding -f colab_LLM/Modelfile.pathfinding
ollama create career-course-rec -f colab_LLM/Modelfile.course_rec
```
