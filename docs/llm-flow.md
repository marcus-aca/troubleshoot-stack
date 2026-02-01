# LLM Orchestration Flow (current implementation)

## High-level flow
```
Raw logs / user input
        |
        v
RuleBasedLogParser
  - NormalizedLog
  - Family parser (Terraform/CloudWatch/Python/Generic)
        |
        v
IncidentFrame (evidence_map + signatures + domain hints)
        |
        v
Storage (save input/frame + compact context)
        |
        v
PromptRegistry + Orchestrator
  - triage: v3 prompt
  - explain: v2 prompt
        |
        v
LLM Adapter
  - Bedrock (LLM_MODE=bedrock)
  - Stub (LLM_MODE=stub, default)
        |
        v
LLM JSON Output (TriageLLMOutput / ExplainLLMOutput)
        |
        v
Guardrails
  - enforce citations against evidence_map
  - redact ARNs/account IDs in hypothesis text
        |
        v
CanonicalResponse
```

## Explain request behavior
- `/explain` requires a `conversation_id`.
- If `incident_frame` is omitted, the API reuses the latest frame from conversation state.
- If there is no prior state, the API returns a `needs_input` response asking for the raw log or trace.
- `tool_results` (if provided) are appended to the user input before the LLM call.

## Caching
- `/explain` responses can be cached via `PgVectorCache` when `PGVECTOR_ENABLED=true`.
- Cache keys include the response text plus primary error signature and detected services/infra components.
- Cache metadata is surfaced in response `metadata.cache_hit` and `metadata.cache_similarity`.

## Guardrails (current)
- Hypotheses must cite evidence map entries; missing citations reduce confidence and annotate the explanation.
- ARNs and account IDs are redacted in hypothesis explanations, further reducing confidence.
- Tool calls are limited to one per response; if a tool call is returned with `completion_state=final`, it is downgraded to `needs_input`.
- A domain-restriction guardrail is enforced in `/triage` (non-DevOps requests return a fixed response).

## Response metadata (selected fields)
- `prompt_version`, `prompt_filename`, `model_id`, `token_usage`
- `guardrails` (citation_missing_count, redactions)
- `cache_hit`, `cache_similarity`
- `guardrail_hits_session`, `client_redaction_hits`, `backend_redaction_hits`
- `cost_estimate_usd` (derived from token usage)
