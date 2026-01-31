# Section
Guardrails (MVP): rate limits, per-user budgets, and ephemeral pgvector caching

## Summary
This MVP keeps guardrails small and demo-focused: (1) API-level rate limiting via API Gateway usage plans, (2) a budget cap in DynamoDB (single shared user, 15-minute window), (3) a **domain-only guardrail** that accepts coding, infrastructure as code, and CI/CD automation requests, and (4) an **ephemeral semantic cache** using pgvector running alongside the API in ECS. The cache is in-memory only (no persistence) so it is easy to explain and cheap to run while still showcasing semantic search.

Goals:
- Prevent runaway cost and abuse.
- Provide predictable latency and cost visibility.
- Demonstrate semantic search + caching in a cloud-native, DevOps-friendly way.
- Provide clear, machine-readable error responses when limits are hit.
Non-goals:
- No enterprise billing or invoicing system.
- No persistent vector store or cross-task cache consistency.
- No complex cache stampede protection or multi-tier plans.

## Design

High-level components
- API Gateway usage plan + per-API-key throttles.
- Lightweight middleware in the API service that:
  - resolves user identity,
  - enforces a per-user budget,
  - checks/updates the semantic cache,
  - records usage and emits metrics.
- DynamoDB table: `llm_usage` — per-user usage records.
- **ECS task with a pgvector container** running next to the API container (ephemeral cache).
- CloudWatch metrics and simple alarms.

Rate limiting (API Gateway)
- Single usage plan per environment:
  - Throttle: steady rate and burst.
- Example defaults (tunable):
  - Demo: 100 RPS, burst 200 (current Terraform defaults).
- API Gateway rejects overages with 429 + Retry-After.

Budget caps (MVP: single shared user, 15-minute window)
- **MVP choice:** no auth in demo, so all traffic is treated as a single shared user. Budget is enforced per 15-minute window to limit blast radius without user management.
- Table: `llm_usage`
  - Schema: PK `user_id`, SK `usage_window` (UTC window key, e.g., `2026-01-30T12:00Z` for 15-minute buckets).
  - Attributes: `tokens_used`, `last_updated_at`.
  - Access: one conditional `UpdateItem` that increments totals only if totals remain under a window cap.
- Middleware flow:
  - Use `user_id = "demo"` for all requests.
  - Estimate tokens from prompt size and `max_tokens`.
  - Conditional update: if over cap, return budget-exceeded error.
  - No reconciliation in MVP; keep it simple and document as future improvement.

Ephemeral semantic caching (pgvector in ECS)
- **Deployment model:** pgvector runs as a second container in the same ECS task definition as the API. This avoids extra networking and makes the cache accessible via `localhost`.
- **Persistence:** none. No EFS/EBS. Cache is reset on task restart or deploy.
- **Why this fits MVP:** shows real semantic search without standing up managed vector databases.
- **Bootstrap on API startup (implemented):**
  - API runs `CREATE EXTENSION vector`, creates `cache_entries`, and creates an HNSW index.
  - Intended for ephemeral cache; schema is rebuilt at task start.
- **Schema (implemented):**
  - `cache_entries(id uuid, embedding vector(256), response jsonb, created_at, expires_at)`
  - HNSW index on `embedding` for fast ANN search (small datasets only).
- **Embedding model (implemented):**
  - Bedrock `amazon.titan-embed-text-v2:0` with `dimensions=256` and `normalize=true`.
- **Cache key (implemented):**
  - `response`, `incident_frame.primary_error_signature`, `incident_frame.services`, `incident_frame.infra_components`.
  - Does **not** include conversation history.
- **Cache lookup flow (implemented):**
  - Sanitize key → embed → kNN lookup → accept if similarity >= 0.95 and `expires_at` > now.
  - Cache is only used for `/explain` (not `/triage`).
- **Cache write (implemented):**
  - Sanitize key → embed → store embedding + full response inline as JSONB.
- **Sanitization (implemented):**
  - Redacts emails, UUIDs, IPs, long hex strings, AWS access keys, bearer tokens, and common secret fields (password/token/api_key).
  - Normalizes whitespace.
- **Security note:** demo-only password in env vars; production would use Secrets Manager or RDS/Aurora.
- **Configuration (implemented via env vars):**
  - `PGVECTOR_ENABLED`, `PGVECTOR_HOST`, `PGVECTOR_PORT`
  - `PGVECTOR_DB`, `PGVECTOR_USER`, `PGVECTOR_PASSWORD`
  - `PGVECTOR_SIMILARITY_THRESHOLD`, `PGVECTOR_TTL_SECONDS`

Error response shapes
- Rate limit exceeded (API Gateway): HTTP 429, body:
  - { "error": "rate_limited", "message": "Rate limit exceeded", "retry_after": seconds }
- Budget exceeded (middleware): HTTP 402 (Payment Required) to signal budget:
  - { "error": "budget_exceeded", "message": "Daily budget exceeded", "remaining_budget": 0, "retry_after": "2026-01-29T00:00:00Z" }
- Budget denied (generic alternative): HTTP 429 if you prefer uniform 429s.

Monitoring & metrics
- CloudWatch metrics:
  - BudgetDeniedCount (planned; emit when wiring metrics)
  - CacheHitCount / CacheMissCount (emitted on /explain lookups)
  - TokensPerRequest
- Simple alarms:
  - BudgetDeniedCount spike (planned)
  - CacheHitRate drop

## Implementation Steps
Ordered actionable steps with notes for owners and priorities. Assume service code lives in repository "service" and uses AWS Lambda or a containerized application behind API Gateway.

1) Provision DynamoDB table (Infra — IaC) [implemented]
   - Create `llm_usage`:
     - Partition key: user_id (String)
     - Sort key: usage_window (String, 15-minute buckets)
     - BillingMode: PAY_PER_REQUEST (on-demand)
     - TTL: optional (retain 30-90 days if desired)
     - IAM role: grant app read/write access
   - Estimated time: 1-2 hours

2) Define API Gateway usage plan (Infra) [implemented]
   - Create one usage plan per environment.
   - Configure throttle (demo):
     - throttle=100 RPS, burst=200
   - Associate API keys to plan; ensure stage-level mapping.
   - Estimated time: 1-2 hours

3) Add pgvector cache container to ECS task (Infra) [implemented]
   - Reuse the existing ECS module and add an optional pgvector container next to the API.
   - Configure env vars (demo defaults):
     - POSTGRES_DB=troubleshooter_cache
     - POSTGRES_USER=postgres
     - POSTGRES_PASSWORD=postgres
   - Expose `5432` **only inside the task** (no public ingress).
   - Estimated time: 1-2 hours

4) Implement user identity resolution & API key mapping (Backend) [planned]
   - Middleware: resolve user_id from:
     - Authenticated JWT token subject (preferred)
     - API key mapping table for API Gateway keys (fallback for dev/demo)
     - For dev only: allow header X-Dev-User-Id when running in dev mode
   - Store mapping in a secure store with least privileges.
   - Estimated time: 2-4 hours

5) Implement per-request budget check middleware (Backend) [implemented]
   - Pseudocode:
     - estimated_tokens = estimate_from_request(req)
     - window = UTC 15-minute bucket key (e.g., YYYY-MM-DDTHH:MMZ)
     - Attempt conditional UpdateItem:
       - Key: { user_id: "demo", usage_window: window }
       - UpdateExpression: SET tokens_used = if_not_exists(tokens_used, :zero) + :est_tokens, last_updated_at = :now
       - ConditionExpression: tokens_used + :est_tokens <= :token_budget
       - ExpressionAttributeValues: provide :est_tokens, :token_budget
     - If ConditionalCheckFailed -> return HTTP 402 { error: "budget_exceeded" }
     - On success -> proceed to cache-check and LLM call
   - Concurrency: use a single conditional UpdateItem per request for atomicity.
   - Estimated time: 4-6 hours (implementation + tests)

6) Implement semantic cache flow (Backend) [implemented]
   - Use Bedrock embeddings (amazon.titan-embed-text-v2:0, 256 dims) and kNN lookup.
   - Threshold: 0.95 (configurable via env).
   - Cache only `/explain`; store full response JSONB.
   - Estimated time: 4-8 hours

7) Emit metrics and create dashboards & alarms (Infra + Backend) [partial]
   - Emit CloudWatch metrics at these points:
     - On budget deny: BudgetDeniedCount
     - After each request: TokensPerRequest
     - On cache hit/miss: CacheHitCount, CacheMissCount
   - Create a dashboard showing CacheHitRate, BudgetDenied trend, TokensPerRequest.
   - Create CloudWatch alarms:
     - BudgetDeniedCount > X in 5 minutes -> PagerDuty
     - CacheHitRate < threshold -> Slack alert
   - Estimated time: 2-4 hours

8) Tests and validation (QA) [planned]
   - Unit tests for middleware with mocked DynamoDB and LLM responses.
   - Integration tests:
     - Simulate concurrent requests to the same user that approach/exceed budget to verify conditional update prevents overspend.
     - Verify cache hits return identical responses.
     - Load test to validate API Gateway throttle behavior and end-to-end system behavior.
   - Estimated time: 6-10 hours

9) Rollout strategy
   - Deploy to staging first.
   - Monitor metrics, especially BudgetDeniedCount and CacheHitRate.
   - Start with conservative budgets and short TTLs in staging, then tune for production.

## Risks
- Race conditions causing budget overspend:
  - Mitigation: use DynamoDB conditional UpdateItem that atomically enforces budget constraints. Use composite PK (user_id + date) to avoid daily reset races.
- Clock skew and reset timing:
  - Use UTC windows consistently. For reset logic, using window key avoids needing reset_at field.
- DynamoDB conditional checks may generate throttling under heavy concurrent load:
  - Mitigation: on-demand capacity, exponential backoff in client, consider sharding or token-bucket at app layer if necessary.
- Privacy leakage by caching user private uploads:
  - Mitigation: default to not caching private content; require explicit opt-in flag and clear UI/terms; store privacy_scope in cache entry.
- Ephemeral cache resets:
  - Mitigation: document that cache is best-effort for MVP; rebuild via new requests.
- Operational complexity and alert fatigue:
  - Mitigation: tune alarms and thresholds before production.

## Rationale & future work
- **Why single shared user now:** the demo has no authentication, so per-user budgeting would be artificial. A shared 15-minute window cap is simple to explain and still prevents runaway cost.
- **Future work:** add auth (JWT/Cognito) and map budgets by user_id (or org_id). Replace the shared `demo` key with authenticated subject + daily budget rows, and optionally support plan tiers.
