# Section
Frontend web app (interactive troubleshooting) and user experience

## Summary
A single-page frontend that lets an operator submit error logs or a trace stack, upload supporting files, and interactively refine troubleshooting with retained context across turns. The UI returns triage results (ranked hypotheses, runbook steps, proposed patch snippets, risk/rollback guidance, and next checks). MVP goals:
- End-to-end user flow (submit → results) completes in < 60 seconds under normal load.
- Safe, readable rendering of markdown and code blocks with clickable citations linking to source docs/snippets.
- Small, maintainable stack: React + Vite (or Next.js if server rendering desired) deployed to S3 + CloudFront for fast delivery.

## Design
High-level architecture and UI/component design decisions:

- Tech stack
  - UI: React (functional components + hooks) + Vite for fast iteration. Optionally Next.js if SSR or routing is needed later.
  - State & data fetching: React Query (or SWR) for background polling, caching, retry strategies.
  - Markdown rendering: a sanitizer + markdown parser (e.g., marked/remark + DOMPurify) and syntax highlighting (Prism.js or Highlight.js).
  - Uploads: presigned S3 PUT flow (backend issues presigned URL).
  - Build & host: static build to S3 + CloudFront. CI pipeline (GitHub Actions) to build & deploy.
  - Telemetry: client-side metrics (browser timing), error logs (Sentry/Datadog RUM), and request tracing (include request-id header returned/displayed).

- API contract (MVP)
  - POST /triage
    - Request: { error_log?: string, trace_stack?: string, context?: {service?, env?, region?}, attachments?: [{name,size,type}], clientRequestId: string, conversation_id?: string }
    - Response:
      - 202 Accepted: { operationId: string } (if server processes asynchronously)
      - or 200 with results: { hypotheses: [...], runbooks: [...], patches: [...], citations: [...], nextChecks: [...] }
  - GET /triage/{operationId}/results
    - Response: same results object when ready, or { status: "pending" }.
  - POST /upload-presign
    - Request: { filename, contentType, size, clientRequestId }
    - Response: { uploadUrl, key, expiresIn }
  - Attachments then uploaded directly to the returned uploadUrl (PUT), client notifies server of completed uploads if required.

- UI pages/components (MVP)
  - Single page app layout:
    - Error log / trace stack text area (required)
    - Optional context fields: service, env, region (selects or free text)
    - Upload component: drag/drop + file list + progress bar using presigned URL flow
    - Submit button -> triggers triage
    - Conversation thread: shows prior user inputs, assistant summaries, and selected hypotheses (linked to conversation_id)
    - Follow-up input: ask clarifying questions without re-uploading logs
    - Results sections (rendered when results available):
      - Ranked hypotheses: confidence score + supporting citations (clickable)
      - Runbook steps: step text, command blocks with "Copy" buttons
      - Proposed fix patches: code diff blocks, "Copy patch" and download
      - Risk / rollback guidance
      - Next checks (actions to run)
  - Small, focused components:
    - LogInputForm, ContextFields, UploadList, ResultPanel, HypothesisCard, RunbookStep (with copy), CitationLink (with snippet preview), CodeBlock, MarkdownRenderer, LoadingSkeleton, ErrorBanner.

- UX details
  - Use progressive disclosure: show top hypothesis first, allow expanding for full details.
  - Show confidence numeric and color-coded badges.
  - Citations show doc title + short snippet; click opens doc in a new tab. Hover shows snippet preview (accessible tooltip).
  - Provide request ID and timestamp in a small footer on results for debugging.
  - Keyboard-accessible copy buttons and focus states following WCAG 2.1 AA basics.

- Security & safety
  - Sanitize all rendered markdown/HTML with DOMPurify (configured to allow safe code blocks).
  - CSP: disallow inline scripts/styles; only allow trusted sources.
  - Presigned URLs: short TTL (e.g., 5–15 minutes), server validates file metadata and size prior to issuing URL.
  - Client-side validation: max file size (e.g., 20 MB per file), allowed file types.
  - Do not render raw HTML from untrusted sources except after strict sanitization; escape where appropriate.
Non-goals
- No complex multi-tenant admin console in MVP.
- No offline support or mobile-native app in MVP.

## Implementation Steps
Step-by-step tasks organized for sprintable execution (approximate order; can be parallelized):

1. Project scaffold (1 day)
   - Create repository, install React + Vite (or Next.js), TypeScript, ESLint, Prettier.
   - Add React Query, axios/fetch wrapper, DOMPurify, markdown parser, clipboard helper, file drop library (react-dropzone), and syntax highlighter.

2. API client + request-id header (0.5 day)
   - Implement apiClient wrapper that adds a uuidv4 clientRequestId header to all requests and exposes it to UI.
   - Expose helper to show request-id on results for debugging.

3. Design system & components baseline (2 days)
   - Implement layout + responsive styles.
   - Create form components: LogInputForm, ContextFields, SubmitButton with disabled states.

4. File upload (presigned URL) flow (1.5 days)
   - Implement UploadList component with drag/drop, file validation (type/size), and preview of filename/size.
   - Call POST /upload-presign per file to receive uploadUrl; perform PUT upload with progress events; show progress bar and success/error states.
   - On upload success, record S3 key in triage request payload or call server notify endpoint if required.

5. Triage request lifecycle and polling (1.5 days)
   - On submit, call POST /triage with error_log or trace_stack + context + attachment keys + clientRequestId + conversation_id (if present).
   - If 202 + operationId received, poll GET /triage/{operationId}/results with exponential backoff (start 1s, then 1.5s), max total wait 50s (configurable).
   - If 200 returned synchronously, render results immediately.
   - Show loading skeleton and progress indicator; show elapsed time and request-id.

6. Results rendering components (2 days)
   - Implement HypothesisCard: confidence badge, short explanation, citation list.
   - Implement CitationLink: clickable title + snippet; open in new tab; tooltip/modal preview on hover/focus.
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
    - Integration/E2E tests (Cypress or Playwright) for the full flow with a mocked backend (including upload flow).
    - Accessibility checks with axe-core.

11. CI/CD and deployment (1 day)
    - Configure GitHub Actions to build, run tests, and deploy static site to S3 + invalidate CloudFront cache.
    - Add environment-specific configuration (staging/prod).

12. Monitoring & observability (0.5 day)
    - Send client-side performance metrics (time to first result, upload durations) to telemetry.
    - Capture errors and attach request-id for server-side lookup.

13. Final QA & performance tuning (0.5–1 day)
    - Verify full flow completes within target < 60s in staging. Adjust polling, concurrent uploads, and build optimizations if needed.

## Risks
Identified risks and mitigations:

- Long model/server processing times
  - Mitigation: asynchronous API with polling; show progress; set clear timeout and fallback messaging; consider streaming or server push later.

- Large or malicious uploads
  - Mitigation: enforce client & server size/type limits; server-side validation on upload completion; presigned URL TTLs.

- XSS via markdown or code rendering
  - Mitigation: strict sanitization (DOMPurify), CSP headers, no dangerouslySetInnerHTML without sanitization.

- Rate limiting / quota exhaustion
  - Mitigation: handle 429 responses gracefully with Retry-After; surface actionable messages; add client-side debounce for repeated submits.

- Data leakage (sensitive info in uploads/results)
  - Mitigation: redact PII at server; access controls; short-lived presigned URLs; user warning about sensitive data.

- Clipboard and browser permissions
  - Mitigation: use standard Clipboard API with fallbacks; ensure copy buttons are keyboard accessible and labeled.

- Browser compatibility and performance on low-end devices
  - Mitigation: keep bundle small, code-split heavy components, test on key target browsers.

## Dependencies
Systems, services, and teams required:

- Backend triage API endpoints: POST /triage, GET /triage/{id}/results
- Upload presign endpoint: POST /upload-presign (backend)
- S3 bucket for uploads and static hosting; CloudFront distribution
- Auth: if app requires auth, Cognito/OAuth provider and token flows
- Runbook/document database or service providing citation URLs and snippets
- CI/CD (GitHub Actions or equivalent)
- Monitoring/telemetry (Sentry, Datadog, CloudWatch)
- Design assets and copy from Product/Design team (icons, color tokens)
- Security review for presigned URL usage and CSP
- QA team for acceptance testing and performance validation

## Acceptance Criteria
The app is acceptable when all of the following are validated (measurable where possible):

- Functional
  - User can submit error logs or a trace stack, optional context, and 1+ attachment and receive triage results.
  - Uploads use presigned URL flow; upload shows progress and reports success/failure.
  - Results include: ranked hypotheses (with confidence), runbook steps, proposed patches, risk/rollback guidance, and next checks.
  - "Copy" buttons for runbook commands and patches work (keyboard accessible) and place expected content on clipboard.
  - Citations are clickable; each citation shows doc title + a readable snippet on hover or in a preview, and opens source doc in a new tab.

- Performance & reliability
  - Typical end-to-end flow (submit → first usable result) completes in under 60 seconds in staging under nominal load. (Define target percentile, e.g., median < 30s, 95th percentile < 60s.)
  - UI shows clear loading states and timeouts; when backend returns rate limit or budget denied, user sees a helpful message with steps.

- Security & safety
  - All markdown and code blocks are rendered safely (sanitized) with no executable scripts or inline event handlers allowed.
  - Presigned upload URLs have short TTLs; file client-side validation prevents oversized uploads.
  - Request-id header included in outbound API calls and displayed in results footer for debugging.

- Quality & accessibility
  - Unit tests and E2E tests covering main flows pass in CI.
  - Basic accessibility checks pass (no high-severity axe-core violations for main pages).
  - App builds and deploys to S3 + CloudFront via CI pipeline and is reachable in the assigned staging environment.

- Observability
  - Client-side metrics (time to results, upload time) and error logs are emitted and associated with request-id for server correlation.

Meeting these criteria signals the frontend is ready for MVP release; any deviations must be documented with mitigation or a plan for follow-up.

## Outcomes
- End-to-end UX for submit → triage → explain with citations and copyable runbook output.
- Secure upload and safe rendering aligned with backend guardrails.
- Observable client flow with request-id correlation.

## Decisions
- **Stack**: React + Vite (Next.js only if SSR needed later).
- **Uploads**: presigned S3 PUT flow (short TTL).
- **Rendering**: sanitized markdown with code highlighting.

## Deliverables
- SPA with log/trace submission, upload flow, and result rendering.
- Components for hypotheses, runbook steps, patches, citations, and next checks.
- Client-side telemetry and error tracking with request-id.

## Implementation tasks
Concrete task list (assignable, PR-sized items)
1. Scaffold project + CI (owner: frontend) — 0.5–1 day
2. API client with request-id + error mapping (owner: frontend) — 0.5 day
3. Log/trace input form + context fields (owner: frontend) — 0.5–1 day
4. Presigned upload flow + progress UI (owner: frontend) — 1–2 days
5. Submit + polling lifecycle (owner: frontend) — 1 day
6. Results rendering (hypotheses/runbook/patches/citations) (owner: frontend) — 1–2 days
7. Safe markdown + code highlighting (owner: frontend) — 0.5–1 day
8. Tests + accessibility checks (owner: frontend/QA) — 1–2 days
