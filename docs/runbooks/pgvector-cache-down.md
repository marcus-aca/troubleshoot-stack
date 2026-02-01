# Runbook: pgvector cache down

## Symptoms
- Cache hit rate drops to zero.
- `/explain` latency increases.
- Logs show `cache_lookup_error` or `cache_write_error`.

## Immediate checks
1) Confirm pgvector status
- Check ECS task definition for pgvector sidecar.
- Look for pgvector container health in ECS.

2) Inspect logs
- Tail `/ecs/<ecs_cluster_name>` and filter `cache_*` events.

## Likely causes
- pgvector container unhealthy or not started.
- Postgres credentials invalid.
- Disk or memory pressure.

## Mitigations
- Restart ECS tasks.
- Temporarily disable cache (`PGVECTOR_ENABLED=false`) to bypass errors.
- Verify env vars for `PGVECTOR_*` are correct.

## Verification
- Cache errors stop; `/explain` latency stabilizes.
- `cache_hit_rate` returns to expected levels when re-enabled.

## Post-incident follow-up
- Add health checks and alerts on pgvector container.
