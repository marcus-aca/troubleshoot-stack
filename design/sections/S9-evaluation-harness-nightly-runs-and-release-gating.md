# Section
Evaluation harness (current implementation)

## Current implementation (source of truth)
- **Runner**: `eval/runner/run_eval.py` posts cases to `/triage` and optional `/explain`.
- **Cases**: JSON fixtures in `eval/cases` with sets defined in `eval/config/manifest.json`.
- **Metrics**: pass rate, citation miss rate, and latency percentiles; output written under `eval/results/<run_id>`.
- **Baseline comparison**: `eval/runner/compare_to_baseline.py` compares summary metrics against a baseline with thresholds from `eval/config/thresholds.json`.

## Not implemented yet (by code)
- CI automation or nightly scheduling.
- Automatic release gating tied to eval thresholds.
