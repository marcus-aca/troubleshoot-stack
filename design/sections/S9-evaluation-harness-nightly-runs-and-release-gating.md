# Section
Evaluation harness, nightly runs, and release gating

## Summary
Provide an automated evaluation harness that runs a curated set of case-based tests against the deployed triage/explain endpoints on a nightly schedule and on PRs. The harness must produce reproducible JSON reports and a human-readable markdown summary, detect regressions versus stored baselines, and gate releases (PRs and main/nightly) according to configurable thresholds. Results and artifacts must be stored in the repository under eval/results/ and baseline artifacts under eval/baselines/. The system must be configurable (case set size, thresholds, gating behavior) and resilient to transient failures.

## Design
- Eval cases
  - Size: default 30–80 cases for full eval; smoke subset 5–10 (default 10) for PRs.
  - Each case is a JSON object with:
    - id (string)
    - error_log or trace_stack (string)
    - optional context (string)
    - expected_primary_cause_category (string)
    - required_steps (array of strings / regex patterns) — steps must be mentioned in the response
    - must_cite (array of citation IDs for log lines or tool outputs)
    - tags (optional: e.g., 'smoke', 'regression', 'critical')
  - Stored at eval/cases/<case-id>.json and a manifest eval/cases/manifest.json that lists which are in the smoke subset and the full set.
- Runner
  - Single executable script (Python recommended) at eval/runner/run_eval.py.
  - For each case:
    - POST to /triage and /explain endpoints with authenticated request (GH Actions will supply credentials via secrets).
    - Capture raw responses, response time, and any HTTP errors.
    - Compute:
      - classification_correct (bool): compares predicted_primary_cause_category in response to expected_primary_cause_category.
      - required_step_coverage: for each pattern in required_steps check presence in response text (string or regex); compute coverage percentage per case.
      - citation_coverage: for each id in must_cite, check presence in response text; compute % present.
      - latency_ms (per-call and aggregated: p50, p95).
      - estimated cost_usd (optional: if cost-per-invocation provided).
    - Record failures and parse errors.
  - Produce two outputs:
    - per-run detailed JSON: eval/results/<run-id>/cases.json (per-case records)
    - aggregate summary JSON: eval/results/<run-id>/summary.json (top-level metrics)
    - human-readable markdown: eval/results/<run-id>/summary.md
  - Implementation details:
    - Use robust retry/backoff for transient HTTP 5xx (configurable).
    - Fail a case only after X retries (configurable, default 2 retries).
- Baseline and thresholds
  - Baselines stored at eval/baselines/<baseline-name>.json (summary metrics and full per-case outputs).
  - Thresholds stored in eval/config/thresholds.json. Default thresholds:
    - minimum_pass_rate_delta_absolute: -3.0 (fail if pass rate drops more than 3 percentage points vs baseline)
    - maximum_citation_miss_increase_absolute: 5.0 (fail if citation-miss rate increases by >5 percentage points)
    - optional latency_p95_increase_ms: 200 (fail if p95 latency increases by >200 ms)
  - All thresholds configurable per-job (PR vs nightly) and overrideable per-run.
- Scheduling and gating
  - PRs: run smoke subset (10 cases) in the PR workflow. If smoke eval fails gating thresholds, block merge.
  - Main/nightly: run full eval on main scheduled nightly run (cron). If full eval fails thresholds, mark nightly failure and open a failure ticket or post to alerts channel (configurable).
  - Artifacts: upload both detailed per-case JSON and summary JSON and markdown as build artifacts and commit the summary JSON to eval/results/ with metadata (requires repo write access token).
- Visualization & trend
  - Upload time-series JSON to eval/trends/ or store artifacts; optional badge generation by action that consumes latest summary JSON and writes an SVG badge into the repo or a dedicated status endpoint.
  - Provide a simple CSV/JSON per-run to feed external dashboards.
- CI integration
  - GH Actions workflows living under .github/workflows:
    - eval-pr.yml: triggered on PRs -> runs smoke eval (uses smaller matrix).
    - eval-nightly.yml: scheduled cron on main -> runs full eval and archives results.
- A post-run step compares summary.json to baseline and exits non-zero on regression per thresholds (this is what fails CI).
Non-goals
- No model training or fine-tuning in MVP evaluation harness.
- No external analytics platform dependency for MVP results (keep in-repo + artifacts).

## Implementation Steps
1. Define data artifacts and repository layout
   - Create directories:
     - eval/cases/
     - eval/runner/
     - eval/results/
     - eval/baselines/
     - eval/config/
     - eval/trends/
   - Add README eval/README.md describing how to add cases and run locally.
2. Define eval JSON schemas (schema files in eval/config/)
   - case schema: eval/config/case_schema.json (fields listed in Design).
   - per-case record schema and summary schema: eval/config/result_schema.json and eval/config/summary_schema.json.
   - thresholds schema: eval/config/thresholds_schema.json and default thresholds file eval/config/thresholds.json.
3. Implement the runner
   - Create eval/runner/run_eval.py (or .js):
     - CLI arguments: --cases-dir, --manifest, --endpoints (triage/explain), --output-dir, --retries, --timeout, --auth-token, --thresholds.
     - For each case:
       - POST JSON payloads to endpoints; record response (raw), status_code, latency_ms.
       - Extract predicted_primary_cause_category from response (configurable JSON path).
       - Run required_steps coverage: run full-text regex search (case-insensitive by default).
       - Run must_cite coverage: exact string match or ID regex.
     - Aggregate metrics and write outputs: cases.json, summary.json, summary.md.
     - Exit codes: 0 = success, 2 = regression detected (when run in comparison mode), 1 = internal error.
4. Create baseline results
   - On a tagged baseline commit or stable main, run the full eval once and store:
     - eval/baselines/<baseline-name>.json (both summary + pointer to per-case artifacts).
     - Add instructions and script eval/runner/build_baseline.sh that loads baseline_name and stores results.
   - Document semantic for naming baselines (e.g., baseline/v1.0-YYYYMMDD).
5. Implement comparison step
   - eval/runner/compare_to_baseline.py that:
     - Accepts summary.json and baseline summary JSON.
     - Computes deltas for metrics: pass_rate_delta (absolute points), citation_miss_rate_delta, latency_p95_delta.
     - Reads thresholds from eval/config/thresholds.json and returns non-zero exit if any configured threshold is exceeded.
     - Outputs a small markdown table with differences to stdout and writes compare.json.
6. GH Actions workflows
   - eval-pr.yml (path .github/workflows/eval-pr.yml):
     - Trigger: pull_request.
     - Checkout code, set up Python, run eval/runner with manifest filtered to smoke cases (manifest contains smoke tag).
     - Save artifacts (cases.json, summary.json, summary.md).
     - Run compare_to_baseline.py using the configured PR thresholds (use smaller tolerances if desired).
     - On regression exit non-zero to fail the PR status check.
   - eval-nightly.yml (path .github/workflows/eval-nightly.yml):
     - Trigger: schedule cron (e.g., 0 2 * * *) and on push to main.
     - Run full eval, upload artifacts, compute comparison to baseline, commit eval/results/<run-id>/summary.json to repo (requires PAT in GH secret). Also invoke optional badge generator.
     - If regression, create or update a GitHub issue or post to a monitoring Slack channel (requires webhook secret).
7. Commit and artifact storage
   - By default, upload results as workflow artifacts and also attempt to commit summary.json to eval/results/<run-id>/summary.json. If commit fails (no write token), at minimum upload artifacts.
   - Always record run metadata: run_id, commit_sha, branch, run_time, workflow_id.
8. Visualization and badge (optional)
   - Implement eval/runner/generate_badge.py to create a small SVG badge summarizing pass/fail or pass rate. The action can commit the badge to README or a designated path.
   - Alternatively, upload trend JSON to eval/trends/ and rely on an external dashboard or manual review.
9. Initial population and smoke set selection
   - Curate 30–80 eval cases; tag ~10 as 'smoke' in manifest. Ensure coverage across primary categories and critical fail modes.
   - Produce metadata: how required_steps and must_cite were determined and references to log line ranges or tool output IDs for each case.
10. Documentation and runbook
    - Document how to add cases, how to update baseline, how to adjust thresholds, and owner/responsibilities for nightly alerts.
    - Add an emergency procedure: If nightly fails, create issue with eval artifacts and assign on-call.

## Risks
- Flaky tests and network instability:
  - Mitigation: retries + backoff, stable smoke set for PRs, exclude known-flaky cases or mark flaky and ignore in gating.
- Data leakage / label drift:
  - Mitigation: keep evaluation cases separate from training/finetune data; regularly review cases; record data provenance for each case.
- False positives (CI failing due to minor noise):
  - Mitigation: conservative default thresholds, ability to override thresholds per-run, keep PR gating on small smoke set to reduce noisy full-run failures.
- Unauthorized commits from CI:
  - Mitigation: restrict token scope, require human review when changing baseline; log any automated commits.
- Cost and time budget:
  - Mitigation: limit case count for PRs, measure estimated cost per-run and set cost alarms; runs must complete within CI timeout—use parallelization where possible.
- Hallucination detection is imperfect:
  - "Must-cite" presence is a proxy; may have false negatives if citation phrasing changes.
  - Mitigation: use canonical citation IDs and robust matching rules; include human review for failures.
- Changing response schema from model/service:
  - Mitigation: make parser paths configurable; add schema validation and fail early with clear errors.

## Dependencies
- Deployed endpoints:
  - /triage and /explain must be live and accept authenticated requests.
- CI environment:
  - GitHub Actions runners (or alternate CI) with sufficient concurrency and runtime.
- Secrets:
  - API tokens for endpoints and repository write token (PAT) if committing results.
  - Webhook/Slack tokens for alerts (optional).
- Storage:
  - Repo disk space and GH artifact retention policies (ensure artifacts are retained long enough).
- Baseline artifacts:
  - Initial baseline summary JSON and per-case outputs.
- Human processes:
  - Owners who will act on nightly failures and manage baselines and thresholds.
- Case provenance:
- Access to sample logs/tool outputs referenced by must_cite IDs so required-cite assertions are meaningful.

## Acceptance Criteria
- Functional outputs
  - Every eval run produces:
    - eval/results/<run-id>/cases.json (detailed per-case records)
    - eval/results/<run-id>/summary.json (aggregated metrics including pass_rate, citation_miss_rate, latency stats, run metadata, baseline comparisons)
    - eval/results/<run-id>/summary.md (human-readable markdown summary)
  - Artifacts uploaded as GH Action artifacts and summary.json committed to eval/results/ (if repo write permission exists).
- Gating behavior
  - PRs: smoke eval runs on every PR and the PR status check fails if the smoke eval triggers regression per configured thresholds.
  - Main/nightly: full eval runs nightly; failures trigger alerting and create/update a tracking issue (or similar).
- Regression detection
  - Default thresholds are applied and documented (baseline delta and citation-miss increases).
  - CI/Workflow returns non-zero exit code on regression so CI failure blocks merge (PR gating) or marks nightly failure.
- Baseline and thresholds
  - Baseline artifacts created and stored under eval/baselines/ and referenced by the compare step.
  - Thresholds are configurable in eval/config/thresholds.json and used by comparison logic.
- Observability and traceability
  - Each per-case result must include links or IDs for required must-cite references (log line ranges or tool output IDs).
  - Trend data (time-series JSON/CSV) is available for at least the last N runs (as artifacts or stored under eval/trends/).
- Operational
  - Documentation added (eval/README.md) describing how to run locally, add cases, update baselines, and respond to failures.
  - Owners identified for nightly failures and baseline updates.
- Practical defaults (concrete defaults to start with)
  - Smoke subset: 10 cases.
  - Full eval: 50 cases (adjustable between 30–80).
  - PR fail threshold: pass rate drop > 3 percentage points (absolute) OR citation-miss rate increase > 5 percentage points.
  - Nightly fail threshold: pass rate drop > 2 percentage points (absolute) OR citation-miss rate increase > 3 percentage points OR p95 latency increase > 200 ms.
  - These defaults must be stored in eval/config/thresholds.json and can be tuned by owners.

## Outcomes
- Repeatable, automated quality checks for triage/explain with regression gating.
- Nightly and PR feedback loops with artifacts and trend visibility.
- Clear baseline-driven thresholds for release readiness.

## Decisions
- **Runner**: Python CLI for eval execution and reporting.
- **Gating**: PR smoke set + nightly full set with baseline deltas.
- **Artifacts**: summary JSON committed (when token allows) + full artifacts stored in CI.

## Deliverables
- eval/runner scripts (run_eval.py, compare_to_baseline.py).
- eval/cases corpus with manifest and schemas in eval/config/.
- CI workflows eval-pr.yml and eval-nightly.yml.
- Baseline artifacts and documentation (eval/README.md).

## Implementation tasks
Concrete task list (assignable, PR-sized items)
1. Define eval JSON schemas + config defaults (owner: ML/QA) — 0.5–1 day
2. Implement run_eval.py with retry + metrics (owner: ML/QA) — 1–2 days
3. Implement compare_to_baseline.py (owner: ML/QA) — 0.5–1 day
4. Create GH Actions workflows (owner: infra) — 0.5–1 day
5. Curate cases + manifest (owner: ML) — 1–2 days
6. Build baseline artifacts + docs (owner: ML/QA) — 0.5–1 day

Note: All thresholds, case selections, and gating policies should be documented and owned; treat the defaults above as a starting point and iterate based on observed noise and operational needs.
