# Troubleshoot Stack

A production‑ready AI triage platform that demonstrates end‑to‑end platform engineering across infrastructure, observability, governance, and LLM reliability. It parses raw logs into incident frames, runs structured triage/explain flows, and returns evidence‑backed guidance through an API and lightweight web UI, with budgets, guardrails, and evaluation gates baked in.

## Value delivered
- **Faster incident triage**: normalizes logs into evidence‑mapped incident frames and produces actionable hypotheses and fix steps.
- **Governed AI usage**: guardrails, redaction, citation enforcement, and optional token budgets for cost control.
- **Operational readiness**: request IDs, structured logs, metrics dashboards/alarms, and tracing.
- **Regression safety**: built‑in eval harness with baseline comparison (`eval/`).

## Platform attributes
- **Production IaC**: Terraform modules for VPC, ECS/ALB, API Gateway, DynamoDB, CloudFront, and observability.
- **APM-grade telemetry**: OpenTelemetry → ADOT sidecar → AWS X‑Ray, plus CloudWatch logs/metrics.
- **CI quality gates**: OpenAPI linting, Terraform validation, API unit tests, and eval smoke runs.


## How to run (infra-first)
Prerequisites:
- Create a public ACM certificate in `us-east-1` for your intended domain (Route 53 validation) or select existing Cert.
- Fill out `infra/terraform/terraform.tfvars` for your environment (replace variables specific for your stack, domain etc)

All environment configuration is driven by infrastructure as code. Terraform outputs feed runtime settings and the frontend build (`frontend/.env`), so treat the Terraform stack as the reference source of truth.

From the repo root:

```bash
make tf-apply 
make push-api 
make frontend-env 
make deploy-frontend 
```

## Architecture (current implementation)
- **API**: FastAPI on ECS Fargate behind ALB + API Gateway (REST), with request IDs and structured JSON logs.
- **State**: DynamoDB tables for inputs, sessions, conversation events/state, and budgets (optional via `USE_DYNAMODB=true`; otherwise in‑memory).
- **Caching**: Optional `pgvector` sidecar cache for `/explain` with Bedrock embeddings.
- **Frontend**: Vite/React app served from S3 + CloudFront (optional).
- **Observability**: CloudWatch logs/metrics + dashboards/alarms, with OpenTelemetry traces exported to an ADOT sidecar and AWS X‑Ray.
- **Infra as code**: Terraform modules for VPC, ECS, ALB, API Gateway usage plans, DynamoDB, CloudFront, and observability.

## API endpoints
- `GET /status` healthcheck (ALB target group points here)
- `POST /triage` initial log triage
- `POST /explain` follow-up and tool-result explanation
- `GET /metrics/summary` API/LLM/cache/budget summary
- `GET /budget/status` current token budget window status

## Parsing
Rule-first parser with explicit log family matching (Terraform, CloudWatch, Python tracebacks) and a generic fallback.

## Storage
When `USE_DYNAMODB=true`, conversation context, incident frames, and canonical responses are stored in DynamoDB (inputs + conversation events/state). When disabled, the API falls back to in-memory storage. See `docs/storage.md`.


## Makefile targets
- `build-api`: Build the API Docker image (`troubleshooter-api:latest`).
- `push-api`: Build and push the API image to ECR, then force a new ECS deployment.
- `test-api`: Run the API unit test suite.
- `tf-apply`: Initialize and apply the Terraform stack in `infra/terraform` using `AWS_PROFILE` (defaults to `pi`).
- `tf-destroy`: Destroy the Terraform stack in `infra/terraform` using `AWS_PROFILE` (defaults to `pi`).
- `frontend-env`: Generate `frontend/.env` from Terraform outputs (API base URL + API key).
- `build-frontend`: Install frontend deps and build the static bundle.
- `deploy-frontend`: Build + sync `frontend/dist` to S3 and invalidate CloudFront.
- `login-ecr`: Log in to the ECR registry referenced by Terraform outputs (requires `terraform apply` in `infra/terraform`).

## OpenAPI validation
From the repo root:

```bash
npx @redocly/openapi-cli lint docs/openapi.json
```

Alternate validator:

```bash
npx openapi-cli validate docs/openapi.json
```

## CI automation (current status)
- **API unit tests**: `.github/workflows/api-unit-tests.yml` runs `make test-api` on PRs and pushes to `main`.
- **Eval smoke tests**: `.github/workflows/eval-pr.yml` runs the eval smoke set on PRs or manual dispatch, then compares to `eval/baseline/summary.json` and publishes a job summary.
- **OpenAPI lint**: `.github/workflows/openapi-check.yml` runs OpenAPI linting on PRs.
- **Terraform checks**: `.github/workflows/terraform-check.yml` runs `terraform fmt -check`, `init -backend=false`, and `validate` on PRs.

## Runbooks
Operational runbooks are available under `docs/runbooks/`.

## Tracing (OpenTelemetry + X-Ray)
- Enable via Terraform: set `otel_enabled=true` (see `infra/terraform/terraform.tfvars`).
- The API exports OTLP traces to an ADOT sidecar, which forwards to AWS X-Ray.
See `docs/assets/trace.png`
- X-Ray service map URL is available as a Terraform output: `xray_service_map_url`.
See `docs/assets/trace_map.png`

## Eval notes
- If token budgets are exhausted in a shared environment, run evals with `--budget-bypass` and set `BUDGET_ALLOW_BYPASS=true` on the API service.


## Frontend configuration
The frontend reads build-time settings from `frontend/.env`:

```
VITE_API_BASE_URL=https://api.example.com
VITE_API_KEY=replace_me
```

You can generate this file with:

```bash
make frontend-env
```

## LLM response repair (API)
- **JSON repair + recovery**: attempts to repair invalid JSON (bad escapes/control chars/missing commas) before parsing.
- **Schema validation**: Pydantic model validation enforces response shape for triage/explain outputs.
- **Citation normalization**: normalizes/filters citations to the allowed evidence map; missing citations are flagged.
- **Safety redaction**: identifier redaction is applied to model output where needed, with counts tracked.
- **Fallback responses**: guardrail-triggered fallbacks return structured prompts for missing details or restricted domains.

## Operational focus (current strengths)
- Infrastructure is fully codified (VPC, ECS/ALB, API Gateway usage plans, DynamoDB, CloudFront).
- Guardrails and budgets are enforced in the request path with audit-friendly metadata.
- Observability is wired end-to-end:
  - **Request IDs**: `x-request-id` is accepted or generated, then echoed as `X-Request-Id` and included in JSON logs.
  - **Structured logs**: the API emits JSON log lines for request start/end, errors, LLM calls, cache events, and budget denials.
  - **Metrics**: optional CloudWatch metrics for API/LLM latency, error rate, cache hit rate, and budget denials (with in-memory fallbacks when disabled).
  - **Dashboards/alarms**: Terraform provisions CloudWatch dashboards and alarms via `infra/terraform/modules/observability`. See `docs/assets/dashboard.png`.
- An evaluation harness exists under `eval/` to run regression cases and compare against baselines.
- MVP gaps to close for full platform polish: include `trace_id`/`span_id` in CloudWatch log payloads for log/trace correlation.

## Keywords
AI platform engineering, LLM orchestration, OpenAI/Bedrock-style adapters, FastAPI, Python, React, Vite, AWS ECS Fargate, Application Load Balancer (ALB), API Gateway (REST), DynamoDB, S3, CloudFront, VPC, Terraform (IaC), OpenTelemetry (OTel), ADOT collector, AWS X-Ray, CloudWatch logs/metrics/dashboards/alarms, CI/CD (GitHub Actions), evaluation harnesses, prompt guardrails, redaction, rate limiting, token budgets, caching (pgvector), structured logging, incident triage, runbooks.
