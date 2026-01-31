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

### Explain request guardrails
- `/explain` requires a `conversation_id` and an existing triage session.
- If `incident_frame` is omitted, the API reuses the latest frame from the conversation state.

### Triage LLM output (before guardrails)
```json
{
  "category": "iam",
  "assistant_message": "I need the IAM policy attached to the role to confirm permissions. Please run the command below.",
  "completion_state": "needs_input",
  "next_question": "Run the command and paste the output.",
  "tool_calls": [
    {
      "id": "tool-iam-1",
      "title": "Fetch IAM role policy",
      "command": "aws iam get-role-policy --role-name example-role --policy-name InlinePolicy",
      "expected_output": "Policy document JSON"
    }
  ],
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
  "fix_steps": []
}
```

### Explain LLM output (after tool output)
```json
{
  "assistant_message": "The role policy is missing iam:CreateRole. Add it and re-run terraform apply.",
  "completion_state": "final",
  "next_question": null,
  "tool_calls": [],
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
  "fix_steps": ["Add iam:CreateRole to the policy and re-apply."]
}
```

### CanonicalResponse (after guardrails)
```json
{
  "request_id": "req-xyz",
  "timestamp": "2026-01-30T11:23:55Z",
  "assistant_message": "The role policy is missing iam:CreateRole. Add it and re-run terraform apply.",
  "completion_state": "final",
  "next_question": null,
  "tool_calls": [],
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
  "fix_steps": ["Add iam:CreateRole to the policy and re-apply."],
  "metadata": {
    "prompt_version": "v2",
    "prompt_filename": "services/api/prompts/v2/explain/explain.md",
    "model_id": "amazon.titan-text-lite-v1",
    "token_usage": { "prompt_tokens": 312, "completion_tokens": 178, "total_tokens": 490, "generated_at_ms": 1769797435000 },
    "guardrails": { "citation_missing_count": 0, "redactions": 0, "domain_restricted": 0, "issues": [] }
  },
  "conversation_id": "conv-abc"
}
```

## Flow summary
- Parser extracts a stable incident frame from raw logs and maps evidence lines.
- Storage keeps recent events; a compact summary is used for context.
- Prompt registry pins the prompt version used by each endpoint.
- LLM returns structured JSON; guardrails validate citations, redact identifiers, and enforce domain-only requests.
- The API returns a canonical response with metadata for auditability.
