from __future__ import annotations

import json
from typing import Optional


def extract_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("{") and text.endswith("}"):
        return _load_json_with_repair(text)
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("No JSON object found in LLM output")
    return _load_json_with_repair(text[start : end + 1])


def sanitize_llm_output(text: str, max_chars: int = 400) -> str:
    text = text.replace("\n", " ")
    return text[:max_chars]


def _load_json_with_repair(payload: str) -> dict:
    try:
        return json.loads(payload)
    except json.JSONDecodeError:
        repaired = _repair_invalid_escapes(payload)
        return json.loads(repaired)


def _repair_invalid_escapes(payload: str) -> str:
    valid_escapes = {"\"", "\\", "/", "b", "f", "n", "r", "t", "u"}
    result = []
    in_string = False
    escape = False
    i = 0
    while i < len(payload):
        ch = payload[i]
        if not in_string:
            if ch == "\"":
                in_string = True
            result.append(ch)
            i += 1
            continue

        if escape:
            result.append(ch)
            escape = False
            i += 1
            continue

        if ch == "\\":
            next_char = payload[i + 1] if i + 1 < len(payload) else ""
            if next_char in valid_escapes:
                result.append(ch)
            else:
                result.append("\\\\")
            escape = True if next_char else False
            i += 1
            continue

        if ch == "\"":
            in_string = False
        result.append(ch)
        i += 1
    return "".join(result)
