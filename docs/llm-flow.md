# LLM Orchestration Flow (Parser → Context → LLM → Guardrails → Response)

## Diagram (high level)
```
Raw logs / user input
        |
        v
RuleBasedLogParser
  - NormalizedLog
  - Family parser (Terraform/CloudWatch/Python/Generic)
        |
        v
IncidentFrame (evidence_map + signatures + domain hints)
        |
        v
Storage (save input/frame + compact context)
        |
        v
PromptRegistry + Orchestrator
  - prompt template (v1)
  - context (recent events + frame + evidence)
        |
        v
LLM Adapter (Bedrock or stub)
        |
        v
LLM JSON Output (TriageLLMOutput / ExplainLLMOutput)
        |
        v
Guardrails
  - enforce citations
  - redact identifiers
        |
        v
CanonicalResponse
```

## Example data shapes (mocked)

### NormalizedLine / NormalizedLog
```json
{
  "raw_text": "2026-01-30T11:23:45Z Error: AccessDenied ...\n2026-01-30T11:23:46Z ...",
  "lines": [
    { "number": 1, "text": "2026-01-30T11:23:45Z Error: AccessDenied ...", "lowered": "2026-01-30t11:23:45z error: accessdenied ..." },
    { "number": 2, "text": "2026-01-30T11:23:46Z ...", "lowered": "2026-01-30t11:23:46z ..." }
  ],
  "timestamps": ["2026-01-30T11:23:45Z", "2026-01-30T11:23:46Z"]
}
```

### EvidenceMapEntry
```json
{
  "source_type": "log",
  "source_id": "raw-input",
  "line_start": 1,
  "line_end": 1,
  "excerpt_hash": "5f3c1f0f..."
}
```

### IncidentFrame (parser output)
```json
{
  "frame_id": "frame-123",
  "conversation_id": "conv-abc",
  "request_id": "req-xyz",
  "source": "user_input",
  "parser_version": "rule-based-v1",
  "parse_confidence": 0.72,
  "created_at": "2026-01-30T11:23:50Z",
  "primary_error_signature": "2026-01-30T11:23:45Z Error: AccessDenied ...",
  "secondary_signatures": ["on main.tf line 12"],
  "time_window": { "start": "2026-01-30T11:23:45Z", "end": "2026-01-30T11:23:46Z" },
  "services": ["api"],
  "infra_components": ["terraform"],
  "suspected_failure_domain": "iam",
  "evidence_map": [
    {
      "source_type": "log",
      "source_id": "raw-input",
      "line_start": 1,
      "line_end": 1,
      "excerpt_hash": "5f3c1f0f..."
    }
  ]
}
```

### LLM context (built for prompt)
```json
{
  "conversation_id": "conv-abc",
  "latest_incident_frame": {
    "primary_error_signature": "2026-01-30T11:23:45Z Error: AccessDenied ..."
  },
  "latest_response_summary": {
    "top_hypothesis": {
      "id": "hyp-1",
      "confidence": 0.62,
      "explanation": "Permission issue on IAM role creation."
    }
  },
  "recent_events": [
    {
      "request_id": "req-prev",
      "primary_error_signature": "Timeout contacting upstream",
      "services": ["api"],
      "infra_components": ["alb"],
      "top_hypothesis": { "id": "hyp-timeout", "confidence": 0.61 }
    }
  ],
  "prompt": "You are an expert troubleshooting assistant... Evidence map: [...]"
}
```

### Triage LLM output (before guardrails)
```json
{
  "category": "iam",
  "hypotheses": [
    {
      "id": "hyp-iam-1",
      "rank": 1,
      "confidence": 0.7,
      "explanation": "IAM policy lacks permissions for role creation.",
      "citations": [
        {
          "source_type": "log",
          "source_id": "raw-input",
          "line_start": 1,
          "line_end": 1,
          "excerpt_hash": "5f3c1f0f..."
        }
      ]
    }
  ],
  "recommended_tool_calls": [
    { "tool": "iam.get_policy", "call_spec": { "role_name": "example-role" } }
  ]
}
```

### Explain LLM output (before guardrails)
```json
{
  "hypotheses": [
    {
      "id": "hyp-iam-1",
      "rank": 1,
      "confidence": 0.62,
      "explanation": "AccessDenied indicates missing IAM permissions.",
      "citations": [
        {
          "source_type": "log",
          "source_id": "raw-input",
          "line_start": 1,
          "line_end": 1,
          "excerpt_hash": "5f3c1f0f..."
        }
      ]
    }
  ],
  "runbook_steps": [
    {
      "step_number": 1,
      "description": "Inspect IAM policy for CreateRole permissions.",
      "command_or_console_path": "IAM console > Roles",
      "estimated_time_mins": 10
    }
  ],
  "proposed_fix": "Add iam:CreateRole to the policy and re-apply.",
  "risk_notes": ["Use least-privilege when updating policies."],
  "rollback": ["Revert the policy change if unexpected access occurs."],
  "next_checks": ["Re-run terraform apply and confirm success."]
}
```

### CanonicalResponse (after guardrails)
```json
{
  "request_id": "req-xyz",
  "timestamp": "2026-01-30T11:23:55Z",
  "hypotheses": [
    {
      "id": "hyp-iam-1",
      "rank": 1,
      "confidence": 0.62,
      "explanation": "AccessDenied indicates missing IAM permissions.",
      "citations": [
        {
          "source_type": "log",
          "source_id": "raw-input",
          "line_start": 1,
          "line_end": 1,
          "excerpt_hash": "5f3c1f0f..."
        }
      ]
    }
  ],
  "runbook_steps": [
    {
      "step_number": 1,
      "description": "Inspect IAM policy for CreateRole permissions.",
      "command_or_console_path": "IAM console > Roles",
      "estimated_time_mins": 10
    }
  ],
  "proposed_fix": "Add iam:CreateRole to the policy and re-apply.",
  "risk_notes": ["Use least-privilege when updating policies."],
  "rollback": ["Revert the policy change if unexpected access occurs."],
  "next_checks": ["Re-run terraform apply and confirm success."],
  "metadata": {
    "prompt_version": "v1",
    "prompt_filename": "services/api/prompts/v1/explain/explain.md",
    "model_id": "amazon.titan-text-lite-v1",
    "token_usage": { "prompt_tokens": 312, "completion_tokens": 178, "total_tokens": 490, "generated_at_ms": 1769797435000 },
    "guardrails": { "citation_missing_count": 0, "redactions": 0, "issues": [] }
  },
  "conversation_id": "conv-abc"
}
```

## Flow summary
- Parser extracts a stable incident frame from raw logs and maps evidence lines.
- Storage keeps recent events; a compact summary is used for context.
- Prompt registry pins the prompt version used by each endpoint.
- LLM returns structured JSON; guardrails validate citations and redact identifiers.
- The API returns a canonical response with metadata for auditability.
