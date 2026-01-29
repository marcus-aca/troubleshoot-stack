# Section
Security, privacy, and cost hygiene hardening

## Summary
This section defines the security, privacy, and cost-hygiene hardening work needed to protect user data, avoid leakage of secrets/PII, and prevent runaway cloud costs. Goals:
- Ensure no raw sensitive user data (prompts, uploads, generated responses) is persisted in logs or long-lived storage unless explicitly required and approved.
- Apply defense-in-depth: encryption at rest/in transit, IAM least-privilege, runtime redaction, and PII detection/redaction.
- Constrain LLM usage and infrastructure concurrency to enforce predictable costs.
- Provide operational controls, monitoring, and acceptance criteria so changes are auditable and testable.

Owners: Security engineer (primary), Backend lead (implementation), Product manager (policy sign-off).

## Design
High-level design decisions and enforcement points:

1. Data lifecycle and storage
   - All user uploads and derived artifacts (parsed incident frames, redacted logs) are stored in S3 with SSE-KMS and S3 lifecycle rules that automatically delete or transition objects after a configurable TTL.
   - Raw prompts/responses are not persisted by default. If retention is required (e.g., for debugging or analytics), it must be authorized, stored in a dedicated encrypted bucket with short TTL, and tagged for audit.

2. Logging and telemetry
   - Application logs must never include raw prompt text or sensitive fields. Logging middleware performs structured logging with redaction based on LOG_REDACTION_MODE.
   - Correlation IDs are used for tracing; these IDs cannot be used to reconstruct user data.

3. PII/secret handling
   - Two-tier approach:
     - Automatic PII/secrets detection at ingestion (regex + configurable ML detector). Detected items are redacted or tokenized before further processing.
     - UI-level warnings to instruct users not to paste secrets; client-side redaction optional but server-side enforcement required.
   - Optionally, provide an "opt-in debug" workflow where raw data is stored for troubleshooting under strict access controls and TTL.

4. IAM and service separation
   - Separate IAM roles for ingestion (parsing, redaction, storage) and serving (runtime calls to LLMs). Each role follows least privilege and has distinct KMS key access and S3 prefixes.
   - Bedrock/LLM calls are only allowed from a hardened service role; model whitelist enforced in application config and validated before invoking SDK.

5. Cost controls
   - Input limits: MAX_INPUT_CHARS enforced in API validation and in-service.
   - Model generation limits: MAX_OUTPUT_TOKENS enforced in model request wrappers.
  - Concurrency and rate limits: API Gateway throttles requests per API key/account. ECS autoscaling configured with reasonable max capacity; burst protection via queueing.
   - Caching: repeated explain requests are cached via semantic cache (OpenSearch Serverless vector index) with TTL metadata to avoid repeated expensive calls.
   - Budgeting/alerting: CloudWatch billing alarms and AWS budgets trigger alerts when spend approaches thresholds.

6. Configuration and auditability
   - Config flags (LOG_REDACTION_MODE, MAX_INPUT_CHARS, MAX_OUTPUT_TOKENS) are environment variables with documented defaults and are exposed in a secure config dashboard for ops.
   - A security review checklist, README threat model, and change log are added to the repo for audits.

## Implementation Steps
This is an actionable, ordered plan. Each step should include owner, estimated effort, and a test plan.

1. Prepare policies, checklist, and documentation (Owner: Security, Effort: 1 week)
   - Add README section describing threat model, data flow, and mitigations.
   - Add security review checklist (PR checklist and deployment checklist) to repo.
   - Define and approve retention SLAs for uploads vs parsed artifacts (e.g., uploads = 30 days, parsed artifacts = 30–90 days) — configurable.
   - Deliverable: PR with documents; sign-off by Product & Security.

2. Logging and redaction middleware (Owner: Backend, Effort: 3–5 days)
   - Implement LOG_REDACTION_MODE options: "none", "partial", "full".
     - none: no redaction (for local dev only).
     - partial: redact detected PII/secrets and long text fields; keep metadata.
     - full: redact all user-provided text fields; log only hashes/correlation IDs.
   - Integrate middleware to apply redaction before logs are emitted and before telemetry is sent to third parties.
   - Tests: unit tests verifying redaction policies; integration test ensuring logs contain no prompt text.

3. Prevent raw prompts/responses in logs/traces (Owner: Backend, Effort: 2 days)
   - Update all logging calls to accept structured payloads; ensure prompt/response fields pass through redaction prior to logging.
   - Review all places where exceptions are logged and ensure error paths do not leak request bodies.
   - Tests: grep CI job that scans log artifacts for strings matching prompt patterns; fail build on matches.

4. PII detection and redaction at ingestion (Owner: Data/Backend, Effort: 1 week)
   - Implement a pluggable PII detection pipeline:
     - Quick heuristics: email, credit card, SSN, API keys (regex).
     - Optional: Amazon Comprehend or a light ML model for names/addresses (if approved).
   - Redaction options: mask, replace with placeholder token, or extract and store separately in secure store (for audited use).
   - Tests: unit tests with PII sample corpus; fuzz tests.

5. Storage encryption and lifecycle (Owner: Infra, Effort: 3 days)
   - Create S3 buckets with SSE-KMS encryption. Use separate buckets/prefixes for raw uploads vs processed artifacts.
   - Apply S3 lifecycle rules and object tagging to enforce TTLs. Make TTL a deploy-time variable.
   - Ensure KMS keys have key policies scoping access to specific IAM roles only.
   - Tests: create test objects and verify lifecycle transitions and eventual deletion (or TTL tags).

6. IAM role separation and least privilege (Owner: Infra/Security, Effort: 3 days)
   - Define and implement separate IAM roles and policies:
     - ingestion-role: permissions to write encrypted objects to uploads bucket, call PII detector, no Bedrock access.
     - serving-role: permissions to call Bedrock/LLM, read parsed artifacts, but no write to raw uploads.
   - Apply role assumption patterns for ECS tasks and Lambda functions.
   - Tests: principle-of-least-privilege verification using IAM Access Analyzer or in-house checks.

7. Model call constraints and enforcement (Owner: Backend, Effort: 3 days)
   - Implement a model-whitelist config that contains approved model IDs and per-model max tokens.
   - Wrap all Bedrock/LLM invocations in a validated client that:
     - Enforces MAX_OUTPUT_TOKENS (fail or truncate).
     - Validates model is in whitelist.
     - Records model and token usage metrics to CloudWatch/Prometheus.
   - Tests: unit tests and integration tests that attempt calls with disallowed models or token counts and assert rejection.

8. API Gateway throttling and payload validation (Owner: Infra, Effort: 2 days)
   - Configure API Gateway to validate payload size against MAX_INPUT_CHARS and enforce request throttling (burst and steady rate).
   - Send 413 or 429 with clear error codes in response body for clients.
   - Tests: load tests to ensure throttles behave and payload validation blocks oversized inputs.

9. Concurrency, autoscaling, and cost caps (Owner: Infra, Effort: 2 days)
   - Set ECS autoscaling min/max; configure scale-in/out policies with safeties to avoid cost spikes.
   - Implement per-account or per-API-key concurrency caps (soft limit enforced by app).
   - Configure CloudWatch billing alarms and AWS Budgets with threshold notifications.
   - Tests: simulated load test to validate autoscaling behavior and queueing/backpressure.

10. Caching repeated explains (Owner: Backend, Effort: 3 days)
    - Implement semantic cache using OpenSearch Serverless:
      - Embed sanitized input + normalized context and store in vector index with TTL metadata.
      - Cache only safe-to-cache responses (do not cache PII-containing outputs unless scrubbed and user opted in).
      - Store large responses in S3 and reference from cache docs.
    - Tests: verify cache hit/miss behavior, similarity thresholding, and that cache reduces Bedrock calls.

11. Secure dev/test workflows and opt-in debug storage (Owner: Security/Backend, Effort: 2 days)
    - Define a documented opt-in debug process: manual approval, temporary storage bucket with access logs, short TTL, and audit trail.
    - Implement tooling to redact or purge debug artifacts automatically at end of debug window.
    - Tests: audit logs show approval and deletion events.

12. Monitoring, alerting, and compliance tests (Owner: SRE, Effort: 3 days)
    - Implement metrics and dashboards: token usage, model-call counts, redaction rate, PII detections, S3 object counts & TTL compliance, budget alerts.
    - Add automated tests to CI: scanning logs for raw prompts, IAM policy checks, S3 lifecycle presence.
    - Tests: simulated infra and functional tests to trigger alerts and verify notification flow.

## Risks
List of risks, likelihood, and mitigations.

1. Residual prompt leakage in logs or 3rd-party telemetry
   - Likelihood: Medium
   - Mitigation: enforced redaction middleware, CI grep tests, regular audits, and limited third-party telemetry scopes.

2. Over-redaction reduces product utility (loss of context)
   - Likelihood: Medium
   - Mitigation: LOG_REDACTION_MODE with environments (dev vs prod), configurable redaction policies, product/UX review, user opt-in for debug.

3. False negatives/positives in PII detection
   - Likelihood: Medium
   - Mitigation: layered approach (regex + ML), allow manual review for flagged items, provide override workflows with strict audit logging.

4. Unauthorized model selection or token misuse
   - Likelihood: Low–Medium
   - Mitigation: model whitelist, server-side validation, IAM enforcement, telemetry + alerts on sudden token spike.

5. Cost spikes due to concurrency or cache misses
   - Likelihood: Medium
   - Mitigation: API throttles, ECS autoscaling caps, caching, CloudWatch billing alarms, per-account quotas.

6. Misconfigured lifecycle or encryption settings
   - Likelihood: Low
   - Mitigation: infra-as-code templates (CloudFormation/Terraform) with automated tests, cross-account KMS key policies, peer review.

7. Operational burden for debug/opt-in retention
   - Likelihood: Medium
   - Mitigation: automate approval and TTL enforcement; limit number of concurrent opt-in sessions.

## Dependencies
Concrete external systems, approvals, and teams required.

- AWS services: S3 (lifecycle & SSE-KMS), KMS, ECS/Lambda, API Gateway (fronting ALB when using ECS), CloudWatch, Budgets, IAM, (optional) Comprehend.
- OpenSearch Serverless for semantic caching of repeated explains.
- CI/CD pipeline to run log scans and policy checks.
- Security team for policy and threat model sign-off.
- Product/Legal for retention SLAs and opt-in debug policy.
- Access to Bedrock or chosen LLM provider credentials and any quotas.
- IAM Access Analyzer or similar tooling for privilege validation.

## Acceptance Criteria
(High-level acceptance criteria — must be met before feature release)
- No production logs (application logs, CloudWatch logs, or third-party telemetry) contain raw user prompts or raw responses unless explicitly authorized by documented opt-in.
- All stored user uploads and parsed artifacts are encrypted with SSE-KMS and have lifecycle TTLs configured according to approved retention SLAs.
- LLM/Bedrock calls are restricted to an approved model whitelist and per-model max token limits; attempts to use disallowed models or exceed token limits are rejected server-side.
- Monitoring and alerts present: token usage metrics, PII detection counts, cache hit/miss stats, S3 TTL compliance, and a billing alert threshold.
- Repo contains a security review checklist and README section describing the threat model and mitigations.

## Privacy/security controls
- Data retention:
  - S3 lifecycle rules for uploads and parsed artifacts; retention durations must be configurable via infra variables (examples: uploads=30d default, parsed artifacts=30–90d default).
  - Avoid storing raw prompts/responses unless necessary. If stored:
    - Store in a dedicated "debug" bucket with SSE-KMS.
    - Attach tags/metadata recording approval and TTL.
    - Enforce automatic deletion via lifecycle and a scheduled job to purge expired objects.
- PII/secrets:
  - Automatic redaction for uploads and optionally for free-text fields such as error log or trace stack text.
  - Implement server-side PII detection (regex + optional ML) that either masks or extracts PII before further processing.
  - UI: display a prominent warning banner advising users not to paste secrets or sensitive personal information. Provide a consent checkbox before uploading.
  - Maintain an opt-in debug workflow with access logging and temporary storage only with explicit approval.
- IAM:
  - Least privilege policies for ECS tasks and Lambdas. Use separate roles for ingestion vs serving with explicitly scoped permissions.
  - KMS keys are scoped to roles and rotated per org policy.
  - Use IAM role assumption patterns and avoid embedding long-lived credentials.

## Cost controls
- Enforce max tokens in generation:
  - MAX_OUTPUT_TOKENS enforced in model-client wrapper; configurable per-model.
- Input size and content limits:
  - MAX_INPUT_CHARS enforced at API Gateway and validated server-side.
  - Reject or truncate inputs that would cause tokens to exceed budget.
- Cache repeated explains:
  - Use semantic cache (OpenSearch Serverless vector index) with embeddings of sanitized input + context; store TTL metadata.
  - Avoid caching outputs containing unredacted PII.
- Concurrency controls:
  - ECS autoscaling limits: configure min/max tasks and avoid unlimited scaling.
  - API Gateway throttles: establish per-API-key and global throttles (burst/steady).
  - Per-user or per-account quotas enforced in application to avoid abuse.
- Billing guardrails:
  - AWS Budgets + CloudWatch billing alarms that notify at 75%, 90%, and 100% of planned monthly budget.
  - Automated soft-reduction of concurrency or blocking of non-critical features if cost thresholds are breached (requires product approval).

## Acceptance criteria
(Specific, testable items)
- No raw uploads appear in logs: CI test that scans a set of recent logs for patterns resembling raw prompts and fails if found.
- Storage has TTL/lifecycle configured: infra tests validate S3 lifecycle rules and test-object lifecycle transitions.
- Bedrock calls constrained to approved models and max token settings: integration tests attempt disallowed-model invocation and oversized token requests; these must be rejected and logged.
- Config flags present and enforced:
  - LOG_REDACTION_MODE exists and toggles redaction behavior; unit tests cover each mode.
  - MAX_INPUT_CHARS enforces payload validation at API gate and server; functional tests verify 413 for oversize.
  - MAX_OUTPUT_TOKENS enforced in model wrapper and verified by test harness.
- Auditability:
  - Security review checklist in repo and README threat model exist and are approved.
  - Access logs, KMS key usage, and lifecycle activities are available to SRE/security teams.

## Implementation tasks
- Add config flags (Owner: Backend)
  - LOG_REDACTION_MODE: enum {"none","partial","full"}; default "partial" in staging, "full" in production.
  - MAX_INPUT_CHARS: integer; default 10,000 (tune per product). Reject > limit with HTTP 413.
  - MAX_OUTPUT_TOKENS: integer; default 512 per request; also allow per-model overrides in whitelist config.
  - Implement these as environment variables and document them in README/config reference.
- Add security review checklist in repo (Owner: Security)
  - Checklist items: retention SLA approved, KMS keys created with proper policies, model whitelist in place, CI redaction tests, S3 lifecycle present, IAM roles separated.
- Add README section describing threat model and mitigations (Owner: Security/Product)
  - Include diagrams of data flow, list of accepted risks, opt-in debug process, retention SLAs, and contact points.
- Add CI checks and tests (Owner: SRE/Backend)
  - Log scan job to detect prompt-like strings in logs.
  - IAM policy linting.
  - Test that S3 buckets have lifecycle rules and encryption enabled.
  - Integration tests validating model-whitelist and token enforcement.
- Add dashboards and alerts (Owner: SRE)
  - Token usage, model-call rates, PII detection rates, cache hit rate, S3 object counts & time-to-delete, budget alarms.

Notes:
- All changes touching data retention or model usage must go through the security review checklist and be signed off by Security and Product before production deployment.
- Default values provided here are starting points; tune them based on usage patterns and regulatory requirements.
