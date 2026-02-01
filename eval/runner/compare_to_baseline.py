#!/usr/bin/env python3
import argparse
import json
from pathlib import Path
from typing import Any, Dict


def _load_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _get(metric: str, current: Dict[str, Any], baseline: Dict[str, Any]) -> tuple:
    return current.get(metric), baseline.get(metric)


def _delta(current: float, baseline: float) -> float:
    return round(current - baseline, 2)


def compare(current: Dict[str, Any], baseline: Dict[str, Any], thresholds: Dict[str, Any]) -> Dict[str, Any]:
    results = {}

    current_pass, baseline_pass = _get("pass_rate", current, baseline)
    if current_pass is not None and baseline_pass is not None:
        results["pass_rate_delta"] = _delta(current_pass, baseline_pass)

    current_cite, baseline_cite = _get("citation_miss_rate", current, baseline)
    if current_cite is not None and baseline_cite is not None:
        results["citation_miss_rate_delta"] = _delta(current_cite, baseline_cite)

    current_p95, baseline_p95 = _get("triage_latency_p95_ms", current, baseline)
    if current_p95 is not None and baseline_p95 is not None:
        results["triage_latency_p95_delta_ms"] = _delta(current_p95, baseline_p95)
        if baseline_p95:
            results["triage_latency_p95_delta_percent"] = round(
                ((current_p95 - baseline_p95) / baseline_p95) * 100.0, 2
            )

    current_p50, baseline_p50 = _get("triage_latency_p50_ms", current, baseline)
    if current_p50 is not None and baseline_p50 is not None:
        results["triage_latency_p50_delta_ms"] = _delta(current_p50, baseline_p50)
        if baseline_p50:
            results["triage_latency_p50_delta_percent"] = round(
                ((current_p50 - baseline_p50) / baseline_p50) * 100.0, 2
            )

    failures = []
    min_pass_drop = thresholds.get("minimum_pass_rate_delta_absolute")
    if min_pass_drop is not None and "pass_rate_delta" in results:
        if results["pass_rate_delta"] < min_pass_drop:
            failures.append("pass_rate_delta")

    max_cite_increase = thresholds.get("maximum_citation_miss_increase_absolute")
    if max_cite_increase is not None and "citation_miss_rate_delta" in results:
        if results["citation_miss_rate_delta"] > max_cite_increase:
            failures.append("citation_miss_rate_delta")

    max_p95_increase = thresholds.get("latency_p95_increase_ms")
    if max_p95_increase is not None and "triage_latency_p95_delta_ms" in results:
        if results["triage_latency_p95_delta_ms"] > max_p95_increase:
            failures.append("triage_latency_p95_delta_ms")

    max_p95_increase_pct = thresholds.get("latency_p95_increase_percent")
    if max_p95_increase_pct is not None and "triage_latency_p95_delta_percent" in results:
        if results["triage_latency_p95_delta_percent"] > max_p95_increase_pct:
            failures.append("triage_latency_p95_delta_percent")

    max_p50_increase_pct = thresholds.get("latency_p50_increase_percent")
    if max_p50_increase_pct is not None and "triage_latency_p50_delta_percent" in results:
        if results["triage_latency_p50_delta_percent"] > max_p50_increase_pct:
            failures.append("triage_latency_p50_delta_percent")

    results["failed_checks"] = failures
    return results


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--summary", required=True)
    parser.add_argument("--baseline", required=True)
    parser.add_argument("--thresholds", default="eval/config/thresholds.json")
    parser.add_argument("--out", default="eval/results/compare.json")

    args = parser.parse_args()
    summary = _load_json(Path(args.summary))
    baseline = _load_json(Path(args.baseline))
    thresholds = _load_json(Path(args.thresholds))

    results = compare(summary, baseline, thresholds)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, sort_keys=True)

    if results["failed_checks"]:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
