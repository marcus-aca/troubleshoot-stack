# Section
Frontend web app (interactive troubleshooting) and user experience

## Summary
A single-page frontend that lets an operator submit error logs or a trace stack, and interactively refine troubleshooting with retained context across turns. The UI renders triage results (ranked hypotheses, runbook steps, proposed patch snippets, risk/rollback guidance, and next checks). MVP goals:
- End-to-end user flow (submit → results) completes in < 60 seconds under normal load.
- Safe, readable rendering of markdown and code blocks with citations linked to evidence lines from the input.
- Small, maintainable stack: React + Vite (or Next.js if SSR is needed later) deployed to S3 behind CloudFront.

## Design
High-level architecture and UI/component design decisions:

- Tech stack
  - UI: React (functional components + hooks) + Vite for fast iteration. Optionally Next.js if SSR or routing is needed later.
  - State & data fetching: React Query (or SWR) for caching, retries, and request dedupe.
  - Markdown rendering: a sanitizer + markdown parser (e.g., marked/remark + DOMPurify) and syntax highlighting (Prism.js or Highlight.js).
  - Build & host: static build uploaded to the Terraform-managed `frontend_bucket` (S3) and served through CloudFront with OAC; the bucket remains private.
  - Telemetry: client-side metrics (browser timing), error logs (Sentry/Datadog RUM), and request tracing (include `x-request-id` header and display `X-Request-Id` from responses).

- API contract (MVP, per `services/api`)
  - Headers: `x-api-key` for auth; optional `x-request-id` for client-generated request IDs (server always returns `X-Request-Id`).
  - POST /triage
    - Request: `{ request_id?, conversation_id?, source?, raw_text, timestamp? }` (`raw_text` is required).
    - Response (200): canonical response with `request_id`, `timestamp`, `hypotheses[]`, `runbook_steps[]`, `proposed_fix?`, `risk_notes[]`, `rollback[]`, `next_checks[]`, `metadata`, and `conversation_id`.
  - POST /explain
    - Request: `{ request_id?, conversation_id?, question, incident_frame? }` (`question` is required).
    - Response (200): same canonical response schema as `/triage`.
  - GET /status
    - Response (200): `{ status, timestamp, dependencies[] }` where `dependencies` is a string list.
  - Errors: FastAPI error bodies for validation and 4xx/5xx, plus RFC 7807 when configured by gateway.

- UI pages/components (MVP)
  - Single page app layout:
    - Error log / trace stack text area (required)
    - Source selector or hidden default (e.g., `source: "user"`) for API compliance
    - Optional context fields: service, env, region (local-only hints shown in UI; not sent to API unless added later)
    - Submit button -> triggers `/triage`
    - Conversation thread: prior user inputs, assistant summaries, and selected hypotheses (linked to `conversation_id`)
    - Follow-up input: ask clarifying questions via `/explain` using `question` and `conversation_id`
    - Results sections (rendered when results available):
      - Ranked hypotheses: confidence score + supporting citations (clickable)
      - Runbook steps: step text, command blocks with "Copy" buttons
      - Proposed fix patches: code diff blocks, "Copy patch" and download
      - Risk / rollback guidance
      - Next checks (actions to run)
  - Small, focused components:
    - LogInputForm, ContextFields, ResultPanel, HypothesisCard, RunbookStep (with copy), CitationLink (log line preview), CodeBlock, MarkdownRenderer, LoadingSkeleton, ErrorBanner.

- UX details
  - Use progressive disclosure: show top hypothesis first, allow expanding for full details.
  - Show confidence numeric and color-coded badges.
  - Citations map to evidence lines from the submitted log; clicking jumps to the highlighted log snippet or opens a modal preview.
  - Provide request ID and timestamp in a small footer on results for debugging.
  - Keyboard-accessible copy buttons and focus states following WCAG 2.1 AA basics.

- Security & safety
  - Sanitize all rendered markdown/HTML with DOMPurify (configured to allow safe code blocks).
  - CSP: disallow inline scripts/styles; only allow trusted sources.
  - Client-side validation: require non-empty payload and basic input length limits to avoid accidental large pastes.
  - Do not render raw HTML from untrusted sources except after strict sanitization; escape where appropriate.
Non-goals
- No complex multi-tenant admin console in MVP.
- No offline support or mobile-native app in MVP.

## Implementation Steps
Step-by-step tasks organized for sprintable execution (approximate order; can be parallelized):

1. Project scaffold (1 day)
   - Create repository, install React + Vite (or Next.js), TypeScript, ESLint, Prettier.
   - Add React Query, axios/fetch wrapper, DOMPurify, markdown parser, clipboard helper, and syntax highlighter.

2. API client + request-id header (0.5 day)
   - Implement apiClient wrapper that adds `x-request-id` (uuidv4) and `x-api-key` to all requests and exposes it to UI.
   - Surface `X-Request-Id` from responses in the results footer for debugging.

3. Design system & components baseline (2 days)
   - Implement layout + responsive styles.
   - Create form components: LogInputForm, ContextFields, SubmitButton with disabled states.

4. Triage request lifecycle (1 day)
   - On submit, call POST /triage with `{ source, raw_text, timestamp?, conversation_id? }`.
   - Always send `x-request-id` and `x-api-key` headers; display the returned `X-Request-Id`.
   - Render results immediately on 200; show loading skeleton and elapsed time while waiting.

5. Explain request lifecycle (0.5 day)
   - On follow-up, call POST /explain with `{ question, conversation_id, request_id? }`.
   - Allow advanced UI to pass `incident_frame` when the operator has one.

6. Results rendering components (2 days)
   - Implement HypothesisCard: confidence badge, short explanation, citation list.
   - Implement CitationLink: clickable evidence reference that opens a modal/snippet preview and highlights lines in the input.
   - Implement RunbookStep: markdown renderer for step text, code blocks with copy button (accessible), and optional "Run locally" tooling placeholder.
   - Implement PatchDisplay: show diff with syntax highlight and "Copy patch" and "Download" buttons.
   - Implement Risk/Rollback section and NextChecks list as markdown.

7. Safe markdown & code rendering (1 day)
   - Use remark/marked to convert markdown to HTML.
   - Sanitize output with DOMPurify; allow safe tags for code blocks and links; strip scripts and event attributes.
   - Syntax highlight code blocks on render.

8. Loading states & error handling (1 day)
   - Implement global ErrorBanner for API errors (budget denied, rate limited, network).
   - Map backend error codes to user-friendly messages and retry suggestions.
   - Implement rate limit handling with Retry-After awareness and display.

9. Accessibility and keyboard flows (0.5–1 day)
   - Ensure all interactive elements are keyboard accessible, have ARIA labels where needed, contrast checks, and focus management.
   - Add skip link and ensure form labels are associated.

10. Tests (1.5 days)
    - Unit tests for components and API client.
    - Integration/E2E tests (Cypress or Playwright) for the full flow with a mocked backend.
    - Accessibility checks with axe-core.

11. CI/CD and deployment (1 day)
    - Configure GitHub Actions to build, run tests, and deploy static site to the S3 frontend bucket.
    - Invalidate CloudFront on deploy; keep the S3 bucket private and serve via CloudFront only.
    - Add environment-specific configuration (staging/prod).

12. Monitoring & observability (0.5 day)
    - Send client-side performance metrics (time to first result) to telemetry.
    - Capture errors and attach request-id for server-side lookup.

13. Final QA & performance tuning (0.5–1 day)
    - Verify full flow completes within target < 60s in staging. Adjust timeouts and build optimizations if needed.

## Risks
Identified risks and mitigations:

- Long model/server processing times
  - Mitigation: show progress; set clear timeout and fallback messaging; consider streaming or server push later.

- XSS via markdown or code rendering
  - Mitigation: strict sanitization (DOMPurify), CSP headers, no dangerouslySetInnerHTML without sanitization.

- Rate limiting / quota exhaustion
  - Mitigation: handle 429 responses gracefully with Retry-After; surface actionable messages; add client-side debounce for repeated submits.

- Data leakage (sensitive info in logs/results)
  - Mitigation: redact PII at server; access controls; user warning about sensitive data.

- Clipboard and browser permissions
  - Mitigation: use standard Clipboard API with fallbacks; ensure copy buttons are keyboard accessible and labeled.

- Browser compatibility and performance on low-end devices
  - Mitigation: keep bundle small, code-split heavy components, test on key target browsers.

## Dependencies
Systems, services, and teams required:

- Backend triage API endpoints: POST /triage, POST /explain, GET /status
- CloudFront distribution in front of the frontend S3 bucket (private bucket + OAC)
- Auth: if app requires auth, Cognito/OAuth provider and token flows
- CI/CD (GitHub Actions or equivalent)
- Monitoring/telemetry (Sentry, Datadog, CloudWatch)
- Design assets and copy from Product/Design team (icons, color tokens)
- Security review for CSP and frontend hosting configuration
- QA team for acceptance testing and performance validation

## Acceptance Criteria
The app is acceptable when all of the following are validated (measurable where possible):

- Functional
  - User can submit error logs or a trace stack, optional local context, and receive triage results.
  - Results include: ranked hypotheses (with confidence), runbook steps, proposed patches, risk/rollback guidance, and next checks.
  - "Copy" buttons for runbook commands and patches work (keyboard accessible) and place expected content on clipboard.
  - Citations are clickable; each citation shows the relevant log snippet (line range) in a preview and can jump to that location in the input.

- Performance & reliability
  - Typical end-to-end flow (submit → first usable result) completes in under 60 seconds in staging under nominal load. (Define target percentile, e.g., median < 30s, 95th percentile < 60s.)
  - UI shows clear loading states and timeouts; when backend returns rate limit or budget denied, user sees a helpful message with steps.

- Security & safety
  - All markdown and code blocks are rendered safely (sanitized) with no executable scripts or inline event handlers allowed.
  - Client-side validation prevents empty submissions and overly large payloads.
  - `x-request-id` header included in outbound API calls and displayed in results footer for debugging.

- Quality & accessibility
  - Unit tests and E2E tests covering main flows pass in CI.
  - Basic accessibility checks pass (no high-severity axe-core violations for main pages).
  - App builds and deploys to the S3 frontend bucket via CI pipeline and is reachable in the assigned staging environment via CloudFront.

- Observability
  - Client-side metrics (time to results) and error logs are emitted and associated with request-id for server correlation.

Meeting these criteria signals the frontend is ready for MVP release; any deviations must be documented with mitigation or a plan for follow-up.

## Outcomes
- End-to-end UX for submit → triage → explain with citations and copyable runbook output.
- Safe rendering aligned with backend guardrails.
- Observable client flow with request-id correlation.

## Decisions
- **Stack**: React + Vite (Next.js only if SSR needed later).
- **Uploads**: not in MVP; logs are pasted into `raw_text` input.
- **Rendering**: sanitized markdown with code highlighting.

## Deliverables
- SPA with log/trace submission and result rendering served via CloudFront + S3.
- Components for hypotheses, runbook steps, patches, citations, and next checks.
- Client-side telemetry and error tracking with request-id.

## Implementation tasks
Concrete task list (assignable, PR-sized items)
1. Scaffold project + CI (owner: frontend) — 0.5–1 day
2. API client with request-id + error mapping (owner: frontend) — 0.5 day
3. Log/trace input form + context fields (owner: frontend) — 0.5–1 day
4. Submit lifecycle for `/triage` + `/explain` (owner: frontend) — 1 day
5. Results rendering (hypotheses/runbook/patches/citations) (owner: frontend) — 1–2 days
6. Safe markdown + code highlighting (owner: frontend) — 0.5–1 day
7. CI/CD deploy to S3 + CloudFront invalidation (owner: frontend/infra) — 0.5–1 day
8. Tests + accessibility checks (owner: frontend/QA) — 1–2 days
9. Monitoring hooks + error reporting (owner: frontend) — 0.5 day
