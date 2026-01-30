from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional, Tuple

from ..parser import ParserAdapter
from ..schemas import (
    CanonicalResponse,
    EvidenceMapEntry,
    ExplainLLMOutput,
    Hypothesis,
    RunbookStep,
    TriageLLMOutput,
)
from ..storage import StorageAdapter, build_llm_context
from .bedrock import BedrockAdapter
from .guardrails import GuardrailReport, enforce_guardrails
from .json_utils import extract_json, sanitize_llm_output
from .prompt_registry import PromptRegistry
from ..observability import CloudWatchMetrics, log_event, start_timer, stop_timer


class LLMOrchestrator:
    def __init__(
        self,
        storage: StorageAdapter,
        parser: ParserAdapter,
        prompt_registry: Optional[PromptRegistry] = None,
        llm_adapter: Optional[BedrockAdapter] = None,
    ) -> None:
        self.storage = storage
        self.parser = parser
        self.prompt_registry = prompt_registry or PromptRegistry()
        self.llm = llm_adapter or BedrockAdapter()
        self.metrics = CloudWatchMetrics()

    def triage(
        self,
        raw_text: str,
        request_id: str,
        conversation_id: str,
    ) -> Tuple[CanonicalResponse, GuardrailReport, object]:
        frame = self.parser.parse(raw_text, request_id, conversation_id)
        prompt_meta = self.prompt_registry.get_prompt("triage")
        prompt = self._build_prompt("triage", frame.model_dump(), raw_text, conversation_id)
        timer = start_timer()
        try:
            result = self.llm.generate(prompt, request_id=request_id)
            payload = extract_json(result.text)
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
                },
            )
            raise

        hypotheses, report = enforce_guardrails(
            llm_output.hypotheses, allowed_citations=frame.evidence_map
        )

        response = CanonicalResponse(
            request_id=request_id,
            timestamp=datetime.now(timezone.utc),
            hypotheses=hypotheses,
            runbook_steps=llm_output.runbook_steps or _default_triage_runbook(frame.evidence_map),
            proposed_fix="Review the top hypothesis and apply targeted mitigation.",
            risk_notes=["LLM output is advisory; validate before production changes."],
            rollback=["Revert the change or disable the feature flag if symptoms worsen."],
            next_checks=["Verify error rate drops within 10 minutes.", "Confirm logs no longer show the signature."],
            metadata={
                "parser_version": frame.parser_version,
                "parse_confidence": frame.parse_confidence,
                "prompt_version": prompt_meta.metadata.get("prompt_version"),
                "prompt_filename": prompt_meta.filename,
                "model_id": result.model_id,
                "token_usage": result.token_usage,
                "guardrails": report.__dict__,
                "category": llm_output.category,
                "recommended_tool_calls": [call.model_dump() for call in llm_output.recommended_tool_calls],
            },
            conversation_id=conversation_id,
        )
        latency_ms = stop_timer(timer)
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
            },
        )
        return response, report, frame

    def explain(
        self,
        frame: Optional[dict],
        question: str,
        request_id: str,
        conversation_id: str,
    ) -> Tuple[CanonicalResponse, GuardrailReport]:
        prompt_meta = self.prompt_registry.get_prompt("explain")
        prompt = self._build_prompt("explain", frame or {}, question, conversation_id)
        timer = start_timer()
        try:
            result = self.llm.generate(prompt, request_id=request_id)
            payload = extract_json(result.text)
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
                },
            )
            raise

        evidence = []
        if frame:
            evidence = [EvidenceMapEntry(**entry) for entry in frame.get("evidence_map", [])]

        hypotheses, report = enforce_guardrails(llm_output.hypotheses, allowed_citations=evidence)

        response = CanonicalResponse(
            request_id=request_id,
            timestamp=datetime.now(timezone.utc),
            hypotheses=hypotheses,
            runbook_steps=llm_output.runbook_steps or _default_explain_runbook(),
            proposed_fix=llm_output.proposed_fix,
            risk_notes=llm_output.risk_notes,
            rollback=llm_output.rollback,
            next_checks=llm_output.next_checks,
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
        return (
            f"{prompt.text}\n\n"
            f"Conversation ID: {conversation_id}\n"
            f"Question or raw input: {input_text}\n"
            f"Incident frame: {frame}\n"
            f"Conversation context: {context.get('recent_events', [])}\n"
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


def _default_triage_runbook(evidence: list[EvidenceMapEntry]) -> list[RunbookStep]:
    return [
        RunbookStep(
            step_number=1,
            description="Confirm the error signature in the raw logs.",
            command_or_console_path="CloudWatch Logs or log viewer",
            estimated_time_mins=5,
        ),
        RunbookStep(
            step_number=2,
            description="Identify recent deploys or config changes.",
            command_or_console_path="CI/CD dashboard",
            estimated_time_mins=10,
        ),
    ]


def _default_explain_runbook() -> list[RunbookStep]:
    return [
        RunbookStep(
            step_number=1,
            description="Collect additional logs or traces that capture the failure.",
            command_or_console_path="Log viewer or APM",
            estimated_time_mins=10,
        )
    ]
