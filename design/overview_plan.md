# Infra Troubleshooter (Logs + Tools) on AWS — 4 Week MVP

Scope classification: 4 week MVP

## Overview
Build a web + API system where a user pastes error logs or a trace stack (Terraform/EKS/ALB/IAM, etc.) and iteratively works with the assistant to diagnose issues. The assistant maintains conversation context across turns and returns ranked hypotheses with citations to user-provided logs and tool outputs, a step-by-step runbook, proposed fixes, risk/rollback notes, and next-branch checks. Implement credible LLMOps: Bedrock model selection, tool-assisted log ingestion, rate limits/budgets/caching, evaluation harness with nightly runs and release gating, and production-grade observability (logs/metrics/traces) deployed via Terraform. API ingress is handled by AWS API Gateway; compute is recommended on ECS Fargate (with Lambda as an optional alternative for lower-volume or lighter workloads).

## Sections

### S1: Architecture, requirements, and repo setup
Status: not started

Finalize MVP boundaries, define request/response contracts, choose libraries, and establish repo structure, environments, and CI basics.

### S2: Infrastructure as Code (Terraform) foundation
Status: not started

Provision core AWS resources with least-privilege IAM, networking, and deployment primitives for API, tooling, logging, and storage.

### S3: Log parsing and normalization (non-RAG)
Status: not started

Normalize user-provided logs/trace stacks into a structured incident frame with extracted entities, timestamps, and key error signatures. This replaces any vector KB ingestion and keeps the system grounded in the user's pasted evidence and tool outputs.

### S4: Bedrock LLM orchestration (interactive triage + explain) with prompt/version management
Status: not started

Implement an interactive loop: triage to classify error logs/trace stacks and plan tool calls, then explain to generate ranked hypotheses and actionable runbook output with citations and guardrails. Preserve conversation state so the assistant can ask follow-ups and refine results.

### S5: Tools layer and secure log ingestion UX
Status: not started

Add at least one credible tool workflow to reduce copy/paste risk and improve troubleshooting context (secure upload + redaction + short-lived access).

### S6: Guardrails: rate limits, per-user budgets, and caching
Status: not started

Implement operational cost controls with API Gateway throttling, DynamoDB-based per-user daily budgets, and TTL caching for repeat queries.

### S7: Frontend web app (interactive troubleshooting) and user experience
Status: not started

Deliver a simple web UI that accepts error logs/trace stacks, supports secure log upload, maintains session context across turns, and renders structured troubleshooting output with citations to log lines and tool results.

### S8: Observability, auditability, and dashboards (logs/metrics/traces)
Status: not started

Instrument the system with structured logs, OpenTelemetry tracing, and CloudWatch dashboards/alarms to look production-real and debuggable.

### S9: Evaluation harness, nightly runs, and release gating
Status: not started

Create an automated eval dataset and runner that measures quality, latency, cost, and citation coverage; run nightly and gate releases on regression.

### S10: Security, privacy, and cost hygiene hardening
Status: not started

Add pragmatic security controls: data retention, PII handling, access control, and cost safeguards suitable for an LLMOps portfolio.

### S11: Delivery plan and milestones (4-week MVP)
Status: not started

Define weekly milestones, integration order, and demo checklist to ensure a shippable, interview-ready portfolio.
