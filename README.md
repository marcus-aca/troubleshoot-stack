# Troubleshoot Stack

## API endpoints (MVP)
- `GET /status` healthcheck (ALB target group points here)
- `POST /triage`
- `POST /explain`

## Parsing (MVP)
Rule-first parser with explicit log family matching (Terraform, CloudWatch, Python tracebacks) and a generic fallback.

## Storage (MVP)
Conversation context, incident frames, and canonical responses are stored in DynamoDB (inputs + conversation events/state). See `docs/storage.md`.

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
- `test-api-parser`: Run the API parser unit tests.
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
