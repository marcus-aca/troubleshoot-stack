import hashlib
import os
import sys
import unittest


CURRENT_DIR = os.path.dirname(__file__)
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, ".."))
FIXTURE_DIR = os.path.join(CURRENT_DIR, "fixtures")

sys.path.append(PROJECT_ROOT)

from app.parser import RuleBasedLogParser  # noqa: E402


def _read_fixture(name: str) -> str:
    path = os.path.join(FIXTURE_DIR, name)
    with open(path, "r", encoding="utf-8") as handle:
        return handle.read()


def _hash_line(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class ParserFixtureTests(unittest.TestCase):
    def setUp(self):
        self.parser = RuleBasedLogParser()

    def test_terraform_parser(self):
        raw_text = _read_fixture("terraform.log")
        frame = self.parser.parse(raw_text, request_id="req-1")

        expected_primary = "2026-01-30T11:23:45Z Error: Error creating IAM Role example-role: AccessDenied: User is not authorized"
        self.assertEqual(frame.primary_error_signature, expected_primary)
        self.assertIn("terraform", frame.infra_components)
        self.assertIsNotNone(frame.time_window)
        self.assertEqual(frame.time_window.start, "2026-01-30T11:23:45Z")
        self.assertEqual(frame.time_window.end, "2026-01-30T11:23:45Z")

        primary_evidence = frame.evidence_map[0]
        self.assertEqual(primary_evidence.line_start, 1)
        self.assertEqual(primary_evidence.line_end, 1)
        self.assertEqual(primary_evidence.excerpt_hash, _hash_line(expected_primary))
        self.assertEqual(primary_evidence.excerpt, expected_primary)

    def test_cloudwatch_parser(self):
        raw_text = _read_fixture("cloudwatch.log")
        frame = self.parser.parse(raw_text, request_id="req-2")

        expected_primary = "2026-01-30 11:24:01Z ERROR Failed to deliver logs to destination"
        self.assertEqual(frame.primary_error_signature, expected_primary)
        self.assertIn("cloudwatch", frame.infra_components)
        self.assertIsNotNone(frame.time_window)
        self.assertEqual(frame.time_window.start, "2026-01-30 11:24:00Z")
        self.assertEqual(frame.time_window.end, "2026-01-30 11:24:02Z")

        primary_evidence = frame.evidence_map[0]
        self.assertEqual(primary_evidence.line_start, 2)
        self.assertEqual(primary_evidence.line_end, 2)
        self.assertEqual(primary_evidence.excerpt_hash, _hash_line(expected_primary))
        self.assertEqual(primary_evidence.excerpt, expected_primary)

    def test_python_traceback_parser(self):
        raw_text = _read_fixture("python_traceback.log")
        frame = self.parser.parse(raw_text, request_id="req-3")

        expected_primary = "ValueError: bad input"
        self.assertEqual(frame.primary_error_signature, expected_primary)
        self.assertGreaterEqual(len(frame.secondary_signatures), 1)

        primary_evidence = frame.evidence_map[0]
        self.assertEqual(primary_evidence.line_start, 6)
        self.assertEqual(primary_evidence.line_end, 6)
        self.assertEqual(primary_evidence.excerpt_hash, _hash_line(expected_primary))
        self.assertEqual(primary_evidence.excerpt, expected_primary)

    def test_generic_parser(self):
        raw_text = _read_fixture("generic.log")
        frame = self.parser.parse(raw_text, request_id="req-4")

        expected_primary = "Upstream request failed after 2 retries"
        self.assertEqual(frame.primary_error_signature, expected_primary)
        self.assertEqual(frame.evidence_map[0].line_start, 1)
        self.assertEqual(frame.evidence_map[0].line_end, 1)
        self.assertEqual(frame.evidence_map[0].excerpt_hash, _hash_line(expected_primary))
        self.assertEqual(frame.evidence_map[0].excerpt, expected_primary)


if __name__ == "__main__":
    unittest.main()
