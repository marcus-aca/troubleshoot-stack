# Section
Guardrails, rate limits, budgets, and caching

## Current implementation (source of truth)
- **Domain guardrail**: `/triage` rejects non-DevOps topics with a fixed response.
- **Citation enforcement**: hypotheses without valid evidence citations are downgraded.
- **Identifier redaction**: ARNs/account IDs are redacted in hypothesis text.
- **Input redaction**:
  - Client-side redaction in the frontend (regex-based).
  - Server-side redaction in the API before parsing/LLM calls.
- **Budgets**: DynamoDB-backed token budget window (`BUDGET_*` env vars). Requests over budget return HTTP 402.
- **Rate limiting**: API Gateway usage plans and API keys.
- **Caching**: optional pgvector cache for `/explain` using Bedrock embeddings; TTL-based eviction.

## Not implemented yet (by code)
- Per-tenant auth and quotas beyond API Gateway keys.
- Cross-session cache invalidation strategies.
