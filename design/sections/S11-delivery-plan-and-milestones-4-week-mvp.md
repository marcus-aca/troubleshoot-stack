# Section
Delivery plan and milestones (current implementation snapshot)

## Current status
- API service with `/triage`, `/explain`, `/status`, `/metrics/summary`, `/budget/status`.
- Rule-based parser with evidence mapping and incident frames.
- LLM orchestration with prompt registry and guardrails.
- Optional pgvector cache for `/explain`.
- Terraform stack for VPC, ECS/ALB, API Gateway, DynamoDB, S3, CloudFront, IAM, and CloudWatch dashboards/alarms.
- Frontend UI for triage/explain with ops panels.
- Evaluation harness with cases, baselines, and comparison tool.

## Next milestones (not implemented yet)
- CI workflows for tests, OpenAPI validation, and Terraform checks.
- Secure ingestion pipeline for file uploads and tool execution.
- OpenTelemetry tracing and deeper observability.
