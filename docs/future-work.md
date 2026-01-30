# Future work

## Better hypothesis matching beyond keywords
1) **Structured error signature extraction**
- Parse common log formats into fields (`error_code`, `service`, `operation`, `resource`, `status_code`).
- Match on `error_code` (e.g., `AccessDenied`, `UnauthorizedOperation`, `ThrottlingException`) instead of raw text.

2) **Rule-based regex patterns per log family**
- Regexes for known error shapes (AWS, Terraform, Python tracebacks, Kubernetes).
- Map pattern → hypothesis + confidence.

3) **Weighted scoring over features**
- Build a feature set (error_code, status_code, service tokens, retry hints, timeout indicators).
- Score hypotheses by weighted sum instead of boolean keyword checks.

4) **Lightweight classifier (statistical)**
- Train a simple model (e.g., logistic regression) on labeled error snippets.
- Use n-grams + extracted fields for probabilistic matching.

5) **LLM-assisted classification (bounded)**
- Use a small prompt to classify error types from parsed structure (not raw logs).
- Keep it low-token and fall back to rules when confidence is low.

## Guardrail expansion
1) **Claim-level validation**
- Validate LLM claims against raw log snippets and tool outputs, not just citations.
- Require citation coverage per concrete assertion (error codes, resource names, regions).

2) **Stronger citation enforcement**
- Enforce minimum evidence coverage for top hypotheses before returning.
- Flag hypotheses with weak evidence for manual review.
