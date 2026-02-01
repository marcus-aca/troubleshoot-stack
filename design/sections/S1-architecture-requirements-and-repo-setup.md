# Section
Architecture, requirements, and repo setup

## Current implementation (source of truth)
- **Runtime**: Python + FastAPI (`services/api`).
- **Endpoints**: `GET /status`, `POST /triage`, `POST /explain`, `GET /metrics/summary`, `GET /budget/status`.
- **Request IDs**: `x-request-id` accepted and echoed as `X-Request-Id`; structured logs include request metadata.
- **Parser**: rule-based log parser (Terraform, CloudWatch, Python tracebacks, generic) with evidence mapping.
- **LLM orchestration**: prompt registry with versioned prompts (`triage` v3, `explain` v2). Bedrock or stub mode.
- **Guardrails**: domain restriction for non-DevOps queries, citation enforcement, identifier redaction, budget enforcement.
- **Storage**: DynamoDB when `USE_DYNAMODB=true`, in-memory fallback otherwise.
- **Caching**: optional pgvector-backed semantic cache for `/explain`.
- **Infra layout**: API Gateway -> ALB -> ECS Fargate, VPC, DynamoDB tables, S3 buckets, CloudFront for frontend, ECR for images, CloudWatch logs/metrics.
- **Repo layout**:
  - `services/api`: FastAPI service
  - `frontend`: Vite/React UI
  - `infra/terraform`: IaC
  - `eval`: evaluation harness + cases
  - `docs`, `design/sections`: documentation

## Not implemented yet (by code)
- Application-level API key validation in the service (API Gateway usage plans handle keys today).
- Knowledge-base ingestion or OpenSearch Serverless retrieval.
- Automated tool execution; tool calls are suggested but not run server-side.
- CI workflows and ADRs.
