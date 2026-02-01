# Runbook: LLM errors or timeouts

## Symptoms
- `/triage` or `/explain` returns 502 (LLM invalid JSON) or 5xx.
- Logs show `triage_error` or `explain_error` with LLM output preview.
- LLM latency spikes.

## Immediate checks
1) Confirm LLM mode
- Check ECS task env vars for `LLM_MODE` and `BEDROCK_MODEL_ID`.

2) Inspect LLM errors
- Tail logs for `triage_error` / `explain_error` and `llm_call`.

3) Validate Bedrock access
- Confirm IAM task role has `bedrock:InvokeModel` permission for the model.

## Likely causes
- Bedrock throttling or model unavailability.
- Invalid JSON in LLM output (schema mismatch).
- Prompt length exceeds limits or invalid parameters.

## Mitigations
- Switch to stub mode temporarily (`LLM_MODE=stub`).
- Lower `LLM_MAX_TOKENS` and/or `LLM_TEMPERATURE`.
- Roll back to last known good prompt version.

## Verification
- LLM errors stop and 502 rate drops.
- `triage`/`explain` return valid JSON responses.

## Post-incident follow-up
- Add prompt regression tests or output validators.
- Consider retry/backoff with circuit breaker.
