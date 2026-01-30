import os
import sys
import unittest

CURRENT_DIR = os.path.dirname(__file__)
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, ".."))
sys.path.append(PROJECT_ROOT)

from app.llm.guardrails import enforce_guardrails  # noqa: E402
from app.schemas import EvidenceMapEntry, Hypothesis  # noqa: E402


class GuardrailsTests(unittest.TestCase):
    def test_missing_citations_caps_confidence(self) -> None:
        hypothesis = Hypothesis(
            id="h1",
            rank=1,
            confidence=0.8,
            explanation="Something failed.",
            citations=[],
        )
        updated, report = enforce_guardrails([hypothesis], allowed_citations=[])
        self.assertEqual(report.citation_missing_count, 1)
        self.assertTrue(updated[0].explanation.startswith("No citation found."))
        self.assertLessEqual(updated[0].confidence, 0.3)

    def test_filters_invalid_citations(self) -> None:
        allowed = EvidenceMapEntry(
            source_type="log",
            source_id="raw-input",
            line_start=1,
            line_end=1,
            excerpt_hash="abc",
        )
        invalid = EvidenceMapEntry(
            source_type="log",
            source_id="raw-input",
            line_start=2,
            line_end=2,
            excerpt_hash="def",
        )
        hypothesis = Hypothesis(
            id="h1",
            rank=1,
            confidence=0.6,
            explanation="Evidence cited.",
            citations=[allowed, invalid],
        )
        updated, report = enforce_guardrails([hypothesis], allowed_citations=[allowed])
        self.assertEqual(report.citation_missing_count, 0)
        self.assertEqual(len(updated[0].citations), 1)
        self.assertEqual(updated[0].citations[0].excerpt_hash, "abc")

    def test_redacts_identifiers(self) -> None:
        hypothesis = Hypothesis(
            id="h1",
            rank=1,
            confidence=0.7,
            explanation="Failure in arn:aws:iam::123456789012:role/Admin.",
            citations=[],
        )
        updated, report = enforce_guardrails([hypothesis], allowed_citations=[])
        self.assertGreaterEqual(report.redactions, 1)
        self.assertIn("[REDACTED_IDENTIFIER]", updated[0].explanation)
        self.assertLessEqual(updated[0].confidence, 0.2)


if __name__ == "__main__":
    unittest.main()
