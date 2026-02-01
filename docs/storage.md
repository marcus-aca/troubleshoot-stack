# Storage model (current implementation)

This document describes how inputs, incident frames, and canonical responses are persisted today.

## Storage modes
- **DynamoDB** (enabled when `USE_DYNAMODB=true`): production-style persistence.
- **In-memory** (default): local/dev fallback using in-process dictionaries.

## Tables (DynamoDB)
- **Inputs table** (TTL)
  - Stores raw user inputs keyed by `input_id` for deterministic citations.
  - Stores derived artifacts as separate items:
    - `item_type=incident_frame`
    - `item_type=canonical_response`
- **Conversation events table** (TTL)
  - PK: `conversation_id`
  - SK: `event_id` (`<epoch>#<request_id>`)
  - Stores per turn: raw input, incident frame, canonical response.
- **Conversation state table** (TTL)
  - PK: `conversation_id`
  - Stores latest incident frame + response summary for fast context assembly.
- **Sessions table** (TTL)
  - PK: `conversation_id`
  - Tracks latest request/input for quick lookups.
- **Budget table** (TTL managed by window keys)
  - PK: `user_id`
  - SK: `usage_window`
  - Tracks token usage within a time window.

## Write flow
### /triage
1. Save raw input (inputs table).
2. Parse to incident frame.
3. Save incident frame (inputs table, `item_type=incident_frame`).
4. Build canonical response.
5. Save canonical response (inputs table, `item_type=canonical_response`).
6. Append conversation event.
7. Update conversation state.

### /explain
- If an incident frame is supplied, it is merged with the latest frame.
- If no frame is supplied, the API attempts to reuse the latest frame from conversation state.
- The response is persisted the same way as /triage.

## LLM context
`build_llm_context` pulls conversation state + recent events to assemble a compact prompt payload for the LLM adapter.

## TTL defaults
- Inputs: 1 day (`INPUT_TTL_SECONDS`)
- Conversation events/state: 7 days (`CONVERSATION_TTL_SECONDS`)
