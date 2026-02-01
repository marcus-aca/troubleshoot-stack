# Section
Parser + evidence extraction (current implementation)

## Current implementation (source of truth)
- **Rule-based parser**: `RuleBasedLogParser` builds an `IncidentFrame` from raw logs.
- **Supported families**: Terraform, CloudWatch, Python tracebacks, and a generic fallback.
- **Evidence mapping**: each frame includes `evidence_map` entries with `line_start`, `line_end`, and `excerpt_hash` for citations.
- **Context assembly**: conversation state + recent events are compacted for prompt context.
- **Storage**: inputs, frames, and canonical responses persisted to DynamoDB (when enabled) for deterministic citations.

## Not implemented yet (by code)
- Knowledge-base ingestion or retrieval (OpenSearch/KB pipelines).
- External tool output ingestion beyond user-supplied `tool_results`.
