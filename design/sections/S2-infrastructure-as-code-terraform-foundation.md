# Section
Infrastructure as Code (Terraform) foundation

## Current implementation (source of truth)
- **State**: remote S3 backend with DynamoDB locks (`infra/terraform/backend.tf`).
- **Modules in use** (see `infra/terraform/main.tf`):
  - `vpc`: public/private subnets across AZs.
  - `ecs_service`: ECS Fargate service + ALB + autoscaling.
  - `ecr`: container registry for the API image.
  - `dynamodb`: sessions, inputs, conversation events/state, and budget tables.
  - `s3`: outputs bucket + frontend static bucket.
  - `cloudfront`: optional distribution for the frontend bucket.
  - `apigw`: REST API Gateway fronting the ALB, OpenAPI-based routes, usage plans + API keys.
  - `observability`: CloudWatch dashboard + alarms.
  - `iam`: least-privilege task/execution roles with access to DynamoDB, S3, Bedrock.
- **Optional cache**: `pgvector` sidecar container in ECS task definition when `pgvector_enabled=true`.
- **CORS**: API Gateway OpenAPI template injects `cors_allow_origin`.

## Key outputs
- API Gateway invoke URL + API keys.
- ALB DNS name.
- DynamoDB table names.
- CloudFront distribution ID/domain.
- CloudWatch dashboard URL.

## Not implemented yet (by code)
- Lambda service module usage (module exists but is not wired in `main.tf`).
- Additional storage buckets for upload/ingestion pipelines.
