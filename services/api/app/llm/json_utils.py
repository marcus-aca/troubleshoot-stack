from __future__ import annotations

import json
from typing import Optional


def extract_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("{") and text.endswith("}"):
        return _load_json_with_repair(text)
    start = text.find("{")
    end = text.rfind("}")
    if start == -1:
        raise ValueError("No JSON object found in LLM output")
    if end == -1 or end <= start:
        recovered = _recover_truncated_json(text[start:])
        if recovered:
            return _load_json_with_repair(recovered)
        raise ValueError("No complete JSON object found in LLM output")
    candidate = text[start : end + 1]
    try:
        return _load_json_with_repair(candidate)
    except json.JSONDecodeError:
        recovered = _recover_truncated_json(text[start:])
        if recovered:
            return _load_json_with_repair(recovered)
        raise


def sanitize_llm_output(text: str, max_chars: int = 400) -> str:
    text = text.replace("\n", " ")
    return text[:max_chars]


def _load_json_with_repair(payload: str) -> dict:
    try:
        return json.loads(payload)
    except json.JSONDecodeError:
        repaired = _repair_invalid_escapes(payload)
        repaired = _escape_control_chars_in_strings(repaired)
        try:
            return json.loads(repaired, strict=False)
        except json.JSONDecodeError:
            recovered = _try_insert_missing_commas(repaired)
            if recovered is not None:
                return recovered
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


def _escape_control_chars_in_strings(payload: str) -> str:
    result = []
    in_string = False
    escape = False
    for ch in payload:
        if in_string:
            if escape:
                result.append(ch)
                escape = False
                continue
            if ch == "\\":
                result.append(ch)
                escape = True
                continue
            if ch == "\"":
                in_string = False
                result.append(ch)
                continue
            if ch == "\n":
                result.append("\\n")
                continue
            if ch == "\r":
                result.append("\\r")
                continue
            if ch == "\t":
                result.append("\\t")
                continue
            result.append(ch)
            continue
        else:
            if ch == "\"":
                in_string = True
            result.append(ch)
    return "".join(result)


def _try_insert_missing_commas(payload: str, *, max_attempts: int = 3) -> dict | None:
    current = payload
    for _ in range(max_attempts):
        try:
            return json.loads(current, strict=False)
        except json.JSONDecodeError as exc:
            if "Expecting ',' delimiter" not in str(exc):
                return None
            pos = exc.pos
            if pos <= 0 or pos >= len(current):
                return None
            prev_idx = pos - 1
            while prev_idx >= 0 and current[prev_idx].isspace():
                prev_idx -= 1
            next_idx = pos
            while next_idx < len(current) and current[next_idx].isspace():
                next_idx += 1
            if prev_idx < 0 or next_idx >= len(current):
                return None
            prev_ch = current[prev_idx]
            next_ch = current[next_idx]
            if prev_ch in ('"', "}", "]") and next_ch in ('"', "{", "["):
                current = current[:pos] + "," + current[pos:]
                continue
            return None
    return None


def _recover_truncated_json(payload: str) -> str | None:
    trimmed = payload.strip()
    if not trimmed.startswith("{"):
        return None
    balanced = _extract_balanced_object(trimmed)
    if balanced:
        return balanced
    closed = _attempt_close_json(trimmed)
    if closed:
        return closed
    return None


def _extract_balanced_object(text: str) -> str | None:
    depth = 0
    in_string = False
    escape = False
    last_complete = None
    for idx, ch in enumerate(text):
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == "\"":
                in_string = False
            continue
        if ch == "\"":
            in_string = True
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                last_complete = idx + 1
    if last_complete:
        return text[:last_complete]
    return None


def _attempt_close_json(text: str) -> str | None:
    depth = 0
    in_string = False
    escape = False
    for ch in text:
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == "\"":
                in_string = False
            continue
        if ch == "\"":
            in_string = True
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth = max(depth - 1, 0)
    if depth == 0 and not in_string:
        return None
    suffix = ""
    if in_string:
        suffix += "\""
    if depth > 0:
        suffix += "}" * depth
    closed = (text + suffix).strip()
    return closed if closed != text else None
