# Section
Observability, auditability, and dashboards (logs/metrics/traces)

## Summary
Provide end-to-end observability (logs, metrics, traces) and operational dashboards for the API and backend services so every request can be audited, traced, and measured against SLOs. Deliverables:
- Structured, correlated logs for each request including model, prompt version, cost estimate, cache metadata, and tool usage.
- OpenTelemetry traces with key spans (HTTP, model generation, tool calls, DB).
- Custom metrics (EMF or PutMetricData) for latency percentiles, cost per request, cache hit rate, error rates, and evaluation pass rates.
- CloudWatch dashboards and alarms with runbooks and alert actions.
- Automated deployment steps, tests, and rollout plan.

Owner: Observability/Platform team lead.
Target timeline: 4 weeks (config + instrumentation + dashboards + tests) — adjust per team capacity.

## Design
Goals:
- Correlate logs, traces, and metrics using a single request_id propagated across components.
- Keep logs structured (JSON) with stable field names and controlled cardinality.
- Use OpenTelemetry (OTEL) for traces and metrics; export via ADOT Collector (or OTLP) to CloudWatch / X-Ray / third-party APM as required.
- Emit CloudWatch-native metrics using EMF for high-cardinality dimensions to avoid PutMetricData throttling; keep high-cardinality fields in logs & traces, not as metric dimensions.
- Protect sensitive data: do not log raw prompt text or PII. Provide deterministic redaction & hashed identifiers for sensitive values.
- Provide dashboards that reflect SLO-style indicators and support drill-down via request_id.
Non-goals:
- No custom SIEM or full enterprise security analytics in MVP.
- No per-user metric dimensions (avoid high-cardinality metrics).

Key components:
- API Gateway / load balancer: inject upstream request id header (X-Request-Id) if not present, forward trace headers (traceparent).
- Application service(s): add OTEL SDK + logger middleware that:
  - Generates or accepts request_id
  - Starts root span and attaches trace context
  - Emits structured logs per request and per significant events
  - Emits custom metrics (EMF) for request-level aggregates
- OTEL Collector (ADOT) in AWS (or as sidecar) to export traces to chosen backend (CloudWatch, X-Ray, or third-party), and metrics to CloudWatch.
- Storage/retention: CloudWatch Logs (30/90/365 days depending on compliance), S3 for long-term archived logs if required.
- Dashboards: CloudWatch dashboard with widgets and alarms integrated with SNS / PagerDuty for notifications.

Log fields and metric naming conventions:
- Log namespace: /aws/service/<component> or application/<service-name>
- Structured logs (JSON) with fields: request_id, user_id (hashed if PII), endpoint, model_id, prompt_version, tokens_in, tokens_out, cost_estimate_usd, cache_hit (bool), cache_id, similarity_score, tool_calls (map name->count), latency_ms (map: total, http, model_generate, tool_calls), log_level, timestamp, environment, deployment_id.
- Metric namespace: MyApp/Observability (or product-specific). Metric names: RequestLatencyMs, RequestCount, ErrorCount, CacheHitRate, CostPerRequestUSD, TokensPerRequest.

Tracing:
- Use W3C trace context propagation (traceparent, tracestate). OTEL root span name convention: service.http_request or http_request.<method>.
- Spans to create: http_request (root), bedrock_generate (or model_generate), tool_call.<tool_name>, dynamodb_query, downstream_http_call.
- Attach attributes correlating to log fields (request_id, user_hash, model_id, prompt_version, cache_hit).
- Sampling: default 1% production, configurable to higher for specific request types; allow full-trace for debug/canary.

Security & Privacy:
- Redact or hash user identifiers and prompt content before logging.
- Logs and metrics must not contain PII. Provide policy and code snippet for redaction.
- Restrict CloudWatch log group access via IAM and enable encryption at rest (KMS).

Retention & Cost management:
- Configure retention and lifecycle (CloudWatch Log groups 90 days for hot, archive to S3 for >90 days).
- Track metric emission cost; avoid high-cardinality metric dimensions.

## Implementation Steps
1. Define schemas and standards (2 days)
   - Finalize structured log schema, metric names, dimensions, units, and trace/span naming conventions.
   - Publish conventions doc and add to developer onboarding.

2. Instrumentation prep (1 day)
   - Add OTEL SDK and logging library wrapper to language runtime (e.g., Python/Node/Java).
   - Provide utility library for:
     - request_id generation/propagation
     - PII redaction and hashing (salted HMAC)
     - EMF metric emitter helper
     - Span creation helpers

3. API Gateway / Ingress changes (1 day)
   - Ensure X-Request-Id is generated at the edge if not present (API Gateway mapping template or ALB header).
   - Ensure traceparent is forwarded from clients or generated at edge.
   - Document client requirements for propagating trace headers (optional).

4. Application instrumentation (3–6 days across services)
   - Middleware to:
     - Read/generate request_id, accept upstream request id header, and inject into logs and traces.
     - Start OTEL root span with service.name and request attributes.
     - Capture per-request structured log at request start and request end with latency breakdown, tokens, etc.
   - Instrument model generation, DB queries, and tool calls to create named spans with attributes.
   - Emit EMF metrics at end of request: RequestCount=1, RequestLatencyMs, TokensIn, TokensOut, CostPerRequestUSD, CacheHit=0/1.
   - Implement sampling rules (1% default) and option to force full traces for debug.

5. Collector and export configuration (2 days)
   - Deploy ADOT Collector (AWS Distro for OpenTelemetry) as service/agent or sidecar.
   - Configure OTLP exporter to CloudWatch Logs, CloudWatch Metrics (via EMF), and X-Ray (if used). Include metric transformation if needed.
   - Verify IAM roles/policies for collector to PutMetricData, PutTraceSegments (X-Ray), and write to CloudWatch Logs.

6. Logging & Metrics pipelines (2 days)
   - Create CloudWatch Log Groups, set retention, and KMS encryption.
   - Configure log group naming conventions.
   - Create CloudWatch metric filters only if needed (prefer EMF).
   - Implement EMF JSON wrappers to submit metrics with dimensions: environment, service, model_id (careful with cardinality).

7. Dashboards & Alarms (2–3 days)
   - Build CloudWatch dashboard(s) with widgets:
     - P95 latency, P50, request count, 5xx rate
     - Cost/request, tokens/request (avg)
     - Cache hit rate (trend)
     - Error breakdown by endpoint and model_id (top-N)
     - Live tail log widget or Insights query link
   - Create alarms with SNS topic -> PagerDuty / Slack:
     - p95 latency > threshold for N minutes
     - 5xx rate > threshold %
     - Cache hit rate < threshold %
     - Cost per request > threshold for N minutes
   - Add runbook links and playbook in alarm descriptions.

8. Tests, verification and rollout (2–3 days)
   - Unit tests for logger, metrics emitter, and trace helpers.
   - Integration test: send synthetic traffic that exercises cache hit/miss, tool calls, and model generation. Verify:
     - One request_id appears in logs across services
     - Traces show spans in correct order with attributes
     - Metrics are emitted with expected names/values
     - Dashboard widgets update with synthetic traffic
   - Canary rollout: enable instrumentation in 5% traffic, monitor, then 25% and 100%.
   - Backout plan: feature flag to disable EMF emission and revert OTEL config; documented rollback commands.

9. Documentation & runbooks (1 day)
   - Publish how-to for searching by request_id, tracing examples, dashboard guide, and alarm runbooks.

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

## Acceptance Criteria
- All of the following must be true before rollout completes:
  - Instrumented API service emits structured logs (JSON) for each request containing required fields (see Structured logs section) with documented types and examples.
  - EMF metrics (or equivalent PutMetricData) are emitted for RequestLatencyMs, RequestCount, ErrorCount, CacheHitRate, CostPerRequestUSD, and they appear in CloudWatch Metrics.
  - OpenTelemetry traces record the prescribed spans (http_request, bedrock_generate/model_generate, tool_call_*, dynamodb_query) and traces can be visualized in the chosen tracing backend.
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
