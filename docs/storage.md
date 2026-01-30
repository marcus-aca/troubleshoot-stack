# Storage model (MVP)

This document describes how we persist inputs, incident frames, and canonical responses to support multi-turn troubleshooting.

## Tables
- **Inputs table** (DynamoDB, TTL)
  - Stores raw user inputs keyed by `input_id` for deterministic citations.
  - Also stores derived artifacts as separate items if needed (incident frames, canonical responses).
- **Conversation events table** (DynamoDB, TTL)
  - PK: `conversation_id`
  - SK: `event_id` (timestamp#request_id)
  - Stores per-turn: raw input, incident frame, canonical response.
- **Conversation state table** (DynamoDB, TTL)
  - PK: `conversation_id`
  - Stores latest incident frame + response summary for fast context assembly.
- **Sessions table** (DynamoDB, TTL)
  - PK: `conversation_id`
  - Tracks latest request/input for quick lookups.

## Write flow
### /triage
1. Save raw input (`inputs` table).
2. Parse to incident frame.
3. Save incident frame (derived artifact).
4. Build canonical response.
5. Save canonical response (derived artifact).
6. Append conversation event.
7. Update conversation state.

### /explain
- If an incident frame is supplied, the response is persisted the same way as /triage.

## LLM context
`build_llm_context` pulls conversation state + recent events and emits a compact payload, plus a Bedrock-ready `inputText` prompt.

## TTL defaults
- Inputs: 1 day (`INPUT_TTL_SECONDS`)
- Conversation events/state: 7 days (`CONVERSATION_TTL_SECONDS`)
