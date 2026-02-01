# Troubleshoot Stack

Troubleshoot Stack is a log-triage system that parses raw logs into an incident frame, runs a structured triage/explain flow through an LLM adapter, and returns evidence-backed guidance through an API and a lightweight web UI. It is designed for safe iteration: request IDs, guardrails, budget limits, and observability are first-class.

## What it does
- Parses pasted logs (Terraform, CloudWatch, Python tracebacks, generic) into a normalized incident frame with evidence mapping.
- Runs `/triage` for initial hypotheses and `/explain` for follow-ups, grounded in conversation context.
- Enforces guardrails (citations, identifier redaction, domain restriction) and optional token budgets.
- Exposes live operational summaries via `/metrics/summary` and `/budget/status`.

## Architecture (current implementation)
- **API**: FastAPI on ECS Fargate behind an ALB and API Gateway (REST).
- **State**: DynamoDB tables for inputs, sessions, conversation events/state, and budgets (optional via `USE_DYNAMODB=true`; otherwise in-memory).
- **Caching**: Optional `pgvector` sidecar cache for `/explain` with Bedrock embeddings.
- **Frontend**: Vite/React app served from S3 + CloudFront (optional).
- **Observability**: CloudWatch logs/metrics; in-memory rolling metrics when CloudWatch metrics are disabled.

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

## OpenAPI validation
From the repo root:

```bash
npx @redocly/openapi-cli lint docs/openapi.json
```

Alternate validator:

```bash
npx openapi-cli validate docs/openapi.json
```

## Makefile targets
- `login-ecr`: Log in to the ECR registry referenced by Terraform outputs (requires `terraform apply` in `infra/terraform`).
- `build-api`: Build the API Docker image (`troubleshooter-api:latest`).
- `push-api`: Build and push the API image to ECR, then force a new ECS deployment.
- `test-api`: Run the API unit test suite.
- `tf-apply`: Initialize and apply the Terraform stack in `infra/terraform` using `AWS_PROFILE` (defaults to `pi`).
- `tf-destroy`: Destroy the Terraform stack in `infra/terraform` using `AWS_PROFILE` (defaults to `pi`).
- `frontend-env`: Generate `frontend/.env` from Terraform outputs (API base URL + API key).
- `build-frontend`: Install frontend deps and build the static bundle.
- `deploy-frontend`: Build + sync `frontend/dist` to S3 and invalidate CloudFront.

## Quick infra + frontend flow
From the repo root:

```bash
make tf-apply
make frontend-env
make deploy-frontend
```

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

## Operational focus (current strengths)
- Infrastructure is fully codified (VPC, ECS/ALB, API Gateway usage plans, DynamoDB, CloudFront).
- Guardrails and budgets are enforced in the request path with audit-friendly metadata.
- Observability is wired end-to-end (request IDs, structured logs, CloudWatch metrics, dashboards/alarms).
- An evaluation harness exists under `eval/` to run regression cases and compare against baselines.
