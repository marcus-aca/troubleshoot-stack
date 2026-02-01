from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional, Tuple

from ..parser import ParserAdapter
from ..schemas import (
    CanonicalResponse,
    EvidenceMapEntry,
    ExplainLLMOutput,
    TriageLLMOutput,
)
from ..storage import StorageAdapter, build_llm_context
from .bedrock import BedrockAdapter
from .guardrails import GuardrailReport, citation_signature, enforce_guardrails
from .json_utils import extract_json, sanitize_llm_output
from .prompt_registry import PromptRegistry
from ..observability import CloudWatchMetrics, log_event, start_timer, stop_timer
from opentelemetry import trace


class LLMOrchestrator:
    def __init__(
        self,
        storage: StorageAdapter,
        parser: ParserAdapter,
        prompt_registry: Optional[PromptRegistry] = None,
        llm_adapter: Optional[BedrockAdapter] = None,
        rolling_llm_latency: Optional[object] = None,
    ) -> None:
        self.storage = storage
        self.parser = parser
        self.prompt_registry = prompt_registry or PromptRegistry()
        self.llm = llm_adapter or BedrockAdapter()
        self.metrics = CloudWatchMetrics()
        self.rolling_llm_latency = rolling_llm_latency

    def triage(
        self,
        raw_text: str,
        request_id: str,
        conversation_id: str,
    ) -> Tuple[CanonicalResponse, GuardrailReport, object]:
        tracer = trace.get_tracer(__name__)
        frame = self.parser.parse(raw_text, request_id, conversation_id)
        prompt_meta = self.prompt_registry.get_prompt("triage")
        prompt = self._build_prompt("triage", frame.model_dump(), raw_text, conversation_id)
        timer = start_timer()
        try:
            with tracer.start_as_current_span("llm.generate", attributes={"endpoint": "triage"}):
                result = self.llm.generate(prompt, request_id=request_id)
            payload = extract_json(result.text)
            payload = _normalize_llm_payload(payload, frame.evidence_map)
            llm_output = TriageLLMOutput.model_validate(payload)
        except Exception as exc:
            latency_ms = stop_timer(timer)
            self._record_metrics(
                endpoint="triage",
                model_id=self.llm.model_id,
                latency_ms=latency_ms,
                token_usage={},
                guardrails=GuardrailReport(),
                success=False,
            )
            log_event(
                "triage_error",
                {
                    "request_id": request_id,
                    "conversation_id": conversation_id,
                    "error": str(exc),
                    "llm_output_preview": sanitize_llm_output(result.text if "result" in locals() else ""),
                    "llm_output": result.text if "result" in locals() else "",
                },
            )
            raise

        hypotheses, report = enforce_guardrails(
            llm_output.hypotheses, allowed_citations=frame.evidence_map
        )

        tool_calls = llm_output.tool_calls[:1]
        next_question = llm_output.next_question if not tool_calls else None
        completion_state = llm_output.completion_state
        if tool_calls and completion_state == "final":
            completion_state = "needs_input"
        response = CanonicalResponse(
            request_id=request_id,
            timestamp=datetime.now(timezone.utc),
            assistant_message=llm_output.assistant_message,
            completion_state=completion_state,
            next_question=next_question,
            tool_calls=tool_calls,
            hypotheses=hypotheses,
            fix_steps=llm_output.fix_steps,
            metadata={
                "parser_version": frame.parser_version,
                "parse_confidence": frame.parse_confidence,
                "prompt_version": prompt_meta.metadata.get("prompt_version"),
                "prompt_filename": prompt_meta.filename,
                "model_id": result.model_id,
                "token_usage": result.token_usage,
                "guardrails": report.__dict__,
                "category": llm_output.category,
            },
            conversation_id=conversation_id,
        )
        latency_ms = stop_timer(timer)
        rolling_llm_latency = getattr(self, "rolling_llm_latency", None)
        if rolling_llm_latency:
            rolling_llm_latency.add(latency_ms)
        self._record_metrics(
            endpoint="triage",
            model_id=result.model_id,
            latency_ms=latency_ms,
            token_usage=result.token_usage,
            guardrails=report,
            success=True,
        )
        log_event(
            "triage_response",
            {
                "request_id": request_id,
                "conversation_id": conversation_id,
                "prompt_version": prompt_meta.metadata.get("prompt_version"),
                "prompt_filename": prompt_meta.filename,
                "model_id": result.model_id,
                "token_usage": result.token_usage,
                "guardrails": report.__dict__,
                "completion_state": response.completion_state,
                "next_question": llm_output.next_question,
                "question_plan": [llm_output.next_question] if llm_output.next_question else [],
                "tool_call_plan": [call.model_dump() for call in llm_output.tool_calls],
                "tool_calls": [call.model_dump() for call in tool_calls],
            },
        )
        return response, report, frame

    def explain(
        self,
        frame: Optional[dict],
        response: str,
        request_id: str,
        conversation_id: str,
    ) -> Tuple[CanonicalResponse, GuardrailReport]:
        tracer = trace.get_tracer(__name__)
        prompt_meta = self.prompt_registry.get_prompt("explain")
        prompt = self._build_prompt("explain", frame or {}, response, conversation_id)
        timer = start_timer()
        try:
            with tracer.start_as_current_span("llm.generate", attributes={"endpoint": "explain"}):
                result = self.llm.generate(prompt, request_id=request_id)
            payload = extract_json(result.text)
            payload = _normalize_llm_payload(payload, (frame or {}).get("evidence_map", []))
            llm_output = ExplainLLMOutput.model_validate(payload)
        except Exception as exc:
            latency_ms = stop_timer(timer)
            self._record_metrics(
                endpoint="explain",
                model_id=self.llm.model_id,
                latency_ms=latency_ms,
                token_usage={},
                guardrails=GuardrailReport(),
                success=False,
            )
            log_event(
                "explain_error",
                {
                    "request_id": request_id,
                    "conversation_id": conversation_id,
                    "error": str(exc),
                    "llm_output_preview": sanitize_llm_output(result.text if "result" in locals() else ""),
                    "llm_output": result.text if "result" in locals() else "",
                },
            )
            raise

        evidence = []
        if frame:
            evidence = [EvidenceMapEntry(**entry) for entry in frame.get("evidence_map", [])]

        hypotheses, report = enforce_guardrails(llm_output.hypotheses, allowed_citations=evidence)

        tool_calls = llm_output.tool_calls[:1]
        next_question = llm_output.next_question if not tool_calls else None
        completion_state = llm_output.completion_state
        if tool_calls and completion_state == "final":
            completion_state = "needs_input"
        response = CanonicalResponse(
            request_id=request_id,
            timestamp=datetime.now(timezone.utc),
            assistant_message=llm_output.assistant_message,
            completion_state=completion_state,
            next_question=next_question,
            tool_calls=tool_calls,
            hypotheses=hypotheses,
            fix_steps=llm_output.fix_steps,
            metadata={
                "prompt_version": prompt_meta.metadata.get("prompt_version"),
                "prompt_filename": prompt_meta.filename,
                "model_id": result.model_id,
                "token_usage": result.token_usage,
                "guardrails": report.__dict__,
            },
            conversation_id=conversation_id,
        )
        latency_ms = stop_timer(timer)
        rolling_llm_latency = getattr(self, "rolling_llm_latency", None)
        if rolling_llm_latency:
            rolling_llm_latency.add(latency_ms)
        self._record_metrics(
            endpoint="explain",
            model_id=result.model_id,
            latency_ms=latency_ms,
            token_usage=result.token_usage,
            guardrails=report,
            success=True,
        )
        log_event(
            "explain_response",
            {
                "request_id": request_id,
                "conversation_id": conversation_id,
                "prompt_version": prompt_meta.metadata.get("prompt_version"),
                "prompt_filename": prompt_meta.filename,
                "model_id": result.model_id,
                "token_usage": result.token_usage,
                "guardrails": report.__dict__,
            },
        )
        return response, report

    def _build_prompt(
        self,
        endpoint: str,
        frame: dict,
        input_text: str,
        conversation_id: str,
    ) -> str:
        prompt = self.prompt_registry.get_prompt(endpoint)
        context = build_llm_context(self.storage, conversation_id, limit=5)
        latest_summary = context.get("latest_response_summary") or {}
        return (
            f"{prompt.text}\n\n"
            f"Conversation ID: {conversation_id}\n"
            f"User input: {input_text}\n"
            f"Incident frame: {frame}\n"
            f"Conversation context: {context.get('recent_events', [])}\n"
            f"Recent user inputs: {context.get('recent_messages', [])}\n"
            f"Latest response summary: {latest_summary}\n"
            f"Evidence map: {frame.get('evidence_map', [])}\n"
            "Return ONLY valid JSON."
        )

    def _record_metrics(
        self,
        *,
        endpoint: str,
        model_id: str,
        latency_ms: float,
        token_usage: dict,
        guardrails: GuardrailReport,
        success: bool,
    ) -> None:
        self.metrics.put_llm_metrics(
            endpoint=endpoint,
            model_id=model_id,
            latency_ms=latency_ms,
            tokens_total=int(token_usage.get("total_tokens", 0)),
            success=success,
            guardrail_missing=guardrails.citation_missing_count,
            guardrail_redactions=guardrails.redactions,
        )

    def classify_answer(
        self,
        *,
        question: str,
        answer: str,
        request_id: str,
        conversation_id: str,
    ) -> tuple[bool, float]:
        prompt = (
            "Determine if the user's reply answers the question. "
            "Return JSON: {\"answered\": true|false, \"confidence\": 0-1}.\n\n"
            f"Question: {question}\n"
            f"Answer: {answer}\n"
            "Return ONLY valid JSON."
        )
        timer = start_timer()
        try:
            result = self.llm.generate(prompt, request_id=request_id)
            payload = extract_json(result.text)
            answered = bool(payload.get("answered"))
            confidence = float(payload.get("confidence", 0.5))
            confidence = max(0.0, min(1.0, confidence))
            self._record_metrics(
                endpoint="answer_classifier",
                model_id=result.model_id,
                latency_ms=stop_timer(timer),
                token_usage=result.token_usage,
                guardrails=GuardrailReport(),
                success=True,
            )
            log_event(
                "answer_classifier",
                {
                    "request_id": request_id,
                    "conversation_id": conversation_id,
                    "answered": answered,
                    "confidence": confidence,
                    "model_id": result.model_id,
                },
            )
            return answered, confidence
        except Exception as exc:
            self._record_metrics(
                endpoint="answer_classifier",
                model_id=self.llm.model_id,
                latency_ms=stop_timer(timer),
                token_usage={},
                guardrails=GuardrailReport(),
                success=False,
            )
            log_event(
                "answer_classifier_error",
                {
                    "request_id": request_id,
                    "conversation_id": conversation_id,
                    "error": str(exc),
                },
            )
            return False, 0.0



def _normalize_llm_payload(payload: dict, evidence_map: list[object]) -> dict:
    if not isinstance(payload, dict):
        return payload

    hypotheses = payload.get("hypotheses")
    if not isinstance(hypotheses, list):
        return payload

    allowed_entries = _normalize_evidence_entries(evidence_map)
    if not allowed_entries:
        for hypothesis in hypotheses:
            if isinstance(hypothesis, dict):
                hypothesis["citations"] = []
        return payload

    allowed_by_signature = {}
    allowed_by_hash = {}
    allowed_by_excerpt = {}
    allowed_by_lines = {}
    for entry in allowed_entries:
        signature = citation_signature(entry)
        allowed_by_signature[signature] = entry
        if entry.excerpt_hash:
            allowed_by_hash[entry.excerpt_hash] = entry
        if entry.excerpt:
            allowed_by_excerpt[entry.excerpt.strip()] = entry
        allowed_by_lines[(entry.source_type, entry.source_id, entry.line_start, entry.line_end)] = entry

    required_keys = {"source_type", "source_id", "line_start", "line_end", "excerpt_hash"}
    for hypothesis in hypotheses:
        if not isinstance(hypothesis, dict):
            continue
        citations = hypothesis.get("citations", [])
        if not isinstance(citations, list):
            hypothesis["citations"] = []
            continue
        normalized: list[dict] = []
        for citation in citations:
            if isinstance(citation, EvidenceMapEntry):
                normalized.append(citation.model_dump())
                continue
            if not isinstance(citation, dict):
                continue
            if required_keys.issubset(citation.keys()):
                normalized.append(citation)
                continue

            matched = _match_citation(
                citation,
                allowed_by_signature=allowed_by_signature,
                allowed_by_hash=allowed_by_hash,
                allowed_by_excerpt=allowed_by_excerpt,
                allowed_by_lines=allowed_by_lines,
                allowed_entries=allowed_entries,
            )
            if matched:
                normalized.append(matched.model_dump())
        hypothesis["citations"] = normalized

    return payload


def _normalize_evidence_entries(evidence_map: list[object]) -> list[EvidenceMapEntry]:
    normalized: list[EvidenceMapEntry] = []
    for entry in evidence_map:
        if isinstance(entry, EvidenceMapEntry):
            normalized.append(entry)
            continue
        try:
            normalized.append(EvidenceMapEntry.model_validate(entry))
        except Exception:
            continue
    return normalized


def _match_citation(
    citation: dict,
    *,
    allowed_by_signature: dict[str, EvidenceMapEntry],
    allowed_by_hash: dict[str, EvidenceMapEntry],
    allowed_by_excerpt: dict[str, EvidenceMapEntry],
    allowed_by_lines: dict[tuple[str, str, int, int], EvidenceMapEntry],
    allowed_entries: list[EvidenceMapEntry],
) -> EvidenceMapEntry | None:
    entry_id = citation.get("evidence_map_entry_id")
    if entry_id is not None:
        key = str(entry_id)
        if key in allowed_by_signature:
            return allowed_by_signature[key]
        if key in allowed_by_hash:
            return allowed_by_hash[key]
        if key.isdigit():
            idx = int(key)
            if 0 <= idx < len(allowed_entries):
                return allowed_entries[idx]

    excerpt_hash = citation.get("excerpt_hash")
    if excerpt_hash in allowed_by_hash:
        return allowed_by_hash[excerpt_hash]

    excerpt = citation.get("excerpt")
    if isinstance(excerpt, str):
        matched = allowed_by_excerpt.get(excerpt.strip())
        if matched:
            return matched

    line_start = citation.get("line_start")
    line_end = citation.get("line_end")
    if isinstance(line_start, int) and isinstance(line_end, int):
        source_type = citation.get("source_type") or "log"
        source_id = citation.get("source_id") or "raw-input"
        matched = allowed_by_lines.get((source_type, source_id, line_start, line_end))
        if matched:
            return matched

    return None
