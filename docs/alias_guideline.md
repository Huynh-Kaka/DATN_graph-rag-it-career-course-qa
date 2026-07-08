# Hướng dẫn bổ sung alias domain (VN / EN / viết tắt)

## Mục đích

File [`data/domain_aliases.json`](../data/domain_aliases.json) giúp:

- **Qdrant**: `index_text` giàu từ khóa → embed khớp câu hỏi tiếng Việt
- **Query**: mở rộng câu hỏi trước khi search vector
- **CareerMatcher**: map "dev backend" → `Backend Developer`
- **SFT JSONL**: paraphrase câu hỏi user đồng bộ với retrieval

## Cấu trúc JSON

```json
{
  "careers": {
    "Backend Developer": {
      "vi": ["lập trình viên backend", "..."],
      "abbrev": ["BE", "back-end"]
    }
  },
  "competencies": {
    "Python": {
      "vi": ["học python", "..."],
      "abbrev": ["py"]
    }
  },
  "abbrev_to_career": {
    "BE": "Backend Developer"
  }
}
```

- **Key career/competency**: phải trùng tên canonical trong Neo4j (`career_name`, `item_name`).
- **vi**: cụm tiếng Việt user hay gõ (chữ thường, không dấu cũng được nếu matcher fuzzy bắt được).
- **abbrev**: viết tắt IN HOA hoặc thường; tránh 1–2 ký tự dễ nhầm (vd. đừng map "C" → career).

## Quy trình bổ sung

1. Export tên từ Neo4j:
   ```cypher
   MATCH (c:Career) RETURN c.career_name ORDER BY c.career_name;
   MATCH (n) WHERE n:ProgrammingLanguage OR n:Framework RETURN n.item_name LIMIT 100;
   ```
2. Với mỗi nghề: thêm ≥2 alias VN + abbrev phổ biến.
3. Chạy `python scripts/build_index_corpus.py` rồi `python scripts/index_qdrant.py`.
4. Chạy `python scripts/eval_retrieval.py` — sửa alias cho case fail.

## Checkpoint

- 100% career trong graph có ≥2 alias VN trong file (hoặc fuzzy đủ gần).
- Top 30 competency có alias.
- `retrieval_gold.jsonl`: Recall@5 ≥ 0.6 (course), career hit ≥ 0.7.

## Không làm

- Không thêm skill/khóa học không có trong Neo4j.
- Không embed alias thay cho ground truth graph khi trả lời cuối — alias chỉ hỗ trợ **tìm** đúng node.
