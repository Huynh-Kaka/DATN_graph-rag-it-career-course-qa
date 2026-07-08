"""
D-03 — Đánh giá chất lượng câu trả lời end-to-end (LLM-as-a-Judge).

Chạy:
  python scripts/smoke_judge.py
  python scripts/eval_answer_quality.py
  python scripts/eval_answer_quality.py --limit 3 --delay 3
  python scripts/eval_answer_quality.py --gold data/eval/answer_quality_gold.jsonl

Cấu hình .env:
  JUDGE_PROVIDER=local           # gemini | openai | groq | local (khuyến nghị local)
  CHATBOT_LOCAL_BASE_URL=http://localhost:8081/v1
  CHATBOT_LOCAL_API_KEY=sk-chatbot-local
  JUDGE_LOCAL_MODEL=...          # fallback CHATBOT_LOCAL_MODEL
  JUDGE_GROQ_API_KEY=gsk_...     # khi JUDGE_PROVIDER=groq
  JUDGE_GEMINI_API_KEY=          # khi JUDGE_PROVIDER=gemini
  JUDGE_REQUEST_DELAY_SECONDS=2.5
"""

from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv

load_dotenv(PROJECT_ROOT / ".env", override=True)

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from app.core.config import settings  # noqa: E402
from app.db.enums import TargetRole  # noqa: E402
from app.db.profile_snapshot import ProfileSnapshot  # noqa: E402
from app.eval.llm_judge import (  # noqa: E402
    JudgeClient,
    JudgeScores,
    create_judge_client,
    judge_model_label,
)
from app.generator.validator import count_course_citations  # noqa: E402
from app.services.chat_service import ChatService  # noqa: E402

_DEFAULT_GOLD = PROJECT_ROOT / "data" / "eval" / "answer_quality_gold.jsonl"
_DEFAULT_CSV = PROJECT_ROOT / "data" / "eval" / "answer_quality_results.csv"

# Gold intent (taxonomy eval) → route_intent hợp lệ từ IntentRouter Gen 3.
ACCEPTABLE_ROUTES: dict[str, set[str]] = {
    "pathfinding": {"pathfinding", "roadmap_followup"},
    "course_rec": {"course_rec"},
    "skills_gap": {"roadmap_followup", "pathfinding", "competency_slot_fill"},
    "competency_relation": {"competency_relation"},
}


def acceptable_routes_for_gold_intent(gold_intent: str) -> set[str]:
    return set(ACCEPTABLE_ROUTES.get(gold_intent, set()))


def route_acceptable(
    gold_intent: str,
    route_intent: str | None,
    *,
    acceptable_routes: set[str] | None = None,
) -> bool:
    if not route_intent:
        return False
    allowed = acceptable_routes if acceptable_routes is not None else acceptable_routes_for_gold_intent(gold_intent)
    return route_intent in allowed if allowed else True


def _acceptable_routes_for_case(case: dict[str, Any]) -> set[str] | None:
    custom = case.get("acceptable_routes")
    if custom:
        return {str(r) for r in custom}
    expected = str(case.get("expected_intent") or case.get("intent") or "")
    default = acceptable_routes_for_gold_intent(expected)
    return default if default else None


RUN_STATUS_VALID = "valid_run"
RUN_STATUS_ROUTE_MISMATCH = "route_mismatch"
RUN_STATUS_INFRA_ERROR = "infra_error"

_INFRA_ERROR_MARKERS = (
    "503",
    "413",
    "payload too large",
    "request entity too large",
    "timeout",
    "timed out",
    "connection refused",
    "connection error",
    "connect error",
    "unavailable",
    "high demand",
    "rate limit",
    "quota",
    "connectionreset",
    "name or service not known",
)


def is_infra_error_message(message: str | None) -> bool:
    """True when failure looks like transient infrastructure, not answer quality."""
    if not message:
        return False
    lower = message.lower()
    return any(marker in lower for marker in _INFRA_ERROR_MARKERS)


def classify_run_status(
    *,
    gold_intent: str,
    route_intent: str | None,
    error: str | None = None,
    is_error: bool = False,
    parse_fallback: bool = False,
    reply: str | None = None,
    expected_intent: str | None = None,
    acceptable_routes: set[str] | None = None,
) -> str:
    if error or is_error or is_infra_error_message(reply):
        return RUN_STATUS_INFRA_ERROR
    eval_intent = expected_intent or gold_intent
    if not route_acceptable(
        eval_intent,
        route_intent,
        acceptable_routes=acceptable_routes,
    ):
        return RUN_STATUS_ROUTE_MISMATCH
    if parse_fallback and route_intent == "slot_fill" and eval_intent != "slot_fill":
        return RUN_STATUS_ROUTE_MISMATCH
    return RUN_STATUS_VALID


def aggregate_valid_rows(rows: list["EvalRow"]) -> tuple["IntentAggregate", dict[str, "IntentAggregate"]]:
    """Build aggregates from valid_run rows only."""
    overall = IntentAggregate(intent="all")
    by_intent: dict[str, IntentAggregate] = {}
    for row in rows:
        if row.run_status != RUN_STATUS_VALID:
            continue
        overall.add(row)
        bucket = by_intent.setdefault(row.intent, IntentAggregate(intent=row.intent))
        bucket.add(row)
    return overall, by_intent


def compute_run_status_rates(rows: list["EvalRow"]) -> dict[str, float | int]:
    total = len(rows)
    if total == 0:
        return {
            "total": 0,
            "valid_n": 0,
            "route_mismatch_n": 0,
            "infra_error_n": 0,
            "route_mismatch_rate": 0.0,
            "infra_error_rate": 0.0,
        }
    valid_n = sum(1 for r in rows if r.run_status == RUN_STATUS_VALID)
    route_mismatch_n = sum(1 for r in rows if r.run_status == RUN_STATUS_ROUTE_MISMATCH)
    infra_error_n = sum(1 for r in rows if r.run_status == RUN_STATUS_INFRA_ERROR)
    return {
        "total": total,
        "valid_n": valid_n,
        "route_mismatch_n": route_mismatch_n,
        "infra_error_n": infra_error_n,
        "route_mismatch_rate": route_mismatch_n / total,
        "infra_error_rate": infra_error_n / total,
    }


def _load_gold(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _normalize_case(raw: dict[str, Any]) -> dict[str, Any]:
    """Hỗ trợ schema D-03 và legacy D-01 (query/gold_skills/gold_course_codes)."""
    question = raw.get("question") or raw.get("query") or ""
    intent = raw.get("intent") or "pathfinding"
    expected_intent = str(raw.get("expected_intent") or intent)
    expected_careers = list(raw.get("expected_careers") or [])
    if not expected_careers and raw.get("career"):
        expected_careers = [str(raw["career"])]
    if not expected_careers and raw.get("expected_career"):
        expected_careers = [str(raw["expected_career"])]
    expected_skills = list(raw.get("expected_skills") or raw.get("gold_skills") or [])
    expected_courses = list(
        raw.get("expected_courses") or raw.get("gold_course_codes") or []
    )
    acceptable_routes = list(raw.get("acceptable_routes") or [])
    out: dict[str, Any] = {
        "id": raw.get("id") or uuid.uuid4().hex[:8],
        "question": question,
        "intent": intent,
        "expected_intent": expected_intent,
        "expected_careers": expected_careers,
        "expected_skills": expected_skills,
        "expected_courses": expected_courses,
        "session_setup": raw.get("session_setup"),
    }
    if acceptable_routes:
        out["acceptable_routes"] = acceptable_routes
    if raw.get("competency") and intent == "course_rec" and not expected_skills:
        out["expected_skills"] = [str(raw["competency"])]
    if raw.get("turns"):
        out["turns"] = raw["turns"]
    if raw.get("follow_up_question"):
        out["follow_up_question"] = raw["follow_up_question"]
    if raw.get("notes"):
        out["notes"] = raw["notes"]
    if raw.get("gold_source"):
        out["gold_source"] = raw["gold_source"]
    if raw.get("gold_cohort"):
        out["gold_cohort"] = raw["gold_cohort"]
    if raw.get("neo4j_probe_status"):
        out["neo4j_probe_status"] = raw["neo4j_probe_status"]
    return out


def _cohort_for_case(case: dict[str, Any]) -> str:
    cohort = str(case.get("gold_cohort") or "").strip()
    if cohort:
        return cohort
    source = str(case.get("gold_source") or "")
    if source.startswith("quality_gold_v2.2"):
        return "v22_new14"
    return "v21_legacy"


def aggregate_by_cohort(
    rows: list[EvalRow],
    cases: list[dict[str, Any]],
) -> dict[str, dict[str, float | int]]:
    case_cohort = {c["id"]: _cohort_for_case(c) for c in cases}
    cohort_rows: dict[str, list[EvalRow]] = {}
    for row in rows:
        cohort = case_cohort.get(row.case_id, "v21_legacy")
        cohort_rows.setdefault(cohort, []).append(row)

    out: dict[str, dict[str, float | int]] = {}
    for cohort, crows in cohort_rows.items():
        rates = compute_run_status_rates(crows)
        overall, _ = aggregate_valid_rows(crows)
        means = overall.means()
        out[cohort] = {
            **rates,
            "faithfulness": means["faithfulness"],
            "skill_completeness": means["skill_completeness"],
            "no_hallucination_rate": means["no_hallucination_rate"],
        }
    return out


def _git_revision() -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip() or None
    except (OSError, subprocess.CalledProcessError):
        return None


def _write_report_json(
    path: Path,
    *,
    rows: list[EvalRow],
    cases: list[dict[str, Any]],
    by_intent: dict[str, IntentAggregate],
    overall: IntentAggregate,
    status_rates: dict[str, float | int],
    run_label: str | None = None,
) -> None:
    probe_excluded = [
        c["id"]
        for c in cases
        if str(c.get("neo4j_probe_status") or "") == "fail"
    ]
    payload = {
        "run_label": run_label,
        "code_revision": _git_revision(),
        "judge": judge_model_label(),
        "overall": {
            **status_rates,
            **overall.means(),
        },
        "by_intent": {
            intent: {"n": agg.n, **agg.means()}
            for intent, agg in by_intent.items()
        },
        "by_cohort": aggregate_by_cohort(rows, cases),
        "probe_excluded_ids": probe_excluded,
        "route_mismatch_ids": [r.case_id for r in rows if r.run_status == RUN_STATUS_ROUTE_MISMATCH],
        "infra_error_ids": [r.case_id for r in rows if r.run_status == RUN_STATUS_INFRA_ERROR],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


@dataclass
class EvalRow:
    case_id: str
    intent: str
    question: str
    reply_preview: str
    judge: JudgeScores
    citations: dict[str, int]
    route_intent: str | None = None
    expected_intent: str | None = None
    run_status: str = RUN_STATUS_VALID
    error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "intent": self.intent,
            "expected_intent": self.expected_intent or self.intent,
            "question": self.question,
            "route_intent": self.route_intent,
            "run_status": self.run_status,
            "faithfulness": self.judge.faithfulness,
            "skill_completeness": self.judge.skill_completeness,
            "no_hallucination": self.judge.no_hallucination,
            "n_citations": self.citations.get("n_citations", 0),
            "n_valid_citations": self.citations.get("n_valid_citations", 0),
            "error": self.error,
        }


@dataclass
class IntentAggregate:
    intent: str
    n: int = 0
    faithfulness_sum: float = 0.0
    completeness_sum: float = 0.0
    no_hallucination_count: int = 0
    citation_valid_sum: int = 0
    citation_total_sum: int = 0

    def add(self, row: EvalRow) -> None:
        self.n += 1
        self.faithfulness_sum += row.judge.faithfulness
        self.completeness_sum += row.judge.skill_completeness
        if row.judge.no_hallucination:
            self.no_hallucination_count += 1
        self.citation_valid_sum += row.citations.get("n_valid_citations", 0)
        self.citation_total_sum += row.citations.get("n_citations", 0)

    def means(self) -> dict[str, float]:
        if self.n == 0:
            return {
                "faithfulness": 0.0,
                "skill_completeness": 0.0,
                "no_hallucination_rate": 0.0,
                "valid_citation_rate": 0.0,
            }
        rate = self.no_hallucination_count / self.n
        cite_rate = (
            self.citation_valid_sum / self.citation_total_sum
            if self.citation_total_sum
            else 1.0
        )
        return {
            "faithfulness": self.faithfulness_sum / self.n,
            "skill_completeness": self.completeness_sum / self.n,
            "no_hallucination_rate": rate,
            "valid_citation_rate": cite_rate,
        }


def _flatten_known_skills(known_by_type: dict[str, list[str]]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for skills in known_by_type.values():
        for skill in skills:
            label = (skill or "").strip()
            key = label.lower()
            if label and key not in seen:
                seen.add(key)
                out.append(label)
    return out


async def _seed_session(
    chat: ChatService,
    session_id: str,
    case: dict[str, Any],
) -> None:
    state = await chat._sessions.get_or_create(session_id)
    setup = case.get("session_setup") or {}
    gold_intent = str(case.get("intent") or "")

    if setup.get("career"):
        state.career = str(setup["career"])
    elif case.get("expected_careers"):
        state.career = str(case["expected_careers"][0])

    for type_code, skills in (setup.get("known_by_type") or {}).items():
        if skills:
            state.record_known_for_type(str(type_code), list(skills))

    needs_profile = gold_intent == "skills_gap" or bool(setup.get("known_by_type"))
    if needs_profile and state.career:
        known_by_type = dict(state.known_by_type)
        known_skills = _flatten_known_skills(known_by_type)
        state.profile = ProfileSnapshot(
            profile_id=f"eval-{session_id}",
            background="fresher",
            role=TargetRole.other.value,
            role_note=state.career,
            known_skills=known_skills,
            weekly_time="5to10",
            goals=["career_growth"],
            initial_question=case.get("question"),
            profile_completed=True,
        )
        state.phase = "gap_summary"

    await chat._sessions.save(state)


def _empty_citations() -> dict[str, int]:
    return {"n_citations": 0, "n_valid_citations": 0, "n_invalid_citations": 0}


async def _run_case_once(
    chat: ChatService,
    judge: JudgeClient,
    case: dict[str, Any],
    *,
    delay: float,
) -> EvalRow:
    case_id = case["id"]
    intent = case["intent"]
    expected_intent = str(case.get("expected_intent") or intent)
    acceptable = _acceptable_routes_for_case(case)
    session_id = f"eval-judge-{case_id}-{uuid.uuid4().hex[:6]}"

    await _seed_session(chat, session_id, case)

    turns = case.get("turns") or []
    follow_up = case.get("follow_up_question")
    if follow_up and not turns:
        turns = [{"question": case["question"]}, {"question": follow_up}]
    elif not turns:
        turns = [{"question": case["question"]}]

    result: dict[str, Any] = {}
    question = case["question"]
    for idx, turn in enumerate(turns):
        q = turn.get("question") if isinstance(turn, dict) else str(turn)
        question = str(q or "")
        try:
            result = await chat.handle_message(message=question, session_id=session_id)
        except Exception as exc:
            result = {
                "reply": str(exc),
                "is_error": True,
                "route": {"intent": None, "parse_fallback": False},
            }
        if idx < len(turns) - 1:
            await asyncio.sleep(min(delay, 0.5))

    reply = str(result.get("reply") or "")
    graph = result.get("graph")
    route_payload = result.get("route") or {}
    route = route_payload.get("intent")
    is_error = bool(result.get("is_error"))
    parse_fallback = bool(route_payload.get("parse_fallback"))

    run_status = classify_run_status(
        gold_intent=intent,
        expected_intent=expected_intent,
        route_intent=route,
        error=None,
        is_error=is_error,
        parse_fallback=parse_fallback,
        reply=reply,
        acceptable_routes=acceptable,
    )
    if run_status == RUN_STATUS_ROUTE_MISMATCH:
        allowed = sorted(acceptable or acceptable_routes_for_gold_intent(expected_intent))
        print(
            f"    WARN: route_intent={route!r} không thuộc {allowed} "
            f"(expected intent={expected_intent!r}) — excluded from aggregate"
        )
    elif run_status == RUN_STATUS_INFRA_ERROR:
        print(
            f"    WARN: infra_error (is_error={is_error}, route={route!r}) — "
            "skipped judge"
        )

    if run_status != RUN_STATUS_VALID:
        return EvalRow(
            case_id=case_id,
            intent=intent,
            question=question,
            reply_preview=reply[:160].replace("\n", " "),
            judge=JudgeScores(0.0, 0.0, False),
            citations=_empty_citations(),
            route_intent=route,
            expected_intent=expected_intent,
            run_status=run_status,
            error=reply[:200] if is_error or is_infra_error_message(reply) else None,
        )

    ground_truth = {
        "expected_careers": case["expected_careers"],
        "expected_skills": case["expected_skills"],
        "expected_courses": case["expected_courses"],
        "eval_intent": expected_intent,
    }
    graph_ctx = _compact_graph_context(graph, gold_intent=intent)

    scores = judge.score(
        question=question,
        answer=reply,
        ground_truth=ground_truth,
        graph_context=graph_ctx,
    )
    cites = count_course_citations(reply, graph_snapshot=graph if isinstance(graph, dict) else None)

    await asyncio.sleep(delay)

    return EvalRow(
        case_id=case_id,
        intent=intent,
        question=question,
        reply_preview=reply[:160].replace("\n", " "),
        judge=scores,
        citations=cites,
        route_intent=route,
        expected_intent=expected_intent,
        run_status=run_status,
    )


async def _run_case(
    chat: ChatService,
    judge: JudgeClient,
    case: dict[str, Any],
    *,
    delay: float,
    max_retries: int = 2,
) -> EvalRow:
    case_id = case["id"]
    question = case["question"]
    intent = case["intent"]
    last_error: str | None = None

    for attempt in range(max_retries + 1):
        try:
            return await _run_case_once(chat, judge, case, delay=delay)
        except Exception as exc:
            last_error = str(exc)
            if not is_infra_error_message(last_error) or attempt >= max_retries:
                break
            backoff = 2 ** (attempt + 1)
            print(f"    RETRY {attempt + 1}/{max_retries} after infra error ({backoff}s): {last_error[:80]}")
            await asyncio.sleep(backoff)

    return EvalRow(
        case_id=case_id,
        intent=intent,
        question=question,
        reply_preview="",
        judge=JudgeScores(0.0, 0.0, False),
        citations=_empty_citations(),
        route_intent=None,
        expected_intent=str(case.get("expected_intent") or intent),
        run_status=RUN_STATUS_INFRA_ERROR,
        error=last_error,
    )


def _compact_graph_context(graph: Any, *, gold_intent: str = "") -> dict[str, Any]:
    if not isinstance(graph, dict):
        return {}
    out: dict[str, Any] = {}
    list_cap = 8 if gold_intent == "skills_gap" else 10

    def _cap(val: Any) -> Any:
        if isinstance(val, list) and len(val) > list_cap:
            return val[:list_cap]
        return val

    for key in (
        "career_name",
        "career_code",
        "competency_name",
        "competencies",
        "skills_known",
        "skills_missing",
        "courses",
        "pathfinding",
    ):
        if key in graph and graph[key]:
            out[key] = _cap(graph[key])
    if "pathfinding" in graph and isinstance(graph["pathfinding"], dict):
        pf = graph["pathfinding"]
        for k in ("career_name", "skills_known", "skills_missing", "competencies"):
            if pf.get(k):
                out[k] = _cap(pf[k])
    return out


def _markdown_report(
    rows: list[EvalRow],
    by_intent: dict[str, IntentAggregate],
    overall: IntentAggregate,
    status_rates: dict[str, float | int],
) -> str:
    lines = [
        "## LLM-as-Judge — Answer Quality (D-03)\n",
        f"Judge: `{judge_model_label()}` | Cases: {len(rows)} | "
        f"Valid: {status_rates['valid_n']} | "
        f"Route mismatch: {status_rates['route_mismatch_n']} "
        f"({status_rates['route_mismatch_rate']:.1%}) | "
        f"Infra error: {status_rates['infra_error_n']} "
        f"({status_rates['infra_error_rate']:.1%})\n",
        "| Scope | intent | N | Faithfulness | Skill completeness | No-hallucination rate | Valid citations |",
        "|-------|--------|---|--------------|------------------|----------------------|-----------------|",
    ]
    for scope, agg in [("overall", overall), *[(f"by_intent", v) for v in by_intent.values()]]:
        m = agg.means()
        label = agg.intent if scope == "by_intent" else "all"
        lines.append(
            f"| {scope} | {label} | {agg.n} | "
            f"{m['faithfulness']:.2%} | {m['skill_completeness']:.2%} | "
            f"{m['no_hallucination_rate']:.2%} | {m['valid_citation_rate']:.2%} |"
        )

    lines.append("\n### Chi tiết từng case\n")
    lines.append(
        "| ID | intent | route | status | faith | complete | no_halluc | cites | error |"
    )
    lines.append("|----|--------|-------|--------|-------|----------|-----------|-------|-------|")
    for r in rows:
        err = (r.error or "")[:40]
        lines.append(
            f"| {r.case_id} | {r.intent} | {r.route_intent or '-'} | {r.run_status} | "
            f"{r.judge.faithfulness:.2f} | {r.judge.skill_completeness:.2f} | "
            f"{r.judge.no_hallucination} | "
            f"{r.citations.get('n_valid_citations', 0)}/{r.citations.get('n_citations', 0)} | "
            f"{err} |"
        )
    return "\n".join(lines)


def _write_csv(path: Path, rows: list[EvalRow]) -> None:
    import csv

    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "case_id",
        "intent",
        "expected_intent",
        "route_intent",
        "run_status",
        "faithfulness",
        "skill_completeness",
        "no_hallucination",
        "n_citations",
        "n_valid_citations",
        "error",
    ]
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            d = row.as_dict()
            writer.writerow({k: d.get(k) for k in fields})


def _judge_unavailable_message() -> str:
    provider = (settings.judge_provider or "gemini").lower()
    if provider == "openai":
        return "ERROR: JUDGE_OPENAI_API_KEY / OPENAI_API_KEY chưa cấu hình trong .env"
    if provider == "groq":
        return "ERROR: JUDGE_GROQ_API_KEY / GROQ_API_KEY chưa cấu hình trong .env"
    if provider == "local":
        return "ERROR: JUDGE_PROVIDER=local nhưng CHATBOT_LOCAL_BASE_URL chưa cấu hình"
    return "ERROR: JUDGE_GEMINI_API_KEY / GEMINI_API_KEY chưa cấu hình trong .env"


async def _main_async(args: argparse.Namespace) -> int:
    if not args.gold.is_file():
        print(f"ERROR: missing gold file {args.gold}")
        return 1

    judge = create_judge_client()
    if not judge.available:
        print(_judge_unavailable_message())
        return 1

    cases = [_normalize_case(r) for r in _load_gold(args.gold)]
    if args.limit is not None:
        cases = cases[: max(0, args.limit)]

    chat = ChatService()
    rows: list[EvalRow] = []
    delay = max(0.0, args.delay if args.delay is not None else settings.judge_request_delay_seconds)

    print(f"Evaluating {len(cases)} cases (delay={delay}s between judge calls)…")
    print(f"Judge: {judge_model_label()}")
    for i, case in enumerate(cases, start=1):
        print(f"  [{i}/{len(cases)}] {case['id']} ({case['intent']}) …")
        row = await _run_case(chat, judge, case, delay=delay)
        rows.append(row)
        if row.error:
            print(f"    WARN: {row.error}")

    status_rates = compute_run_status_rates(rows)
    overall, by_intent = aggregate_valid_rows(rows)

    print("\n" + _markdown_report(rows, by_intent, overall, status_rates))

    if not args.no_csv:
        _write_csv(args.output_csv, rows)
        print(f"\nCSV saved: {args.output_csv}")

    if args.report_json:
        _write_report_json(
            args.report_json,
            rows=rows,
            cases=cases,
            by_intent=by_intent,
            overall=overall,
            status_rates=status_rates,
            run_label=args.run_label,
        )
        print(f"Report JSON: {args.report_json}")

    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="D-03 LLM-as-Judge answer quality eval")
    parser.add_argument("--gold", type=Path, default=_DEFAULT_GOLD)
    parser.add_argument("--output-csv", type=Path, default=_DEFAULT_CSV)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument(
        "--delay",
        type=float,
        default=None,
        help="Seconds between judge API calls (default: JUDGE_REQUEST_DELAY_SECONDS)",
    )
    parser.add_argument("--no-csv", action="store_true")
    parser.add_argument("--report-json", type=Path, default=None)
    parser.add_argument(
        "--run-label",
        type=str,
        default=None,
        help="Label for report JSON metadata (e.g. v2.2-D0)",
    )
    args = parser.parse_args()
    raise SystemExit(asyncio.run(_main_async(args)))


if __name__ == "__main__":
    main()
