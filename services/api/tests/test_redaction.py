import os
import sys
import unittest

CURRENT_DIR = os.path.dirname(__file__)
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, ".."))
sys.path.append(PROJECT_ROOT)

from app.main import redact_sensitive_text  # noqa: E402


class RedactionTests(unittest.TestCase):
    def assertRedacts(self, text: str, expected: str) -> None:
        redacted, hits = redact_sensitive_text(text)
        self.assertIn(expected, redacted)
        self.assertGreaterEqual(hits, 1)

    def test_redacts_passport(self) -> None:
        self.assertRedacts("passport no A1234567", "[PASSPORT_NUMBER]")

    def test_redacts_driver_license(self) -> None:
        self.assertRedacts("driver's license: D123-456-789", "[DRIVER_LICENSE]")

    def test_redacts_business_number(self) -> None:
        self.assertRedacts("EIN: 12-3456789", "[BUSINESS_NUMBER]")

    def test_redacts_mac_address(self) -> None:
        self.assertRedacts("device mac 00:1A:2B:3C:4D:5E", "[MAC_ADDRESS]")

    def test_redacts_mac_address_cisco(self) -> None:
        self.assertRedacts("switch mac 001A.2B3C.4D5E", "[MAC_ADDRESS]")


if __name__ == "__main__":
    unittest.main()
