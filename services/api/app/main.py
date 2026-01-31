from __future__ import annotations

from datetime import datetime, timezone
from typing import List
from uuid import uuid4

import os

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import ValidationError

from .parser import RuleBasedLogParser
from .cache import PgVectorCache
from .budget import BudgetEnforcer, estimate_tokens
from .llm.orchestrator import LLMOrchestrator
from .schemas import (
    CanonicalResponse,
    ExplainRequest,
    Hypothesis,
    IncidentFrame,
    RunbookStep,
    StatusResponse,
    TriageRequest,
)
from .storage import get_storage
from .observability import log_event

app = FastAPI(title="Troubleshooter API", version="0.1.0")

storage = get_storage()
parser = RuleBasedLogParser()
llm_orchestrator = LLMOrchestrator(storage=storage, parser=parser)
cache = PgVectorCache()
budget = BudgetEnforcer()

cors_origins = [
    origin.strip()
    for origin in os.getenv("CORS_ALLOWED_ORIGINS", "").split(",")
    if origin.strip()
]
if cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
        expose_headers=["X-Request-Id"],
    )


@app.middleware("http")
async def cors_header_middleware(request: Request, call_next):
    response = await call_next(request)
    origin = request.headers.get("origin")
    if origin and origin in cors_origins:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Methods"] = "GET,POST,OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type,X-Request-Id,X-Api-Key"
        response.headers["Access-Control-Expose-Headers"] = "X-Request-Id"
        response.headers["Vary"] = "Origin"
    return response


@app.on_event("startup")
async def bootstrap_cache() -> None:
    cache.bootstrap()


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

    log_event(
        "triage_request",
        {
            "request_id": request_id,
            "conversation_id": conversation_id,
            "source": payload.source,
        },
    )
    input_id = storage.save_input(conversation_id, request_id, raw_text)
    _enforce_budget_or_raise(raw_text)
    try:
        response, _, frame = llm_orchestrator.triage(raw_text, request_id, conversation_id)
    except (ValueError, ValidationError) as exc:
        raise HTTPException(status_code=502, detail="LLM returned invalid JSON") from exc
    response.metadata["input_id"] = input_id
    storage.save_response(response)
    storage.save_frame(frame)
    storage.save_event(conversation_id, request_id, raw_text, frame, response, input_id)
    storage.update_conversation_state(conversation_id, request_id, frame, response)
    return response


@app.post("/explain", response_model=CanonicalResponse)
async def explain(payload: ExplainRequest, request: Request) -> CanonicalResponse:
    request_id = payload.request_id or request.state.request_id
    conversation_id = payload.conversation_id or request_id
    frame_obj = payload.incident_frame
    if not frame_obj:
        context = storage.get_conversation_context(conversation_id)
        latest_frame = (context.get("state") or {}).get("latest_incident_frame")
        if latest_frame:
            frame_obj = IncidentFrame.model_validate(latest_frame)
        else:
            return CanonicalResponse(
                request_id=request_id,
                timestamp=datetime.now(timezone.utc),
                hypotheses=[
                    Hypothesis(
                        id="hyp-1",
                        rank=1,
                        confidence=0.3,
                        explanation="No incident frame was provided. Provide logs or a trace to deepen analysis.",
                        citations=[],
                    )
                ],
                runbook_steps=[
                    RunbookStep(
                        step_number=1,
                        description="Collect recent logs and provide the relevant error snippet.",
                        command_or_console_path="",
                        estimated_time_mins=5,
                    )
                ],
                proposed_fix="Provide additional context and re-run triage.",
                risk_notes=["Explanation confidence is limited without raw evidence."],
                rollback=["No action taken."],
                next_checks=["Attach the failing request id or stack trace."],
                metadata={"parser_version": "unknown"},
                conversation_id=conversation_id,
            )

    log_event(
        "explain_request",
        {
            "request_id": request_id,
            "conversation_id": conversation_id,
        },
    )
    frame = frame_obj.model_dump()

    cache_key = cache.get_explain_cache_key(frame_obj, payload.question)
    cache_hit = cache.lookup(endpoint="explain", query_text=cache_key)
    if cache_hit:
        cached_response = _hydrate_cached_response(
            cache_hit.response,
            request_id=request_id,
            conversation_id=conversation_id,
            similarity=cache_hit.similarity,
        )
        storage.save_response(cached_response)
        storage.save_event(
            conversation_id,
            request_id,
            frame_obj.primary_error_signature or "",
            frame_obj,
            cached_response,
            input_id=cached_response.request_id,
        )
        storage.update_conversation_state(conversation_id, request_id, frame_obj, cached_response)
        log_event(
            "cache_hit",
            {
                "request_id": request_id,
                "conversation_id": conversation_id,
                "similarity": cache_hit.similarity,
            },
        )
        return cached_response

    _enforce_budget_or_raise(cache_key)

    try:
        response, _ = llm_orchestrator.explain(
            frame,
            payload.question,
            request_id,
            conversation_id,
        )
    except (ValueError, ValidationError) as exc:
        raise HTTPException(status_code=502, detail="LLM returned invalid JSON") from exc
    storage.save_response(response)
    storage.save_event(
        conversation_id,
        request_id,
            frame_obj.primary_error_signature or "",
            frame_obj,
            response,
            input_id=response.request_id,
        )
    storage.update_conversation_state(conversation_id, request_id, frame_obj, response)
    cache.put(endpoint="explain", query_text=cache_key, response=response)
    return response


def _hydrate_cached_response(
    cached: CanonicalResponse,
    *,
    request_id: str,
    conversation_id: str,
    similarity: float,
) -> CanonicalResponse:
    payload = cached.model_dump()
    payload["request_id"] = request_id
    payload["conversation_id"] = conversation_id
    payload["timestamp"] = datetime.now(timezone.utc)
    metadata = payload.get("metadata") or {}
    metadata.update(
        {
            "cache_hit": True,
            "cache_similarity": similarity,
            "cache_source": "pgvector",
        }
    )
    payload["metadata"] = metadata
    return CanonicalResponse.model_validate(payload)


def _enforce_budget_or_raise(text: str) -> None:
    max_tokens = int(os.getenv("LLM_MAX_TOKENS", "800"))
    estimated_tokens = estimate_tokens(text, max_tokens=max_tokens)
    decision = budget.enforce(estimated_tokens=estimated_tokens)
    if decision.allowed:
        return
    raise HTTPException(
        status_code=402,
        detail={
            "error": "budget_exceeded",
            "message": "Token budget exceeded for this window.",
            "remaining_budget": 0,
            "retry_after": decision.retry_after,
        },
    )


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
