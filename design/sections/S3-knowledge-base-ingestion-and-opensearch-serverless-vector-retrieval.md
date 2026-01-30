# Section
Log parsing and normalization (non-RAG)

## Summary
Note: OpenSearch Serverless is not used in the MVP parser flow. This section focuses on rule-first log parsing and evidence extraction.
Build a reliable parser that turns pasted logs/trace stacks into a structured debug frame used by triage and explanation. This replaces knowledge-base ingestion and vector retrieval for the MVP. The system stays grounded in user-provided evidence plus optional tool outputs and aligns with S1 adapters and canonical response expectations.

## Design
Goals
- Normalize raw logs into structured fields (timestamps, service, environment, severity, error signatures, request ids).
- Extract entities and hints (region, account, cluster, ALB target group, IAM role, Terraform resource, etc.).
- Support deterministic citations back to log line ranges and tool outputs.
- Preserve a minimal, schema-valid frame even when parsing fails.
Non-goals
- No vector knowledge base ingestion or retrieval for MVP.
- No cross-customer log correlation or long-term log analytics.

Inputs
- Raw text pasted into the UI or API payload.

Outputs
- Incident frame object with:
  - primary_error_signature
  - secondary_signatures[]
  - time_window
  - services[]
  - infra_components[]
  - suspected_failure_domain
  - evidence_map[] (line ranges, file ids, tool output ids)
  - parse_confidence
  - parser_version

Parser strategy
- Rule-first parsing for common platforms (Terraform, EKS, ALB, IAM, EC2, CloudWatch).
- Fallback to regex + heuristic extraction for unknown logs.
- Keep raw text with line numbers to support deterministic citations.
- Validate parser output against a schema; if parsing fails, return a minimal frame with raw text and "unknown" fields.

API integration
- /triage calls ParserAdapter.parse(raw_log) before classification.
- /explain receives the incident frame, selected hypotheses, and cited evidence.

Storage and citation map
- Store raw input with line numbers in DynamoDB (inputs table + TTL) so citations can reference stable line ranges.
- Evidence map links to log line ranges and tool output ids for traceability in responses.
- Persist incident frames and canonical responses in a **conversation events** table (PK `conversation_id`, SK `event_id`) so multi-turn context can be reconstructed deterministically.
- Maintain a **conversation state** table with the latest incident frame + response summary for quick LLM context assembly.
- On each turn:
  - Write raw input + incident frame + canonical response to the events table.
  - Update the state table with the latest incident frame + response summary.

Incident frame schema (draft)
- root: {frame_id, conversation_id, request_id, source, parser_version, parse_confidence, created_at}
- signatures: {primary_error_signature, secondary_signatures[]}
- context: {time_window, services[], infra_components[], suspected_failure_domain, environment, region, account_id}
- entities: {cluster, namespace, node, pod, alb_target_group, iam_role, terraform_resource, request_ids[]}
- evidence_map[]: {source_type: log|tool, source_id, line_start, line_end, excerpt_hash}

## Implementation Steps
Phase 1 — Schema and interfaces (1–2 days)
- Define incident frame schema (pydantic + JSON schema) aligned with S1 canonical response expectations.
- Add ParserAdapter interface and stub implementation in /services/api.

Phase 2 — Core parsing and evidence (2–4 days)
- Implement line numbering + normalization (preserve raw lines, compute excerpt hashes).
- Add platform-specific parsers (Terraform, EKS, ALB, IAM, EC2, CloudWatch).
- Implement evidence map generation for citations and tool outputs.
- Return minimal schema-valid frame on parse failure with parse_confidence < 0.3.
- Persist parser outputs into conversation events/state so downstream LLM calls can aggregate across turns.

Phase 3 — Tests and fixtures (2–3 days)
- Add parser unit tests with fixture logs.
- Add golden tests to ensure stable parsing output for known logs.
- Add schema validation tests for malformed inputs.

## Risks
- Parser misses key fields → mitigate with fallbacks and confidence flags.
- Over-parsing leads to false hints → include confidence scores per field and allow "unknown".
- Logs include sensitive data → ensure redaction in the ingestion flow before parsing.
- Citation drift if raw lines change → store raw line-numbered input keyed by request_id.

## Dependencies
- Pydantic, regex, and a small ruleset per platform.
- Fixture set of logs for each supported system.
- DynamoDB table for raw inputs with TTL (defined in S1/S2).

## Acceptance Criteria
- Given a set of fixture logs, the parser outputs a valid incident frame with correct primary_error_signature.
- Evidence map links to line ranges for at least one cited item per fixture.
- Parser emits structured logs with parse_time_ms and parse_confidence.
- /triage can attach incident frame metadata to responses without schema violations.

## Outcomes
- Reliable log normalization pipeline feeding /triage and /explain.
- Deterministic citations that map to raw log lines or tool outputs.
- Stable incident frame schema for evaluation fixtures.

## Decisions
- **No KB ingestion for MVP**: rely on user logs + tool outputs only.
- **Rule-first parsing**: deterministic extraction over LLM-only parsing.
- **Storage**: raw inputs stored in DynamoDB with TTL for evidence citations.

## Deliverables
- ParserAdapter implementation and unit tests.
- Incident frame schema docs and example payloads.
- Fixture log set for at least 5 platforms.
- Evidence map generation utilities and schema validation tests.

## Implementation tasks
Concrete task list (assignable, PR-sized items)
1. Incident frame schema + JSON Schema (owner: backend/ML) — 0.5–1 day
2. ParserAdapter interface + stub (owner: backend) — 0.5 day
3. Line numbering + normalization utilities (owner: backend) — 0.5–1 day
4. Platform parsers: Terraform, EKS, ALB, IAM (owner: ML) — 1–2 days
5. Evidence map generator (owner: backend/ML) — 0.5–1 day
6. Fixtures + golden tests (owner: ML) — 1–2 days
