from __future__ import annotations

import re
from typing import List


def normalize_text(value: str) -> str:
    return " ".join(value.lower().split())


def is_non_informative(answer: str) -> bool:
    if not answer:
        return True
    normalized = normalize_text(answer)
    if normalized in {
        "no",
        "nope",
        "idk",
        "i dont know",
        "i don't know",
        "dont know",
        "don't know",
        "not sure",
        "unsure",
        "unknown",
        "n/a",
        "na",
        "none",
        "cant",
        "can't",
        "cannot",
        "dont have",
        "don't have",
        "dont have it",
        "don't have it",
        "i dont have it",
        "i don't have it",
        "not available",
        "no idea",
    }:
        return True
    return False


def looks_like_structured_payload(answer: str) -> bool:
    if not answer:
        return False
    if any(char in answer for char in ("{", "}", "<", ">", "\n")):
        return True
    if re.search(r"\b\w+\s*[:=]\s*[^,\s]+", answer):
        return True
    if re.search(r"\"[^\"]+\"\s*:\s*\"[^\"]+\"", answer):
        return True
    return False


def looks_like_error_message(answer: str) -> bool:
    if not answer:
        return False
    normalized = normalize_text(answer)
    if any(token in normalized for token in ("error", "invalid", "exception", "failed", "denied")):
        return True
    if ":" in answer and len(answer) > 8:
        return True
    if re.search(r"\b[A-Z]{2,6}\b", answer):
        return True
    return False


def missing_required_details(question: str, answer: str) -> List[str]:
    if not question or not answer:
        return []
    question_norm = normalize_text(question)
    missing: List[str] = []
    payload_requested = any(
        phrase in question_norm
        for phrase in (
            "request payload",
            "request body",
            "request json",
            "request xml",
        )
    )
    response_payload_requested = any(
        phrase in question_norm
        for phrase in (
            "response payload",
            "response body",
            "response json",
            "response xml",
        )
    )
    payload_generic = "payload" in question_norm and not (payload_requested or response_payload_requested)
    if (payload_requested or payload_generic) and not _answer_contains_request_payload(answer):
        missing.append("request payload")
    error_requested = any(
        phrase in question_norm
        for phrase in (
            "error response",
            "error message",
            "exact error",
            "stack trace",
            "stacktrace",
            "trace",
            "logs",
            "log",
        )
    )
    if (error_requested or response_payload_requested) and not _answer_contains_error_response(answer):
        missing.append("error response")
    return missing


def _answer_contains_request_payload(answer: str) -> bool:
    if not answer:
        return False
    normalized = normalize_text(answer)
    if "payload" in normalized and not looks_like_structured_payload(answer):
        return False
    if re.search(r"\b(error|invalid|exception|failed|denied)\b", normalized):
        return False
    return looks_like_structured_payload(answer)


def _answer_contains_error_response(answer: str) -> bool:
    if not answer:
        return False
    normalized = normalize_text(answer)
    if "payload" in normalized and not re.search(r"\b(error|invalid|exception|failed|denied)\b", normalized):
        return False
    return looks_like_error_message(answer)


def rephrase_missing_details(missing: List[str]) -> str:
    if not missing:
        return "Could you share the missing detail? A redacted snippet or field list works too."
    if len(missing) == 1 and missing[0] == "request payload":
        return (
            "I still need the request payload. If you can't share raw values, paste a redacted snippet "
            "or list the fields you send."
        )
    if len(missing) == 1 and missing[0] == "error response":
        return (
            "I still need the exact error response. If you can't share raw values, paste a redacted snippet "
            "or summarize the error code/message."
        )
    return (
        "I still need the missing details. If you can't share raw values, paste a redacted snippet or list the fields."
    )


def is_allowed_domain(text: str) -> bool:
    if not text:
        return True
    normalized = text.lower()
    tokens = set(re.findall(r"[a-z0-9+/.-]+", normalized))
    token_keywords = (
        "terraform",
        "pulumi",
        "cloudformation",
        "ansible",
        "kubernetes",
        "k8s",
        "docker",
        "helm",
        "ecs",
        "eks",
        "lambda",
        "s3",
        "iam",
        "vpc",
        "gitlab",
        "github",
        "jenkins",
        "circleci",
        "pipeline",
        "ci/cd",
        "cicd",
        "build",
        "deploy",
        "release",
        "infra",
        "iac",
        "observability",
        "logging",
        "monitoring",
        "alert",
        "prometheus",
        "grafana",
        "cloudwatch",
        "http",
        "api",
        "yaml",
        "json",
        "sql",
        "database",
        "redis",
        "postgres",
        "mysql",
        "python",
        "node",
        "typescript",
        "javascript",
        "golang",
        "java",
        "rust",
        "linux",
        "nginx",
        "kafka",
        "queue",
        "cache",
    )
    phrase_keywords = (
        "stack trace",
        "traceback",
        "error",
        "exception",
        "failed",
        "timeout",
        "infra as code",
        "infrastructure as code",
    )
    if any(keyword in tokens for keyword in token_keywords):
        return True
    if any(phrase in normalized for phrase in phrase_keywords):
        return True
    if re.search(r"```", text):
        return True
    if re.search(r"\b(class|def|function|SELECT|INSERT|UPDATE|FROM)\b", text, flags=re.IGNORECASE):
        return True
    if re.search(r"\b[A-Za-z0-9_/.-]+\.(py|js|ts|go|java|rb|tf|yaml|yml|json|sh|ps1)\b", text):
        return True
    if re.search(r"\b(4\d{2}|5\d{2})\b", text):
        return True
    return False
