# Runbook: API latency regression

## Symptoms
- p95 latency increases for `/triage` or `/explain`.
- Dashboard alarms for latency thresholds.
- Users see slow responses or timeouts.

## Immediate checks (5-10 min)
1) Identify which path regressed
- Check `/metrics/summary` for API p50/p95 and LLM p50/p95.
- Compare `/triage` vs `/explain` latencies in CloudWatch.

2) Check LLM latency
- Look for `llm_call` events in logs and compare `latency_ms`.
- If Bedrock is used, verify Bedrock health in AWS console.

3) Check cache hit rate
- If pgvector is enabled, inspect cache hit rate metric.
- Low hit rate may increase LLM load.

## Likely causes
- Bedrock latency increase.
- DynamoDB hot partition or throttling.
- ECS CPU saturation causing slow requests.
- Cache miss surge.

## Mitigations
- Scale ECS tasks (increase desired count or CPU/memory).
- If Bedrock is slow, temporarily reduce `LLM_MAX_TOKENS` or switch to stub.
- Disable pgvector if Postgres is slow or unhealthy.

## Verification
- p95 latency returns to baseline.
- `/metrics/summary` reports stable values.

## Post-incident follow-up
- Capture root cause and add guardrail metrics to alert earlier.
