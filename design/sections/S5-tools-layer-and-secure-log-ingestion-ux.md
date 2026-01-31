# Section
Tools layer and secure log ingestion UX

## Summary
Provide a secure, user-friendly tool flow that lets users upload error logs or trace stacks (terraform logs, kubectl describe output, installer logs, stack traces) without pasting them into chat. The backend will accept uploads via pre-signed S3 URLs, perform server-side PII/secret redaction, extract structured signals (error lines, stack frames, resource names, timestamps, resource IDs), store only the redacted artifact (with a short TTL) and metadata, and surface the extracted signals to the explanation/assistant pipeline. The goal is an MVP that improves assistant accuracy while minimizing risk of sensitive data leakage.

Key constraints:
- Max file size: 1–2 MB (configurable)
- Pre-signed PUT URL TTL: short (e.g., 5 minutes)
- Redacted object TTL: 7 days (configurable lifecycle)
- No raw file contents persisted or logged

## Design
Goals
- Reduce copy/paste risk by enabling secure uploads with redaction and structured extraction.
- Provide deterministic, auditable evidence artifacts for /explain citations.
- Keep uploads small and short-lived to minimize exposure and cost.
Non-goals
- No long-term raw log storage or cross-user log sharing.
- No LLM-based redaction in MVP; rule-based only.

High-level flow
1. UI requests an upload URL from API (POST /upload-url).
2. Backend validates user/session and returns a pre-signed S3 PUT URL + object key.
3. UI PUTs the file directly to S3 using the pre-signed URL.
4. UI notifies backend that upload completed (POST /analyze-upload) including object key and user_id.
5. Backend fetches the object server-side (GetObject), validates content-type/size/hash, runs redaction, writes redacted version to S3 under a user-specific restricted prefix, performs structured extraction, emits tracing spans and metadata, and returns extracted signals to the caller.
6. The assistant's `/explain` pipeline consumes the extracted signals to improve contextual explanations.

Data model and storage
- Object key naming:
  - Upload temp key: uploads/<user_id>/<uuid>.uploaded (used for pre-signed PUT)
  - Redacted stored key: redacted/<user_id>/<uuid>.redacted.log
- Only redacted key is retained beyond immediate processing; original uploaded object is deleted post-processing or placed in a quarantined prefix with immediate lifecycle expiry if needed for debugging (disabled in prod).
- Metadata stored in DB (or DynamoDB) per upload: user_id, object_key_redacted, sha256(redacted), size, extracted_signals_count, timestamp, server-side redaction_count, scan_version.
- S3 encryption: server-side encryption with KMS (SSE-KMS) or SSE-S3 depending on org requirements.
- IAM: pre-signed PUT only allows writing to the specific uploads/<user_id>/<uuid>.uploaded key. Backend service role must be able to GetObject/PutObject/DeleteObject on relevant prefixes.

Redaction strategy
- Conservative, rule-based redaction by default (MVP): regex-driven removals/substitutions with allowlist/denylist approach for patterns we know are high risk.
- Patterns to redact (examples):
  - AWS Access Key ID: AKIA[0-9A-Z]{16}
  - AWS Secret Access Key (candidate): (?<![A-Za-z0-9/+=])[A-Za-z0-9/+=]{40}(?![A-Za-z0-9/+=])
  - Bearer/JWT tokens: Bearer\s+[A-Za-z0-9\-_.=]+\.[A-Za-z0-9\-_.=]+(?:\.[A-Za-z0-9\-_.=]+)?
  - Generic long base64-like secrets (configurable length threshold)
  - Emails: \b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b
  - kube tokens/service account tokens: patterns beginning with eyJ[A-Za-z0-9-_=.]{10,}
  - MAC addresses: (?:[0-9A-F]{2}[:-]){5}[0-9A-F]{2} and [0-9A-F]{4}\.[0-9A-F]{4}\.[0-9A-F]{4}
  - Passport numbers (keyworded): passport(?:\s*no|\s*number)?\s*[:#-]*[A-Z0-9]{6,9}
  - Driver's license numbers (keyworded): driver'?s?\s*licen[cs]e|DL|D/L
  - Business/tax numbers (keyworded): EIN|TIN|VAT|ABN|BN|GST|Business No|Company No
- Redaction output: replace matches with placeholders such as [REDACTED-<TYPE>] or mask partial characters (e.g., AKIAxxxxxxxxxxxxxx).
- Maintain an audit-safe record: do not keep original matched substring; instead increment a redaction_count and record pattern IDs (not matched values) for telemetry.

Signal extraction
- Parsers extract structured items: lines containing ERROR/FAIL/Exception, resource identifiers (ARNs, pod/namespace names), timestamps, command snippets, status codes.
- Extraction output format: JSON array of signals with fields {type, value, source_line, confidence_score}
- Provide a "summary" short text (3–6 lines) summarizing top findings to feed `/explain`.

UX behavior
- UI shows a simple file picker and progress. After upload, UI displays:
  - upload success
  - number of redactions (e.g., “3 sensitive values were removed”)
  - short extracted summary
  - a button to attach selected signals/context to the chat message
- If redaction removed a substantial portion of the file (configurable threshold), prompt user to confirm or re-upload with a different file.

Tracing and observability
- Emit spans for: tool_s3_fetch, tool_redact, tool_extract
- Include non-sensitive attributes: user_id, object_key_redacted, bytes_processed, redaction_count, extracted_signals_count
- Log only hashes and metadata; never raw contents.

API contract (MVP)
- POST /upload-url
  - Request: { user_id, file_name, content_type (optional), max_size (optional) }
  - Response: { presigned_put_url, upload_key, expires_at }
- POST /analyze-upload
  - Request: { user_id, upload_key, uploaded_sha256 (optional) }
  - Response: { redacted_key, redaction_count, extracted_signals: [...], summary, status }
- Errors: 400 for validation issues, 401/403 for auth, 413 for too-large file, 500 for server errors.

## Implementation Steps
1. Design & schema (1–2 days)
   - Finalize object key patterns, DB metadata schema, lifecycle TTL values, IAM policies, and KMS key usage.
   - Decide default TTLs: presigned_url_ttl = 5 minutes, redacted_object_ttl = 7 days.
   - Owner: Backend lead.

2. Build S3 pre-signed URL endpoint (3 days)
   - Implement POST /upload-url
   - Validate user/session, enforce content type white-list and max_size, generate random uuid, construct upload_key in uploads/<user_id> prefix, create V4 presigned PUT with content-length-range and content-type constraints.
   - Return presigned URL, upload_key, and expires_at.
   - Tests: unit tests for key generation & TTL, integration test for PUT to returned URL.

3. Frontend upload UI (2–4 days)
   - File picker, size check in client, PUT to presigned URL with progress UI, handle presign expiry and retries, show success and call analyze endpoint.
   - UX: show warning if redaction removes content (after analyze).

4. Backend analyze pipeline (5–8 days)
   - Implement POST /analyze-upload which:
     - Validates user/auth and upload_key ownership.
     - Performs server-side GetObject for uploads/<user_id>/<uuid>.uploaded.
     - Re-checks content-type, max_size, and computes SHA256.
     - Runs redaction module on the full text.
     - Stores redacted output to redacted/<user_id>/<uuid>.redacted.log with SSE-KMS and object ACL private.
     - Delete or expire the uploaded object (immediately DeleteObject or set a quarantined prefix with a short lifecycle).
     - Runs signal extraction and prepares summary.
     - Write metadata record to DB and emit tracing spans.
     - Return redaction_count, extracted_signals, summary, redacted_key.
   - Tests: unit tests for each step, integration test end-to-end, property tests for redaction edge cases.

5. Implement redaction module (4–6 days)
   - Create a configurable rule engine for regex patterns and redaction actions (mask vs remove).
   - Implement ability to register pattern IDs and disable/enable patterns at runtime.
   - Ensure deterministic placeholders ([REDACTED-AWS_KEY]) without leaking matched content.
   - Add unit tests with positive and negative cases (verify no unredacted secrets remain).
   - Provide a small CLI/test harness to run on local sample logs.

6. Implement extraction module (3–5 days)
   - Basic parsers for error lines, ARNs, names, resource IDs, timestamps.
   - Confidence scoring heuristics and deduplication.
   - Unit tests and sample-corpus integration tests.

7. Observability & tracing (2 days)
   - Emit spans: tool_s3_fetch, tool_redact, tool_extract with safe attributes.
   - Add metrics: uploads_count, redactions_total, extracted_signals_total, upload_failures_by_reason.

8. Security review & hardened config (2–3 days)
   - Review regex rules for false positives/negatives and avoid over-broad base64 redaction that will redact benign strings.
   - Ensure no raw contents are logged anywhere in pipeline.
   - Validate IAM/KMS policies, SSE usage, and S3 bucket policies to restrict public access.

9. Testing, QA & rollout (3–5 days)
   - E2E tests, exploit tests (malicious large uploads, boundary cases), performance tests.
   - Staged rollout: feature-flagged for limited users, monitor metrics and error rates, then full rollout.

10. Documentation & support (1–2 days)
    - Update developer docs (API spec, pattern docs), user-facing help text explaining what is redacted and TTLs.
    - Provide support runbook for false redaction and reprocessing.

## Risks
- False negatives/positives in redaction
  - Risk: sensitive items escape redaction (false negative) or benign info is removed (false positive).
  - Mitigation: start conservative (only high-confidence patterns), maintain a pattern tuning process, add test corpus and CI checks for no-secret leakage, provide a feedback path for users to flag over-redaction.

- Leakage via logs/telemetry
  - Risk: raw file content could be inadvertently logged.
  - Mitigation: code review & lint rules to prevent logging contents; only log SHA256, size, counts, and pattern IDs.

- Malicious or very large uploads
  - Risk: DoS or high processing cost.
  - Mitigation: enforce client and server size limits, reject oversized uploads (413), rate-limit upload endpoints, validate content-type and max_size during presign request.

- S3 misconfiguration (public read)
  - Risk: accidental public exposure.
  - Mitigation: bucket policy denies public access, enforce SSE, use private prefixes, least-privilege IAM for presign generation.

- Incorrect IAM permissions for presigned PUT
  - Risk: user could upload outside allowed prefix.
  - Mitigation: generate presigned URL only for exact key, and constrain in presign request; test IAM policies.

- Over-reliance on regex-based extraction
  - Risk: brittle extraction logic leading to poor assistant outputs.
  - Mitigation: keep extraction simple for MVP, iterate with telemetry, and add ML-based extractors later.

## Dependencies
- Storage: S3-compatible object store with support for presigned PUTs and SSE-KMS
- Auth: existing authentication/authorization system to identify user_id and enforce per-user prefixes
- KMS: for SSE-KMS (optional based on policy)
- Database: metadata storage (RDBMS or DynamoDB) for upload metadata and audit
- Observability: tracing and metrics backend (OpenTelemetry/Jaeger/Prometheus)
- Frontend: UI components to perform PUTs to presigned URL and call analyze API
- Backend libraries: reliable regex engine, streaming read/write, hash (sha256) computation, robust content-type parsing
- Security review team and legal for compliance checks (PII handling)
- Test corpus with representative logs for QA

## Acceptance Criteria
- Functional
  - A user can successfully upload a <=2 MB log file through the UI without pasting into chat.
  - POST /upload-url returns a working presigned PUT URL that accepts the file; UI can PUT to it and receive success.
  - POST /analyze-upload triggers server-side fetch, redaction, extraction and returns:
    - redacted_key (S3 path), redaction_count, extracted_signals array, and short summary.
  - Redaction is applied: known sensitive patterns (covered by unit tests) are removed or masked in the stored redacted object.
  - Extracted signals include at least error lines and top 3 resource identifiers (when present).
  - The assistant’s /explain endpoint consumes the extracted_signals and demonstrates measurable improvement in a set of sample queries (benchmarked on sample corpus).

- Security & Privacy
  - No raw file contents are present in logs or telemetry; only hashes/metadata and counts are logged.
  - Uploaded objects are stored under per-user prefixes and accessible only by backend service roles.
  - Redacted objects are stored with SSE (KMS or S3) and a lifecycle policy configured to delete after 7 days.
  - Pre-signed URL TTL is short (<= 5 minutes) and keys are scoped to a specific key.

- Observability & Reliability
  - Tracing spans tool_s3_fetch, tool_redact, tool_extract are emitted for each analyze run with safe attributes.
  - Metrics are emitted: uploads_count, upload_failures_by_reason, redactions_total, extracted_signals_total.
  - E2E tests cover happy path and error cases (invalid file type, oversized file, expired presign).

- Testing & Rollout
  - Unit tests for redaction patterns and extraction pass in CI.
  - Integration/E2E test asserts that sensitive patterns from a curated test corpus are not present in redacted objects.
- Feature is behind a flag for staged rollout; first rollout to internal users and then to broader customers after monitoring for 1–2 days.

## Tooling approach (MVP)
### Secure log bundle upload
- Web UI allows user to upload a text file (e.g., `terraform.log`, `kubectl describe.txt`)
- Backend creates **pre-signed S3 URL** for upload (short TTL)
- After upload, API:
  - downloads server-side (GetObject)
  - runs **PII/secret redaction** (regex for tokens, keys, emails)
  - stores redacted version in S3 with TTL lifecycle policy
  - extracts structured signals (error lines, resource names)
- Tool result summarized and fed into `/explain`

## Security considerations
- Enforce content-type and max size (e.g., 1–2 MB) at presign and server-side validation
- Use separate S3 prefix per `user_id`
- Object lifecycle expiration (e.g., 7 days) on redacted objects
- Do not log raw file contents; log only hashes/metadata (sha256, size, redaction_count)
- Use SSE-KMS (recommended) or SSE-S3, and ensure bucket policy denies public access

## Outcomes
- Secure upload workflow that yields redacted, structured signals for /explain without exposing raw logs.
- Deterministic evidence artifacts with line-level citations for troubleshooting output.
- Reduced copy/paste friction while keeping data retention short-lived.

## Decisions
- **Storage**: only redacted artifacts retained; raw uploads deleted immediately.
- **Redaction**: rule-based regex patterns for MVP; no ML-based redaction.
- **Upload flow**: presigned S3 PUT with short TTL.

## Deliverables
- /upload-url and /analyze-upload endpoints with documented schemas.
- Redaction module with test corpus and configurable pattern registry.
- Extraction module producing signals and summaries for /explain.
- Upload UI with progress, redaction summary, and attach-to-chat flow.

## Implementation tasks
Concrete task list (assignable, PR-sized items)
1. /upload-url endpoint and presign validation (owner: backend) — 0.5–1 day
2. /analyze-upload pipeline (fetch → redact → store → extract) (owner: backend) — 2–3 days
3. Redaction rules engine + tests (owner: backend/security) — 1–2 days
4. Signal extraction module + tests (owner: backend/ML) — 1–2 days
5. Frontend upload UI + progress + attach flow (owner: frontend) — 1–2 days
6. Observability spans and metrics (owner: platform) — 0.5–1 day
- Generate presigned PUTs only for exact keys; validate ownership of upload_key in analyze step

## Acceptance criteria
- User can upload a log file without pasting into chat
- Redaction applied; sensitive patterns removed (validated by unit/integration tests over a test corpus)
- Explain output improves with tool-derived context (benchmarked improvement on sample queries)
- Pre-signed URL TTL <= 5 minutes and redacted object lifecycle <= 7 days
- No raw contents appear in logs; only metadata/hash recorded
- Tracing spans emitted: tool_s3_fetch, tool_redact, tool_extract
