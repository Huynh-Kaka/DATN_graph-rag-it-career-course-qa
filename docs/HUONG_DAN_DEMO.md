# Kịch bản demo — Tương tác trên web

Tài liệu dùng khi **trình diễn trực tiếp** hệ thống tư vấn nghề nghiệp IT trên giao diện web (không phải script đánh giá tự động).

### Mục lục nhanh

| Muốn demo | Nhảy tới |
|-----------|----------|
| **Thu thập kỹ năng 7 bước** (`Bước 1/7` … `7/7`) | **§1.5** bên dưới |
| Hỏi liên tục “thế còn …?” | §1.1 |
| Relation → gợi ý khóa học | §1.2 |
| Form → hỏi tiếp nhiều lượt | §1.6 |
| Câu đơn lẻ từng intent | §3 |
| Điền form 4 bước | §4 |

---

## 0. Chuẩn bị trước khi demo (~2 phút)

```powershell
cd DATN_graph-rag-it-career-course-qa   # hoặc đường dẫn thư mục sau khi clone
uvicorn app.main:app --reload
```

Mở trình duyệt:

| Trang | URL |
|-------|-----|
| Landing | http://127.0.0.1:8000/ |
| Chat | http://127.0.0.1:8000/chat.html |
| Form tư vấn | http://127.0.0.1:8000/form.html |
| Health check | http://127.0.0.1:8000/api/health |

**Kiểm tra nhanh:** `checks.neo4j`, `checks.qdrant` = `"ok"`; `.env` có `GEMINI_API_KEY` (hoặc `CHATBOT_LOCAL_*` nếu dùng Ollama).

**Gợi ý khi trình bày:** mỗi intent đơn lẻ nên dùng **chat mới** (nút *tạo chat mới*). **Riêng các kịch bản hỏi liên tục** (mục 1) — **không** tạo chat mới giữa các lượt.

---

## 1. Kịch bản hỏi liên tục (multi-turn) — copy theo từng lượt

> **Quan trọng:** Các bảng dưới đây gửi **tuần tự trong cùng một phiên chat**. Đợi bot trả lời xong rồi mới gửi lượt tiếp theo.

### 1.1 Relation → relation (hỏi “thế còn …?”)

**Kịch bản A — React rồi Vue**

| Lượt | Bạn gõ | Bot kỳ vọng |
|------|--------|-------------|
| 1 | `React cần học gì trước?` | competency_relation → JavaScript / tiên quyết |
| 2 | `Thế còn Vue?` | Giữ relation, đổi sang Vue |

**Kịch bản B — Django rồi FastAPI**

| Lượt | Bạn gõ | Bot kỳ vọng |
|------|--------|-------------|
| 1 | `Muốn học Django thì cần biết ngôn ngữ nào?` | Django → Python |
| 2 | `Thế còn FastAPI?` | FastAPI → Python |

**Kịch bản C — AWS rồi Azure**

| Lượt | Bạn gõ | Bot kỳ vọng |
|------|--------|-------------|
| 1 | `Chứng chỉ nào validate AWS platform?` | Chứng chỉ / năng lực AWS |
| 2 | `Thế còn Azure?` | Chuyển sang Azure (AZ-900, …) |

**Kịch bản D — Angular rồi Vue**

| Lượt | Bạn gõ | Bot kỳ vọng |
|------|--------|-------------|
| 1 | `Angular cần học gì trước?` | TypeScript / tiên quyết |
| 2 | `Thế còn Vue?` | Vue → JavaScript |

---

### 1.2 Relation → course (pivot sang khóa học)

| Lượt | Bạn gõ | Bot kỳ vọng |
|------|--------|-------------|
| 1 | `Vue.js prerequisite là gì?` | competency_relation |
| 2 | `Thế còn React?` | competency_relation (so sánh tiếp) |
| 3 | `Oke cho mình khóa Vue` | **course_rec** → course card Vue |

*Điểm demo:* lượt 3 có từ “khóa” → hệ thống pivot từ hỏi quan hệ sang gợi ý khóa cụ thể.

---

### 1.3 Pathfinding → course (hỏi lộ trình rồi hỏi khóa)

**Một phiên chat mới:**

| Lượt | Bạn gõ | Bot kỳ vọng |
|------|--------|-------------|
| 1 | `Làm Backend Developer cần học những gì?` | pathfinding — danh sách kỹ năng |
| 2 | `Khóa Docker nào phù hợp?` | course_rec — course card Docker |
| 3 | `Khóa Python nào cho người mới?` | course_rec — course card Python |

*Lượt 2–3:* hệ thống nhớ `career` từ lượt 1 (session PostgreSQL).

---

### 1.4 Slot fill → pathfinding (bot hỏi lại rồi trả lời)

| Lượt | Bạn gõ | Bot kỳ vọng |
|------|--------|-------------|
| 1 | `Xin chào` | slot_fill — bot hỏi lại nghề / mục tiêu |
| 2 | `Mình muốn làm Backend Developer` | pathfinding hoặc hỏi thêm |
| 3 | `Backend Developer cần học gì?` | pathfinding — lộ trình đầy đủ |

---

### 1.5 ⭐ Thu thập kỹ năng 7 bước (`competency_slot_fill`)

> **Đây là kịch bản bạn đang tìm.** Bot lần lượt hỏi **7 nhóm** kỹ năng; mỗi lượt hiện card **Bước X/7** trên chat.

Luồng bot hỏi **Bước 1/7 … 7/7** theo nhóm:

`Programming Language` → `Framework` → `Platform` → `Tool` → `Knowledge` → `Softskill` → `Certification`

#### Cách vào luồng (phiên chat mới — copy từng dòng)

| Lượt | Bạn gõ (copy) | Bot kỳ vọng |
|------|---------------|-------------|
| 1 | `Mình hướng tới Backend Developer` | Ghi nhận nghề mục tiêu |
| 2 | `Khai báo kỹ năng từng nhóm cho Backend Developer` | Vào `competency_slot_fill`, hiện **Bước 1/7** + card chip |

*Nếu lượt 2 chưa thấy “Bước 1/7”:* thử `Python, SQL, Git` (liệt kê kỹ năng đã biết, có dấu phẩy) sau khi đã gõ lượt 1.

#### Kịch bản đầy đủ — đi hết 7 bước (cùng phiên, không tạo chat mới)

Sau **Bước 1/7**, mỗi lượt bot hỏi một nhóm — bạn trả lời rồi chờ bot sang bước kế:

| Lượt | Bot hỏi (tóm tắt) | Bạn trả lời (gợi ý demo) |
|------|-------------------|---------------------------|
| 1 | *(vào luồng — xem bảng trên)* | `Khai báo kỹ năng từng nhóm…` |
| 2 | **Bước 1/7** — Programming Language | `Python, SQL` *(hoặc bấm chip trên card)* |
| 3 | **Bước 2/7** — Framework | `Django` hoặc `không` *(bỏ qua nhóm)* |
| 4 | **Bước 3/7** — Platform | `Docker` |
| 5 | **Bước 4/7** — Tool | `Git` |
| 6 | **Bước 5/7** — Knowledge | `không` |
| 7 | **Bước 6/7** — Softskill | `không` |
| 8 | **Bước 7/7** — Certification | `không` |
| 9 | *(tổng kết gap)* | Bot hiện **skills thiếu / đã có** |

**Rút gọn khi thiếu thời gian:** sau Bước 1/7, gõ `xem tổng kết` → nhảy thẳng bảng gap (bỏ qua các bước còn lại).

#### Thao tác trên UI trong lúc 7 bước

| Bạn làm | Ý nghĩa |
|---------|---------|
| Gõ `Python, Git` | Ghi nhận kỹ năng nhóm hiện tại → sang bước kế |
| Gõ `không` hoặc bấm **Bỏ qua nhóm này** | Bỏ qua nhóm → sang bước kế |
| Bấm **chip** gợi ý trên card | Chọn nhanh kỹ năng graph gợi ý |
| Gõ `xem tổng kết` | Nhảy thẳng **gap_summary** |

#### Sau khi xong 7 bước / tổng kết (vẫn cùng phiên)

| Lượt | Bạn gõ | Bot kỳ vọng |
|------|--------|-------------|
| +1 | `Gợi ý khóa Python` | course_rec |
| +2 | `Mình nên học theo thứ tự nào?` | roadmap_followup / pathfinding |

**Lưu ý:** Luồng 7 bước là **chat** (`competency_slot_fill`). Form tư vấn (§4) nhảy thẳng tới gap — **không** đi qua 7 bước.

---

### 1.6 Form → chat → hỏi tiếp (chuỗi dài nhất, ~6–8 lượt)

**Bước A — điền form** (xem mục 4), bấm *Gửi & nhận tư vấn* → chuyển sang chat có structured reply.

**Bước B — hỏi tiếp trong cùng phiên (không tạo chat mới):**

| Lượt | Bạn gõ | Bot kỳ vọng |
|------|--------|-------------|
| 1 | *(tin bot từ form — tự hiện)* | skills thiếu + khóa gợi ý |
| 2 | `Mình nên bắt đầu từ đâu?` | roadmap_followup (biết profile form) |
| 3 | `Tôi đã biết Python, còn thiếu gì cho Backend?` | skills_gap |
| 4 | `Gợi ý khóa Docker cho mình` | course_rec |
| 5 | `Mốc 30 ngày đầu nên làm gì?` | follow-up lộ trình |

*Sau lượt 1 có thể bấm **bubble gợi ý** dưới tin bot (nếu hiện) thay vì gõ tay.*

---

### 1.7 Demo nhanh chỉ multi-turn (~3 phút)

Chọn **một** chuỗi:

- **Ngắn:** §1.1 kịch bản A (2 lượt)
- **Vừa:** §1.2 (3 lượt, có pivot course)
- **7 bước:** §1.5 (khai báo kỹ năng từng nhóm)
- **Dài:** §1.6 (form + 3 câu hỏi tiếp)

---

## 2. Luồng demo đầy đủ (~15 phút)

Thứ tự đề xuất để hội đồng thấy đủ hai kênh tương tác (chat + form) và các loại câu trả lời có cấu trúc.

| # | Phần | Thời gian | Điểm cần nhấn |
|---|------|-----------|---------------|
| 1 | Landing → Chat | 1 phút | Giao diện chào, nút *trò chuyện ngay*, dark mode |
| 2 | Pathfinding | 2 phút | Lộ trình kỹ năng theo nghề, card có cấu trúc |
| 3 | Course recommendation | 2 phút | Gợi ý khóa học cụ thể (course card) |
| 4 | Competency relation | 2 phút | Quan hệ tiên quyết giữa công nghệ |
| 5 | Subject → career | 1,5 phút | Liên kết môn học trên trường với nghề IT |
| 6 | Multi-turn | 2 phút | §1.1 hoặc §1.2 |
| 6b | **Thu thập 7 bước** | 3 phút | **§1.5** — card `Bước X/7` |
| 7 | Form tư vấn 4 bước | 4 phút | Hồ sơ → advice JSON → chuyển sang chat |
| 8 | Skills gap / follow-up | 2 phút | Hỏi tiếp sau khi đã có profile |
| 9 | Feedback 👍/👎 | 30 giây | HITL trên tin nhắn bot |

---

## 3. Demo Chat — từng intent (câu đơn lẻ)

Vào **Chat** → bấm **tạo chat mới** trước mỗi mục. *Chuỗi nhiều lượt xem **mục 1**.*

### 3.1 Pathfinding — lộ trình / kỹ năng theo nghề

**Câu hỏi mẫu (chọn 1):**

```
Làm Backend Developer cần học những gì?
```

```
Lộ trình Data Scientist cần học những gì?
```

```
DevOps Engineer roadmap
```

**Kỳ vọng trên UI:**

- Bot trả lời danh sách kỹ năng / lộ trình gắn với nghề mục tiêu.
- Có thể hiện **structured card** (skills, sections).
- Có thanh **👍 / 👎** dưới tin nhắn bot (trừ khi lỗi hệ thống).

**Câu nói gợi ý khi demo:** *"Hệ thống tra cứu graph Neo4j (NEED_*) kết hợp vector retrieval, không chỉ dựa vào kiến thức sẵn của LLM."*

---

### 3.2 Course recommendation

**Câu hỏi mẫu:**

```
Khóa Python nào phù hợp cho người mới?
```

```
Gợi ý khóa học React beginner
```

```
Khóa Kubernetes cho beginner
```

**Kỳ vọng:**

- **Course card** với tên khóa, mô tả ngắn.
- Khóa học lấy từ graph (TEACH_*), Validator loại citation ảo.

---

### 3.3 Competency relation

**Câu hỏi mẫu:**

```
Muốn học Django thì cần biết ngôn ngữ nào?
```

```
React cần học gì trước khi bắt đầu?
```

```
CKA validate technology gì?
```

**Kỳ vọng:**

- Giải thích quan hệ tiên quyết (ví dụ Django → Python).
- Không nhầm sang gợi ý khóa học (trừ khi user hỏi rõ về khóa).

---

### 3.4 Subject → career

**Câu hỏi mẫu:**

```
Học môn OOP thì sau này làm nghề gì?
```

```
Môn cơ sở dữ liệu liên quan nghề nào?
```

**Kỳ vọng:**

- Liệt kê nghề IT liên quan môn học (multi-hop IN_SUBJECT trên graph).

---

### 3.5 Slot fill

**Câu hỏi mẫu:**

```
Xin chào
```

```
Mình muốn học thêm kỹ năng
```

**Kỳ vọng:**

- Bot **hỏi lại** (nghề mục tiêu, kỹ năng cụ thể…) thay vì đoán bừa.

**Tiếp theo trong cùng phiên:** xem **§1.4** (chuỗi slot fill → pathfinding).

---

### 3.6 Gợi ý nhanh trên UI

Khi mở chat mới, có **bubble gợi ý** sẵn (từ `frontend/js/chat.js`):

- *Làm Backend Developer cần học những gì?*
- *So sánh Frontend và Backend Developer*
- *Khóa Python nào phù hợp cho người mới?*

Có thể **bấm trực tiếp** bubble thay vì gõ tay — tiện khi demo nhanh.

---

## 4. Demo Form tư vấn (Gen 2)

Vào **form tư vấn** từ chat (link *form tư vấn*) hoặc `http://127.0.0.1:8000/form.html`.

### Kịch bản mẫu — Fresher muốn làm Backend

| Bước | Chọn / nhập |
|------|-------------|
| **1 — Xuất phát điểm** | 🎓 Sinh viên năm 4 / sắp ra trường |
| **2 — Mục tiêu nghề** | Backend Developer |
| | Mục tiêu cụ thể: `Muốn vào công ty product trong 6 tháng` |
| **3 — Kỹ năng & thời gian** | Python, SQL, Git |
| | Programming Language: `Python` |
| | Thời gian: `10–20 giờ/tuần` |
| **4 — Mong muốn** | ✅ Lộ trình học cụ thể, ✅ Phân tích điểm còn thiếu, ✅ Gợi ý khóa học |
| | Câu hỏi riêng: `Cần học gì để vào công ty product trong 6 tháng?` |

Bấm **Gửi & nhận tư vấn ↗**.

**Kỳ vọng:**

- Chuyển sang **chat** (`chat.html?from=form`).
- Tin nhắn bot đầu tiên chứa **kết quả tư vấn có cấu trúc**: skills thiếu, skills đã có, khóa học gợi ý.
- `profile_id` / `session_id` lưu localStorage — phiên chat gắn với hồ sơ form.

**Câu nói gợi ý:** *"Form dùng Gemini structured output; chat Gen 3 dùng Graph-RAG tight fusion — hai luồng bổ sung nhau."*

---

**Hỏi tiếp sau form:** xem **§1.6** (chuỗi 5 lượt).

---

## 5. Demo sau Form — skills gap & roadmap follow-up

*Đã gộp chi tiết từng lượt vào **§1.6**. Tóm tắt:*

```
Tôi đã biết Python, muốn làm Backend Developer còn thiếu gì?
```

```
Gợi ý khóa Docker cho mình
```

```
Mình nên học theo thứ tự nào?
```

**Kỳ vọng:**

- Hệ thống biết **career + kỹ năng đã khai** từ form → trả lời skills gap / follow-up chính xác hơn session trống.
- Intent có thể là `skills_gap`, `roadmap_followup`, hoặc `course_rec` tùy câu hỏi.

---

## 6. Tính năng phụ trợ (demo ngắn)

| Tính năng | Cách thao tác | Ghi chú |
|-----------|---------------|---------|
| **Lịch sử chat** | ☰ sidebar → chọn phiên cũ | Cần PostgreSQL (`DATABASE_URL`) |
| **Tạo chat mới** | Nút *tạo chat mới* | Reset ngữ cảnh demo |
| **Dark mode** | Nút theme góc phải | Landing + Chat |
| **Feedback HITL** | 👍 hoặc 👎 dưới tin bot | Không hiện trên tin lỗi (`is_error`) |
| **Thử lại khi lỗi** | Nút *Thử lại* trên bubble đỏ | Khi LLM 503/quota |
| **Quay landing** | ← quay lại | Từ chat |

---

## 7. Demo nhanh 5 phút (khi thiếu thời gian)

1. **Landing** → *trò chuyện ngay*
2. Bấm bubble: *Làm Backend Developer cần học những gì?* → pathfinding
3. Chat mới → *Khóa Python nào phù hợp cho người mới?* → course_rec
4. Chat mới → *Muốn học Django thì cần biết ngôn ngữ nào?* → competency_relation
4. **Cùng phiên** — §1.1A: `React cần học gì trước?` → `Thế còn Vue?`
5. **Form** (2 phút): Fresher → Backend → Python/SQL → gửi
6. **Cùng phiên form** — §1.6 lượt 2–3
7. 👍 một tin nhắn bot

---

## 8. Xử lý sự cố khi demo trực tiếp

| Triệu chứng | Cách xử lý nhanh |
|-------------|------------------|
| Trả lời chậm | Bình thường (LLM + retrieval); nói trước "đang tra graph + vector" |
| Bubble đỏ / lỗi 503 | Bấm **Thử lại**; kiểm tra `GEMINI_API_KEY` |
| Trả lời lệch intent | **Tạo chat mới**, hỏi lại câu rõ ràng hơn (có tên nghề / tên công nghệ) |
| Không có lịch sử sidebar | `DATABASE_URL` chưa cấu hình — vẫn chat được, chỉ không persist |
| Course card trống | Kiểm tra Neo4j + Qdrant qua `/api/health` |

---

## 9. Bảng tra cứu intent ↔ câu hỏi mẫu

| Intent | Câu hỏi demo (copy-paste) |
|--------|---------------------------|
| `pathfinding` | `Frontend Developer học gì?` |
| `course_rec` | `Học FastAPI cho Python` |
| `competency_relation` | `FastAPI built on language nào?` |
| `subject_career` | `Học môn OOP thì sau này làm nghề gì?` |
| `skills_gap` | `Backend Developer đã biết Python, gap còn lại?` *(nên có profile)* |
| `slot_fill` | `Xin chào` → bot hỏi lại |
| `roadmap_followup` | Sau form: `Mình nên bắt đầu từ đâu?` |
| Multi-turn relation | §1.1 — `React…` → `Thế còn Vue?` |
| Multi-turn → course | §1.2 — 3 lượt pivot khóa Vue |
| Pathfinding → course | §1.3 |
| 7 bước thu thập kỹ năng | §1.5 |
| Form + hỏi tiếp | §1.6 |

Nguồn mở rộng thêm 52 case: `data/eval/answer_quality_gold.jsonl`.

---

## 10. Phân biệt với tài liệu kiểm tra lại

| File | Mục đích |
|------|----------|
| **`docs/HUONG_DAN_DEMO.md`** (file này) | Kịch bản **trình diễn trên web** cho hội đồng / người dùng |
| `docs/HUONG_DAN_KIEM_TRA_LAI.md` | Tái lập **kết quả thực nghiệm** (pytest, gold, E2E eval) |
