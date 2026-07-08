# Experiments (draft) — Phase 2

## RQ4

SFT từ log chat đã duyệt có cải thiện fluency tiếng Việt mà vẫn grounded so với Gemini+graph?

## Baselines

| ID | Mô tả |
|----|--------|
| B3 | Neo4j + Gemini + session (mặc định) |
| B3−vector | B3 không inject Qdrant context |
| B4 | B3 + `USE_LOCAL_GENERATOR=1` (Ollama) |

Chạy: `python scripts/run_ablation.py --message "Backend Developer cần học gì?"`

## Metrics

- **Offline:** val loss / perplexity (Colab), ROUGE-L trên 20 câu val
- **Grounding:** `hallucination_rate` — % citation `[Course: CODE]` không có trong graph
- **Retrieval:** Recall@5 trên 50 câu gold (sau `scripts/index_qdrant.py`)
- **Human:** Likert 1–5 trên 30 câu (3 người × 10 câu): đúng nghề, grounded, hữu ích

## Human eval protocol

1. Chọn 30 câu từ `data/eval/` hoặc export val set.
2. Mỗi người chấm độc lập; tính trung bình và Cohen's κ giữa 2 người (nếu đủ thời gian).
3. So sánh B3 vs B4 trên cùng câu hỏi.

## Artifacts

- `data/ft_generator_*_train.jsonl`
- `scripts/export_chat_dataset.py`
- `colab_LLM/Modelfile.*`
