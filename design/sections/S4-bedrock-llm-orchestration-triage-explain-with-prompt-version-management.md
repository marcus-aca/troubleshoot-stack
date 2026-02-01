# Section
LLM orchestration: triage + explain (current implementation)

## Current implementation (source of truth)
- **Prompt registry**: maps endpoint -> prompt version/file.
  - `triage` -> v3 (`services/api/prompts/v3/triage/triage.md`)
  - `explain` -> v2 (`services/api/prompts/v2/explain/explain.md`)
- **Adapters**:
  - Bedrock when `LLM_MODE=bedrock`.
  - Stub mode by default for local/dev.
- **JSON enforcement**: LLM responses are parsed with `extract_json` and validated against pydantic schemas.
- **Guardrails**:
  - Hypotheses require citations from `evidence_map`; missing citations reduce confidence and annotate the explanation.
  - ARN/account identifiers in hypothesis text are redacted and confidence reduced.
- **Tool calls**: only the first tool call is surfaced; if a tool call exists, `completion_state` is forced to `needs_input`.
- **Metrics**: optional CloudWatch metrics for LLM latency, tokens, and guardrail counts.

## Not implemented yet (by code)
- Retries/backoff or circuit breakers around LLM calls.
- Explicit tool execution pipeline.
- OpenTelemetry tracing spans.
