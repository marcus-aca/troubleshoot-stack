# Runbook: API 5xx spike

## Symptoms
- API Gateway 5xx rate spikes for `/triage` or `/explain`.
- Clients see `Request failed (5xx)`.
- ALB target health may drop.

## Immediate checks (5-10 min)
1) Confirm scope
- Check CloudWatch dashboard for API Gateway 5xx and ALB target errors.
- Check `/metrics/summary` for `api_error_rate` and recent latency.

2) Validate ECS health
- `aws ecs describe-services --cluster <ecs_cluster> --services <ecs_service>`
- `aws elbv2 describe-target-health --target-group-arn <tg_arn>`

3) Inspect recent logs
- `aws logs tail /ecs/<ecs_cluster_name> --since 15m --follow`
- Look for `request_error`, `triage_error`, `explain_error` events.

## Likely causes
- Unhandled exceptions in FastAPI or parser/LLM JSON validation.
- Downstream failures (Bedrock call, DynamoDB, pgvector).
- Memory/CPU starvation causing timeouts.

## Mitigations
- Scale ECS service: increase desired count or min capacity.
- Temporarily disable Bedrock by switching to stub (`LLM_MODE=stub`) if failures are in LLM calls.
- Disable pgvector cache if Postgres is failing (`PGVECTOR_ENABLED=false`).
- Roll back to last known good image (ECR tag).

## Verification
- 5xx rate returns to baseline.
- `/status` and `/triage` return 200.
- CloudWatch alarms clear.

## Post-incident follow-up
- Add regression test for the failing path.
- Review logs for unhandled exceptions and add guardrails.
