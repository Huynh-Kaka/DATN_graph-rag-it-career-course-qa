# Chương X — Kết quả thực nghiệm

Hệ thống Graph-RAG tư vấn hướng nghiệp IT được đánh giá trên ba trục: (1) chất lượng truy hồi thông tin (retrieval), (2) chất lượng câu trả lời end-to-end (LLM-as-a-Judge), và (3) độ tin cậy của tập gold đánh giá (provenance). Các thí nghiệm được thiết kế sau khi rà soát phương pháp luận nhằm tách bạch lỗi vận hành (infra), lỗi định tuyến (route) và chất lượng nội dung thực sự của hệ thống.

---

## X.1. Thiết lập thực nghiệm

### X.1.1. Môi trường và công cụ

- **Knowledge graph:** Neo4j, nạp từ tập Excel nguồn `data/bộ dữ liệu.xlsx`.
- **Vector retrieval:** Qdrant + BM25Okapi + RRF fusion; chế độ `RETRIEVAL_STRICT=1` khi đánh giá retrieval.
- **LLM:** Gemini (router + generator); judge đánh giá E2E: Groq `llama-3.1-8b-instant`.
- **Kiểm thử hồi quy:** **301** unit/integration test (`pytest`), tất cả pass (sau nâng cấp v2.2).

### X.1.2. Tập dữ liệu gold

| Tập gold | Số mẫu | Mục đích | Nguồn nhãn (`gold_source`) |
|----------|--------|----------|------------------------------|
| `retrieval_gold.jsonl` | 248 | Đánh giá retrieval (D-02) | Gán nhãn thủ công / paraphrase |
| `answer_quality_gold.jsonl` | **52** | Đánh giá E2E LLM judge (D-03) | `quality_gold_v2.1` (38) + `quality_gold_v2.2` (14) |
| `answer_gold.jsonl` | 25 | Ablation chất lượng (D-01) | `derived_from_graph_repository` |
| `answer_gold_independent.jsonl` | 45 | Ablation độc lập runtime | `excel_derived` (từ Excel, không gọi GraphRepository) |

**Lưu ý phương pháp luận:** Bộ `excel_derived` phá vòng tròn đánh giá tại runtime (không truy vấn Neo4j khi sinh gold), nhưng vẫn cùng nguồn dữ liệu gốc với quá trình ingest graph. Trong luận văn, bộ này được mô tả là *độc lập implementation*, không phải *độc lập provenance hoàn toàn*.

### X.1.3. Quy tắc đo lường đã chuẩn hóa

1. **Route validity (D-03):** Mỗi lượt E2E được gắn nhãn `valid_run`, `route_mismatch` hoặc `infra_error`. Chỉ các lượt `valid_run` mới đưa vào aggregate faithfulness và skill completeness.
2. **Định tuyến chấp nhận được:** Không so khớp intent cứng 1-1; dùng tập `ACCEPTABLE_ROUTES` (ví dụ `skills_gap` chấp nhận `pathfinding` khi phiên đã có profile).
3. **Retrieval:** Báo cáo song song **HitRate@k** (hit nhị phân: có ≥1 relevant trong top-k) và **RecallFull@k** (|relevant ∩ top-k| / |relevant|), cùng **MAP@k**.
4. **Độ khó truy vấn:** Phân loại `trivial` (query chứa sẵn entity gold) vs `paraphrased`.

---

## X.2. Kết quả đánh giá retrieval (D-02)

Thực nghiệm chạy trên toàn bộ 248 truy vấn trong `retrieval_gold.jsonl`, cutoff **k = 5**.

### Bảng X.1 — Metric retrieval theo phạm vi (k = 5, N = 248)

| Phạm vi | HitRate@5 | RecallFull@5 | MAP@5 | MRR | nDCG@5 |
|---------|-----------|--------------|-------|-----|--------|
| Toàn bộ | 60,48% | 59,68% | 0,3716 | 0,3765 | 0,4309 |
| `career` (N=152) | 61,84% | 61,84% | 0,4026 | 0,4046 | 0,4568 |
| `course` (N=79) | 62,03% | 62,03% | 0,3485 | 0,3601 | 0,4195 |
| `competency` (N=17) | 41,18% | **29,41%** | 0,2010 | 0,2010 | 0,2525 |
| Truy vấn *paraphrased* (N=120) | 57,50% | 55,83% | 0,3564 | 0,3614 | 0,4113 |
| Truy vấn *trivial* (N=128) | 63,28% | 63,28% | 0,3858 | 0,3906 | 0,4492 |

### Bảng X.2 — Phân bố độ khó truy vấn retrieval

| Nhãn | Số lượng | Tỷ lệ |
|------|----------|-------|
| Trivial | 128 | 51,6% |
| Paraphrased | 120 | 48,4% |

Phân bố theo `doc_type` × độ khó: `career:paraphrased` (93), `course:trivial` (69), `career:trivial` (59), `competency:paraphrased` (17), `course:paraphrased` (10).

### Nhận xét (Retrieval)

1. **HitRate@5 toàn tập đạt 60,48%**, thấp hơn đáng kể so với con số ~95% quan sát trên subset 20 truy vấn đầu — cho thấy subset nhỏ không đại diện và dễ gây đánh giá lạc quan.
2. **RecallFull@5 (59,68%) thấp hơn HitRate@5 (60,48%) 0,8 điểm phần trăm** ở mức toàn tập; chênh lệch **lớn hơn rõ rệt ở `competency` (11,77 điểm phần trăm)**, nơi một truy vấn có thể có nhiều tài liệu liên quan nhưng retriever chỉ tìm được một phần.
3. Truy vấn **trivial đạt ~63%**, cao hơn **paraphrased ~57%** khoảng 6 điểm phần trăm — một nửa tập gold chứa gợi ý trực tiếp trong câu hỏi, nên metric retrieval phản ánh cả khớp lexical lẫn hiểu ngữ nghĩa.
4. **`competency` là nhóm yếu nhất** (RecallFull 29,41%), phù hợp với đặc thù ontology đa nhãn (ProgrammingLanguage, Framework, …) và truy vấn ngắn.

---

## X.2bis. Kết quả sau nâng cấp Graph-RAG v2.1 (22/06/2026)

Các thay đổi chính: RRF `K`/`POOL` cấu hình hoá; scoring router `competency_relation` + follow-up đa lượt; edge documents + cap edge trong rerank; gold E2E mở rộng 38 case; judge fallback Local→Groq→Gemini.

### Bảng X.1b — Retrieval sau tối ưu (k = 5, N = 248; `data/eval/retrieval_results.csv`, verification 22/06/2026)

| Phạm vi | HitRate@5 | RecallFull@5 | MAP@5 | So baseline (18/06) |
|---------|-----------|--------------|-------|---------------------|
| Toàn bộ | **65,32%** | **64,72%** | 0,4157 | +4,84 / +5,04 điểm % |
| `career` (N=152) | **67,76%** | **67,76%** | 0,4263 | +5,92 điểm % |
| `course` (N=79) | 56,96% | 56,96% | 0,3392 | −5,07 điểm % |
| `competency` (N=17) | **82,35%** | **73,53%** | 0,6765 | **+44,12 điểm %** RecallFull |
| Truy vấn *paraphrased* (N=120) | 70,83% | 69,58% | 0,4665 | — |
| Truy vấn *trivial* (N=128) | 60,16% | 60,16% | 0,3681 | — |

**Đạt KPI v2.1:** RecallFull@5 competency ≥ 45% (đạt 73,53%). Career cải thiện; course giảm nhẹ (−5,07 điểm %) — cần ghi nhận trong hạn chế.

---

## X.2ter. Kết quả sau nâng cấp bộ kiểm tra v2.2 (23/06/2026)

Các thay đổi chính: gold **52 case** (cohort `v21_legacy` 38 + `v22_new14` 14); scoring guard `course_rec` vs `competency_relation`; follow-up phân biệt relation vs pivot course_rec; judge payload thu nhỏ `skills_gap`; probe Neo4j bắt buộc khi build gold; báo cáo `--report-json` theo cohort.

### Lịch sử kiểm tra (changelog)

| Mốc | Ngày | Cohort | valid_run | route_mm | infra | faithfulness (valid) | Ghi chú |
|-----|------|--------|-----------|----------|-------|----------------------|---------|
| [v2.1-final] | 2026-06-22 | v21_38 | 73,68% (28/38) | 7 | 3 | 76,79% | Trước v2.2 |
| [v2.2-D0] | 2026-06-22 | v21_38 | 73,68% (28/38) | 7 | 3 | 76,79% | Baseline đóng băng CSV v2.1 |
| [v2.2-D1] | 2026-06-23 | v21_38 | **89,47% (34/38)** | **4** | **0** | **76,18%** | Sau router/judge fix |
| [v2.2-D2] | 2026-06-24 | full52 | 88,46% (46/52) | 5 | 1 | 75,22% | delay 2,5s; lần chạy trước |
| **[v2.2-D2-rerun]** | **2026-06-24** | **full52** | **84,62% (44/52)** | **5** | **3** | **75,68%** | **delay 6s; Groq judge — báo cáo chính thức** |

### Bảng X.3d — Cohort KPI ([v2.2-D2-rerun], delay 6s)

| Cohort | N | valid_run | route_mm | infra | faithfulness (valid) | skill compl. | Ghi chú |
|--------|---|-----------|----------|-------|----------------------|--------------|---------|
| `v21_legacy` | 38 | **81,58% (31/38)** | 4 | **3** | 74,52% | 72,90% | Infra 413 skills_gap tái phát |
| `v22_new14` | 14 | **92,86% (13/14)** | 1 | 0 | **78,46%** | 73,85% | Đạt KPI valid ≥80% |
| `full52` | 52 | **84,62% (44/52)** | 5 | 3 | **75,68%** | **73,18%** | Chưa đạt 90% valid toàn tập |

Lệnh đọc nhanh:

```powershell
python -c "import json; d=json.load(open('results/eval_summary.json',encoding='utf-8')); print(json.dumps(d.get('by_cohort',d.get('overall')), indent=2, ensure_ascii=False))"
```

### Bảng X.3c — Attribution D0 → D1 (cohort `v21_38` only)

| Chỉ số | [v2.2-D0] | [v2.2-D1] | Δ |
|--------|-----------|-----------|---|
| valid_run | 28/38 (73,68%) | **34/38 (89,47%)** | **+6 case** |
| route_mismatch | 7 | **4** | **−3** |
| infra_error | 3 | **0** | **−3** (judge payload cap) |
| faithfulness (valid) | 76,79% | 76,18% | −0,6 điểm % |

**Route mismatch còn lại (D1):** `rel_spring_02` (→ pathfinding); `mt_rel_*` ×3 (lượt 2 → course_rec).

**Cải thiện rõ:** `cr_react_01`, `cr_fastapi_02`, `sg_bc_01` và 3 case infra `skills_gap` đã valid.

Playbook: [`docs/HUONG_DAN_KIEM_TRA_LAI.md`](docs/HUONG_DAN_KIEM_TRA_LAI.md) · Baseline: `results/baseline_pre_router_v22.json` · D1: `results/post_fix_v21_38.json` · D2: `results/eval_summary.json`

---

## X.3ter. Kết quả E2E D-03 full 52 case ([v2.2-D2-rerun], 24/06/2026)

Pipeline đầy đủ `ChatService` trên **52 case** (`answer_quality_gold.jsonl`: cohort `v21_legacy` 38 + `v22_new14` 14), chấm LLM-as-a-Judge (Groq `llama-3.1-8b-instant`), **delay judge 6 giây** (giảm rate limit). Kết quả: `data/eval/answer_quality_results.csv`, `results/eval_summary.json`, log `logs/eval_e2e_d2_delay6.txt`.

### Bảng X.3e — Tỉ lệ vận hành E2E (full52, N = 52)

| Chỉ số | Giá trị |
|--------|---------|
| `valid_run` | **44/52 (84,62%)** |
| `route_mismatch` | **5 (9,62%)** |
| `infra_error` | **3 (5,77%)** |
| Faithfulness (valid) | **75,68%** |
| Skill completeness (valid) | **73,18%** |
| No-hallucination (valid) | **75,00%** |
| Valid citations | **100%** |

**Route mismatch (5):** `rel_spring_02` (competency_relation → pathfinding); `mt_rel_react_vue_01`, `mt_rel_aws_azure_01`, `mt_rel_django_fastapi_01`, `mt_rel_angular_vue_v22_01` (multi-turn lượt 2 → course_rec).

**Infra error (3):** `sg_be_02`, `sg_devops_02`, `sg_cloud_02` — judge Groq lỗi **413** (payload context quá lớn cho skills_gap); delay 6s không khắc phục được lỗi kích thước request.

### Bảng X.3f — Chất lượng E2E theo intent (valid_run, N = 44)

| Intent | N valid | Faithfulness | Skill completeness | No-hallucination |
|--------|---------|--------------|-------------------|------------------|
| **Toàn tập** | 44 | **75,68%** | **73,18%** | **75,00%** |
| Pathfinding | 10 | 75,00% | 74,00% | 50,00% |
| Course rec | 12 | **95,83%** | **90,00%** | **100%** |
| Skills gap | 7 | 75,71% | 65,71% | 57,14% |
| Competency relation | 15 | 60,00% | 62,67% | 80,00% |

### Bảng X.3g — So sánh cohort trong cùng lần chạy D2-rerun

| Cohort | N | valid_run | route_mm | infra | Faithfulness | Skill compl. |
|--------|---|-----------|----------|-------|--------------|--------------|
| `v21_legacy` | 38 | 81,58% | 4 | 3 | 74,52% | 72,90% |
| `v22_new14` | 14 | **92,86%** | 1 | 0 | **78,46%** | 73,85% |
| **full52** | 52 | **84,62%** | 5 | 3 | **75,68%** | **73,18%** |

### Bảng X.3h — Lịch sử kiểm tra E2E (D0 → D2)

| Mốc | Cohort | valid_run | route_mm | infra | Faithfulness (valid) | Ghi chú |
|-----|--------|-----------|----------|-------|----------------------|---------|
| D0 | v21_38 | 73,68% | 7 | 3 | 76,79% | Baseline đóng băng |
| D1 | v21_38 | **89,47%** | 4 | **0** | 76,18% | Sau router/judge fix |
| D2 (delay 2,5s) | full52 | 88,46% | 5 | 1 | 75,22% | Lần chạy trước |
| **D2-rerun (delay 6s)** | **full52** | **84,62%** | **5** | **3** | **75,68%** | **Báo cáo chính thức** |

### Nhận xét (E2E D2-rerun)

1. **Delay 6s** không cải thiện valid_run so với lần delay 2,5s (84,62% vs 88,46%) — **3 case skills_gap** tái phát infra 413; lỗi do **kích thước payload**, không phải rate limit.
2. **Faithfulness 75,68%** và **skill completeness 73,18%** — ổn định quanh mức ~75% trên tập 52 case.
3. **Course rec** vẫn mạnh nhất: faithfulness **95,83%**, không hallucination; completeness **90%** (một case valid chưa đủ gold).
4. **Competency relation** completeness **62,67%** trên 15 valid — cải thiện so với baseline 14 case (34%); faithfulness **60%** còn thấp.
5. Cohort **v22_new14** đạt **92,86% valid** và faithfulness **78,46%** — gần KPI 78%; cohort **v21_legacy** trong cùng lần chạy chỉ **81,58% valid** do 3 infra skills_gap.

### Cấu hình & kiểm tra lại

- Biến môi trường mới: `RETRIEVAL_RRF_K`, `RETRIEVAL_RRF_POOL_SIZE`, `RETRIEVAL_MAX_EDGE_IN_TOP_K`, `COMPETENCY_RELATION_INTENT_ENABLED=1`
- Playbook tái lập: [`docs/HUONG_DAN_KIEM_TRA_LAI.md`](docs/HUONG_DAN_KIEM_TRA_LAI.md)
- Script: `.\scripts\run_full_verification.ps1`

### E2E D-03 v2.1 (38 case, 22/06/2026)

Thí nghiệm chạy pipeline đầy đủ `ChatService` trên **38 case** trong `answer_quality_gold.jsonl` (8/intent + 3 hybrid + 3 multi-turn), chấm LLM-as-Judge (Groq `llama-3.1-8b-instant`). Delay judge: 2,5 giây. `ACCEPTABLE_ROUTES` strict cho `competency_relation`.

#### Bảng X.3b — Tỉ lệ vận hành pipeline E2E (N = 38)

| Chỉ số | Giá trị | KPI v2.1 |
|--------|---------|----------|
| `valid_run` | **28 (73,68%)** | ≥ 90% |
| `route_mismatch_rate` | **18,42%** (7 case) | 0% |
| `infra_error_rate` | **7,89%** (3 case — judge 413 TPM) | < 5% |

**Route mismatch (7):** `cr_react_01`, `cr_fastapi_02` (course_rec → competency_relation); `sg_bc_01` (skills_gap → competency_relation); `rel_spring_02` (competency_relation → subject_career); `mt_rel_*` ×3 (multi-turn lượt 2 → course_rec).

**Infra error (3):** `sg_be_02`, `sg_ds_02`, `sg_cloud_02` — judge Groq lỗi **413** (context/request quá lớn).

#### Bảng X.4b — Chất lượng trên lượt `valid_run` (N = 28)

| Phạm vi | N | Faithfulness | Skill completeness | No-hallucination |
|---------|---|--------------|-------------------|------------------|
| **Toàn bộ** | 28 | **76,79%** | **73,93%** | 67,86% |
| `pathfinding` | 8 | 80,00% | 71,25% | 62,50% |
| `course_rec` | 6 | **100,00%** | **100,00%** | **100%** |
| `skills_gap` | 4 | 80,00% | 67,50% | 0,00% |
| `competency_relation` | 10 | 59,00% | **63,00%** | 80,00% |

#### Bảng X.4c — Nhóm đặc biệt v2.1

| Nhóm | N | Valid | Faithfulness | Completeness | Ghi chú |
|------|---|-------|--------------|--------------|---------|
| Hybrid career+relation | 3 | 3 | 50,00% | 50,00% | Route đúng; judge thấp do câu so sánh đa lựa chọn |
| Multi-turn (2 lượt) | 3 | **0** | — | — | Cả 3 lượt 2 bị route `course_rec` |

#### So sánh E2E baseline (14) → v2.1 (28 valid)

| Chỉ số | Baseline N=14 | v2.1 valid N=28 | Δ |
|--------|---------------|-----------------|---|
| Faithfulness | 80,00% | 76,79% | −3,2 điểm % |
| Skill completeness | 66,43% | **73,93%** | **+7,5 điểm %** |
| `competency_relation` completeness | 34,00% (N=5) | **63,00%** (N=10) | **+29 điểm %** |
| Route mismatch | 0%* | 18,42% | Tăng — strict routes + router quá nhạy |
| Infra error | 0% | 7,89% (judge 413) | 3 case skills_gap |

\*Baseline 0% theo metric `route_mismatch`; một số case relation vẫn bị route semantic sai nhưng không bị loại (xem Bảng X.5).

**Nhận xét E2E v2.1:**

1. **Intent `competency_relation` cải thiện rõ** khi route đúng: completeness **63%** (vượt KPI 55%); nhiều case `rel_*` đạt 0,8–1,0 faithfulness.
2. **Tradeoff router v2.1:** scoring relation hút nhầm câu `course_rec` có tên framework (React, FastAPI) và **follow-up multi-turn** chưa giữ context relation (3/3 mismatch).
3. **Faithfulness tổng 76,79%** — dưới ngưỡng 78%; infra judge 413 trên 3 case `skills_gap` và hybrid faithfulness thấp (50%).
4. **`course_rec` vẫn mạnh nhất** trên case route đúng: 96,67% / 100%.
5. Cần tinh chỉnh router (ưu tiên tín hiệu “khóa học/course” trước relation) trước khi kỳ vọng `route_mismatch` → 0%.

Kết quả CSV: `data/eval/answer_quality_results.csv` · Log: `logs/eval_e2e_v21_2026-06-22.txt`

---

## X.3. Kết quả đánh giá chất lượng câu trả lời E2E (D-03) — baseline trước v2.1

Thí nghiệm chạy pipeline đầy đủ `ChatService` trên 14 case trong `answer_quality_gold.jsonl`, chấm bằng LLM-as-a-Judge (Groq). Delay giữa các lần gọi judge: 2,5 giây.

### Bảng X.3 — Tỉ lệ vận hành pipeline E2E (N = 14)

| Chỉ số | Giá trị |
|--------|---------|
| `valid_run` | 14 (100%) |
| `route_mismatch_rate` | 0% |
| `infra_error_rate` | 0% |

Trong lần chạy đầy đủ này, không ghi nhận lỗi định tuyến hay lỗi hạ tầng router/judge đủ điều kiện loại khỏi aggregate.

### Bảng X.4 — Chất lượng câu trả lời trên lượt `valid_run` (N = 14)

| Phạm vi | N | Faithfulness | Skill completeness | No-hallucination | Valid citations |
|---------|---|--------------|------------------|------------------|-----------------|
| **Toàn bộ** | 14 | **80,00%** | **66,43%** | 85,71% | 100% |
| `pathfinding` | 3 | 80,00% | 76,67% | 66,67% | 100% |
| `course_rec` | 3 | 93,33% | **100,00%** | **100%** | 100% |
| `skills_gap` | 3 | 80,00% | 76,67% | 100% | 100% |
| `competency_relation` | 5 | 72,00% | **34,00%** | 80,00% | 100% |

### Bảng X.5 — Chi tiết từng case E2E (trích)

| Case | Intent kỳ vọng | Route thực tế | Faithfulness | Skill completeness |
|------|----------------|---------------|--------------|-------------------|
| pf_ds_01 | pathfinding | pathfinding | 0,80 | 0,90 |
| cr_py_01 | course_rec | course_rec | 1,00 | 1,00 |
| cr_react_01 | course_rec | course_rec | 1,00 | 1,00 |
| sg_mle_01 | skills_gap | pathfinding* | 0,80 | 0,70 |
| rel_aws_cert_e2e_01 | competency_relation | course_rec | 0,80 | 0,00 |
| rel_cka_e2e_01 | competency_relation | course_rec | 1,00 | 0,00 |
| rel_empty_ansible_e2e_01 | competency_relation | pathfinding | 0,00 | 0,00 |

\*Route `pathfinding` được chấp nhận cho intent `skills_gap` theo `ACCEPTABLE_ROUTES`.

### Nhận xét (E2E)

1. Hệ thống **trung thực với dữ liệu đồ thị ở mức 80%** (faithfulness) trên tập E2E đa intent.
2. **Skill completeness (66,43%) thấp hơn faithfulness**, cho thấy câu trả lời thường bám đúng nguồn nhưng **chưa liệt kê đủ** các kỹ năng/khóa học trong gold — đặc biệt với intent quan hệ competency.
3. **`course_rec` là điểm mạnh nhất:** faithfulness 93,33%, completeness 100%, không hallucination.
4. **`competency_relation` là điểm yếu nhất:** completeness chỉ 34%; nhiều case bị route sang `pathfinding` hoặc `course_rec` thay vì luồng chuyên biệt, dẫn đến câu trả lời không bao phủ quan hệ competency kỳ vọng.
5. Tỉ lệ **no-hallucination 85,71%** — 2/14 case judge phát hiện thông tin không có trong ground truth (ví dụ pf_gd_01, rel_aws_cert_e2e_01).

---

## X.4. So sánh gold derived vs excel-derived (kiểm tra circular evaluation)

Để kiểm tra giả thuyết *circular evaluation* (gold sinh từ cùng GraphRepository đang được chấm), so sánh sơ bộ 5 case pathfinding trên hai bộ gold.

### Bảng X.6 — So sánh faithfulness E2E (mẫu 5 case pathfinding)

| Bộ gold | `gold_source` | N valid | Faithfulness | Infra error |
|---------|---------------|---------|--------------|-------------|
| `answer_gold.jsonl` | derived_from_graph_repository | 4/5 | 87,50% | 20% (judge TPM 413) |
| `answer_gold_independent.jsonl` | excel_derived | 4/5 | 85,00% | 20% (judge TPM 413) |

**Chênh lệch faithfulness: 2,5 điểm phần trăm** trên mẫu nhỏ. Cả hai bộ đều chạy cùng pipeline ChatService + Neo4j tại thời điểm đánh giá; khác biệt nằm ở **cách sinh nhãn gold**, không phải ở hành vi runtime.

### Nhận xét (Provenance)

1. Không có bằng chứng mạnh rằng hệ thống “ăn điểm” nhờ gold trùng GraphRepository trên mẫu thử nghiệm; chênh lệch nhỏ và có thể nằm trong sai số mẫu.
2. Bộ `excel_derived` (45 case) cần được dùng song song với bộ derived trong các thí nghiệm ablation để báo cáo minh bạch.
3. Lỗi judge 413 (context quá lớn) chiếm 20% trên mẫu 5 case — đã được phân loại `infra_error` và loại khỏi aggregate sau chuẩn hóa phương pháp luận.

---

## X.5. Kết luận thực nghiệm

### X.5.1. Đối với mục tiêu Graph-RAG

| Thành phần | Kết luận |
|------------|----------|
| Hybrid retrieval | Đạt ~60% HitRate/RecallFull trên 248 query; khả dụng cho gợi ý career/course, yếu hơn ở competency |
| Knowledge graph grounding | Faithfulness E2E 80% — câu trả lời chủ yếu bám đồ thị, hallucination thấp (85,71% case sạch) |
| Intent routing | 0% route mismatch trên tập D-03; định tuyến ổn định với taxonomy mở rộng |
| Course recommendation | Hoàn thiện nhất trên gold (completeness 100%) |
| Competency relation | v2.1: completeness **63%** trên valid (N=10); route mismatch 18% tổng thể — cần tinh chỉnh router course vs relation |

### X.5.2. Đối với phương pháp đo lường

1. **Bắt buộc tách** `valid_run` / `infra_error` / `route_mismatch` trước khi báo cáo faithfulness — tránh nhầm lỗi vận hành với chất lượng.
2. **Bắt buộc báo cáo RecallFull** bên cạnh HitRate, đặc biệt với multi-relevant query.
3. **Bắt buộc báo cáo breakdown trivial/paraphrased** — hơn một nửa query retrieval là trivial.
4. Gold ablation nên dùng **hai nguồn** (`derived` + `excel_derived`) và ghi rõ provenance trong luận văn.

### X.5.3. Hạn chế

- Tập E2E judge **52 case** ([v2.2-D2-rerun], delay 6s): **44 valid_run** (84,62%), route_mismatch 9,62%, infra_error 5,77% (3× skills_gap 413); faithfulness valid **75,68%**.
- Judge Groq free tier giới hạn TPM → một số case context lớn bị `infra_error`.
- Bộ `excel_derived` chưa qua review chuyên gia thủ công (annotator).
- Thí nghiệm ablation đa chế độ fusion (D-01) không trình bày chi tiết trong mục này; xem chương/thí nghiệm ablation riêng.

---

## Phụ lục — Lệnh tái lập kết quả

```bash
# Retrieval (248 queries)
python scripts/eval_retrieval.py --k 5 --output-csv data/eval/retrieval_results.csv

# E2E answer quality full 52 (v2.2-D2)
python scripts/eval_answer_quality.py --gold data/eval/answer_quality_gold.jsonl --report-json results/eval_summary.json --run-label v2.2-D2 --delay 2.5

# Build / validate gold E2E
python scripts/build_answer_quality_gold.py
python scripts/validate_gold.py data/eval/answer_quality_gold.jsonl --probe-neo4j

# Re-index corpus (sau thay đổi edge docs)
python scripts/build_index_corpus.py --out data/index_corpus.jsonl
# (tiếp theo: upsert Qdrant + BM25 theo pipeline ingest)

# Kiểm thử hồi quy
pytest -q

# Playbook đầy đủ (Windows)
.\scripts\run_full_verification.ps1
```

*Số liệu baseline ghi nhận ngày 18/06/2026; retrieval sau tối ưu: `data/eval/retrieval_results.csv` (verification 22/06/2026). Chi tiết: `audit_baseline_2026-06-18.md`, `docs/HUONG_DAN_KIEM_TRA_LAI.md`.*
