# Runbook: DynamoDB throttling or errors

## Symptoms
- Requests fail or slow down when `USE_DYNAMODB=true`.
- Logs show DynamoDB errors or conditional failures unrelated to budgets.
- CloudWatch shows throttled requests or high latency.

## Immediate checks
1) Confirm throttling
- Check DynamoDB table metrics for `ThrottledRequests` and `ConsumedRead/WriteCapacityUnits`.

2) Identify affected tables
- Inputs, sessions, conversation events/state, budget table.

3) Inspect logs
- Look for `storage` errors or timeouts.

## Likely causes
- Traffic spikes beyond on-demand limits.
- Hot partition keys (same conversation_id).
- IAM permission changes.

## Mitigations
- Reduce write amplification (limit events stored per request).
- Temporarily disable DynamoDB by switching to in-memory for non-prod.
- Increase capacity or add adaptive capacity adjustments.

## Verification
- Throttling metrics drop.
- API responses return to normal latencies.

## Post-incident follow-up
- Add partition key distribution review.
- Consider batching writes or reducing TTL windows.
