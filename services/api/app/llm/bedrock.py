from __future__ import annotations

from dataclasses import dataclass
import json
import os
import re
import time
from typing import Any, Dict, Optional

import boto3

from ..observability import log_event, start_timer, stop_timer

@dataclass(frozen=True)
class LLMResult:
    text: str
    model_id: str
    provider: str
    token_usage: Dict[str, int]
    request_id: Optional[str] = None


class BedrockAdapter:
    def __init__(self) -> None:
        self.mode = os.getenv("LLM_MODE", "stub").lower()
        self.model_id = os.getenv("BEDROCK_MODEL_ID", "amazon.titan-text-lite-v1")
        self.client = None
        if self.mode == "bedrock":
            self.client = boto3.client("bedrock-runtime")

    def generate(self, prompt: str, *, request_id: Optional[str] = None) -> LLMResult:
        if self.mode != "bedrock":
            return self._stub_response(prompt, request_id=request_id)
        if not self.client:
            raise RuntimeError("Bedrock client not initialized")

        payload = self._build_request(prompt)
        timer = start_timer()
        success = False
        try:
            response = self.client.invoke_model(
                modelId=self.model_id,
                body=json.dumps(payload).encode("utf-8"),
                accept="application/json",
                contentType="application/json",
            )
            raw_body = response.get("body")
            if hasattr(raw_body, "read"):
                raw_body = raw_body.read()
            data = json.loads(raw_body)
            text = self._extract_text(data)
            token_usage = _estimate_tokens(prompt, text)
            success = True
            return LLMResult(
                text=text,
                model_id=self.model_id,
                provider="bedrock",
                token_usage=token_usage,
                request_id=request_id,
            )
        finally:
            latency_ms = stop_timer(timer)
            log_event(
                "llm_call",
                {
                    "request_id": request_id,
                    "model_id": self.model_id,
                    "provider": "bedrock",
                    "latency_ms": round(latency_ms, 2),
                    "success": success,
                },
            )

    def _stub_response(self, prompt: str, *, request_id: Optional[str] = None) -> LLMResult:
        lowered = prompt.lower()
        if "explain" in lowered:
            payload = {
                "assistant_message": "Here is a concise explanation based on the latest context.",
                "completion_state": "final",
                "next_question": None,
                "tool_calls": [],
                "hypotheses": [
                    {
                        "id": "hyp-1",
                        "rank": 1,
                        "confidence": 0.52,
                        "explanation": "Primary error signature suggests a configuration or permission issue.",
                        "citations": [],
                    }
                ],
                "fix_steps": ["Verify the config and redeploy if the change is confirmed."],
            }
        else:
            payload = {
                "category": "other",
                "assistant_message": "I need a bit more context. Please share the exact error output.",
                "completion_state": "needs_input",
                "next_question": "Share the exact error output or stack trace.",
                "tool_calls": [],
                "hypotheses": [
                    {
                        "id": "hyp-1",
                        "rank": 1,
                        "confidence": 0.55,
                        "explanation": "Likely misconfiguration or dependency issue based on the log signature.",
                        "citations": [],
                    }
                ],
                "fix_steps": [],
            }
        text = json.dumps(payload)
        token_usage = _estimate_tokens(prompt, text)
        return LLMResult(
            text=text,
            model_id="stub-model",
            provider="stub",
            token_usage=token_usage,
            request_id=request_id,
        )

    def _build_request(self, prompt: str) -> Dict[str, Any]:
        if self.model_id.startswith("openai.gpt-oss-"):
            return {
                "model": self.model_id,
                "messages": [
                    {"role": "system", "content": "You are a helpful troubleshooting assistant."},
                    {"role": "user", "content": prompt},
                ],
                "max_completion_tokens": int(os.getenv("LLM_MAX_TOKENS", "800")),
                "reasoning_effort": os.getenv("LLM_REASONING_EFFORT", "low"),
                "temperature": float(os.getenv("LLM_TEMPERATURE", "0.2")),
                "top_p": float(os.getenv("LLM_TOP_P", "0.9")),
                "stream": False,
            }
        return {"inputText": prompt}

    def _extract_text(self, data: Dict[str, Any]) -> str:
        if self.model_id.startswith("openai.gpt-oss-"):
            choices = data.get("choices", [])
            if not choices:
                return ""
            message = choices[0].get("message", {})
            content = message.get("content", "")
            if isinstance(content, list):
                raw = "".join(part.get("text", "") for part in content)
            else:
                raw = content or ""
            return _strip_reasoning(raw)
        return _strip_reasoning(data.get("results", [{}])[0].get("outputText", ""))


def _estimate_tokens(prompt: str, completion: str) -> Dict[str, int]:
    prompt_tokens = max(1, int(len(prompt) / 4))
    completion_tokens = max(1, int(len(completion) / 4))
    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": prompt_tokens + completion_tokens,
        "generated_at_ms": int(time.time() * 1000),
    }


def _strip_reasoning(text: str) -> str:
    if not text:
        return text
    return re.sub(r"<reasoning>.*?</reasoning>", "", text, flags=re.DOTALL).strip()
