# Section
Guardrails: rate limits, per-user budgets, and caching

## Summary
This section defines guardrails to control cost and latency for LLM usage: (1) API-level rate limiting via API Gateway usage plans, (2) per-user daily budget enforcement backed by DynamoDB, and (3) semantic response caching for idempotent endpoints (primarily /explain) using OpenSearch Serverless vector search. The plan includes concrete schemas, middleware behavior, error responses, monitoring, and an ordered implementation plan with risks and dependencies called out.

Goals:
- Prevent runaway cost and abuse.
- Provide predictable latency and cost visibility.
- Reuse identical LLM responses to reduce calls and cost.
- Provide clear, machine-readable error responses when limits are hit.
Non-goals:
- No enterprise billing or invoicing system in MVP.
- No cross-tenant caching without explicit privacy_scope opt-in.

## Design

High-level components
- API Gateway usage plans + per-API-key throttles and quotas (steady + burst + daily quota).
- Application middleware (in the service or Lambda) that:
  - resolves user identity,
  - checks and enforces per-user budget,
  - checks/updates cache,
  - estimates cost before invoking LLM and reconciles after,
  - records usage and emits metrics.
- DynamoDB table:
  - llm_usage — per-user daily usage records (cost & tokens).
- OpenSearch Serverless vector index:
  - semantic cache for sanitized inputs and cached response metadata.
- CloudWatch custom metrics and alarms for budgeting and cache performance.

Rate limiting (API Gateway)
- Usage plan per API key (or per plan tier). Controls:
  - Throttle: steady rate (requests/second) and burst capacity.
  - Quota: requests/day for demo or trial tiers.
- Example defaults (tunable per environment):
  - Demo: steady 5 RPS, burst 10, quota 5,000/day.
  - Production base-tier: steady 20 RPS, burst 50, quota none (or a large quota).
- API Gateway rejects requests beyond throttle/quota with 429 and standard Retry-After.

Per-user budget caps (DynamoDB)
- Table: llm_usage
  - Recommended schema (robust vs reset logic): use composite key (PK: user_id, SK: usage_date YYYY-MM-DD) to avoid manual reset jobs and reduce race conditions. This is preferred to a single-row-per-user with reset_at.
  - Attributes:
    - user_id (PK)
    - usage_date (SK) — YYYY-MM-DD (UTC)
    - tokens_used (Number)
    - cost_estimate (Number) — USD or chosen unit
    - last_updated_at (ISO timestamp)
    - budget_daily (Number) — optional, per-user quota
  - Access pattern: read-and-conditional-update the current day's row with a single UpdateItem that checks (tokens_used + estimated_tokens <= budget_tokens) or (cost_estimate + estimated_cost <= budget_daily). Use ConditionalExpression to enforce atomicity.
  - Provisioning: On-Demand billing for flexibility.
- Middleware flow:
  - Resolve user_id from API key or authenticated token.
  - Compute estimated cost and tokens from request (based on prompt max_tokens, model pricing).
  - Attempt a conditional UpdateItem (increment tokens_used & cost_estimate) only if the increment keeps totals <= budget. If success, proceed.
  - If the conditional update fails, reject with budget-exceeded error.
  - After the LLM call completes, reconcile by writing the actual tokens and cost (UpdateItem) — if actual > estimated, the entry will reflect true usage (no rollback to the LLM call).
  - Optional: allow short negative temporary overshoot for better UX, but flag user and emit metric; or strictly deny if actual > budget — choose policy and reflect in acceptance criteria.

Caching (semantic cache in OpenSearch Serverless)
- Vector index: semantic_cache
  - Document schema (example):
    - cache_id (String) — unique id for the cached item (UUID or hash)
    - endpoint (Keyword) — e.g., /explain
    - embedding (Vector) — embedding of sanitized input + normalized context
    - response_ref (String) — response payload (compact) or S3 key if large
    - created_at (ISO timestamp)
    - expires_at (ISO timestamp)
    - prompt_version (Keyword)
    - model_id (Keyword)
    - privacy_scope (Keyword) — "public" | "team" | "private"
    - tool_result_fingerprint (Keyword)
  - Sanitization & privacy:
    - Only embed and cache sanitized input (redacted PII + secrets). Never embed raw logs with secrets.
    - Default: do not cache private uploads unless explicit opt-in flag is set and privacy_scope permits.
  - Cache lookup:
    - Embed sanitized input + normalized context.
    - Query OpenSearch kNN for top_k neighbors filtered by endpoint, prompt_version, model_id, and privacy_scope.
    - Accept a hit only if similarity >= threshold and expires_at > now.
  - When to cache:
    - Cache POST /explain responses when sanitized input is available and privacy_scope is eligible.
  - Size limits:
    - If response payload is large, store the full response in S3 and keep response_ref as the S3 key + checksum.
  - Expiration:
    - Use expires_at and an index lifecycle policy (or scheduled cleanup) to delete expired cache entries. Treat expired entries as misses even if not yet deleted.
  - Stampede prevention:
    - Best-effort: if cache miss, proceed to LLM call and write cache on success. (Optional later: introduce a short-lived DynamoDB lock keyed by a hash of sanitized input + prompt_version.)

Error response shapes
- Rate limit exceeded (API Gateway): HTTP 429, body:
  - { "error": "rate_limited", "message": "Rate limit exceeded", "retry_after": seconds }
- Budget exceeded (middleware): HTTP 402 (Payment Required) or HTTP 429 with code — choose 402 for explicit budget/billing signaling:
  - { "error": "budget_exceeded", "message": "Daily budget exceeded", "remaining_budget": 0, "retry_after": "2026-01-29T00:00:00Z" }
- Budget denied (generic): HTTP 429 if you prefer uniform 429s; document which status is used in API reference.

Monitoring & metrics
- CloudWatch custom metrics (per region / per stage):
  - BudgetDeniedCount (Count)
  - CacheHitCount (Count)
  - CacheMissCount (Count)
  - CacheHitRate (calculated or emitted as metric)
  - CostPerRequest (Distribution)
  - TokensPerRequest (Distribution)
- Alarms:
  - BudgetDeniedCount > threshold -> paging/alerting.
  - CacheHitRate < expected -> investigate.
  - Sudden increase in CostPerRequest or TokensPerRequest.

## Implementation Steps
Ordered actionable steps with notes for owners and priorities. Assume service code lives in repository "service" and uses AWS Lambda or containerized application behind API Gateway.

1) Provision DynamoDB tables (Infra — IaC)
   - Create llm_usage table:
     - Partition key: user_id (String)
     - Sort key: usage_date (String, YYYY-MM-DD)
     - BillingMode: PAY_PER_REQUEST (on-demand)
     - TTL: none (we retain usage records for auditing; optionally set TTL after 30-90 days)
     - IAM role: grant app read/write access
   - Create OpenSearch Serverless collection + vector index:
     - Collection: semantic-cache
     - Index: semantic_cache (vector dimension aligned to embedding model)
     - Access policy scoped to ECS task role
     - Optional: index lifecycle policy to delete expired docs
   - Estimated time: 1-2 hours

2) Define API Gateway usage plans (Infra)
   - Create usage plan(s) for demo and production tiers.
   - Configure per-API-key throttle & quota:
     - Demo plan: throttle=5 RPS, burst=10, quota=5,000/day
     - Prod default plan: throttle=20 RPS, burst=50, quota=None
   - Associate API keys to plans; ensure stage-level mapping.
   - Estimated time: 1-2 hours

3) Implement user identity resolution & API key mapping (Backend)
   - Middleware function: resolve user_id from:
     - Authenticated JWT token subject (preferred)
     - API key mapping table for API Gateway keys (fallback for dev/demo)
     - For dev only: allow header X-Dev-User-Id when running in dev mode
   - Ensure mapping stored in a secure store (Cognito, Secrets Manager, or a secure mapping table with least privileges).
   - Estimated time: 2-4 hours

4) Implement per-request budget check middleware (Backend)
   - Pseudocode:
     - estimated_tokens, estimated_cost = estimate_from_request(req)
     - today = UTC date YYYY-MM-DD
     - Attempt conditional UpdateItem:
       - Key: { user_id, usage_date: today }
       - UpdateExpression: SET tokens_used = if_not_exists(tokens_used, :zero) + :est_tokens, cost_estimate = if_not_exists(cost_estimate, :zero) + :est_cost, last_updated_at = :now
       - ConditionExpression: (if budget defined) cost_estimate + :est_cost <= :budget_daily AND tokens_used + :est_tokens <= :token_budget
       - ExpressionAttributeValues: provide :est_tokens, :est_cost, :budget_daily
     - If ConditionalCheckFailed -> return HTTP 402 { error: "budget_exceeded" }
     - On success -> proceed to cache-check and LLM call
   - Reconciliation after LLM call:
     - UpdateItem to add actual tokens and actual cost (difference between estimated and actual). This UpdateItem may be unconditional (it will simply increment).
     - If actual > estimated and pushes totals over budget, policy choices:
       - Allow but emit metric BudgetOvershootCount (recommended initial behavior).
       - Or immediately block further requests (set a flag or rely on next request's conditional update to fail) — document chosen behavior.
   - Concurrency: use a single conditional UpdateItem per request for atomicity; this prevents multiple concurrent requests from collectively exceeding budget if condition checks current totals.
   - Estimated time: 6-10 hours (implementation + tests)

5) Implement caching layer (Backend)
   - Normalization & embedding:
     - Sanitize input (redact secrets/PII), then normalize (canonical ordering, whitespace, stable identifiers).
     - Build embedding from sanitized input + normalized context (triage frame + tool_result_fingerprint).
   - Cache lookup flow:
     - If privacy_scope == "private" and user did not opt-in => skip cache.
     - Query OpenSearch Serverless kNN for top_k neighbors filtered by endpoint, prompt_version, model_id, and privacy_scope.
     - If best hit similarity >= threshold and expires_at > now -> CacheHitCount++ and return response (resolve response_ref or fetch from S3 if needed).
     - If miss -> proceed to LLM call.
   - When writing cache:
     - Store embedding + metadata in OpenSearch.
     - If response payload large, upload to S3 and store response_ref as s3://... + checksum.
     - Set expires_at = now + TTL (default 24 hours; configurable per endpoint).
   - Estimated time: 6-12 hours

6) Emit metrics and create dashboards & alarms (Infra + Backend)
   - Emit custom CloudWatch metrics at these points:
     - On budget deny: BudgetDeniedCount
     - On cache hit/miss: CacheHitCount, CacheMissCount
     - After each request: CostPerRequest, TokensPerRequest
     - On LLM invocation success/failure: LLMCallSuccess/Failure
   - Create a dashboard showing CacheHitRate (CacheHitCount/(Hit+Miss)), BudgetDenied trend, CostPerRequest percentile.
   - Create CloudWatch alarms:
     - BudgetDeniedCount > X in 5 minutes -> PagerDuty
     - CacheHitRate < threshold -> Slack alert
   - Estimated time: 4-8 hours

7) Tests and validation (QA)
   - Unit tests for middleware with mocked DynamoDB and LLM responses.
   - Integration tests:
     - Simulate concurrent requests to the same user that approach/exceed budget to verify conditional update prevents overspend.
     - Verify cache hits return identical responses and S3 fallback works.
     - Load test to validate API Gateway throttle behavior and end-to-end system behavior.
   - Acceptance tests listed below.
   - Estimated time: 8-16 hours

8) Rollout strategy
   - Deploy to staging first.
   - Monitor metrics, especially BudgetDeniedCount and CacheHitRate.
   - Start with conservative budgets and longer TTLs in staging, then tighten for production.
   - For users with existing usage records, backfill their current day's usage if migrating to the new schema.

## Risks
- Race conditions causing budget overspend:
  - Mitigation: use DynamoDB conditional UpdateItem that atomically enforces budget constraints. Use composite PK (user_id + date) to avoid daily reset races.
- Clock skew and reset timing:
  - Use UTC dates consistently. For reset logic, using date as SK avoids needing reset_at field.
- DynamoDB conditional checks may generate throttling under heavy concurrent load:
  - Mitigation: on-demand capacity, exponential backoff in client, consider sharding or token-bucket at app layer if necessary.
- Cache stampede (many concurrent misses):
  - Mitigation: best-effort caching; optionally add a short-lived DynamoDB lock keyed by hash(sanitized_input + prompt_version) if needed.
- Privacy leakage by caching user private uploads:
  - Mitigation: default to not caching private content; require explicit opt-in flag and clear UI/terms; store privacy_scope in cache entry.
- Large responses exceeding DynamoDB item size:
  - Mitigation: store responses in S3 and reference from cache table.
- Incorrect cost estimates leading to unexpected denials or overspend:
  - Mitigation: conservative estimate policy (e.g., estimate = max_tokens + model overhead). Reconcile after call and emit overshoot metrics. Optionally allow small overshoot threshold.
- Operational complexity and alert fatigue:
  - Mitigation: tune alarms and thresholds before production.

## Dependencies
- AWS services:
  - API Gateway (usage plans, API keys)
  - DynamoDB (llm_usage)
  - OpenSearch Serverless (semantic cache)
  - S3 (optional for large cached responses)
  - CloudWatch (metrics, logs, alarms, dashboards)
  - IAM roles with least privilege for app to access DynamoDB/S3/CloudWatch
  - (Optional) Cognito or AuthN provider for user identity
- Application:
  - LLM provider client (OpenAI, Anthropic, etc.) and pricing/usage model to estimate tokens/cost
  - Application runtime (Lambda or container) with middleware support
- Infra tooling:
  - IaC (CloudFormation / Terraform / CDK) to provision DynamoDB tables, API Gateway usage plans, alarms, and IAM policies
- Observability:
- Logging library integrated with structured logs to capture cache_hit, similarity_score, cache_id, user_id (anonymized if needed), request_id
- Optional:
  - Secrets Manager or parameter store for API key mapping; PagerDuty/Slack for alerts

## Acceptance Criteria
- Rate limiting:
  - API Gateway usage plan rejects requests above configured throttle/quota with HTTP 429 and Retry-After header.
  - Demonstrated via load test: when exceeding throttle, API Gateway returns 429 for excess requests.
- Per-user budget enforcement:
  - A user attempting an action that would exceed their daily budget receives a clear budget-exceeded response:
    - HTTP 402 (Payment Required) with JSON { error: "budget_exceeded", message, remaining_budget, reset_at } OR documented alternative (HTTP 429) if chosen.
  - Conditional update logic prevents concurrent requests from causing spend above budget in tested concurrent scenarios.
  - Post-call reconciliation correctly records actual tokens/cost and metrics reflect true totals.
- Caching:
  - Cache hit rate is available in CloudWatch metrics (CacheHitCount, CacheMissCount, calculated CacheHitRate).
  - Repeated semantically similar /explain requests (same endpoint + prompt_version + tool_result_fingerprint with high similarity) yield cache hits and faster response times vs cold LLM calls.
  - Private uploads are not cached unless user explicitly opts in; opt-in requests are cached only if privacy_scope indicates consent.
  - Large responses are successfully stored in S3 and retrieved via cache entries when needed.
- Monitoring and alerts:
  - CloudWatch dashboard shows BudgetDeniedCount, CacheHitRate, CostPerRequest.
  - Alarm fires when BudgetDeniedCount exceeds configured threshold in given time window.
- Operational:
  - Logs include cache_id, cache hit/miss, similarity_score, user_id (or masked), estimated_cost, actual_cost, and request_id for traceability.
  - Documentation updated: API reference includes error shapes and guidance on budgets, caching opt-in, and rate limiting behavior.

## Outcomes
- Predictable spend controls with enforceable budgets and rate limits.
- Reduced latency/cost for repeated queries via semantic caching.
- Clear, machine-readable errors and metrics for operational oversight.

## Decisions
- **Budget enforcement**: DynamoDB conditional updates per user/day.
- **Rate limiting**: API Gateway usage plans per API key.
- **Caching**: OpenSearch Serverless semantic cache on sanitized inputs only.

## Deliverables
- llm_usage DynamoDB table and budget enforcement middleware.
- API Gateway usage plans + quotas configured per environment.
- Semantic cache index + S3 fallback for large responses.
- CloudWatch metrics and alerts for budget and cache behavior.

## Implementation tasks
Concrete task list (assignable, PR-sized items)
1. Create llm_usage DynamoDB table (owner: infra) — 0.5 day
2. Provision OpenSearch Serverless collection + vector index (owner: infra) — 0.5–1 day
3. Add API Gateway usage plans and map API keys (owner: infra) — 0.5 day
4. Implement budget middleware + reconciliation (owner: backend) — 1–2 days
5. Implement semantic cache with S3 fallback (owner: backend) — 1–2 days
6. Emit metrics + dashboards/alarms (owner: platform) — 0.5–1 day
7. Integration + concurrency tests (owner: QA) — 1 day

Notes / recommendations
- Prefer composite key (user_id + usage_date) for llm_usage to simplify resets and auditing. If you must keep a single-row-per-user model with reset_at, include a migration path and implement atomic reset logic (transactional or double-checked conditional writes).
- Default cache TTL: 24 hours for /explain (tune per use-case). Allow per-endpoint TTL override via configuration.
- Start with conservative budget enforcement (deny if estimated would exceed budget) and allow a "grace overshoot" policy if you want a smoother UX; ensure overshoots are visible in metrics and backfilled billing.
- Document precisely in your API docs which endpoints are cached and how to opt-in for private content caching.
