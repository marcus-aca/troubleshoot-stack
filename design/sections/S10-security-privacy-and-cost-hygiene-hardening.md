# Section
Security, privacy, and cost hygiene (current implementation)

## Current implementation (source of truth)
- **Redaction**:
  - Client-side redaction in the frontend for common secrets/PII.
  - Server-side redaction before parsing/LLM calls.
- **Guardrails**:
  - Domain restriction for non-DevOps requests.
  - Citation enforcement with confidence downgrades.
  - ARN/account ID redaction in hypothesis text.
- **Budgets**: DynamoDB-backed token budgets with explicit 402 responses when exceeded.
- **Rate limiting**: API Gateway usage plans + API keys.
- **Least privilege**: ECS task role scoped to DynamoDB/S3/Bedrock resources in Terraform.

## Not implemented yet (by code)
- S3 ingestion pipeline with presigned uploads and KMS enforcement.
- Dedicated ingestion/serving IAM roles with separate data paths.
- Formal PII detection beyond regex redaction.
