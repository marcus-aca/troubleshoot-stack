import os
import sys
import unittest

CURRENT_DIR = os.path.dirname(__file__)
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, ".."))
sys.path.append(PROJECT_ROOT)

from app.main import _is_allowed_domain  # noqa: E402


class DomainGuardrailTests(unittest.TestCase):
    def test_allows_terraform(self) -> None:
        self.assertTrue(_is_allowed_domain("terraform init error: no configuration files"))

    def test_allows_cicd(self) -> None:
        self.assertTrue(_is_allowed_domain("GitHub Actions CI pipeline failed on deploy"))

    def test_blocks_non_technical(self) -> None:
        self.assertFalse(_is_allowed_domain("What is the capital of France?"))

    def test_blocks_personal_request(self) -> None:
        self.assertFalse(_is_allowed_domain("Recommend a restaurant for tonight"))


if __name__ == "__main__":
    unittest.main()
