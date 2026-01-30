from __future__ import annotations

from datetime import datetime, timezone
from typing import List
from uuid import uuid4

from fastapi import FastAPI, Header, HTTPException, Request

from .parser import RuleBasedLogParser
from .schemas import (
    CanonicalResponse,
    ExplainRequest,
    Hypothesis,
    RunbookStep,
    StatusResponse,
    TriageRequest,
)
from .storage import get_storage

app = FastAPI(title="Troubleshooter API", version="0.1.0")

storage = get_storage()
parser = RuleBasedLogParser()


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    request_id = request.headers.get("x-request-id") or str(uuid4())
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-Id"] = request_id
    return response


@app.get("/status", response_model=StatusResponse)
async def status() -> StatusResponse:
    return StatusResponse(
        status="ok",
        dependencies=["parser", "storage"],
        timestamp=datetime.now(timezone.utc),
    )


@app.post("/triage", response_model=CanonicalResponse)
async def triage(payload: TriageRequest, request: Request) -> CanonicalResponse:
    request_id = payload.request_id or request.state.request_id
    conversation_id = payload.conversation_id or request_id
    raw_text = payload.raw_text.strip()

    if not raw_text:
        raise HTTPException(status_code=400, detail="raw_text is required")

    input_id = storage.save_input(conversation_id, request_id, raw_text)
    frame = parser.parse(raw_text, request_id, conversation_id)
    storage.save_frame(frame)

    hypotheses = build_hypotheses(frame, raw_text)
    runbook_steps = build_runbook_steps(frame, raw_text)

    response = CanonicalResponse(
        request_id=request_id,
        timestamp=datetime.now(timezone.utc),
        hypotheses=hypotheses,
        runbook_steps=runbook_steps,
        proposed_fix="Review the top hypothesis and apply targeted mitigation.",
        risk_notes=["Results are heuristic. Validate in staging before production changes."],
        rollback=["Revert the change or disable the feature flag if symptoms worsen."],
        next_checks=["Verify error rate drops within 10 minutes.", "Confirm logs no longer show the signature."],
        metadata={
            "parser_version": frame.parser_version,
            "parse_confidence": frame.parse_confidence,
            "input_id": input_id,
        },
        conversation_id=conversation_id,
    )
    storage.save_response(response)
    storage.save_event(conversation_id, request_id, raw_text, frame, response, input_id)
    storage.update_conversation_state(conversation_id, request_id, frame, response)
    return response


@app.post("/explain", response_model=CanonicalResponse)
async def explain(payload: ExplainRequest, request: Request) -> CanonicalResponse:
    request_id = payload.request_id or request.state.request_id
    conversation_id = payload.conversation_id or request_id

    if payload.incident_frame:
        frame = payload.incident_frame
        raw_text = frame.primary_error_signature or ""
        hypotheses = build_hypotheses(frame, raw_text)
    else:
        hypotheses = [
            Hypothesis(
                id="hyp-1",
                rank=1,
                confidence=0.4,
                explanation="No incident frame was provided. Provide logs or a trace to deepen analysis.",
                citations=[],
            )
        ]

    runbook_steps = [
        RunbookStep(
            step_number=1,
            description="Collect recent logs and provide the relevant error snippet.",
            command_or_console_path="",
            estimated_time_mins=5,
        )
    ]

    response = CanonicalResponse(
        request_id=request_id,
        timestamp=datetime.now(timezone.utc),
        hypotheses=hypotheses,
        runbook_steps=runbook_steps,
        proposed_fix="Provide additional context and re-run triage.",
        risk_notes=["Explanation confidence is limited without raw evidence."],
        rollback=["No action taken."],
        next_checks=["Attach the failing request id or stack trace."],
        metadata={
            "parser_version": getattr(payload.incident_frame, "parser_version", "unknown"),
        },
        conversation_id=conversation_id,
    )
    if payload.incident_frame:
        storage.save_response(response)
        storage.save_event(
            conversation_id,
            request_id,
            payload.incident_frame.primary_error_signature or "",
            payload.incident_frame,
            response,
            input_id=response.request_id,
        )
        storage.update_conversation_state(conversation_id, request_id, payload.incident_frame, response)
    return response


def build_hypotheses(frame, raw_text: str) -> List[Hypothesis]:
    lowered = raw_text.lower()
    evidence = frame.evidence_map[:1] if frame.evidence_map else []

    if "timeout" in lowered or "timed out" in lowered:
        return [
            Hypothesis(
                id="hyp-timeout",
                rank=1,
                confidence=0.74,
                explanation="Likely upstream timeout or slow dependency response.",
                citations=evidence,
            )
        ]
    if "permission" in lowered or "access denied" in lowered or "accessdenied" in lowered:
        return [
            Hypothesis(
                id="hyp-permissions",
                rank=1,
                confidence=0.7,
                explanation="Permissions or IAM policy may be blocking the request.",
                citations=evidence,
            )
        ]
    if "not found" in lowered or "404" in lowered:
        return [
            Hypothesis(
                id="hyp-missing-resource",
                rank=1,
                confidence=0.65,
                explanation="Referenced resource does not exist or was deleted.",
                citations=evidence,
            )
        ]

    return [
        Hypothesis(
            id="hyp-generic",
            rank=1,
            confidence=0.4,
            explanation="Generic failure. Provide more context to improve precision.",
            citations=evidence,
        )
    ]


def build_runbook_steps(frame, raw_text: str) -> List[RunbookStep]:
    return [
        RunbookStep(
            step_number=1,
            description="Identify the exact error signature and affected service.",
            command_or_console_path="CloudWatch Logs or application log viewer",
            estimated_time_mins=5,
        ),
        RunbookStep(
            step_number=2,
            description="Check recent deploys or configuration changes.",
            command_or_console_path="CI/CD dashboard",
            estimated_time_mins=10,
        ),
    ]
