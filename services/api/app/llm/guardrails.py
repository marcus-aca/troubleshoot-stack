from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Iterable, List, Tuple

from ..schemas import EvidenceMapEntry, Hypothesis


ARN_PATTERN = re.compile(r"arn:aws[a-z-]*:[^\s]+", re.IGNORECASE)
ACCOUNT_ID_PATTERN = re.compile(r"\b\d{12}\b")


@dataclass
class GuardrailReport:
    citation_missing_count: int = 0
    redactions: int = 0
    issues: List[str] = field(default_factory=list)


def enforce_guardrails(
    hypotheses: Iterable[Hypothesis],
    allowed_citations: Iterable[EvidenceMapEntry],
) -> Tuple[List[Hypothesis], GuardrailReport]:
    allowed = {citation_signature(entry) for entry in allowed_citations}
    report = GuardrailReport()
    updated: List[Hypothesis] = []

    for hypothesis in hypotheses:
        hypothesis = hypothesis.model_copy(deep=True)
        valid_citations = [
            entry
            for entry in hypothesis.citations
            if citation_signature(entry) in allowed
        ]
        if not valid_citations:
            hypothesis.confidence = min(hypothesis.confidence, 0.3)
            hypothesis.explanation = f"No citation found. {hypothesis.explanation}"
            report.citation_missing_count += 1
        hypothesis.citations = valid_citations

        redacted, redactions = _redact_identifiers(hypothesis.explanation)
        if redactions:
            hypothesis.explanation = redacted
            hypothesis.confidence = min(hypothesis.confidence, 0.2)
            report.redactions += redactions
            report.issues.append("redacted_identifiers")
        updated.append(hypothesis)

    return updated, report


def citation_signature(entry: EvidenceMapEntry) -> str:
    return f"{entry.source_type}:{entry.source_id}:{entry.line_start}:{entry.line_end}:{entry.excerpt_hash}"


def _redact_identifiers(text: str) -> Tuple[str, int]:
    redactions = 0
    if ARN_PATTERN.search(text):
        text, count = ARN_PATTERN.subn("[REDACTED_IDENTIFIER]", text)
        redactions += count
    if ACCOUNT_ID_PATTERN.search(text):
        text, count = ACCOUNT_ID_PATTERN.subn("[REDACTED_IDENTIFIER]", text)
        redactions += count
    return text, redactions
