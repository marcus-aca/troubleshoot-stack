# Section
Architecture, requirements, and repo setup

## Summary
Provide a concrete, actionable plan to initialize the project repository, define the minimal viable API surface, and establish infra + CI guardrails so engineering can iterate quickly on model, log parsing, tools, and evaluation work. Key objectives:
- Choose and document runtime and libraries (recommendation: Python + FastAPI).
- Deliver stable API contracts for `/triage`, `/explain`, `/status`, plus conversation context handling.
- Create repo skeleton with CI, formatting, linting, and an IaC layout using Terraform.
- Produce an OpenAPI draft and canonical response schema for evaluation and integration tests.
- Establish request-id propagation, logging, and minimal auth (API key).
- Finalize architecture decisions: API Gateway → ECS Fargate in `us-west-2`, DynamoDB session storage, and semantic caching via OpenSearch Serverless.

Target audience: backend engineers, infra engineer, and ML engineer starting tool/eval integration.

## Design
High-level architecture
- Runtime: Python 3.11, FastAPI for the API service. Rationale: fast iteration for LLM/eval, good async support, simple OpenAPI generation.
- Services layout:
  - /infra/terraform — Terraform modules
  - /services/api — FastAPI service: endpoints, model + tool adapters, log parsing hooks
  - /services/web — (placeholder) frontend skeleton
  - /eval — eval datasets, runners, and baseline eval scripts
- Deployment target:
  - Single region `us-west-2`, single-tenant API Gateway in front of compute. Recommended compute is ECS/Fargate for containerized FastAPI. Lambda remains an optional alternative for lower-volume or lightweight endpoints. Infra should be abstracted so runtime details can change.
- Auth:
  - API key header (`Authorization: ApiKey <key>` or `x-api-key`) for MVP with usage plans. Plan for pluggable auth so switching to Cognito/Okta later is simple.
- Observability:
  - Automatic `x-request-id` header propagation, structured JSON logs, and metrics hooks for latency and error rate.
- Data flow (request -> response):
  - Request arrives with error logs/trace stack -> auth -> request-id assigned if missing -> input validated -> conversation context loaded -> log parsing + triage pipeline invoked -> optional tool calls -> model scoring -> canonical response assembled -> response returned with request-id and trace headers -> logs emitted. Updated context stored for next turn.
- Evidence storage:
  - Store raw user inputs keyed by session UUID in DynamoDB with a short TTL. Store parsed incident frames as derived artifacts in the same table or a sibling table to support citations back to log lines and tool outputs.
- Caching:
  - Semantic cache of sanitized input stored in OpenSearch Serverless (vector index). Cache adapter uses embeddings of sanitized input + prompt version to retrieve semantically similar prior responses with TTL metadata.

Canonical API contracts (high level)
- /triage: analyze an incoming error log or trace stack with optional context, return candidate hypotheses and recommended runbook steps and fixes.
- /explain: given a hypothesis id, trace, or follow-up question with prior context, return an explanation with citations and confidence.
- /status: health and readiness for service + dependency checks.
- Context handling: include `conversation_id` in requests to maintain multi-turn troubleshooting state (stored server-side or via signed context token).

Canonical response schema (full definition in Deliverables; see Implementation Steps for required keys)
- Root fields include `request_id`, `timestamp`, `hypotheses[]`, `runbook_steps[]`, `proposed_fix`, `risk_notes`, `rollback`, `next_checks`, `metadata`.

Non-functional requirements
- CI enforces lint, formatting, type checks, unit tests.
- OpenAPI spec must validate against example requests and responses.
- PR checks must pass before merge: tests, lint, tfmt.

## Implementation Steps
Order tasks to produce a working MVP in 2–4 sprints. Provide owners and suggested estimates (small team: 2–4 engineers).

Phase 0 — Repo and governance (1–2 days)
- Create repo skeleton:
  - Top-level directories: infra/, services/api/, services/web/, eval/, docs/.
  - Add README.md, CONTRIBUTING.md, CODEOWNERS, ISSUE_TEMPLATE.md, PR_TEMPLATE.md.
  - Add .gitignore, .gitattributes.
- Initialize Python project in services/api:
  - Use Poetry (recommended) or pip-tools and virtualenv. Include pyproject.toml with dependencies.
  - Required packages: fastapi, uvicorn[standard], pydantic, pytest, pytest-asyncio, httpx, black, isort, flake8, mypy, types-requests, boto3, opensearch-py, sqlalchemy or a minimal DB adapter if needed.
  - Add pre-commit hooks (black, isort, ruff/flake8).

Phase 1 — API surface + schemas (2–4 days)
- Design OpenAPI skeleton:
  - /triage POST (accepts error logs/trace stack + optional context and conversation_id)
  - /explain POST (accepts follow-up questions + conversation_id)
  - /status GET
- Implement pydantic schemas for request and canonical response. Minimal example fields:
  - request: {id?, source, payload, timestamp, context?, conversation_id?, prior_messages?}
  - response: {request_id, timestamp, hypotheses[], runbook_steps[], proposed_fix, risk_notes[], rollback[], next_checks[], metadata, conversation_id}
- Ensure automatic generation of OpenAPI via FastAPI; commit an OpenAPI JSON/YAML to /docs/openapi.json for review.
- Add example cassettes: sample requests and expected responses (for tests and OpenAPI validation).

Phase 2 — Core service plumbing (3–7 days)
- Implement FastAPI app, router for endpoints, and middleware:
  - Request ID middleware (header `x-request-id`): if absent generate a UUID4, attach to request.state and response headers.
  - Logging middleware that logs request_id, endpoint, duration, status code, and errors.
  - Auth dependency to validate API keys against a small secrets store (e.g., env var map or secrets manager).
  - Conversation context middleware or helper to load/store prior context (DynamoDB).
- Implement adapter interfaces:
  - ModelAdapter: predict(hypotheses) -> scores, explanation text
  - ToolAdapter: run(tool_call) -> tool_result
  - ParserAdapter: parse(raw_log) -> incident_frame
  - CacheAdapter: semantic get/set with vector similarity + TTL metadata
- Add placeholder implementations for adapters (local stub) and wiring for later replacement with real LLM and tool integrations.

Phase 3 — Schema-driven responses & examples (2–4 days)
- Implement canonical response builder that enforces schema and includes:
  - hypotheses[]: list of objects {id, rank (int), confidence (0-1 float), explanation (text), citations[]}
  - runbook_steps[]: ordered list {step_number, description, command_or_console_path, estimated_time_mins}
  - proposed_fix: code/patch snippets or config changes (plain text + language tag)
  - risk_notes[]: list of strings
  - rollback[]: list of steps for rollback
  - next_checks[]: list of follow-up checks with triggers and metrics
  - metadata: model_version, tool_versions, cache_hit, latency_ms
- Provide JSON Schema (or pydantic models) and attach example instances under /docs/examples/.

Phase 4 — CI, linting, and infra baseline (2–3 days)
- GitHub Actions workflows:
  - lint-and-test.yml: run formatting (black --check), isort check, ruff/flake8, mypy, pytest (unit tests).
  - infra-validate.yml: run terraform fmt -check and terraform validate in /infra/terraform.
- Add terraform skeleton:
  - /infra/terraform/modules/{network,service,iam}
  - README describing `terraform init`, `terraform plan -var-file=dev.tfvars`.
- Add CI job to validate OpenAPI: use openapi-cli or prism to validate examples against spec.

Phase 5 — Integration & example pipeline (3–7 days)
- Wire a demonstration triage flow using stub tools + a simple scoring model:
  - Hard-code a few error patterns and expected outcomes in /eval/fixtures.
  - Implement a runner script in /eval to call /triage with sample events and assert expected fields.
- Add unit tests for middleware, schema validation, and adapters.
- Add end-to-end integration test that starts the FastAPI app via TestClient and validates the OpenAPI contract with example responses.

Phase 6 — Documentation & ADRs (1–2 days)
- Produce ADRs in /docs/adrs:
  - model-choice.md
  - tooling-strategy.md
  - caching.md
  - budget-enforcement.md
- Document how to swap adapters (ModelAdapter/ToolAdapter/ParserAdapter) and versioning policy for models and tools.

Operational details (small, actionable items)
- Request-id: header name `x-request-id`; generate UUID4 when absent; echo back in `X-Request-Id` response header. Persist in logs as `request_id`.
- Error format: follow RFC 7807 (Problem Details) with `type`, `title`, `status`, `detail`, `instance` = request_id.
- OpenAPI publishing: commit auto-generated openapi.json to /docs/openapi.json and optionally serve at /docs (FastAPI) in non-prod.

## Risks
- Model & tool iteration: choice of model or tool may require refactor of adapters — mitigate by designing thin, well-documented interfaces and writing integration tests for the adapters.
- Cost runaway: LLM usage can explode. Mitigations:
  - Budget-enforcement ADR + throttling and usage quotas in gateway.
  - Mock mode for local dev and tests.
  - Sampling + temperature defaults and max tokens per request in configuration.
- Data leakage / PII in logs or returned citations: redact sensitive fields before logging or returning. Add a data-sanitization step to pipeline.
- Infra complexity: starting with Terraform and multiple modules may slow first delivery. Mitigate by providing a minimal terraform that provisions no-live resources (plan-only) and keep actual cloud deployment optional for MVP.
- Security: API key in headers is simplistic; plan to rotate keys and add credential store. Use HTTPS enforced by gateway.
- Schema drift: as models evolve, response shape may change. Mitigate by semantic versioning of API and model_version in metadata, with backward-compatible defaults.
- Single point of failure: single-region, single-replica MVP may be fragile; capture this in runbook and acceptance criteria.

## Dependencies
- Team: 1 backend engineer (FastAPI + infra), 1 infra engineer (Terraform/CICD), 1 ML engineer (model + tooling), reviewer for ADRs.
- External services (optional for MVP):
  - OpenSearch Serverless (vector index) for semantic cache of sanitized inputs.
  - Secrets manager (e.g., AWS Secrets Manager) for production API keys; env vars for dev.
- Tools and SDKs:
  - Python 3.11, Poetry, GitHub Actions, Terraform >= 1.4, OpenAPI validator (openapi-cli/prism), Docker (for containerization).
- Third-party risk: LLM provider (OpenAI, Anthropic, etc.) — plan for pluggable provider adapter.

## Acceptance Criteria
(Consolidated and actionable — must be testable)
- OpenAPI:
  - An OpenAPI JSON/YAML exists at /docs/openapi.json and validates against example request/response pairs using an openapi validator in CI.
  - The OpenAPI includes `/triage` (POST), `/explain` (POST), and `/status` (GET) with request and response schemas matching the canonical schema.
- API functionality:
  - /status returns 200 and includes a `dependencies` list indicating the health of mocked services (cache, parser, tools, model).
  - /triage accepts the canonical request and returns the canonical response shape with `request_id`, `hypotheses[]`, and at least one `runbook_steps[]`.
  - /explain returns an explanation with at least one citation and confidence score for a sample input.
- CI:
  - GitHub Actions pipeline runs on PRs and fails on formatting (black), lint (ruff/flake8), type checks (mypy), and pytest unit tests.
  - Terraform formatting/validation step runs on the infra folder and passes (or is included but non-blocking until infra is complete).
- Tests:
  - Unit tests cover middleware (request-id generation), schema validation, and one adapter stub.
  - At least one end-to-end integration test using TestClient that verifies OpenAPI contract vs example.
- Repo hygiene:
  - Repo contains CONTRIBUTING.md, CODEOWNERS, PR/Issue templates, ADRs for the four topics listed in Deliverables.
- Operational:
  - Request ID is propagated: request header `x-request-id` accepted and echoed, and present in logs. Error responses include the request_id.

## Outcomes
- Clear MVP scope and acceptance criteria
- Stable API contracts for `/triage`, `/explain`, `/status`
- Repo skeleton with CI, formatting, linting, and IaC layout

## Decisions
- **Backend runtime**: Python (FastAPI) or Node (NestJS). Recommend **Python + FastAPI** for faster LLM/eval iteration.
- **Auth**: start with API key per user (API Gateway usage plans). Optional: Cognito later.
- **Region**: `us-west-2` for all AWS resources in MVP.
- **Compute**: API Gateway → ECS Fargate (Lambda optional but not primary).
- **Session storage**: raw user input stored in DynamoDB keyed by session UUID with TTL.
- **Caching**: semantic cache over sanitized input using OpenSearch Serverless vector index.
- **App layout**:
  - `/infra/terraform` (IaC)
  - `/services/api` (LLM + tools + log parsing)
  - `/services/web` (frontend)
  - `/eval` (eval dataset + runner)

## Deliverables
- OpenAPI spec draft for endpoints and schemas (commit to /docs/openapi.json)
- ADRs (short docs) for: model choice, tooling strategy, caching, budget enforcement
- Canonical response schema implemented as pydantic models in services/api/app/schemas.py and JSON Schema in /docs/schemas/canonical_response.json
- GitHub Actions workflows:
  - lint-and-test.yml
  - infra-validate.yml
- Terraform skeleton under /infra/terraform with modules and README
- Request-id middleware implementation and examples in middleware logs
- Example eval runner in /eval that demonstrates /triage flow against fixtures

## Acceptance criteria
(Repeat to ensure CI and deliverables alignment)
- OpenAPI validates against examples (CI enforced)
- CI runs unit tests + lint on PRs
- Repo includes ADRs and minimal terraform skeleton
- End-to-end test verifies `/triage` returns canonical response with `hypotheses[]` and `runbook_steps[]`

## Implementation tasks
Concrete task list (assignable, PR-sized items)
1. Repo skeleton + governance files (owner: infra/backend) — 0.5 day
   - Create top-level dirs, README, CONTRIBUTING, CODEOWNERS, templates.
2. Python project init for services/api (owner: backend) — 0.5 day
   - pyproject.toml, poetry lock, dependency list, pre-commit.
3. FastAPI app + routers + middleware (owner: backend) — 1–2 days
   - Implement request-id middleware, auth dependency, logging middleware.
4. Pydantic schemas + OpenAPI auto-generation + example fixtures (owner: backend/ML) — 1 day
   - Implement canonical response schema and commit openapi.json example.
5. Adapter interfaces + stubs (owner: ML/backend) — 1–2 days
   - ModelAdapter, ToolAdapter, ParserAdapter, CacheAdapter, and in-memory stubs.
6. CI workflows (owner: infra) — 0.5–1 day
   - GitHub Actions for lint-test and infra-validate.
7. Terraform skeleton + README (owner: infra) — 1 day
   - Modules folder, example env tfvars, docs on running validate.
8. Unit tests + integration test (owner: backend) — 1–2 days
   - Tests for middleware, schema validation, /status, /triage sample flow.
9. Eval runner + fixtures (owner: ML) — 1–2 days
   - /eval runner to exercise endpoints and assert contract.
10. ADRs + documentation (owner: all) — 0.5–1 day
   - Four ADRs and short README on swapping adapters and model versioning.

Additional Implementation details (scripts & commands)
- Local run:
  - cd services/api
  - poetry install
  - poetry run uvicorn app.main:app --reload --port 8000
- Run tests:
  - poetry run pytest -q
- Format & lint:
  - poetry run black .
  - poetry run isort .
  - poetry run ruff check .
- Terraform:
  - cd infra/terraform
  - terraform init
  - terraform fmt
  - terraform validate

Notes on incremental launches
- Start by merging small PRs for repo skeleton and CI.
- Next iterate API and schema until OpenAPI and example validations pass.
- Then wire adapters and tests.
- Keep infra changes non-blocking for initial API dev (use plan-only branches).

Implementation tasks (existing list continuity)
- Define canonical response schema including:
  - `hypotheses[]` (rank, confidence, explanation, citations)
  - `runbook_steps[]` (step, command/console path/query)
  - `proposed_fix` (patch snippets)
  - `risk_notes`, `rollback`, `next_checks`
- Create request id propagation plan (header `x-request-id` generated if absent)
- Add basic GitHub Actions workflow: test + lint + terraform fmt/validate

(End of section)
