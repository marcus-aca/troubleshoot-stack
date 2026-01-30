from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
from typing import Dict, Optional


@dataclass(frozen=True)
class Prompt:
    text: str
    metadata: Dict[str, str]
    filename: str


DEFAULT_PROMPT_REGISTRY = {
    "triage": {"version": "v2", "filename": "v2/triage/triage.md"},
    "explain": {"version": "v1", "filename": "v1/explain/explain.md"},
}


class PromptRegistry:
    def __init__(self, prompt_root: Optional[Path] = None) -> None:
        self.prompt_root = prompt_root or _default_prompt_root()
        self.registry = _load_registry()

    def get_prompt(self, endpoint: str, version: Optional[str] = None) -> Prompt:
        entry = self.registry.get(endpoint)
        if not entry:
            raise ValueError(f"Unknown prompt endpoint: {endpoint}")
        if version and entry.get("version") != version:
            raise ValueError(f"Prompt version {version} not found for endpoint {endpoint}")
        filename = entry.get("filename")
        if not filename:
            raise ValueError(f"Prompt filename missing for endpoint {endpoint}")
        path = self.prompt_root / filename
        if not path.exists():
            raise FileNotFoundError(f"Prompt file not found: {path}")
        text = path.read_text(encoding="utf-8")
        metadata, body = _parse_prompt(text)
        metadata.setdefault("prompt_version", entry.get("version", "unknown"))
        metadata.setdefault("designed_for_endpoint", endpoint)
        return Prompt(text=body, metadata=metadata, filename=str(path))


def _default_prompt_root() -> Path:
    return Path(__file__).resolve().parents[2] / "prompts"


def _load_registry() -> Dict[str, Dict[str, str]]:
    raw = os.getenv("PROMPT_REGISTRY_JSON")
    if not raw:
        return DEFAULT_PROMPT_REGISTRY
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("PROMPT_REGISTRY_JSON must be valid JSON") from exc
    if not isinstance(parsed, dict):
        raise ValueError("PROMPT_REGISTRY_JSON must be a JSON object")
    return parsed


def _parse_prompt(text: str) -> tuple[Dict[str, str], str]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, text.strip()
    metadata: Dict[str, str] = {}
    body_start = 0
    for idx, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            body_start = idx + 1
            break
        if ":" in line:
            key, value = line.split(":", 1)
            metadata[key.strip()] = value.strip()
    body = "\n".join(lines[body_start:]).strip()
    return metadata, body
