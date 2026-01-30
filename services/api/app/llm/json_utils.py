from __future__ import annotations

import json
from typing import Optional


def extract_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("{") and text.endswith("}"):
        return json.loads(text)
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("No JSON object found in LLM output")
    return json.loads(text[start : end + 1])


def sanitize_llm_output(text: str, max_chars: int = 400) -> str:
    text = text.replace("\n", " ")
    return text[:max_chars]
