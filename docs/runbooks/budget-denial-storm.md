# Runbook: Budget denial storm

## Symptoms
- Many requests return HTTP 402 `budget_exceeded`.
- `/budget/status` shows low or zero remaining budget.
- Metrics show spikes in `BudgetDeniedCount`.

## Immediate checks
1) Validate budget settings
- Check `BUDGET_ENABLED`, `BUDGET_TOKEN_LIMIT`, `BUDGET_WINDOW_MINUTES`.
- Confirm `BUDGET_TABLE_NAME` exists and is accessible.

2) Inspect usage window
- Call `/budget/status` to check `usage_window` and `retry_after`.

## Likely causes
- Traffic spike or large requests exceeding budget.
- Misconfigured token limits or window size.
- Budget table throttling or errors.

## Mitigations
- Increase `BUDGET_TOKEN_LIMIT` or window duration.
- Temporarily disable budgets (`BUDGET_ENABLED=false`) for incident recovery.
- Reduce `LLM_MAX_TOKENS` or `LLM_BUDGET_COMPLETION_TOKENS`.

## Verification
- 402 rate drops.
- `/budget/status` shows remaining budget > 0.

## Post-incident follow-up
- Right-size budget limits and add alerts on early burn.
