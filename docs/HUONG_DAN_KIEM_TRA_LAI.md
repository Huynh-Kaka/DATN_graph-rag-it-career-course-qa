# Hướng dẫn kiểm tra lại toàn bộ (Graph-RAG v2.2)

Tài liệu này dùng khi hội đồng yêu cầu tái lập kết quả sau nâng cấp bộ kiểm tra v2.2 (52 case E2E, cohort KPI).

## Bước 0 — Điều kiện tiên quyết

| Hạ tầng | Kiểm tra |
|---------|----------|
| Python 3.12+ | `python --version` |
| `.env` | `NEO4J_*`, `QDRANT_*`, `GEMINI_API_KEY` hoặc `CHATBOT_LOCAL_*` |
| Neo4j | Graph đã ingest |
| Qdrant | Collection `career_roadmap` có dữ liệu |
| Judge E2E | `JUDGE_PROVIDER=local` (fallback Groq → Gemini) |

```powershell
cd D:\Doantotnghiep
```

## Bước 1 — Kiểm thử hồi quy tự động (bắt buộc)

```powershell
python -m pytest tests/ -q --tb=short
```

**Kỳ vọng:** ≥ 300 test pass.

```powershell
python -m pytest tests/test_competency_relation_scoring.py tests/test_competency_relation_followup.py tests/test_build_answer_quality_gold.py tests/test_eval_answer_quality.py -v
```

## Bước 2 — Build & validate gold (bắt buộc)

```powershell
python scripts/build_answer_quality_gold.py --out data/eval/answer_quality_gold.jsonl --probe-neo4j
python scripts/export_gold_subset.py --all
python scripts/validate_gold.py data/eval/answer_quality_gold.jsonl --probe-neo4j
```

**Kỳ vọng:** 52 case; 0 errors build probe; subsets `baseline14` / `v21_38` / `v22_new14`.

## Bước 3 — Baseline D0 (tham chiếu attribution)

```powershell
python scripts/eval_answer_quality.py `
  --gold data/eval/answer_quality_gold_v21_38.jsonl `
  --output-csv results/baseline_pre_router_v22.csv `
  --report-json results/baseline_pre_router_v22.json `
  --run-label v2.2-D0 `
  --delay 2.5
```

Hoặc dùng baseline đóng băng từ lần chạy v2.1: `results/baseline_pre_router_v22.json` (`source: v2.1_run_2026-06-22_frozen_csv`).

## Bước 4 — Retrieval D-02 (bắt buộc)

```powershell
python scripts/eval_retrieval.py --k 5 --output-csv data/eval/retrieval_results.csv
python scripts/analyze_gold_triviality.py
```

| Chỉ số | Ngưỡng |
|--------|--------|
| HitRate@5 overall | ≥ 58% |
| RecallFull@5 competency | ≥ 45% |

## Bước 5 — Judge smoke (bắt buộc trước E2E)

```powershell
python scripts/smoke_judge.py
```

## Bước 6 — E2E D1 post-fix (cohort v21_38)

```powershell
python scripts/eval_answer_quality.py `
  --gold data/eval/answer_quality_gold_v21_38.jsonl `
  --output-csv results/post_fix_v21_38.csv `
  --report-json results/post_fix_v21_38.json `
  --run-label v2.2-D1 `
  --delay 2.5
```

| Cohort `v21_38` | Ngưỡng chính |
|-----------------|--------------|
| valid_run | ≥ 87% |
| route_mismatch | ≤ 2 case |

## Bước 7 — E2E D2 full 52 case (chạy khi sẵn sàng)

```powershell
# Khuyến nghị judge local để tránh 413/503
$env:JUDGE_PROVIDER="local"

python scripts/eval_answer_quality.py `
  --gold data/eval/answer_quality_gold.jsonl `
  --output-csv data/eval/answer_quality_results.csv `
  --report-json results/eval_summary.json `
  --run-label v2.2-D2 `
  --delay 2.5

python scripts/summarize_eval_results.py `
  --report-json results/eval_summary.json `
  --baseline results/baseline_pre_router_v22.json `
  --out results/verification_summary_v22.json
```

Sau khi chạy xong, cập nhật dòng `[v2.2-D2]` trong bảng **Lịch sử kiểm tra** (Bước 9) và mục X.2ter trong `ket_qua_thuc_nghiem.md` từ `results/eval_summary.json` → `by_cohort`.

| Cohort | Ngưỡng |
|--------|--------|
| `v21_38` | valid_run ≥ 87% (KPI thesis chính) |
| `v22_new14` | valid_run ≥ 80% (coverage phụ) |
| `full52` | valid_run ≥ 90% chỉ khi `v21_38` đạt 87% |
| faithfulness (valid) | ≥ 78% |
| competency_relation completeness | ≥ 55% |

Regression nhanh (~5 phút):

```powershell
python scripts/eval_answer_quality.py --gold data/eval/answer_quality_gold_baseline14.jsonl --delay 2
```

## Bước 8 — Script gom một lệnh

```powershell
.\scripts\run_full_verification.ps1
# Chỉ baseline: .\scripts\run_full_verification.ps1 -BaselineOnly
# Chỉ D1 38 case: .\scripts\run_full_verification.ps1 -PostFix38 -SkipBuildGold
```

## Bước 9 — Ghi nhận cho hội đồng

- [ ] pytest pass
- [ ] gold 52 case + probe ok
- [ ] D0/D1/D2 report JSON có `by_cohort`
- [ ] Cập nhật `ket_qua_thuc_nghiem.md` (thêm dòng changelog mới)

### Lịch sử kiểm tra

| Mốc | Ngày | Cohort | valid_run | route_mm | faithfulness | Ghi chú |
|-----|------|--------|-----------|----------|--------------|---------|
| [v2.1-final] | 2026-06-22 | v21_38 | 73,68% | 7 | 76,79% | Trước plan v2.2 |
| [v2.2-D0] | 2026-06-22 | v21_38 | 73,68% | 7 | 76,79% | Frozen CSV v2.1 (baseline attribution) |
| [v2.2-D1] | 2026-06-23 | v21_38 | 89,47% (34/38) | 4 | 76,18% | Sau router/judge fix; infra=0 |
| [v2.2-D2-rerun] | 2026-06-24 | full52 | 84,62% (44/52) | 5 | 75,68% | delay 6s; infra=3 (skills_gap 413) |

> **Quy ước:** mỗi lần kiểm tra thêm **một dòng mới**; không sửa dòng cũ (trừ typo).
