# Section
Delivery plan and milestones (2–4 week MVP)

## Goal
Deliver a 2–4 week MVP for an interactive troubleshooting assistant that processes pasted logs/trace stacks, maintains conversation context across turns, and runs an LLM-based triage and explanation flow via two endpoints (/triage, /explain), with basic operational and security controls, a minimal frontend, and an evaluation harness.

## MVP scope
- End-to-end flow from log/trace stack paste → parsing → /triage and /explain responses with citations to log lines and tool outputs.
- Secure upload + redaction for optional attachments.
- Basic tool integrations (CloudWatch logs fetch, terraform state query, k8s resource fetch).
- Guardrails: rate limiting, per-user budgets, caching.
- Observability: structured logs, traces, basic dashboards.

## Non-goals for MVP
- Knowledge base ingestion or vector retrieval.
- Document embedding pipelines.
- Automated runbook ingestion.

## Milestones
Week 1 (Foundation)
- Repo scaffolding, CI, OpenAPI skeleton, and schemas.
- ParserAdapter for log parsing + incident frame schema.
- Basic /triage endpoint with deterministic prompts.

Week 2 (Core flow)
- /explain endpoint wired to prompts and citations (log lines + tool outputs).
- Prompt registry and versioning.
- ToolAdapter stubs + initial integrations (CloudWatch, k8s, Terraform).

Week 3 (Quality & safety)
- Redaction pipeline + secure upload flow.
- Guardrails: rate limits, budgets, caching.
- Eval harness with 30–50 cases and smoke subset.

Week 4 (Polish & demo)
- Frontend MVP (paste logs, view outputs, copy steps).
- Observability dashboards + alerting basics.
- Demo prep with 2–3 curated scenarios.

## Work breakdown (key deliverables)
- Parser + incident frame schema with fixtures.
- Bedrock adapter + prompt registry.
- /triage and /explain endpoints with citations.
- Tool integrations (CloudWatch, Terraform state, k8s).
- Redaction + secure uploads with TTL.
- Rate limiting + budget enforcement + caching.
- Evaluation harness + nightly job.
- Minimal React app for interactive troubleshooting.
- Dashboards and logs/traces.

## Dependencies
- Bedrock model access and credentials.
- CloudWatch, K8s API, Terraform state access for tools.
- CI runner with secrets for eval endpoints.

## Risks and mitigations
1. Hallucinations without external KB grounding
   - Mitigation: strict citation requirements to log lines/tool outputs, low-confidence flags when evidence is thin.
2. Tool integration delays
   - Mitigation: start with stubs and progressively enable tools; ensure /explain works with no tools.
3. Log parsing brittleness
   - Mitigation: fallback parser and confidence scoring; add fixture-driven tests.
4. Cost and latency
   - Mitigation: budgets, caching, prompt/token limits, and timeouts.

## Demo checklist
- Paste a Terraform lock error → ranked hypotheses + cited log lines + fix steps.
- Paste EKS Pending pods error → suggested kubectl checks + tool outputs cited.
- Show request_id trace from UI → logs/traces in dashboard.

## Acceptance Criteria
- /triage and /explain return structured responses with citations to log lines/tool outputs.
- Parser produces valid incident frames for at least 5 fixture logs.
- Tool integrations return mocked results in local dev and real data in staging.
- Frontend can paste logs, view results, and copy runbook steps.
- Eval harness runs nightly and gates regressions.
