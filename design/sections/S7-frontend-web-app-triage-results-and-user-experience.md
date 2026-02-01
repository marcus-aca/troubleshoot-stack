# Section
Frontend web app: triage results and user experience

## Current implementation (source of truth)
- **Framework**: Vite + React (`frontend/`).
- **Flow**: first message -> `/triage`, subsequent messages -> `/explain`.
- **Redaction**: client-side regex redaction before sending to API; `redaction_hits` are reported.
- **Tool calls**: surfaced in the UI with copy-to-clipboard; pasted output is sent as `tool_results`.
- **Results view**: assistant response, next question, hypotheses (when `final`), and fix steps.
- **Ops panels**: live polling of `/metrics/summary` and `/budget/status`.

## Not implemented yet (by code)
- Auth beyond an API key provided at build time.
- Citation rendering UI (evidence excerpts are not displayed).
- Multiple tool calls per turn.
