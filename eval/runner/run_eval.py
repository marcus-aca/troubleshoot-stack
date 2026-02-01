#!/usr/bin/env python3
import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any, Dict, List, Tuple

import requests


def _now_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _load_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _save_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, sort_keys=True)


def _save_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        f.write(text)


def _iter_cases(cases_dir: Path, manifest: Dict[str, Any], set_name: str) -> List[Path]:
    sets = manifest.get("sets", {})
    ids = sets.get(set_name, [])
    if not ids:
        raise ValueError(f"No cases found for set '{set_name}'.")
    return [cases_dir / f"{case_id}.json" for case_id in ids]


def _match_all(patterns: List[str], text: str) -> Tuple[int, List[str]]:
    missing = []
    for pattern in patterns:
        if not re.search(pattern, text, re.IGNORECASE | re.MULTILINE):
            missing.append(pattern)
    return len(patterns) - len(missing), missing


def _percent(numerator: float, denominator: float) -> float:
    if denominator == 0:
        return 0.0
    return round((numerator / denominator) * 100.0, 2)


def _post_json(url: str, payload: Dict[str, Any], headers: Dict[str, str], timeout: float) -> Tuple[int, Dict[str, Any], int]:
    started = time.time()
    resp = requests.post(url, json=payload, headers=headers, timeout=timeout)
    latency_ms = int((time.time() - started) * 1000)
    try:
        data = resp.json()
    except Exception:
        data = {"_raw": resp.text}
    return resp.status_code, data, latency_ms


def run_eval(args: argparse.Namespace) -> int:
    cases_dir = Path(args.cases_dir)
    manifest_path = Path(args.manifest)
    output_dir = Path(args.output_dir) / args.run_id
    output_dir.mkdir(parents=True, exist_ok=True)

    manifest = _load_json(manifest_path)
    case_paths = _iter_cases(cases_dir, manifest, args.set_name)

    headers = {}
    if args.api_key:
        headers["x-api-key"] = args.api_key
    if args.auth_header:
        headers["Authorization"] = args.auth_header
    if args.budget_bypass:
        headers["x-budget-bypass"] = "true"

    case_results = []
    triage_latencies = []
    explain_latencies = []
    failures = 0

    for case_path in case_paths:
        case = _load_json(case_path)
        case_id = case.get("id", case_path.stem)
        error_log = case.get("error_log") or case.get("trace_stack")
        context = case.get("context")
        expected_category = case.get("expected_primary_cause_category")
        required_steps = case.get("required_steps", [])
        must_cite = case.get("must_cite", [])

        raw_text = error_log or ""
        if context:
            raw_text = f"{raw_text}\n\nContext:\n{context}".strip()

        triage_payload = {
            "raw_text": raw_text,
            "conversation_id": case.get("conversation_id"),
            "source": case.get("source", "user"),
            "timestamp": case.get("timestamp"),
        }

        triage_status, triage_data, triage_latency = _post_json(
            args.triage_url, triage_payload, headers, args.timeout
        )
        triage_latencies.append(triage_latency)

        assistant_message = str(triage_data.get("assistant_message", ""))
        metadata = triage_data.get("metadata") or {}
        guardrail_domain = metadata.get("guardrail_domain")
        predicted_category = triage_data.get("predicted_primary_cause_category")
        conversation_id = triage_data.get("conversation_id") or case.get("conversation_id")

        steps_present, steps_missing = _match_all(required_steps, assistant_message)
        cites_present, cites_missing = _match_all(must_cite, assistant_message)

        classification_correct = expected_category is None or (
            predicted_category == expected_category
        )
        expect_domain_allowed = case.get("expect_domain_allowed")
        if expect_domain_allowed is None:
            domain_allowed = True
        elif expect_domain_allowed:
            domain_allowed = guardrail_domain != 1
        else:
            domain_allowed = guardrail_domain == 1

        explain_status = None
        explain_data = None
        explain_latency = None
        explain_message = None
        explain_error = None
        if case.get("follow_up"):
            explain_payload = {
                "conversation_id": conversation_id,
                "response": case.get("follow_up"),
            }
            explain_status, explain_data, explain_latency = _post_json(
                args.explain_url, explain_payload, headers, args.timeout
            )
            explain_latencies.append(explain_latency)
            explain_message = (
                str(explain_data.get("assistant_message", ""))
                if isinstance(explain_data, dict)
                else None
            )
            if explain_status != 200:
                explain_error = explain_data

        passed = (
            triage_status == 200
            and (explain_status in (None, 200))
            and classification_correct
            and steps_missing == []
            and cites_missing == []
            and domain_allowed
        )

        if not passed:
            failures += 1

        case_results.append(
            {
                "id": case_id,
                "triage_status": triage_status,
                "triage_latency_ms": triage_latency,
                "explain_status": explain_status,
                "explain_latency_ms": explain_latency,
                "classification_correct": classification_correct,
                "required_steps": required_steps,
                "required_steps_missing": steps_missing,
                "must_cite": must_cite,
                "must_cite_missing": cites_missing,
                "expected_primary_cause_category": expected_category,
                "predicted_primary_cause_category": predicted_category,
                "assistant_message": assistant_message,
                "explain_assistant_message": explain_message,
                "explain_error": explain_error,
                "guardrail_domain": guardrail_domain,
                "expect_domain_allowed": expect_domain_allowed,
                "passed": passed,
            }
        )

    total = len(case_results)
    passed = sum(1 for c in case_results if c["passed"])
    citation_misses = sum(1 for c in case_results if c["must_cite_missing"])

    summary = {
        "run_id": args.run_id,
        "set_name": args.set_name,
        "total_cases": total,
        "passed": passed,
        "failed": failures,
        "pass_rate": _percent(passed, total),
        "citation_miss_rate": _percent(citation_misses, total),
        "triage_latency_p50_ms": median(triage_latencies) if triage_latencies else 0,
        "triage_latency_p95_ms": sorted(triage_latencies)[max(int(len(triage_latencies) * 0.95) - 1, 0)]
        if triage_latencies
        else 0,
        "explain_latency_p50_ms": median(explain_latencies) if explain_latencies else 0,
        "explain_latency_p95_ms": sorted(explain_latencies)[max(int(len(explain_latencies) * 0.95) - 1, 0)]
        if explain_latencies
        else 0,
        "triage_url": args.triage_url,
        "explain_url": args.explain_url,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

    _save_json(output_dir / "cases.json", {"cases": case_results})
    _save_json(output_dir / "summary.json", summary)

    lines = [
        "# Eval Summary",
        "",
        f"Run ID: {summary['run_id']}",
        f"Set: {summary['set_name']}",
        "",
        "| Metric | Value |",
        "| --- | --- |",
        f"| Total cases | {summary['total_cases']} |",
        f"| Passed | {summary['passed']} |",
        f"| Failed | {summary['failed']} |",
        f"| Pass rate | {summary['pass_rate']}% |",
        f"| Citation miss rate | {summary['citation_miss_rate']}% |",
        f"| Triage p50 latency (ms) | {summary['triage_latency_p50_ms']} |",
        f"| Triage p95 latency (ms) | {summary['triage_latency_p95_ms']} |",
        f"| Explain p50 latency (ms) | {summary['explain_latency_p50_ms']} |",
        f"| Explain p95 latency (ms) | {summary['explain_latency_p95_ms']} |",
    ]
    _save_text(output_dir / "summary.md", "\n".join(lines) + "\n")

    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases-dir", default="eval/cases")
    parser.add_argument("--manifest", default="eval/cases/manifest.json")
    parser.add_argument("--set", dest="set_name", default="smoke")
    parser.add_argument("--triage-url", required=True)
    parser.add_argument("--explain-url", required=True)
    parser.add_argument("--budget-bypass", action="store_true")
    parser.add_argument("--output-dir", default="eval/results")
    parser.add_argument("--run-id", default=os.getenv("EVAL_RUN_ID") or _now_run_id())
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--api-key", default=os.getenv("EVAL_API_KEY"))
    parser.add_argument("--auth-header", default=os.getenv("EVAL_AUTH_HEADER"))

    args = parser.parse_args()
    try:
        return run_eval(args)
    except Exception as exc:
        print(f"Eval runner failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
