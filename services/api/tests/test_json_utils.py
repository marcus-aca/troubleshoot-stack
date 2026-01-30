import os
import sys
import unittest

CURRENT_DIR = os.path.dirname(__file__)
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, ".."))
sys.path.append(PROJECT_ROOT)

from app.llm.json_utils import extract_json  # noqa: E402


class JsonUtilsTests(unittest.TestCase):
    def test_extracts_wrapped_json(self) -> None:
        text = "prefix {\"ok\": true, \"value\": 1} suffix"
        data = extract_json(text)
        self.assertEqual(data["ok"], True)
        self.assertEqual(data["value"], 1)

    def test_extracts_plain_json(self) -> None:
        text = "{\"status\": \"ok\"}"
        data = extract_json(text)
        self.assertEqual(data["status"], "ok")


if __name__ == "__main__":
    unittest.main()
