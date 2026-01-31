# Section
Bedrock LLM orchestration (triage + explain) with prompt/version management

## Summary
Implement an orchestration layer that uses Bedrock LLMs to perform state-driven troubleshooting flows grounded in user-provided logs and tool outputs:
1) Triage: consume the incident frame from the parser (S3) and classify the failure, propose hypotheses, and recommend tool calls.
2) Explain: use the incident frame, extracted log signals, and tool results to respond to the *latest* user response with context-aware hypotheses and citations (avoid repeating the initial triage unless explicitly asked). Ask one question or request one tool command at a time until the context is sufficient.

Key non-functional goals:
- Deterministic, JSON-first outputs to reduce parsing errors.
- Prompt versioning stored in repo and surfaced in responses/logs.
- Minimal but auditable model usage (model_id, token usage).
- Strong guardrails: require citations for claims; never invent account-specific identifiers.

Primary deliverables:
- Two HTTP endpoints: POST /triage and POST /explain with documented schemas; both accept a `conversation_id` to preserve multi-turn context and return `assistant_message`, `completion_state`, and optional `next_question`/`tool_calls`.
- Prompt/version registry and file layout in repo.
- LLM client wrapper with retries, backoff, token/cost estimation, tracing.
- Validators (Pydantic) for inbound requests and LLM outputs.
- Tests, monitoring, and rollout plan.

## Design
High-level architecture
- API layer: exposes /triage and /explain endpoints, validates input, loads conversation context, orchestrates parsing + tool calls and LLM calls, persists structured responses internally, and returns chat responses to the frontend.
- Prompt registry: versioned prompt files in repo (e.g., /services/api/prompts/v1/{endpoint}/{prompt-name}.md), and a lightweight runtime registry mapping endpoint -> prompt_version (and optionally prompt filename).
- LLM Adapter: Bedrock client wrapper providing:
  - generate(model_id, prompt, options) — with retries/backoff, token usage estimation and logging.
  - consistent error handling and exceptions.
- Tools:
  - Tool adapters for common calls (e.g., CloudWatch logs fetch, Terraform state query, K8s API/query).
  - Conversation state store (DynamoDB or Redis) maintains prior user inputs, extracted signals, and selected hypotheses between turns.
- Observability:
  - Structured logs include prompt_version, model_id, token counts, request_id, and triage/explain frame.
  - Tracing spans: bedrock_generate, tool_call.
  - Metrics: LLM latency, error rates, token usage by model.

## Implemented (repo)
- Structured JSON logs emitted for triage/explain requests and LLM calls (request_id, conversation_id, prompt_version, model_id, token usage, guardrail counts).
- CloudWatch metrics emission for LLM requests, latency, tokens, errors, and guardrail counters (optional via `CW_METRICS_ENABLED=true`, namespace `CW_METRICS_NAMESPACE`).
- LLM call timing captured in the Bedrock adapter and surfaced in logs/metrics.
- JSON parse/validation failures log a sanitized output preview and return HTTP 502 (no retry).

Data flow (per request)
1. API validates input (Pydantic).
2. For /triage:
   - Parse logs into incident frame (ParserAdapter, S3).
   - Load triage prompt (from registry).
   - Call LLM to classify and propose hypotheses + tool calls (JSON schema).
   - Validate response; store conversation summary + extracted entities; return to caller.
3. For /explain:
   - Accept triage frame + user-provided tool outputs (`tool_results`) or follow-up answers.
   - Merge with conversation context (prior logs/trace stack, user confirmations, previous hypotheses).
  - Load explain prompt (from registry) focused on answering the latest response and requesting one next step if needed.
   - Call LLM to generate structured troubleshoot result (JSON).
   - Validate, attach citations to log lines/tool outputs, compute confidence scores.
   - Return structured JSON plus conversational message.

Prompt/versioning rules
- Each prompt file contains a header with: prompt_version, schema_version, designed_for_endpoint, created_by, created_at, changelog.
- Runtime registry maps endpoint -> prompt_version and prompt file path. The endpoint uses exact prompt_version; fallback behavior: explicit error if requested prompt_version missing (no silent auto-upgrade).
- Each API response includes prompt_version and prompt_filename used.

Output schemas (examples)
- TriageResult (subset of canonical response):
  - category: enum {terraform, eks, alb, iam, other}
  - assistant_message, completion_state, next_question?, tool_calls[]
  - hypotheses: list of {id, rank, confidence, explanation, citations[]}
  - fix_steps[]
  - prompt_version, model_id, token_usage, request_id, conversation_id
- ExplainResult (canonical response shape):
  - assistant_message, completion_state, next_question?, tool_calls[]
  - hypotheses: list of {id, rank, confidence, explanation, citations[]}
  - fix_steps[]
  - prompt_version, model_id, token_usage, request_id, conversation_id
  - citations include line ranges plus an excerpt for display

Guardrails and generation rules
- System and prompt templates encode that every specific infrastructure claim (resource name, ARN, account ID, exact IP, etc.) must be backed by a citation from log lines or tool outputs.
- If the model produces a claim without available citations, the response must explicitly mark "No citation found" and reduce confidence (e.g., confidence <= 0.3) and mark as hypothesis_only.
- The service rejects outputs that contain newly invented ARNs or account IDs; such outputs are normalized to redacted and flagged.
- Require citations for each hypothesis and each specificity claim (per the earlier guardrail list).

Security and privacy
- Redact secrets before sending to LLMs.
- Do not include PII/account-specific secrets in prompts or tool outputs.
- Limit context windows: truncate long logs to most relevant sections using parser heuristics.

Operational constraints
- Default single reasoning-capable Bedrock model for generation to simplify deterministic behavior.
- Log model_id and token usage per request.
- Implement cost-estimation and rate limits per tenant.

## Implementation Steps
Phase 0 — Design and scaffolding (2–3 days)
- Task 0.1: Finalize JSON schemas (Pydantic) for TriageFrame and ExplainResult. Owner: Backend engineer.
- Task 0.2: Define prompt file header format and registry structure. Owner: Tech lead.

Phase 1 — LLM client & prompt registry (3–5 days)
- Task 1.1: Implement BedrockAdapter (LLM client wrapper).
  - Features: retries with exponential backoff and jitter, timeout config, standardized exceptions, token estimation, and logging/tracing instrumentation (OpenTelemetry spans: bedrock_generate).
- Task 1.2: Implement prompt registry loader that reads versioned prompt files and validates header.

Phase 2 — API endpoints and validators (3–5 days)
- Task 2.1: Create /triage endpoint implementation (deterministic settings, JSON validation).
- Task 2.2: Create /explain endpoint implementation (tool calls optional, citations required).
- Task 2.3: Implement JSON-first formatting and a strict JSON extractor.

Phase 3 — Tools integration (4–7 days)
- Task 3.1: Implement minimal tool adapters most likely required: CloudWatch logs fetcher, k8s resource fetcher, terraform state query.
- Task 3.2: Wire tool outputs into /explain flow, and require citations be mapped to source identifiers returned to caller.

Phase 4 — Observability, cost tracking, guardrails enforcement (2–4 days)
- Task 4.1: Add tracing spans and structured logs for request lifecycle, prompt_version, model_id, token usage, and errors.
- Task 4.2: Implement token/cost estimation and a threshold-based abort or warning.
- Task 4.3: Implement output guardrails enforcement (ARN/account detection, citation completeness checks).

Phase 5 — Testing, QA, and rollout (3–5 days)
- Task 5.1: End-to-end tests covering typical log inputs and edge cases.
- Task 5.2: Load tests for LLM adapter and endpoints.
- Task 5.3: Staging rollout with canary (10% traffic) and health thresholds (error rate, latency, citation completeness).

## Risks
1. Hallucination (invented details)
   - Mitigation: strict citation requirement; validators that detect ARNs/account-like patterns; redact and downgrade confidence on missing citations.
2. Parsing failures / inconsistent JSON
   - Mitigation: JSON-first prompts, robust extractor, deterministic post-processing, unit tests and golden examples.
3. Token/cost overruns
   - Mitigation: cost estimation, throttling, maximum tokens per request, warn/abort flows.
4. Prompt drift and inconsistent upgrades
   - Mitigation: prompt_version in repo, CI checks, registry mapping, required changelog and review for prompt changes, canary deployments for new prompts.
5. Latency from long LLM calls
   - Mitigation: sensible timeouts, alternative fast model fallback with reduced functionality.
6. Data leakage / sensitive data exposure
   - Mitigation: redaction pipeline, strict input validators, do-not-send lists, logs sanitized.
7. Tool adapter downtime
   - Mitigation: degrade gracefully (return triage-only response), cache last-known-good tool results, circuit breakers.

## Dependencies
- Amazon Bedrock API access and stable model selection (reasoning-capable model).
- Tools/APIs for telemetry and data retrievals (CloudWatch, K8s API, Terraform state backend).
- Observability stack (OpenTelemetry, logging backend, metrics).
- Git repo to store versioned prompts and registry (CI integration).
- Secrets management for Bedrock credentials and tool credentials.
- Engineers: 1 tech lead, 2 backend engineers, 1 SRE for rollout/monitoring.

## Acceptance Criteria
- Functional
  - POST /triage and POST /explain accept and return JSON matching the Pydantic schemas and JSON Schema exports.
  - Every response includes fields: prompt_version, prompt_filename (or registry key), model_id, token_usage, and assistant_message.
  - For triage results: category is one of the allowed enums, entities list present, recommended_tool_calls formatted and actionable.
  - For explain results: hypotheses are ranked, each hypothesis includes confidence (0.0–1.0) and citations array. If any hypothesis lacks citation, it must be annotated citation_missing and have confidence <= 0.3.
- Quality
  - >= 95% of golden test cases produce valid JSON outputs without parsing errors.
  - <= 5% of production responses contain invented ARNs/account IDs (goal: 0; any violation triggers immediate investigation).
  - Citation completeness: >= 95% of top-1 hypotheses reference at least one log line or tool result.
- Observability and auditing
  - Every request logged with request_id, prompt_version, model_id, token counts, and top-level success/failure reason.
  - Tracing spans for bedrock_generate and tool_call present in traces.
- Performance
  - 95th-percentile latency for /triage under N ms (set target per infra; example: <1.5s for triage), /explain under M ms (example: <3.0s) — adjust to agreed SLOs.
- Security & Compliance
  - No sensitive secrets are sent to the LLM in any tested flows.
  - Prompt CI prevents merging prompts without required headers.

## Outcomes
- Deterministic LLM orchestration for triage and explain flows with strict JSON validation.
- Prompt/version management that is auditable and reproducible.
- Canonical response output aligned with S1 schemas and evaluation harnesses.

## Decisions
- **Parser-first**: incident frame comes from ParserAdapter (S3) before LLM classification.
- **Prompt registry**: prompts versioned in-repo; endpoints pin exact prompt_version.
- **Guardrails**: citations required for concrete claims; invented identifiers rejected or redacted.

## Deliverables
- Prompt registry layout and versioned prompt files under /services/api/prompts.
- BedrockAdapter with retries, logging, and tracing.
- /triage and /explain endpoints wired to parser, tools, and response builder.
- JSON schema exports for triage result and canonical explain response.
- Tests for JSON validity, citation enforcement, and prompt registry rules.

## Implementation tasks
Concrete task list (assignable, PR-sized items)
1. Prompt header format + registry loader (owner: tech lead) — 0.5–1 day
2. BedrockAdapter with retries/backoff + tracing (owner: backend) — 1–2 days
3. /triage endpoint wiring (parser + LLM + validation) — 1–2 days
4. /explain endpoint wiring (tools + LLM + canonical response) — 1–2 days
5. Guardrails enforcement (ARN/account detection + citation checks) — 0.5–1 day
6. Golden tests + JSON schema validation (owner: ML/backend) — 1–2 days
