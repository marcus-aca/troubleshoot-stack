import os
import sys
import unittest

CURRENT_DIR = os.path.dirname(__file__)
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, ".."))
sys.path.append(PROJECT_ROOT)

from app.main import _missing_required_details, _rephrase_missing_details  # noqa: E402


class QuestionHandlingTests(unittest.TestCase):
    def test_missing_details_detects_payload_only(self) -> None:
        question = "Please share the error response and the request payload you used."
        answer = "INVALID: not a valid card number"
        self.assertEqual(_missing_required_details(question, answer), ["request payload"])


    def test_missing_details_detects_error_response_only(self) -> None:
        question = "Please share the exact error response from the gateway."
        answer = "payload: {\"amount\": 10}"
        self.assertEqual(_missing_required_details(question, answer), ["error response"])


    def test_missing_details_detects_payload_when_no_structure(self) -> None:
        question = "Please provide the request payload."
        answer = "payload is blah blah"
        self.assertEqual(_missing_required_details(question, answer), ["request payload"])


    def test_rephrase_missing_details_payload(self) -> None:
        self.assertIn("request payload", _rephrase_missing_details(["request payload"]).lower())


if __name__ == "__main__":
    unittest.main()
