# Section
Observability, auditability, and dashboards (logs/metrics/traces)

## Summary
Provide MVP-level observability for the API service so requests can be audited and measured. Implemented in the current codebase:
- Correlated request_id across responses and logs.
- Structured JSON logs for request start/end and errors.
- Basic CloudWatch metrics for API request count, latency, error count, and budget denials.
 - Metrics summary endpoint (`/metrics/summary`) that surfaces p50/p95 latency from CloudWatch and falls back to in-memory rolling percentiles.
Future scope (not implemented in MVP): full OTEL traces, dashboards/alarms, and multi-service metrics.

Owner: Observability/Platform team lead.
Target timeline: 4 weeks (config + instrumentation + dashboards + tests) — adjust per team capacity.

## Design (MVP)
Goals:
 - Correlate logs and metrics using a single request_id propagated across the API.
 - Keep logs structured (JSON) with stable field names and controlled cardinality.
 - Emit basic CloudWatch metrics via PutMetricData for request count, latency, and error count.
 - Protect sensitive data: do not log raw prompt text or PII.
Non-goals:
 - No OTEL tracing in MVP.
 - No dashboards/alarms in MVP.
 - No per-user metric dimensions (avoid high-cardinality metrics).

Key components (MVP):
- API service middleware:
  - Generates or accepts request_id
  - Emits structured JSON logs per request (start/end/error)
  - Emits basic CloudWatch metrics (request count, latency, error count, budget denied)
- CloudWatch Logs for API log ingestion (retention policy to be configured).

Log fields and metric naming conventions (MVP):
- Log namespace: /aws/service/<component> or application/<service-name>
- Structured logs (JSON) with fields: request_id, endpoint, method, status_code, latency_ms, timestamp.
- Metric namespace: Troubleshooter/LLM (configurable via `CW_METRICS_NAMESPACE`). Metric names: APIRequestCount, APILatencyMs, APIErrorCount, BudgetDeniedCount.
- Metrics summary endpoint: `/metrics/summary` provides `api_latency_p50_ms` and `api_latency_p95_ms` with source `cloudwatch` or `memory`.

Tracing:
- Not implemented in MVP. Plan for OTEL tracing in a future phase.

Security & Privacy:
- Redact or hash user identifiers and prompt content before logging.
- Logs and metrics must not contain PII. Provide policy and code snippet for redaction.
- Restrict CloudWatch log group access via IAM and enable encryption at rest (KMS).

Retention & Cost management:
- Configure retention and lifecycle (CloudWatch Log groups 90 days for hot, archive to S3 for >90 days).
- Track metric emission cost; avoid high-cardinality metric dimensions.

## Implementation Steps (MVP)
1. Define schemas and standards (done)
   - Finalize structured log schema, metric names, dimensions, units, and trace/span naming conventions.
   - Publish conventions doc and add to developer onboarding.

2. Instrumentation prep (done)
   - Structured logging helper (`log_event`).
   - CloudWatch metrics helper (`CloudWatchMetrics`) for API-level metrics.

3. API ingress (future)
   - Optional: generate X-Request-Id at API Gateway/ALB if missing.

4. Application instrumentation (done)
   - Middleware to log request start/end and errors with request_id.
   - Emit CloudWatch metrics for request count, latency, errors, and budget denials.

5. Collector and export configuration (future)

6. Logging & Metrics pipelines (MVP)
   - Use CloudWatch Logs (retention/KMS to be configured).
   - Emit basic API metrics via PutMetricData.

7. Dashboards & Alarms (future)

8. Tests, verification and rollout (MVP)
   - Unit tests for logger, metrics emitter, and trace helpers.
   - Integration test: send synthetic traffic that exercises cache hit/miss, tool calls, and model generation. Verify:
     - One request_id appears in logs across services
   - Metrics are emitted with expected names/values
   - Canary rollout: enable instrumentation in 5% traffic, monitor, then 25% and 100%.
   - Backout plan: feature flag to disable EMF emission and revert OTEL config; documented rollback commands.

9. Documentation & runbooks (MVP)
   - Publish how-to for searching by request_id and checking API metrics.

Total estimated effort: 2–4 sprints depending on number of services and team size.

## Risks
- High-cardinality metric dimensions causing CloudWatch cost and throttling. Mitigation: restrict metric dimensions, keep high-cardinality in logs/traces instead.
- Sensitive data leakage (prompts or PII) in logs. Mitigation: implement redaction/hashing library and code review checks.
- Performance overhead from tracing and logging. Mitigation: use sampling, batch EMF submission, asynchronous logging, and measure added latency during canary.
- Incorrect correlation (request_id mismatch) between API Gateway / services. Mitigation: standardize header name, add guardrails in middleware, and integration tests.
- OTEL Collector misconfiguration causing data loss. Mitigation: staging environment verification and rollbacks.
- Alert storms if thresholds are too low. Mitigation: set reasonable thresholds initially, enable suppression and escalation in PagerDuty/SNS.
- IAM misconfigurations preventing metrics/traces export. Mitigation: pre-define least-privilege roles and test in staging.

## Dependencies
- ADOT / OTEL Collector availability (or vendor APM) and appropriate exports (CloudWatch/X-Ray).
- API Gateway / ALB support for forwarding headers required for correlation.
- IAM permissions for services and collector to publish metrics/traces/logs.
- CloudWatch dashboard and alarm capacity (limits) and SNS/PagerDuty integration.
- Application teams to integrate SDKs and adhere to logging schema.
- KMS for log encryption if required by security/compliance.
- Storage/S3 for long-term archiving (if using).

## Acceptance Criteria (MVP)
- All of the following must be true before rollout completes:
  - Instrumented API service emits structured logs (JSON) for each request containing required fields (see Structured logs section) with documented types and examples.
  - CloudWatch metrics are emitted for APIRequestCount, APILatencyMs, APIErrorCount, and BudgetDeniedCount.
  - Single request can be traced end-to-end using request_id: logs and traces across components are correlated and searchable.
  - CloudWatch dashboard shows live traffic and SLO-style indicators (p95 latency, request count, 5xx rate, cache hit rate, cost/request).
  - Alarms fire under defined test conditions and notify the configured incident channel (SNS/PagerDuty).
  - Unit and integration tests validate instrumentation, and a canary rollout demonstrates acceptable performance overhead (e.g., <5% added p95 latency).
  - Documentation and runbooks for searching by request_id, responding to alarms, and disabling instrumentation are published.

## Structured logs
Schema (JSON keys, types and notes):
- timestamp: ISO8601 string (required)
- request_id: string (UUID v4) (required)
- environment: string (e.g., prod/stage) (required)
- service: string (service name) (required)
- deployment_id: string (CI/CD deploy id) (optional)
- user_id_hash: string (HMAC-SHA256 hashed id, no raw PII) (optional)
- endpoint: string (path or logical endpoint) (required)
- model_id: string (e.g., gpt-4o) (required)
- prompt_version: string (version tag id) (optional)
- tokens_in: int
- tokens_out: int
- cost_estimate_usd: float
- cache_hit: boolean
- tool_calls: object { "<tool_name>": int, ... }
- latency_ms: object { total: int, http: int, model_generate: int, tool_calls: int }
- log_level: string (INFO/ERROR/DEBUG)
- trace_id: string (OTEL trace id)
- span_id: string (current span id)

Example log (single-line JSON):
{"timestamp":"2026-01-28T12:00:00Z","request_id":"...","environment":"prod","service":"api","deployment_id":"2026-01-28-1","user_id_hash":"...","endpoint":"/v1/generate","model_id":"gpt-4o","prompt_version":"v2.3","tokens_in":120,"tokens_out":256,"cost_estimate_usd":0.0123,"cache_hit":false,"cache_id":null,"similarity_score":null,"tool_calls":{"search":1},"latency_ms":{"total":430,"http":15,"model_generate":290,"tool_calls":5},"log_level":"INFO","trace_id":"...","span_id":"..."}

Logging best practices:
- Use structured logger wrappers to enforce schema.
- Log at request start (INFO, minimal fields) and request end (INFO, full fields).
- Log errors with stacktrace at ERROR level, include request_id.
- Avoid logging raw prompt or PII; store prompt hashes or redacted snippets only when necessary.

## Metrics
Core metrics (namespace: MyApp/Requests):
- RequestCount (Count) — dimension: environment, service
- RequestLatencyMs (Milliseconds) — emit distribution as histogram; create CloudWatch percentiles (p50, p95)
- ErrorCount (Count) — labels/dimensions: environment, service, error_type
- CacheHitCount / CacheMissCount (Count) — compute CacheHitRate = hits / (hits + misses)
- CostPerRequestUSD (Gauge) — float in USD
- TokensIn, TokensOut (Count)

SLOs & suggested thresholds (example):
- p95 latency < 1.5s (API) / p95 model_generate < 1.0s for model backend
- 5xx rate < 0.5%
- Cache hit rate > 70% (product dependent)
- Cost per request <= $0.05 (example)

Emission method:
- Use EMF for per-request aggregates. Example EMF payload includes metrics array and dimensions [environment, service, model_id (only when reasonable cardinality)].
- Emit aggregated metrics at end of request to reduce PutMetricData calls.
- Avoid creating per-user metrics; put user_id only in logs/traces, not as metric dimension.

Metric tagging and cardinality guidelines:
- Allowed dimensions: environment, service, deployment_id (low-cardinality), model_id (monitor top N but avoid unlimited values), endpoint (top-level only).
- Do not use user_id or full prompt_version if it creates high cardinality. Use a coarse prompt_version (major versions).

## Tracing
Span naming and attributes:
- Root span: http_request
  - attributes: request_id, endpoint, http.method, http.status_code, user_id_hash, model_id
- tool_call: tool span
  - attributes: tool_name, cache_hit (bool), tool_status
- bedrock_generate / model_generate: model span
  - attributes: model_id, prompt_version (coarse), tokens_in, tokens_out, cost_estimate_usd
- tool_call.<tool_name>: tool spans
  - attributes: tool_name, tool_latency_ms, tool_result_code
- dynamodb_query or db_query: db spans
  - attributes: table_name (or table hash), query_type, items_returned

Trace export:
- OTEL SDK -> ADOT Collector configured to export to CloudWatch/X-Ray/OTLP endpoint.
- Correlate trace_id attribute in logs for easy cross-surface search.

Sampling policy:
- Default probabilistic sampling (e.g., 1%).
- Allow deterministic sampling for traffic flagged for debugging (by request header, deployment, or feature flag).
- Allow higher sampling in canary/staging.

## Dashboards/alarms
Dashboard widgets:
- Latency p50 / p95 / p99 over time (line graph)
- Request count (sum) and requests per second (RPS)
- Error rates: 5xx, 4xx (stacked or separate)
- Cost per request (avg) and tokens/request (avg)
- Cache hit rate (time series) and tool call latency
- Top-N endpoints by error count and p95 latency
- Live tail link or CloudWatch Logs Insights pre-built queries (search by request_id)

Alarms (with sample thresholds — tune to product):
- Latency: p95 RequestLatencyMs > 1500 ms for 5 minutes -> SNS/PagerDuty
- Error rate: 5xx rate > 1% for 5 minutes -> SNS/PagerDuty
- Cache hit rate: CacheHitRate < 60% for 10 minutes -> Ops Slack channel
- Cost per request: CostPerRequestUSD > $0.50 for 10 minutes -> Finance + Ops
Alarm actions:
- First alert -> PagerDuty (on-call)
- Repeated or escalation -> Slack channel + Email
- Include runbook URL and quick remediation steps in alarm description.

Runbooks:
- For latency: steps to check traces by request_id, check model backend health, check retry/backpressure events, scale up replicas, or roll back recent deploy.
- For high error rate: check logs for common error patterns, recent deploy, auth failures, and rollout rollback instructions.

## Acceptance criteria
(This is the second/explicit acceptance checklist focused on observable outcomes)
- End-to-end traceability: For any synthetic test request, you can:
  - Query logs by request_id and see log entries from each component.
  - Open a trace with the same request_id and see spans: http_request → model_generate → tool_call(s) → dynamodb_query.
- Dashboards: CloudWatch dashboard displays live traffic and the following indicators: p95 latency, request count, 5xx rate, cache hit rate, and cost per request.
- Metrics available: RequestLatencyMs, RequestCount, ErrorCount, CacheHitRate, CostPerRequestUSD visible and graphed.
- Alarms: Trigger test alarm conditions and confirm notifications reach configured channels and runbook is actionable.
- Performance overhead: Instrumentation adds acceptable latency (e.g., <5% p95 increase) verified in canary.
- Security: No PII or raw prompt content appears in logs or metrics; verification via PR checklist and automated scan.

## Outcomes
- Traceable request lifecycle across API, model, and tools via request_id.
- SLO-style dashboards and alarms for latency, error rate, cache hit rate, and cost.
- Auditable logs/metrics that remain privacy-safe.

## Decisions
- **Tracing**: OpenTelemetry with ADOT Collector for export.
- **Metrics**: EMF-based per-request aggregates, low-cardinality dimensions only.
- **Retention**: CloudWatch logs with lifecycle policy; optional S3 archive.

## Deliverables
- Structured logging schema + logger middleware.
- OTEL traces with standard spans (http_request, model_generate, tool_call, dynamodb_query).
- CloudWatch dashboards and alarms with runbooks.
- Instrumentation tests and canary rollout plan.

## Implementation tasks
Concrete task list (assignable, PR-sized items)
1. Logging/metric schema definitions + docs (owner: platform) — 0.5–1 day
2. OTEL SDK integration + helper library (owner: platform) — 1–2 days
3. ADOT Collector config + IAM permissions (owner: platform) — 0.5–1 day
4. Dashboard + alarms (owner: platform/SRE) — 0.5–1 day
5. Integration tests + canary rollout (owner: SRE) — 1–2 days

## Implementation tasks
Checklist (concrete tasks with owners and expected time):
- [Platform] Finalize log schema & metric naming doc — 2 days
- [Platform] Create shared observability SDK (logger + OTEL helper + redaction) — 3 days
- [App Team] Add middleware to API service to propagate request_id, start root span, and emit start/end structured logs — 2–4 days per service
- [App Team] Instrument model generation, tool calls, and DB access with spans and attributes — 2–5 days per service
- [Platform] Deploy ADOT Collector and configure exporters + IAM roles — 1–2 days
- [Platform] Create CloudWatch log groups, set retention & encryption — 0.5 day
- [Platform] Implement EMF emission and test metrics visibility — 1 day
- [Platform] Build dashboards and alarm definitions, connect SNS / PagerDuty — 1–2 days
- [QA] Create integration tests that verify end-to-end correlation and metrics emission — 2 days
- [Ops] Canary rollout and monitor overhead/behaviour — 1–2 days
- [Security] Run log scans for PII and approve redaction — 1 day
- [Documentation] Publish runbooks, developer guide, and playbooks — 1 day

Rollback plan:
- Feature-flag instrumentation (toggle EMF and OTEL on/off) and have a runbook to disable collector exports or remove agent.
- Immediate rollback steps: disable instrumentation flag -> stop sending EMF -> revert OTEL collector config -> roll back service if required.

Notes:
- Tune thresholds and sampling after initial telemetry is collected for realistic baselines.
- Schedule a post-rollout review to adjust dashboards, alarms, and retention based on observed usage and cost.
