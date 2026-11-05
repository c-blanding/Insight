"""Run a labeled, local browser QA evaluation benchmark."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import re
import sys
import time
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CASES = _ROOT / "evals" / "agent_qa" / "cases.json"


def load_cases(path: Path = DEFAULT_CASES) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return _validate_cases(payload, path)


def _validate_cases(payload: dict[str, Any], source: Path) -> list[dict[str, Any]]:
    if payload.get("schema_version") != 1 or not isinstance(payload.get("cases"), list):
        raise ValueError(f"Unsupported benchmark schema in {source}")
    seen: set[str] = set()
    cases = payload["cases"]
    valid_categories = {"bug", "no_bug", "inconclusive", "auth_recovery"}
    valid_verdicts = {"bug_confirmed", "not_reproduced", "inconclusive"}
    for case in cases:
        if not isinstance(case, dict):
            raise ValueError(f"Benchmark case must be an object in {source}")
        required = {"id", "category", "path", "bug_description", "expected_verdict"}
        missing = required - case.keys()
        if missing:
            raise ValueError(f"Benchmark case is missing fields: {sorted(missing)}")
        if case["id"] in seen:
            raise ValueError(f"Duplicate benchmark case id: {case['id']}")
        if case["category"] not in valid_categories:
            raise ValueError(f"Unknown benchmark category in {source}: {case['category']}")
        if case["expected_verdict"] not in valid_verdicts:
            raise ValueError(f"Unknown expected verdict in {source}: {case['expected_verdict']}")
        seen.add(case["id"])
    return cases


def _outcome_text(outcome: Any) -> str:
    parts: list[str] = []
    for finding in getattr(outcome, "step_findings", None) or []:
        for field in ("findings", "page_snapshot", "error"):
            value = getattr(finding, field, None)
            if value:
                parts.append(str(value))
    plan = getattr(outcome, "plan", None)
    for step in getattr(plan, "instructions", None) or []:
        if getattr(step, "action", None):
            parts.append(str(step.action))
    report = getattr(outcome, "report", None)
    if report and getattr(report, "report", None):
        parts.append(str(report.report))
    return "\n".join(parts).casefold()


def _evidence_summary(outcome: Any) -> dict[str, Any]:
    findings = getattr(outcome, "step_findings", None) or []
    snapshots = sum(bool(getattr(item, "page_snapshot", None)) for item in findings)
    console = sum(bool(getattr(item, "console_messages", None)) for item in findings)
    network = sum(bool(getattr(item, "network_messages", None)) for item in findings)
    refs: list[dict[str, str]] = []
    for finding in findings:
        for artifact in getattr(finding, "artifacts", None) or []:
            ref = {
                key: str(getattr(artifact, key, ""))
                for key in ("kind", "bucket", "object_key")
                if getattr(artifact, key, None)
            }
            if ref:
                refs.append(ref)
    return {
        "finding_count": len(findings),
        "snapshot_count": snapshots,
        "console_count": console,
        "network_count": network,
        "artifact_refs": refs,
        "observable_evidence": bool(snapshots or console or network or refs),
    }


def _error_category(outcome: Any, *, paused_for_login: bool = False) -> str | None:
    if paused_for_login:
        return "login_required"
    error = str(getattr(outcome, "error", None) or "").casefold()
    if not error:
        return None if getattr(outcome, "report", None) is not None else "no_report"
    if "target url" in error or "target host" in error or "target hostname" in error:
        return "target_policy"
    if "timed out" in error or "timeout" in error:
        return "timeout"
    if "mcp_unreachable" in error or "not reachable" in error or "connection refused" in error:
        return "browser_unavailable"
    if "auth" in error or "login" in error:
        return "authentication"
    if "max_tools_turns" in error or "budget exceeded" in error:
        return "budget_exhausted"
    return "agent_error"


def _install_tool_counter():
    """Count model-visible browser tool invocations without changing agent code."""
    from insightai.mcp_clients import playwright as playwright_module

    original_factory = playwright_module._openai_compatible_tools
    counts: Counter[str] = Counter()

    def instrumented_factory(raw_tools, client=None):
        tools = original_factory(raw_tools, client=client)
        instrumented = []
        for tool in tools:
            original = tool.coroutine
            if original is None:
                instrumented.append(tool)
                continue

            async def counted(*args, _original=original, _name=tool.name, **kwargs):
                counts[_name] += 1
                return await _original(*args, **kwargs)

            instrumented.append(tool.model_copy(update={"coroutine": counted}))
        return instrumented

    playwright_module._openai_compatible_tools = instrumented_factory
    return counts, lambda: setattr(
        playwright_module, "_openai_compatible_tools", original_factory
    )


def _path_reached(case: dict[str, Any], outcome: Any, tool_counts: Counter[str]) -> bool:
    required_tools = set(case.get("required_tools") or [])
    tools_reached = required_tools.issubset(tool_counts.keys())
    markers = [str(value).casefold() for value in case.get("path_markers") or []]
    if not markers:
        marker_reached = True
    else:
        output = _outcome_text(outcome)
        marker_reached = any(marker in output for marker in markers)
    return tools_reached and marker_reached


def _evidence_cited(outcome: Any, evidence: dict[str, Any]) -> bool:
    report = getattr(getattr(outcome, "report", None), "report", None) or ""
    if re.search(r"(?i)\bstep\s+#?\d+\b", report):
        return True
    return any(ref.get("object_key") and ref["object_key"] in report for ref in evidence["artifact_refs"])


def score_record(record: dict[str, Any]) -> dict[str, Any]:
    record["verdict_correct"] = record.get("actual_verdict") == record.get("expected_verdict")
    category = record.get("category")
    record["bug_reproduced"] = bool(
        category == "bug"
        and record.get("actual_verdict") == "bug_confirmed"
        and record.get("key_path_reached")
        and record.get("evidence", {}).get("observable_evidence")
    )
    record["false_positive"] = bool(
        category in {"no_bug", "inconclusive"}
        and record.get("actual_verdict") == "bug_confirmed"
    )
    record["correct_inconclusive"] = bool(
        category == "inconclusive"
        and record.get("actual_verdict") == "inconclusive"
    )
    record["evidence_supported"] = bool(
        record.get("evidence", {}).get("observable_evidence")
        and record.get("report_cites_evidence")
    )
    return record


def _rate(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 4) if denominator else None


def summarize(records: list[dict[str, Any]]) -> dict[str, Any]:
    scored = [
        score_record(dict(item))
        for item in records
        if item.get("status") not in {"skipped", "failed", "interrupted"}
    ]
    bugs = [item for item in scored if item.get("category") == "bug"]
    negatives = [item for item in scored if item.get("category") in {"no_bug", "inconclusive"}]
    inconclusive = [item for item in scored if item.get("category") == "inconclusive"]
    cited_eligible = [item for item in scored if item.get("actual_verdict") in {"bug_confirmed", "not_reproduced"}]
    login_cases = [item for item in scored if item.get("category") == "auth_recovery"]
    attempted_login = [item for item in login_cases if item.get("login_recovery") in {"recovered", "failed"}]
    efficiency = [
        item for item in scored
        if item.get("status") in {"completed", "completed_after_login"}
    ]
    return {
        "cases_total": len(records),
        "cases_scored": len(scored),
        "cases_excluded": len(records) - len(scored),
        "verdict_accuracy": _rate(sum(item["verdict_correct"] for item in scored), len(scored)),
        "bug_reproduction_rate": _rate(sum(item["bug_reproduced"] for item in bugs), len(bugs)),
        "false_positive_rate": _rate(sum(item["false_positive"] for item in negatives), len(negatives)),
        "correct_inconclusive_rate": _rate(sum(item["correct_inconclusive"] for item in inconclusive), len(inconclusive)),
        "evidence_support_rate": _rate(sum(item["evidence_supported"] for item in cited_eligible), len(cited_eligible)),
        "efficiency_cases": len(efficiency),
        "average_tool_calls": round(sum(item.get("tool_call_count", 0) for item in efficiency) / len(efficiency), 2) if efficiency else None,
        "average_duration_seconds": round(sum(item.get("duration_seconds", 0) for item in efficiency) / len(efficiency), 2) if efficiency else None,
        "login_recovery_rate": _rate(sum(item.get("login_recovery") == "recovered" for item in attempted_login), len(attempted_login)),
    }


async def run_benchmark(
    *,
    base_url: str,
    case_ids: set[str] | None = None,
    include_login: bool = False,
    interactive_login: bool = False,
    timeout: float = 900,
    repeats: int = 1,
    cases_path: Path = DEFAULT_CASES,
) -> dict[str, Any]:
    from insightai import InsightAgent, InsightResult, NeedsLogin
    from insightai.evidence.session import release

    selected = [
        case
        for case in load_cases(cases_path)
        if case_ids is None or case["id"] in case_ids
    ]
    if not include_login:
        selected = [case for case in selected if not case.get("requires_interactive_login")]
    if case_ids:
        found = {case["id"] for case in selected}
        missing = case_ids - found
        if missing:
            raise ValueError(f"Unknown or excluded case IDs: {sorted(missing)}")
    if repeats < 1 or repeats > 10:
        raise ValueError("repeats must be between 1 and 10")

    records: list[dict[str, Any]] = []
    for run_index, case in enumerate(selected * repeats, start=1):
        repeat_index = ((run_index - 1) % len(selected)) + 1
        thread_id = f"eval-{case['id']}-{uuid.uuid4().hex[:8]}"
        input_state = {
            "url": f"{base_url.rstrip('/')}{case['path']}",
            "bug_description": case["bug_description"],
        }
        if case.get("expected_behavior"):
            input_state["expected_behavior"] = case["expected_behavior"]

        tool_counts, restore_counter = _install_tool_counter()
        started = time.monotonic()
        outcome: Any = None
        login_recovery = "not_applicable"
        status = "completed"
        try:
            agent = InsightAgent(preflight=True)
            outcome = await agent.arun(
                input_state,
                thread_id=thread_id,
                timeout=timeout,
                check_mcp=True,
            )
            if isinstance(outcome, NeedsLogin):
                status = "needs_login"
                login_recovery = "paused"
                if interactive_login:
                    print(
                        f"\n[{case['id']}] Sign in in the browser, then press Enter to continue; "
                        "press Ctrl+C to record an interrupted login case.",
                        flush=True,
                    )
                    await asyncio.to_thread(input)
                    outcome = await agent.acontinue(outcome.thread_id, timeout=timeout)
                    if isinstance(outcome, NeedsLogin):
                        status = "needs_login_again"
                        login_recovery = "failed"
                    else:
                        status = "completed_after_login"
                        login_recovery = "recovered"
                if isinstance(outcome, NeedsLogin):
                    expected = case.get("expected_verdict_if_paused", "inconclusive")
                    actual_verdict = "inconclusive"
                    error_category = "login_required"
                    await release(thread_id, finished=True)
                else:
                    expected = case["expected_verdict"]
                    actual_verdict = getattr(getattr(outcome, "report", None), "verdict", "inconclusive")
                    error_category = _error_category(outcome)
            else:
                expected = case["expected_verdict"]
                actual_verdict = getattr(getattr(outcome, "report", None), "verdict", "inconclusive")
                error_category = _error_category(outcome)
                if getattr(outcome, "run_status", None) == "failed":
                    status = "failed"
        except KeyboardInterrupt:
            status = "interrupted"
            expected = case["expected_verdict"]
            actual_verdict = "inconclusive"
            error_category = "operator_interrupted"
            login_recovery = "failed" if case.get("requires_interactive_login") else "not_applicable"
            await release(thread_id, finished=True)
        except Exception as exc:
            status = "failed"
            expected = case["expected_verdict"]
            actual_verdict = "inconclusive"
            error_category = _error_category(type("ErrorOutcome", (), {"error": str(exc)})()) or "runner_error"
            await release(thread_id, finished=True)
        finally:
            restore_counter()

        if isinstance(outcome, InsightResult) and outcome.run_status == "failed":
            status = "failed"
        duration = time.monotonic() - started
        evidence = _evidence_summary(outcome) if isinstance(outcome, InsightResult) else {
            "finding_count": 0,
            "snapshot_count": 0,
            "console_count": 0,
            "network_count": 0,
            "artifact_refs": [],
            "observable_evidence": False,
        }
        record = {
            "case_id": case["id"],
            "repeat": repeat_index,
            "category": case["category"],
            "status": status,
            "expected_verdict": expected,
            "actual_verdict": actual_verdict,
            "error_category": error_category,
            "key_path_reached": _path_reached(case, outcome, tool_counts),
            "evidence": evidence,
            "report_cites_evidence": _evidence_cited(outcome, evidence),
            "tool_calls": dict(tool_counts),
            "tool_call_count": sum(tool_counts.values()),
            "duration_seconds": round(duration, 2),
            "login_recovery": login_recovery,
        }
        records.append(score_record(record))
        print(
            f"{case['id']} [trial {repeat_index}/{repeats}]: {actual_verdict} ({status}; "
            f"{record['tool_call_count']} tools; {duration:.1f}s)",
            flush=True,
        )

    return {
        "schema_version": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "base_url_origin": _origin(base_url),
        "model": _model_name(),
        "records": records,
        "summary": summarize(records),
    }


def _origin(url: str) -> str:
    from urllib.parse import urlsplit

    parsed = urlsplit(url)
    host = parsed.hostname or ""
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    try:
        port = parsed.port
    except ValueError:
        port = None
    authority = f"{host}:{port}" if port is not None else host
    return f"{parsed.scheme}://{authority}"


def _model_name() -> str | None:
    import os

    return os.environ.get("OPENAI_MODEL") or None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base-url", default="http://localhost:5500", help="LumenShop origin"
    )
    parser.add_argument(
        "--case", action="append", dest="case_ids", help="Run only this case ID; repeatable"
    )
    parser.add_argument(
        "--include-login", action="store_true", help="Include the interactive rewards/login case"
    )
    parser.add_argument(
        "--interactive-login", action="store_true", help="Pause for a human login and then resume"
    )
    parser.add_argument("--timeout", type=float, default=900, help="Per-case timeout in seconds")
    parser.add_argument("--repeat", type=int, default=1, help="Repeat each case 1-10 times")
    parser.add_argument("--output", type=Path, help="Write the JSON result to this path (stdout if omitted)")
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES, help="Benchmark case JSON path")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.WARNING)
    try:
        result = asyncio.run(
            run_benchmark(
                base_url=args.base_url,
                case_ids=set(args.case_ids) if args.case_ids else None,
                include_login=args.include_login,
                interactive_login=args.interactive_login,
                timeout=args.timeout,
                repeats=args.repeat,
                cases_path=args.cases,
            )
        )
    except KeyboardInterrupt:
        print("Evaluation interrupted", file=sys.stderr)
        return 130
    except Exception as exc:
        print(f"Evaluation failed: {exc}", file=sys.stderr)
        return 2

    text = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
        print(f"Wrote evaluation results to {args.output}")
        print(json.dumps(result["summary"], indent=2))
    else:
        print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
