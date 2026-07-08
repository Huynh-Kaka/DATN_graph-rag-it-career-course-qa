# Hướng dẫn thí nghiệm D-01 / D-02 / D-03

Tài liệu này giải thích **ba bài kiểm tra chính** của đề tài Graph-RAG tư vấn hướng nghiệp IT: mỗi bài đo gì, vì sao cần đo, và kết luận được rút ra.

> **Nguyên tắc thiết kế:** Không dùng thư viện RAGAS nguyên bản; dùng **bộ metric tùy biến** (D-01/D-02/D-03) phù hợp ontology Career–Competency–Course và kiến trúc tight fusion.

---

## 1. Tổng quan: ba trục đánh giá

| Mã | Tên | Tầng đo | Tập gold | Script chính |
|----|-----|---------|----------|--------------|
| **D-01** | Ablation chất lượng Graph-RAG | Context fusion + grounding (có/không LLM sinh) | 80 case (`answer_gold_v2.jsonl`) | `scripts/run_quality_ablation.py` |
| **D-02** | Đánh giá retrieval | Truy hồi hybrid Qdrant + BM25 + RRF | **248** query (`retrieval_gold.jsonl`) | `scripts/eval_retrieval.py` |
| **D-03** | Đánh giá E2E LLM-as-a-Judge | Pipeline đầy đủ (router → Graph-RAG → generator) | **52** case (`answer_quality_gold.jsonl`) | `scripts/eval_answer_quality.py` |

**Vì sao tách ba trục?**

- **D-02** đo tầng truy hồi **độc lập** với LLM — tránh nhầm lỗi retrieval với lỗi sinh câu trả lời.
- **D-01** đối chứng **vector-only vs graph-only vs late vs tight fusion** trên cùng gold — trả lời câu hỏi nghiên cứu “Graph-RAG có hơn RAG vector thuần không?”.
- **D-03** đo **end-to-end** như người dùng thật — bổ sung D-01 bằng cách có intent router, session, multi-turn.

Ba trục **bổ sung cho nhau**, không thay thế lẫn nhau.

---

## 2. D-01 — Ablation chất lượng Graph-RAG

### 2.1. Mục đích

So sánh **bốn cấu hình fusion** trên cùng tập câu hỏi và nhãn gold:

| Cấu hình | Mô tả ngắn |
|----------|------------|
| **vector_only** | Chỉ Qdrant (RAG vector thuần) |
| **graph_only** | Chỉ Neo4j (Cypher, không vector seed) |
| **late_fusion** | Graph + vector song song, gộp muộn |
| **tight_fusion** | Vector trước → ánh xạ hit thành seed node → Cypher có boost → fusion context (**cấu hình đề tài**) |

Pipeline ablation **không đi qua intent router** — cô lập ảnh hưởng của chiến lược fusion.

Hai chế độ chấm:

- **static** (mặc định): formatter tĩnh — nhanh, ổn định, ít phụ thuộc LLM generator.
- **generative**: LLM sinh câu trả lời + cosine similarity so với gold tham chiếu.

### 2.2. Profile **v4** (mặc định) — ba lớp metric, so sánh công bằng 4 nhánh

> **Vì sao v4:** Profile v3 gộp một bảng khiến `vector_only` luôn **Graph Grounding 0% / Off-graph 100%** (định nghĩa, không phải lỗi) và `course_rec` lệch đơn vị tên vs mã. **v4** tách lớp metric; metric không áp dụng → **N/A**, không điền 0/100.

| Lớp | Câu hỏi | Metric | Áp dụng mode |
|-----|---------|--------|--------------|
| **L1 — Retrieval** | P truy xuất khớp gold ontology? | `retrieval_entity_f1`, `retrieval_entity_recall`, `retrieval_hit` | **Cả 4** nhánh |
| **L2 — Vector baseline** | (nhúng trong L1) | Hit/recall trên `vector_only` | vector_only |
| **L3 — Fusion reply** | Reply có đủ entity + ít nhiễu vector? | `answer_entity_f1`, `fusion_off_graph_rate`, `graph_entity_grounding` | graph_only, late, tight |

**Gold:**
- L1: pathfinding → `gold_skills`; course_rec → `gold_course_codes`.
- L3 course_rec: mã + **tên khóa** từ graph snapshot (cùng đơn vị reply).

**Báo cáo luận văn:** dùng **hai bảng** trong JSON `summary_v4_layers` / `latex_table_v4_layers` — không gộp L1 và L3 một hàng.

```powershell
python scripts/run_quality_ablation.py --metrics-profile v4 --gold data/eval/answer_gold_v2.jsonl --json-out results/ablation_d01_v4.json
```

### 2.3. Các chỉ số profile **v3** (legacy — một bảng)

> **Lưu ý phản biện:** D-01 **không** dùng tên Faithfulness/Hallucination như D-03 (LLM judge). Ablation static dùng formatter tĩnh; chỉ số đo **entity grounding** và **độ đúng gold**, không đo ảo giác LLM.

| Chỉ số | Ý nghĩa | Vai trò báo cáo |
|--------|---------|-----------------|
| **Answer Entity F1** (F1 thực thể trong câu trả lời) | F1 giữa tập thực thể **được nhắc trong reply** (M) và gold (G) | **Chỉ số chính** — phân biệt rõ 4 cấu hình fusion |
| **Ontology F1** (F1 đúng/đủ ontology) | F1 giữa tập thực thể **dự đoán** từ graph/retrieval (P) và gold (G) | Đo hệ thống *tìm đúng* kỹ năng/khóa, không phụ thuộc cách formatter in câu |
| **Graph Entity Grounding** | % mention trong reply có trong Neo4j | Đo bám ground-truth đồ thị |
| **Off-Graph Mention Rate** | % mention **không** có trong graph | Đo nhiễu từ vector (không phải hallucination LLM) |
| **Vector-Only Mention Rate** | % mention chỉ từ snippet vector | Phân tích đóng góp vector |
| **Context Entity Grounding** *(phụ)* | % mention bám graph∪vector | Thường ~100% ở static — **không dùng kết luận chính** |

#### 2.2.1. F1 là gì? Hai chỉ số F1 trong D-01 khác nhau thế nào?

**F1** (F-measure) là điểm cân bằng giữa **độ chính xác** (precision) và **độ bao phủ** (recall) khi so hai tập thực thể (tên kỹ năng, mã khóa, …):

\[
\text{Precision} = \frac{|X \cap Y|}{|X|}, \quad
\text{Recall} = \frac{|X \cap Y|}{|Y|}, \quad
F_1(X,Y) = \frac{2 \cdot \text{Precision} \cdot \text{Recall}}{\text{Precision} + \text{Recall}}
\]

Trong đó \(X\) và \(Y\) là hai tập đã chuẩn hóa (bỏ dấu, lowercase, alias) — hàm `skill_f1()` trong [`app/eval/quality_metrics.py`](app/eval/quality_metrics.py).

**Hai chỉ số F1 dùng hai cặp tập khác nhau:**

| Tên trong báo cáo | Ký hiệu | Tập X (dự đoán) | Tập Y (chuẩn) | Câu hỏi trả lời |
|-------------------|---------|-----------------|---------------|-----------------|
| **Ontology F1** | \(F_1(P, G)\) | **P** = `predicted_entities` — thực thể hệ thống *truy xuất* từ Neo4j hoặc vector (danh sách kỹ năng thiếu, mã khóa TEACH_*, …) | **G** = `gold_entities` — nhãn trong file gold | Hệ thống *tìm đúng và đủ* thực thể ontology chưa? |
| **Answer Entity F1** | \(F_1(M, G)\) | **M** = `mentions` — thực thể *xuất hiện trong câu trả lời* (reply), trích bằng khớp với vocab ngữ cảnh + `[Course: CODE]` | **G** = `gold_entities` | Câu trả lời *hiển thị* đúng/đủ so với gold chưa? |

**Gold (G) theo intent** (trong `answer_gold*.jsonl`):

- **pathfinding:** tập kỹ năng/competency kỳ vọng cho nghề (vd. Python, React, SQL).
- **course_rec:** tập **mã khóa** kỳ vọng (vd. `CS101`, `WEB201`) — không phải tên đầy đủ của khóa.

**Predicted (P) lấy từ đâu:**

- **graph_only / tight / late (phần graph):** output Cypher — `skills_missing`, `courses[].course_code`, …
- **vector_only:** entity trích từ top-k snippet Qdrant/BM25.

**Mentions (M) lấy từ đâu:**

- Quét text `reply` (formatter tĩnh hoặc LLM), chỉ chấp nhận token khớp vocab = graph ∪ vector ∪ predicted ∪ gold — tránh đếm từ ngẫu nhiên.

**Ví dụ số (pathfinding):**

- Gold G = {Python, React, SQL} (3 phần tử).
- Graph trả P = {Python, React} → Ontology F1 ≈ 80% (thiếu SQL).
- Reply in “Bạn cần Python, React và Docker” → M = {Python, React, Docker} → Answer Entity F1 thấp hơn vì Docker không có trong gold và thiếu SQL.

**Vì sao cần hai F1:**

- **Ontology F1** trùng nhau ở graph_only / late / tight vì **cùng một lần gọi** `pathfinding()` — chỉ khác phần vector gộp vào reply.
- **Answer Entity F1** mới cho thấy late fusion *thêm tên thừa* từ vector (off-graph) dù ontology vẫn đúng.

**Lưu ý course_rec:** Ontology F1 có thể **100%** (graph liệt kê đúng mã khóa) trong khi Answer Entity F1 **0%** — formatter in *tên khóa*, gold so *mã khóa*; không có nghĩa graph trả sai.

**Không nhầm với D-03:** Faithfulness / Skill completeness ở D-03 do **LLM Judge** chấm toàn câu trả lời; hai F1 trên chỉ là **đếm/thống kê tập thực thể** ở D-01 static.

#### Phiên bản V1/V2 (legacy — không khuyến nghị báo cáo)

| Chỉ số cũ | Thay bằng (v3) |
|-----------|----------------|
| Faithfulness | `context_entity_grounding` (chỉ số phụ) |
| Hallucination rate | `off_graph_mention_rate` |
| Skill accuracy | `ontology_f1` |

### 2.3. Tập gold và provenance

| File | N mẫu | Nguồn | Vai trò |
|------|-------|-------|---------|
| `answer_gold.jsonl` | 25 | `derived_from_graph_repository` | Regression nhanh, kiểm tra hồi quy code |
| `answer_gold_independent.jsonl` | 45 | `excel_derived` | Gold sinh từ Excel **không gọi GraphRepository** — giảm circular evaluation |

### 2.4. Kết quả tiêu biểu (mode static, **v4** — ba lớp metric)

Trên tập 80 case (`answer_gold_v2.jsonl`), tham chiếu `results/ablation_d01_v4.json` (chạy lại 06/2026):

**Lớp 1 — Retrieval (4 mode):**

| Cấu hình | Retrieval F1 | Recall | Hit rate |
|----------|--------------|--------|----------|
| vector_only | 6,88% | 10,00% | 10,00% |
| graph_only | 86,74% | 100% | 100% |
| late_fusion | 86,74% | 100% | 100% |
| tight_fusion | 86,74% | 100% | 100% |

**Lớp 3 — Reply pathfinding (graph_only / late / tight):**

| Cấu hình | Answer Entity F1 | Off-graph | Graph grounding |
|----------|------------------|-----------|-----------------|
| graph_only | 76,13% | 0% | 100% |
| late_fusion | 42,07% | 55,38% | 44,62% |
| tight_fusion | 60,30% | 29,47% | 70,53% |

**Lớp 3 — course_rec:** Retrieval F1 100% (có graph); Answer F1 graph_only **59,25%** (gold mã+tên); tight **17,08%** / off-graph **78,04%** vs late **7,16%** / **91,48%**.

- **vector_only** không báo off-graph/graph grounding (N/A trong JSON).
- **tight_fusion** cải thiện Answer F1 và giảm off-graph so **late_fusion** trên pathfinding.
- Profile v3 (một bảng): `results/ablation_d01_v3_static.json` — legacy.

### 2.5. Ý nghĩa cho đề tài

D-01 **chứng minh có cơ sở khoa học** khi chọn tight fusion thay vì RAG vector thuần: graph làm ground-truth, vector bổ sung bằng chứng; ablation có kiểm định thống kê (t-test, bootstrap CI) trên một số metric.

**Cập nhật pipeline D-01 (v3.1):**

- **A-03 post-graph rerank:** `tight_fusion` gọi `extract_relevant_ids_from_graph` → `retrieve_docs(relevant_ids=...)` giống [`chat_service.py`](../app/services/chat_service.py), không chỉ seed trước Cypher.
- **Course rec — Answer Entity F1:** reply ablation được nối `[Course: CODE]` từ graph (chỉ trong eval), để \(F_1(M,G)\) so cùng đơn vị với `gold_course_codes`; Ontology F1 vẫn dùng mã từ `predicted_entities`.

### 2.6. Lệnh chạy

```powershell
python scripts/validate_gold.py data/eval/answer_gold.jsonl
python scripts/run_quality_ablation.py --eval-mode static --metrics-profile v3
python scripts/run_quality_ablation.py --gold data/eval/answer_gold_independent.jsonl --metrics-profile v3 --json-out results/ablation_d01_v3_independent.json
```

---

## 3. D-02 — Đánh giá retrieval

### 3.1. Mục đích

Đo **tầng truy hồi** (Qdrant + BM25 + RRF, có graph-aware rerank) **không qua LLM generator**.

Mỗi query trong `retrieval_gold.jsonl` có một hoặc nhiều tài liệu đúng (career / course / competency). Hệ thống trả top-k; so khớp với nhãn gold.

**Thiết lập chuẩn:** k = 5, N = 248, `RETRIEVAL_STRICT=1` khi đánh giá.

### 3.2. Các chỉ số chính

| Chỉ số | Công thức / ý nghĩa | Dùng khi nào |
|--------|---------------------|--------------|
| **HitRate@k** | Query có **≥1** tài liệu đúng trong top-k → 1, ngược lại 0; trung bình macro | Đo “có tìm được gì đúng không” |
| **RecallFull@k** | \|relevant ∩ top-k\| / \|relevant\| | Query **nhiều nhãn đúng** — đo mức phủ đủ |
| **MAP@k** | Mean Average Precision | Xếp hạng chất lượng (relevant càng cao càng tốt) |
| **MRR** | 1 / vị trí hit đầu tiên | Đo tốc độ “gặp đúng” |
| **nDCG@k** | Normalized DCG | Thưởng relevant ở hạng cao |

**Lưu ý quan trọng:** HitRate@k **không bằng** RecallFull@k khi một query có nhiều tài liệu liên quan (đặc biệt nhóm **competency**).

### 3.3. Phân tích bổ sung

- **Trivial vs paraphrased:** ~51,6% query trivial (chứa sẵn entity gold) vs ~48,4% paraphrased — metric phản ánh cả khớp lexical lẫn ngữ nghĩa.
- **Theo doc_type:** career (N≈152), course (N≈79), competency (N≈17).

### 3.4. Kết quả tiêu biểu

| Mốc | HitRate@5 | RecallFull@5 | MAP@5 |
|-----|-----------|--------------|-------|
| Baseline (18/06/2026) | 60,48% | 59,68% | 0,3716 |
| Sau tối ưu v2.1 (22/06/2026) | **65,32%** | **64,72%** | 0,4157 |

Nhóm **career** ổn định; **competency** cải thiện mạnh sau v2.1 nhưng mẫu nhỏ (17); **course** có thể dao động theo cấu hình RRF/rerank.

### 3.5. Ý nghĩa cho đề tài

D-02 chứng minh **tầng retrieval khả dụng** làm đầu vào Graph-RAG (~65% trên 248 query). Không đạt 90%+ vì corpus IT đa dạng, query paraphrased và multi-relevant — đây là **hạn chế thực tế**, không phải lỗi đo.

### 3.6. Lệnh chạy

```powershell
python scripts/eval_retrieval.py --k 5 --output-csv data/eval/retrieval_results.csv
python scripts/analyze_gold_triviality.py
```

**KPI tham chiếu (v2.1):** HitRate@5 overall ≥ 58%; RecallFull@5 competency ≥ 45%.

---

## 4. D-03 — Đánh giá E2E (LLM-as-a-Judge)

### 4.1. Mục đích

Chạy **pipeline đầy đủ** qua `ChatService`: intent router → orchestrator → Graph-RAG → generator/formatter → câu trả lời người dùng nhận được.

Một LLM **trọng tài riêng** (Judge — Groq Llama 3.1 8B hoặc fallback Local/Gemini) chấm câu trả lời so với ground truth và graph context.

**Khác D-01:** có router, session, multi-turn, lỗi infra thật.

### 4.2. Quy tắc vận hành (route validity)

Mỗi lượt E2E được gắn nhãn:

| Nhãn | Ý nghĩa | Đưa vào aggregate? |
|------|---------|-------------------|
| **valid_run** | Route chấp nhận được, không lỗi infra | **Có** |
| **route_mismatch** | Intent thực tế không thuộc `ACCEPTABLE_ROUTES` | **Không** |
| **infra_error** | LLM/router/judge lỗi (503, 413 payload quá lớn, …) | **Không** |

**ACCEPTABLE_ROUTES:** Không so khớp intent cứng 1-1 (ví dụ `skills_gap` chấp nhận `pathfinding` khi đã có profile).

### 4.3. Các chỉ số chính

| Chỉ số | Ý nghĩa | Thang đo |
|--------|---------|----------|
| **Faithfulness** | Câu trả lời bám graph/context, không bịa nghề/kỹ năng/khóa học | 0,0 – 1,0 |
| **Skill completeness** | Bao phủ các kỹ năng/lộ trình kỳ vọng trong gold | 0,0 – 1,0 |
| **No-hallucination rate** | Tỷ lệ case judge đánh giá không có bịa đặt rõ ràng | % |
| **Valid citation rate** | Trích dẫn `[Course: CODE]` hợp lệ trong graph | % |
| **valid_run rate** | Tỷ lệ lượt chạy thành công (không route/infra lỗi) | % |
| **route_mismatch_rate** | Tỷ lệ định tuyến sai | % |
| **infra_error_rate** | Tỷ lệ lỗi hạ tầng | % |

### 4.4. Tập gold

| Cohort | N | Mô tả |
|--------|---|-------|
| `v21_legacy` | 38 | 8 case/intent + hybrid + multi-turn |
| `v22_new14` | 14 | Bổ sung competency_relation, multi-turn |
| **full52** | **52** | Báo cáo chính thức |

### 4.5. Kết quả tiêu biểu ([v2.2-D2-rerun], delay judge 6s)

| Chỉ số | Giá trị |
|--------|---------|
| valid_run | **44/52 (84,62%)** |
| route_mismatch | 5 (9,62%) |
| infra_error | 3 (5,77%) — skills_gap, judge 413 |
| Faithfulness (valid) | **75,68%** |
| Skill completeness (valid) | **73,18%** |
| No-hallucination (valid) | 75,00% |
| Valid citations | **100%** |

**Theo intent (valid_run):**

| Intent | Faithfulness | Skill completeness |
|--------|--------------|-------------------|
| course_rec | **95,83%** | **90,00%**
| pathfinding | 75,00% | 74,00% |
| skills_gap | 75,71% | 65,71% |
| competency_relation | 60,00% | 62,67% |

### 4.6. Ý nghĩa cho đề tài

D-03 chứng minh hệ thống **vận hành end-to-end được** với faithfulness ~76% trên tập 52 case. **Course recommendation** gần hoàn hảo; **competency_relation** và **multi-turn** còn yếu — đúng hướng cải thiện đã nêu ở Chương 4.

D-03 **không dùng để suy luận thống kê mạnh** (không báo cáo p-value) vì cỡ mẫu nhỏ và chi phí judge — bổ sung định tính/định lượng cho D-01/D-02.

### 4.7. Lệnh chạy

```powershell
python scripts/smoke_judge.py
python scripts/eval_answer_quality.py `
  --gold data/eval/answer_quality_gold.jsonl `
  --report-json results/eval_summary.json `
  --run-label v2.2-D2 `
  --delay 6
```

Playbook đầy đủ: `docs/HUONG_DAN_KIEM_TRA_LAI.md`.

---

## 5. Bảng tóm tắt: metric → câu hỏi nghiên cứu

| Metric | Trả lời câu hỏi |
|--------|-----------------|
| HitRate@5 / RecallFull@5 | Retriever có tìm đúng tài liệu không? |
| MAP@5 / nDCG@5 | Thứ hạng retrieval có tốt không? |
| Answer Entity F1 / Ontology F1 (D-01) | Câu trả lời có đúng/đủ thực thể gold không? |
| Off-Graph Mention Rate (D-01) | Reply có mention lệch khỏi Neo4j không? (nhiễu vector) |
| Faithfulness (D-03 only) | Câu trả lời E2E có bám graph/context không? (LLM judge) |
| Exclusive Graph Rate (D-01) | Graph có đóng góp thông tin vector không có không? |
| valid_run / route_mismatch | Pipeline vận hành ổn định không? |
| Ontology F1 (D-01) | Có bám ontology 7 nhóm competency không? |

---

## 6. Kết luận tổng hợp cho đề tài

1. **Graph-RAG tight fusion có lợi thế so vector-only** (D-01): giảm hallucination, tăng Ontology F1 và skill accuracy nhờ Neo4j ground-truth.
2. **Retrieval hybrid khả dụng** (D-02): ~65% HitRate/RecallFull trên 248 query; đủ làm nền cho gợi ý career; competency và course cần cải thiện thêm.
3. **Hệ thống E2E hoạt động** (D-03): faithfulness ~76%, course_rec ~96%; citation khóa học 100% hợp lệ.
4. **Điểm yếu còn lại:** competency_relation (faithfulness ~60%), multi-turn follow-up (route_mismatch), skills_gap bị infra judge 413, cỡ mẫu E2E nhỏ (52 case).
5. **Phương pháp luận đã chuẩn hóa:** tách valid/infra/route; báo RecallFull song song HitRate; provenance gold minh bạch; 301+ pytest pass.

---

## 7. Tài liệu liên quan

| File | Nội dung |
|------|----------|
| `ket_qua_thuc_nghiem.md` | Số liệu và bảng chi tiết |
| `audit_report_final.md` | Chuẩn hóa phương pháp luận |
| `docs/HUONG_DAN_KIEM_TRA_LAI.md` | Tái lập v2.2 |
| `chuong_4_ket_luan.md` | Kết luận và hạn chế |
| `results/eval_summary.json` | Snapshot D-03 mới nhất |

---

*Cập nhật: 06/2026 — đối chiếu repository `Doantotnghiep`, báo cáo chính thức D-03: v2.2-D2-rerun.*
