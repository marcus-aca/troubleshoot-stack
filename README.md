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
