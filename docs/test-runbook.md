# Test runbook (current stage)

Use this to validate the deployed API Gateway -> ALB -> ECS stack.

## 1) Get the API Gateway invoke URL and API key
```bash
cd /Users/pi/Working/OpenSource/troubleshoot-stack
terraform -chdir=infra/terraform output -raw apigw_invoke_url
terraform -chdir=infra/terraform output -json apigw_api_keys | jq -r '.[0].value'
```

Optional (direct ALB testing):
```bash
terraform -chdir=infra/terraform output -raw ecs_alb_dns_name
```

## 2) Health check
```bash
curl -sS <APIGW_INVOKE_URL>/status \
  -H "x-api-key: <API_KEY>"
```
Expected: JSON response with `status: "ok"` and a timestamp.

## 3) /triage happy path
```bash
curl -sS -X POST <APIGW_INVOKE_URL>/triage \
  -H "Content-Type: application/json" \
  -H "x-api-key: <API_KEY>" \
  -d '{
    "raw_text": "2026-01-30T11:23:45Z Error: Error creating IAM Role example-role: AccessDenied: User is not authorized\n  on iam.tf line 12, in resource \"aws_iam_role\" \"example\""
  }' | jq
```
Expected:
- `assistant_message`, `completion_state`
- optional `next_question` or `tool_calls[]`
- `metadata.parser_version` and `metadata.parse_confidence`
- `conversation_id` returned

## 4) /explain (auto-load latest incident frame)
```bash
curl -sS -X POST <APIGW_INVOKE_URL>/explain \
  -H "Content-Type: application/json" \
  -H "x-api-key: <API_KEY>" \
  -d '{
    "conversation_id": "<conversation_id_from_triage>",
    "response": "Explain the likely root cause and the safest fix for CI runners."
  }' | jq
```
Expected:
- `assistant_message`, `completion_state`
- optional `next_question` or `tool_calls[]`
- `metadata.prompt_version` and `metadata.model_id`
- Optional cache markers in `metadata.cache_hit` / `metadata.cache_similarity` on repeat calls

## 5) Metrics summary
```bash
curl -sS <APIGW_INVOKE_URL>/metrics/summary \
  -H "x-api-key: <API_KEY>" | jq
```
Expected:
- p50/p95 latency values (CloudWatch or in-memory fallback)
- cache hit rate and API error rate fields

## 6) Budget status
```bash
curl -sS <APIGW_INVOKE_URL>/budget/status \
  -H "x-api-key: <API_KEY>" | jq
```
Expected:
- `usage_window`, `token_limit`, `tokens_used`, `remaining_budget`

## 7) Verify ECS logs
```bash
aws logs tail /ecs/<ecs_cluster_name> --since 10m --follow
```
Expected: request logs for `/status`, `/triage`, `/explain`.

## 8) Validate DynamoDB writes (if enabled)
Confirm entries exist in:
- inputs table
- sessions table
- conversation events table
- conversation state table
- budget table (if `BUDGET_ENABLED=true`)
