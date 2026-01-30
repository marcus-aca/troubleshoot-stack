# Test runbook (current stage)

Use this to validate the deployed ECS + ALB + API stack.

## 1) Get the ALB URL
```bash
cd /Users/pi/Working/OpenSource/troubleshoot-stack
terraform -chdir=infra/terraform output -raw ecs_alb_dns_name
```

## 2) Health check
```bash
curl -sS http://<ALB_DNS_NAME>/status
```
Expected: JSON response with `status: "ok"` and a timestamp.

## 3) /triage happy path
```bash
curl -sS -X POST http://<ALB_DNS_NAME>/triage \
  -H "Content-Type: application/json" \
  -d '{
    "raw_text": "2026-01-30T11:23:45Z Error: Error creating IAM Role example-role: AccessDenied: User is not authorized\n  on iam.tf line 12, in resource \"aws_iam_role\" \"example\""
  }' | jq
```
Expected:
- `hypotheses[]` and `runbook_steps[]` arrays
- `metadata.parser_version` and `metadata.parse_confidence`
- `conversation_id` returned

## 4) /explain (with incident frame)
Use the incident frame from `/triage` (if you want a full multi-turn test).

## 5) Verify ECS logs
```bash
aws logs tail /ecs/<ecs_cluster_name> --since 10m --follow
```
Expected: request logs for `/status` and `/triage`.

## 6) Validate DynamoDB writes (if enabled)
Confirm entries exist in:
- inputs table
- sessions table
- conversation events table
- conversation state table

