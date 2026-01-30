# Troubleshoot Stack

## API endpoints (MVP)
- `GET /status` healthcheck (ALB target group points here)
- `POST /triage`
- `POST /explain`

## Parsing (MVP)
Rule-first parser with explicit log family matching (Terraform, CloudWatch, Python tracebacks) and a generic fallback.

## OpenAPI validation
From the repo root:

```bash
npx @redocly/openapi-cli lint docs/openapi.json
```

Alternate validator:

```bash
npx openapi-cli validate docs/openapi.json
```
