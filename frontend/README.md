# Troubleshoot Frontend

A Vite/React UI for the Troubleshoot Stack API. It renders the triage/explain conversation, surfaces tool calls and fix steps, and shows live ops metrics.

## Quick start

1. Copy `.env.example` to `.env` and set values.
2. Install dependencies: `npm install` (or `pnpm install`).
3. Run dev server: `npm run dev`.

## Environment variables

- `VITE_API_BASE_URL`: API Gateway base URL (custom domain or invoke URL).
- `VITE_API_KEY`: API key injected at build time.

## Behavior notes (current implementation)
- First message calls `/triage`; subsequent messages call `/explain`.
- Client-side redaction runs before submission and reports `redaction_hits`.
- Tool calls from the API are shown with copy-to-clipboard; pasted output is sent as `tool_results`.
- Live panels poll `/metrics/summary` and `/budget/status` every 15 seconds.
