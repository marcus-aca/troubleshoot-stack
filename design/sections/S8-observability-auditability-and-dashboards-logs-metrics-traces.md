# Section
Observability, auditability, dashboards, logs, metrics, traces

## Current implementation (source of truth)
- **Structured logs**: `log_event` writes JSON log lines with request metadata and LLM events.
- **Request IDs**: generated/propagated across responses and logs.
- **CloudWatch metrics** (optional): API latency/error rates, LLM latency/tokens, cache hits, budget denials.
- **In-memory fallbacks**: rolling percentiles and error rates when CloudWatch metrics are disabled.
- **Terraform dashboards/alarms**: CloudWatch dashboard + alarms created via `infra/terraform/modules/observability`.
- **API surfaces**: `/metrics/summary` exposes API/LLM/cache/budget stats.

## Not implemented yet (by code)
- OpenTelemetry tracing and span export.
- Distributed tracing across API Gateway -> ALB -> ECS.
