# Section
Infrastructure as Code (Terraform) foundation

## Summary
Provision a repeatable, secure AWS foundation using Terraform for the MVP in `us-west-2`. The foundation includes networking (VPC), API Gateway (REST) with usage plans and throttling, compute on ECS Fargate (recommended) or Lambda (optional for lower-volume endpoints), DynamoDB for session and budget tables, OpenSearch Serverless for semantic cache, S3 buckets for uploads/artifacts/frontend, CloudWatch observability, and least‑privilege IAM roles/policies. The codebase is modular (reusable modules), with a remote state backend (S3 + DynamoDB locking).

## Design
High-level decisions and resource mapping:

- Terraform
  - Version: >= 1.4. Pin providers in required_providers.
  - AWS provider: AWS provider v4+ (pin exact version in provider block).
  - Remote state: S3 backend + DynamoDB table for locks (single backend for the environment).
  - Directory layout:
    - modules/
      - vpc
      - ecs_service (creates cluster, task_definition, service, optional ALB/NLB)
      - lambda_service (optional; function + log group + permissions)
      - apigw (REST API Gateway + usage plan + API keys + stage)
      - storage (S3 uploads/artifacts buckets and access policy)
      - dynamodb (tables + autoscaling if desired)
      - s3 (buckets with encryption and lifecycle)
      - observability (log groups, dashboards, alarms)
      - iam (reusable role/policy fragments)
    - root configuration under /infra/terraform (backend.tf, providers.tf, variables.tf, main.tf)

- Networking
  - VPC with public and private subnets across >=2 AZs.
  - NAT Gateways as needed (single NAT per AZ or NAT Gateway per AZ depending on budget/HA).
  - Security groups:
    - ecs_service_sg: allow inbound from ALB/NLB on app port.
    - alb_sg / nlb_sg: allow inbound from 0.0.0.0/0 (if public) or restricted source CIDRs.
    - apigw does not use security groups; for private integrations use VPC Link + NLB.

- API Layer
  - Use API Gateway REST API (v1) because usage plans + API keys are required.
  - Integration: front compute with either:
    - Recommended: ECS service behind a load balancer.
      -  public ALB in front of ECS. API Gateway integration uses ALB public endpoint.

  - Import OpenAPI spec for routes from `/docs/openapi.json`; use Terraform resource aws_api_gateway_rest_api and aws_api_gateway_deployment/stage.
  - Define usage plans, API keys, and throttling settings per plan (rate and burst).

- Compute
  - Recommended: ECS Fargate service (serverless compute for tasks).
    - Task role and execution role separated.
    - Task definition references secrets from SSM Parameter Store (do not store secrets in TF state).
    - Autoscaling via ECS Service Auto Scaling (target tracking on CPU and custom CloudWatch metric for requests per target if available).


- Storage & Data
  - DynamoDB: tables for sessions (conversation context / raw inputs) and budgets. Enable encryption, point-in-time recovery optional, and proper read/write capacity or autoscaling (on-demand recommended).
  - OpenSearch Serverless: vector index for semantic cache of sanitized inputs.
  - S3 buckets: frontend hosting as required, served by cloudfront Enforce bucket encryption, block public access, lifecycle rules.

- Observability & Ops
  - CloudWatch log groups for ECS tasks and API Gateway request logs; set retention policy.
  - CloudWatch dashboard with widgets for:
    - API latency (p50/p95/p99), request count, 4xx/5xx rates
    - ECS tasks desired/Running
    - Cost per request (approx via lambda-priced metrics or Cost Explorer linkage)
    - DynamoDB read/write and cache hit rate (derive from app metrics)
  - Alarms:
    - p95 latency threshold (e.g., > 1000 ms for 5m)
    - 5xx error rate spike (e.g., > 5% of requests over 5m)
    - ECS service unhealthy tasks > 0

- Security / least privilege
  - Bedrock IAM policy: allow bedrock:InvokeModel limited to named model ARNs (explicit resource ARNs). Deny wildcard.
  - DynamoDB policies: restrict to specific table ARNs and actions. Use Condition "dynamodb:LeadingKeys" to limit partition-key prefixes where applicable.
  - IAM roles:
    - ecs_task_role: permissions to read/write DynamoDB, S3 (where necessary), secretsmanager:GetSecretValue, and Bedrock Invoke, all scoped to minimum resources.
    - ecs_exec_role: required ECS execution permissions.
    - lambda_exec_role: (optional) Lambda execution permissions scoped to DynamoDB, Bedrock, S3, and Secrets Manager as needed.
    - apigw_role (if needed): for logging/invocation.
  - Secrets: store DB passwords, API keys, model keys in Secrets Manager; pass references to tasks via secrets.

Non-goals
- No multi-region active/active setup in MVP.
- No full-blown SIEM or enterprise IAM workflow; keep IAM least-privilege but pragmatic.

## Implementation Steps
Step-by-step actions, including Terraform commands and verification checks.

1. Bootstrap remote state (one-time)
   - Create S3 bucket for state and DynamoDB lock table (via a bootstrap Terraform configuration) in `us-west-2`:
     - S3 bucket: name "troubleshooter-terraform-state", enable encryption, versioning, block public access.
     - DynamoDB table: name "troubleshooter-terraform-locks", partition key "LockID", billing_mode PAY_PER_REQUEST.
   - Rationale: central remote state ensures safe concurrent runs.

2. Initialize repo and modules
   - Create the modules/ structure and implement each module with clear inputs/outputs.
   - Required module contracts:
     - vpc: variables (cidr, az_count, public_subnet_cidrs, private_subnet_cidrs), outputs (vpc_id, subnet_ids_public, subnet_ids_private).
     - ecs_service: inputs (cluster_name, vpc_id, subnet_ids_private/public, container_image, cpu, memory, port, desired_count, env_vars_secret_arns, task_role_arn, execution_role_arn, alb_enabled), outputs (cluster_arn, service_name, alb_dns_name or nlb_dns_name).
     - lambda_service (optional): inputs (function_name, handler, runtime, memory_mb, timeout_s, env_vars, role_arn), outputs (function_arn, invoke_arn).
     - apigw: inputs (openapi_spec_path or swagger, stage_name, usage_plans), outputs (rest_api_id, invoke_url, api_keys).
     - dynamodb: inputs (table_name, hash_key, range_key optional, billing_mode), outputs (table_arn, name).
     - s3: inputs (bucket_name, versioning, lifecycle_rules), outputs (bucket_arn).
     - observability: inputs (names, log_groups), outputs (dashboard_url).
   - Create README for module usage.

3. Single-environment infrastructure as code
   - In the repo root Terraform directory, create:
     - backend.tf with S3 backend configuration (bucket, key = "terraform.tfstate", dynamodb_table).
     - providers.tf with region provider config.
     - variables.tf and terraform.tfvars for environment-specific values (CIDR ranges, instance types, desired_count).
     - Do not include secrets in envs; if necessary create secrets as secretString in SSP parameter store.

4. Implement API Gateway
   - Implement aws_api_gateway_rest_api with body = file("${path.module}/openapi.yaml") or define resources, methods in TF resources.
   - Create deployment and stage; enable access logging by configuring stage settings and a CloudWatch log group.
   - Create usage_plan and usage_plan_key resources; configure throttle_settings (rate_limit and burst_limit) per plan.
   - Example throttling defaults (adjust for demo requirements):
     - usage plan: rate_limit = 100 rps, burst_limit = 200; stage_level throttle for routes if needed.

5. Implement ECS service + load balancer
   - ecs_service module creates:
     - cluster
     - task definition with container definitions referencing environment variables and secrets (task role for runtime permissions).
     - Fargate service with desired_count and min/max for autoscaling.
     - ALB (or NLB for VPC Link) + target group + listener. If using ALB, create security group that only permits inbound from 0.0.0.0/0 on port 443 (or restrict to known API Gateway CIDRs if public).
   - Autoscaling:
     - Configure Application Auto Scaling with target tracking:
       - CPU utilization target (e.g., 65%).
       - Optionally scale on a custom CloudWatch metric (RequestsPerTarget) using target tracking.
     - Set min_capacity and max_capacity variables.

6. DynamoDB and S3
   - Provision DynamoDB tables with encryption and point-in-time recovery per requirements.
   - Use on-demand billing; enable autoscaling only if needed.
   - Provision S3 buckets with encryption, Block Public Access, and lifecycle policies. Add bucket policy to allow only TLS requests and to deny insecure transport.

7. Observability
   - Create CloudWatch log groups for ECS and API Gateway; set retention periods (e.g., 14d).
   - Create CloudWatch dashboard with widgets:
     - Latency p50/p95/p99 (API Gateway + ALB target metrics).
     - 4xx/5xx counts and rates.
     - ECS service desired vs running tasks.
    - Cache hit rate (application-provided metric or compute from OpenSearch metrics).
   - Alarms:
     - p95 latency > 1s for 5 minutes -> send to Pager/Slack.
     - 5xx error rate > 5% for 5 minutes -> escalation.
     - ECS desired != running tasks for > 2 minutes -> alert.

8. IAM roles & policies
   - Create least-privilege roles as module outputs:
     - Define inline policies for required access and attach them to the task role.
     - Example Bedrock policy snippet (in Terraform IAM JSON form) restricting to specific ARNs; do not allow wildcards.
   - Use Terraform data sources to fetch ARNs for resources to build least-privilege policies.

9. CI/CD & deploy
    - Add CI pipeline steps:
      - terraform fmt && terraform validate
      - terraform init -backend-config=... (use secure secrets for backend)
    - terraform plan -var-file=terraform.tfvars
    - terraform apply (after approvals)
    - Secrets management: use environment variables or CI secret store to provide AWS credentials and sensitive TF vars.

10. Testing & validation (post-apply)
    - Verify remote state is saved.
    - Confirm ECS tasks are RUNNING and target group shows healthy targets:
      - aws ecs describe-services / aws elbv2 describe-target-health
    - Invoke API endpoint (curl) and expect a 200/expected JSON response.
    - Confirm CloudWatch log groups receive logs.
    - Verify uploads bucket is reachable only from ECS role (attempt from another role should be denied).
    - Verify DynamoDB tables are accessible only per IAM policy.

Commands example:
- terraform init
- terraform plan -var-file=terraform.tfvars
- terraform apply -var-file=terraform.tfvars

## Risks
List of risks and mitigations.

- State bootstrap race / missing S3/DynamoDB state bucket
  - Mitigation: bootstrap state bucket manually or provide a single-use bootstrap Terraform that an admin runs first.

- API Gateway vs HTTP API feature mismatch
  - Mitigation: Design chosen -> REST API (v1) to meet usage plan requirement. Document tradeoffs and alternative (HTTP API) if usage plans not needed.

- S3 access and retention misconfiguration
  - Mitigation: Enforce bucket policy tests in CI; validate lifecycle rules in plan and apply.

- Overly permissive IAM policies
  - Mitigation: Enforce policy review, use explicit ARNs, leverage Condition blocks (dynamodb:LeadingKeys, aws:SourceVpc, aws:SourceIp) where possible, and run an IAM policy scanner (e.g., conftest/OPA) in CI.

- Cost overruns
  - Mitigation: Prefer on-demand, set CloudWatch billing alarms, and create budget alerts (AWS Budgets).

- Secrets leakage (sensitive values in TF state)
  - Mitigation: Keep secrets in Secrets Manager or SSM Parameter Store and reference from ECS task definitions. Avoid plaintext sensitive vars in .tfvars; use state encryption.

- Network integration complexity (API Gateway private integrations)
  - Mitigation: Start with public ALB integration; implement NLB + VPC Link for private integration in a follow-up iteration.

## Dependencies
External and internal dependencies required before and during implementation.

- AWS account(s) with sufficient permissions to create VPC, IAM, ECS, ALB/NLB, API Gateway, DynamoDB, S3, CloudWatch, Secrets Manager.
- Region that supports required services (verify Bedrock availability).
- Terraform CLI installed (>=1.4 recommended).
- AWS CLI for manual checks and bootstrapping.
- CI runner (GitHub Actions, GitLab CI, etc.) with secure secrets to run terraform apply for the environment.
- Initial S3 bucket and DynamoDB lock table for remote state (or bootstrap script).
- Container image repository (ECR) with application image builds available to ECS.
- DNS (optional) to map custom domain to API Gateway and ALB.

## Acceptance Criteria
Concrete, testable success conditions.

1. Infrastructure provisioning
   - Running: terraform apply completes without errors and writes state to the configured remote backend.

2. Networking & compute
   - ECS cluster created, service has desired_count tasks in RUNNING state across private subnets.
   - Load balancer (ALB or NLB) created with healthy targets for ECS tasks.

3. API
   - API Gateway REST API deployed with stage and usage plan.
   - Example curl to API Gateway endpoint returns a valid 2xx response for a health endpoint.
   - Usage plan throttling enforced (plan returns 429 when exceeding configured threshold).

4. Observability
   - CloudWatch log groups created for ECS and API Gateway and receiving logs.
   - CloudWatch dashboard URL is available and shows data.
   - At least one alarm (e.g., p95 latency > 1s test threshold) created and can be triggered in test scenario.

5. Data services
   - DynamoDB tables exist and are accessible by ECS task role per IAM policy.
   - Uploads bucket exists; ECS tasks can read/write parsed incident frames; attempts to access from an unauthorized principal are denied.

6. Security & least privilege
   - Bedrock Invoke policy attached to ECS task role allows only specified model ARNs.
   - IAM policies scoped to only the created resources (no wildcard access to unrelated resources).
   - Secrets used by tasks are stored in Secrets Manager and not embedded in TF state.

7. Repeatability
   - Running terraform destroy (or applying a teardown plan) removes provisioned resources (or marks them for removal) without leaving unmanaged critical resources.

## Outcomes
- A reusable Terraform baseline that provisions core services for API, storage, and observability.
- Single environment stack with remote state and CI validation.
- Least-privilege IAM policies and secure data handling defaults.

## Decisions
- **Region**: `us-west-2` for MVP resources.
- **API layer**: API Gateway REST API (v1) to support usage plans and API keys.
- **Compute**: ECS Fargate as primary; Lambda optional for low-volume endpoints.
- **State**: S3 backend + DynamoDB lock table for the environment.

## Deliverables
- Terraform modules under /infra/terraform/modules for vpc, ecs_service, apigw, dynamodb, storage, observability, iam.
- Root-level Terraform config (no env-specific directory).
- CI workflow for terraform fmt/validate/plan.
- README for bootstrapping remote state and applying environments.

## Implementation tasks
Concrete task list (assignable, PR-sized items)
1. Remote state bootstrap docs and template (owner: infra) — 0.5 day
2. Module scaffolding and contracts (owner: infra) — 1–2 days
3. baseline config and plan (owner: infra) — 0.5–1 day
4. API Gateway + ECS service modules (owner: infra) — 1–2 days
5. Storage + DynamoDB modules (owner: infra) — 0.5–1 day
6. Observability module + alarms (owner: infra/SRE) — 0.5–1 day
7. CI workflow for terraform fmt/validate/plan (owner: infra) — 0.5 day

Optional acceptance tests (automatable):
- Automated integration test: CI job that deploys the environment, runs a simple suite that:
  - Calls /health and verifies JSON response.
  - Writes and reads a small object from the uploads bucket using task role credentials.
  - Verifies DynamoDB read/write via a short script using the task role credentials (run via an ECS task or assume-role test).

Notes:
- Adjust throttling and autoscaling numeric values to match expected traffic; the provided thresholds are starting points and should be tuned after load testing.
- Document all module input variables and outputs and include examples alongside the root config to accelerate onboarding.
