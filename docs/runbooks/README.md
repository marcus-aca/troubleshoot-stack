# Runbooks

This folder contains incident runbooks aligned to the current Troubleshoot Stack deployment (API Gateway -> ALB -> ECS, DynamoDB, optional pgvector cache, Bedrock).

## Index
- `api-5xx-spike.md`
- `api-latency-regression.md`
- `llm-errors-or-timeouts.md`
- `dynamodb-throttling.md`
- `pgvector-cache-down.md`
- `budget-denial-storm.md`

## Common context
- API endpoints: `/status`, `/triage`, `/explain`, `/metrics/summary`, `/budget/status`.
- Primary logs: ECS task logs in CloudWatch log group `/ecs/<ecs_cluster_name>`.
- Primary metrics: API Gateway and custom CloudWatch metrics (if `CW_METRICS_ENABLED=true`).
- Request ID propagation: `x-request-id` header is echoed as `X-Request-Id` and logged.

## Links
- Terraform outputs: `infra/terraform/outputs.tf`
- Observability module: `infra/terraform/modules/observability`
- API logging/middleware: `services/api/app/main.py`
