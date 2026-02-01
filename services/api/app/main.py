from __future__ import annotations

from datetime import datetime, timezone
from typing import List
import re
from uuid import uuid4

import os

from fastapi import FastAPI, Header, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import ValidationError

from .parser import RuleBasedLogParser
from .cache import PgVectorCache
from .budget import BudgetEnforcer, estimate_tokens
from .llm.orchestrator import LLMOrchestrator
from .schemas import (
    CanonicalResponse,
    ChatResponse,
    ChatHypothesis,
    ExplainRequest,
    Hypothesis,
    IncidentFrame,
    StatusResponse,
    MetricsSummaryResponse,
    BudgetStatusResponse,
    TriageRequest,
)
from .storage import get_storage
from .observability import (
    CloudWatchMetrics,
    RollingCacheHitRate,
    RollingPercentiles,
    RollingRequestWindow,
    RollingWindowCounter,
    log_event,
    configure_tracing,
    start_timer,
    stop_timer,
)
from .utils.guardrail_utils import (
    is_allowed_domain,
    is_non_informative,
    missing_required_details,
    normalize_text,
    answer_likelihood,
    likely_answers_question,
    rephrase_missing_details,
)
from .utils.redaction_utils import redact_sensitive_text as redact_sensitive_text_util

app = FastAPI(title="Troubleshooter API", version="0.1.0")
configure_tracing(app)

storage = get_storage()
parser = RuleBasedLogParser()
rolling_cache = RollingCacheHitRate(max_samples=int(os.getenv("CACHE_HIT_SAMPLES", "200")))
rolling_llm_latency = RollingPercentiles(max_samples=int(os.getenv("LLM_LATENCY_SAMPLES", "200")))
cache = PgVectorCache(rolling_cache=rolling_cache)
budget = BudgetEnforcer()
metrics = CloudWatchMetrics()
rolling_latency = RollingPercentiles(max_samples=int(os.getenv("API_LATENCY_SAMPLES", "200")))
rolling_requests = RollingRequestWindow(window_seconds=300)
rolling_budget_denied = RollingWindowCounter(window_seconds=300)
llm_orchestrator = LLMOrchestrator(
    storage=storage,
    parser=parser,
    rolling_llm_latency=rolling_llm_latency,
)

cors_origins = [
    origin.strip()
    for origin in os.getenv("CORS_ALLOWED_ORIGINS", "").split(",")
    if origin.strip()
]
allow_all_origins = os.getenv("CORS_ALLOW_ALL", "true").lower() == "true"
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
    if origin and (origin in cors_origins or (not cors_origins and allow_all_origins)):
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Methods"] = "GET,POST,OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type,X-Request-Id,X-Api-Key"
        response.headers["Access-Control-Expose-Headers"] = "X-Request-Id"
        response.headers["Vary"] = "Origin"
    return response


@app.middleware("http")
async def preflight_middleware(request: Request, call_next):
    if request.method != "OPTIONS":
        return await call_next(request)
    origin = request.headers.get("origin")
    if origin and (origin in cors_origins or (not cors_origins and allow_all_origins)):
        return Response(
            status_code=204,
            headers={
                "Access-Control-Allow-Origin": origin,
                "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
                "Access-Control-Allow-Headers": "Content-Type,X-Request-Id,X-Api-Key",
                "Access-Control-Expose-Headers": "X-Request-Id",
                "Vary": "Origin",
            },
        )
    return Response(status_code=204)


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


@app.middleware("http")
async def request_logging_middleware(request: Request, call_next):
    request_id = getattr(request.state, "request_id", None) or request.headers.get("x-request-id")
    endpoint = request.url.path
    method = request.method
    timer = start_timer()
    log_event(
        "request_start",
        {
            "request_id": request_id,
            "endpoint": endpoint,
            "method": method,
        },
    )
    try:
        response = await call_next(request)
        status_code = response.status_code
        return response
    except Exception as exc:
        status_code = 500
        log_event(
            "request_error",
            {
                "request_id": request_id,
                "endpoint": endpoint,
                "method": method,
                "error": str(exc),
            },
        )
        raise
    finally:
        latency_ms = stop_timer(timer)
        rolling_latency.add(latency_ms)
        rolling_requests.add(status_code)
        metrics.put_api_metrics(endpoint=endpoint, status_code=status_code, latency_ms=latency_ms)
        log_event(
            "request_end",
            {
                "request_id": request_id,
                "endpoint": endpoint,
                "method": method,
                "status_code": status_code,
                "latency_ms": round(latency_ms, 2),
            },
        )


@app.get("/status", response_model=StatusResponse)
async def status() -> StatusResponse:
    return StatusResponse(
        status="ok",
        dependencies=["parser", "storage"],
        timestamp=datetime.now(timezone.utc),
    )


@app.get("/budget/status", response_model=BudgetStatusResponse)
async def budget_status() -> BudgetStatusResponse:
    status = budget.get_status()
    if not status:
        return BudgetStatusResponse(
            usage_window="unknown",
            retry_after="unknown",
            token_limit=0,
            tokens_used=0,
            remaining_budget=0,
        )
    return BudgetStatusResponse(**status)


@app.get("/metrics/summary", response_model=MetricsSummaryResponse)
async def metrics_summary() -> MetricsSummaryResponse:
    cloudwatch = metrics.get_api_latency_percentiles(endpoints=["/triage", "/explain"], minutes=5, period=300)
    llm_cloudwatch = metrics.get_llm_latency_percentiles(endpoints=["triage", "explain"], minutes=5, period=300)
    cache_hit_rate = metrics.get_cache_hit_rate(minutes=5, period=300)
    llm_fallback = rolling_llm_latency.percentiles([50, 95])
    if cloudwatch and (cloudwatch.get("p50") is not None or cloudwatch.get("p95") is not None):
        api_error_rate = metrics.get_api_error_rate(endpoints=["/triage", "/explain"], minutes=5, period=300)
        budget_denied = metrics.get_budget_denied_count(minutes=5, period=300)
        return MetricsSummaryResponse(
            timestamp=datetime.now(timezone.utc),
            api_latency_p50_ms=cloudwatch.get("p50"),
            api_latency_p95_ms=cloudwatch.get("p95"),
            llm_latency_p50_ms=llm_cloudwatch.get("p50") if llm_cloudwatch else llm_fallback.get("p50"),
            llm_latency_p95_ms=llm_cloudwatch.get("p95") if llm_cloudwatch else llm_fallback.get("p95"),
            source="cloudwatch",
            cache_hit_rate=cache_hit_rate if cache_hit_rate is not None else rolling_cache.rate(),
            api_error_rate=api_error_rate if api_error_rate is not None else rolling_requests.error_rate(),
            budget_denied_count=budget_denied if budget_denied is not None else rolling_budget_denied.count(),
        )

    fallback = rolling_latency.percentiles([50, 95])
    return MetricsSummaryResponse(
        timestamp=datetime.now(timezone.utc),
        api_latency_p50_ms=fallback.get("p50"),
        api_latency_p95_ms=fallback.get("p95"),
        llm_latency_p50_ms=llm_cloudwatch.get("p50") if llm_cloudwatch else llm_fallback.get("p50"),
        llm_latency_p95_ms=llm_cloudwatch.get("p95") if llm_cloudwatch else llm_fallback.get("p95"),
        source="memory",
        sample_count=rolling_latency.count(),
        cache_hit_rate=cache_hit_rate if cache_hit_rate is not None else rolling_cache.rate(),
        api_error_rate=rolling_requests.error_rate(),
        budget_denied_count=rolling_budget_denied.count(),
    )


@app.post("/triage", response_model=ChatResponse)
async def triage(payload: TriageRequest, request: Request) -> ChatResponse:
    request_id = payload.request_id or request.state.request_id
    conversation_id = payload.conversation_id or request_id
    raw_text = payload.raw_text.strip()
    redacted_text, backend_redaction_hits = redact_sensitive_text_util(raw_text)
    client_redaction_hits = payload.redaction_hits or 0

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
    input_id = storage.save_input(conversation_id, request_id, redacted_text)
    if not is_allowed_domain(redacted_text):
        response, frame = _domain_guardrail_response(
            request_id=request_id,
            conversation_id=conversation_id,
            frame=parser.parse(redacted_text, request_id, conversation_id),
        )
        response.metadata["client_redaction_hits"] = client_redaction_hits
        response.metadata["backend_redaction_hits"] = backend_redaction_hits
        response.metadata["input_id"] = input_id
        _apply_guardrail_session_total(response, conversation_id)
        storage.save_response(response)
        storage.save_frame(frame)
        storage.save_event(conversation_id, request_id, raw_text, frame, response, input_id)
        storage.update_conversation_state(conversation_id, request_id, frame, response)
        return ChatResponse(
            request_id=response.request_id,
            timestamp=response.timestamp,
            assistant_message=response.assistant_message or "",
            completion_state=response.completion_state,
            next_question=response.next_question,
            tool_calls=response.tool_calls,
            hypotheses=[_to_chat_hypothesis(hyp) for hyp in response.hypotheses],
            fix_steps=response.fix_steps,
            metadata=_public_metadata(response.metadata),
            conversation_id=response.conversation_id,
        )
    _enforce_budget_or_raise(redacted_text)
    try:
        response, _, frame = llm_orchestrator.triage(redacted_text, request_id, conversation_id)
    except (ValueError, ValidationError) as exc:
        raise HTTPException(status_code=502, detail="LLM returned invalid JSON") from exc
    response.metadata["client_redaction_hits"] = client_redaction_hits
    response.metadata["backend_redaction_hits"] = backend_redaction_hits
    _apply_guardrail_session_total(response, conversation_id)
    response.metadata["input_id"] = input_id
    storage.save_response(response)
    storage.save_frame(frame)
    storage.save_event(conversation_id, request_id, raw_text, frame, response, input_id)
    storage.update_conversation_state(conversation_id, request_id, frame, response)
    return ChatResponse(
        request_id=response.request_id,
        timestamp=response.timestamp,
        assistant_message=response.assistant_message or "",
        completion_state=response.completion_state,
        next_question=response.next_question,
        tool_calls=response.tool_calls,
        hypotheses=[_to_chat_hypothesis(hyp) for hyp in response.hypotheses],
        fix_steps=response.fix_steps,
        metadata=_public_metadata(response.metadata),
        conversation_id=response.conversation_id,
    )


@app.post("/explain", response_model=ChatResponse)
async def explain(payload: ExplainRequest, request: Request) -> ChatResponse:
    request_id = payload.request_id or request.state.request_id
    if not payload.conversation_id:
        raise HTTPException(
            status_code=400,
            detail="conversation_id is required for /explain",
        )
    conversation_id = payload.conversation_id
    frame_obj = payload.incident_frame
    raw_input = payload.response.strip()
    client_redaction_hits = payload.redaction_hits or 0
    tool_results = payload.tool_results or []
    if not frame_obj:
        context = storage.get_conversation_context(conversation_id)
        latest_frame = (context.get("state") or {}).get("latest_incident_frame")
        if latest_frame:
            frame_obj = IncidentFrame.model_validate(latest_frame)
        else:
            return ChatResponse(
                request_id=request_id,
                timestamp=datetime.now(timezone.utc),
                assistant_message="I need the raw error or trace output to answer precisely. Paste the failing log or stack trace so I can analyze it.",
                metadata=_public_metadata({"parser_version": "unknown"}),
                conversation_id=conversation_id,
                completion_state="needs_input",
                next_question="Paste the failing log or stack trace.",
            )

    log_event(
        "explain_request",
        {
            "request_id": request_id,
            "conversation_id": conversation_id,
        },
    )
    if not raw_input and not tool_results:
        raise HTTPException(status_code=400, detail="response is required")
    context = storage.get_conversation_context(conversation_id)
    latest_summary = (context.get("state") or {}).get("latest_response_summary", {})
    if not latest_summary:
        raise HTTPException(
            status_code=400,
            detail="explain requires an existing triage session; start with /triage first",
        )
    pending_question = (latest_summary or {}).get("next_question") or ""
    answered_pending = _answer_matches_pending(pending_question, raw_input)
    non_informative = is_non_informative(raw_input)
    missing_details = missing_required_details(pending_question, raw_input)
    if pending_question and raw_input and not non_informative and not missing_details:
        heuristic_score = answer_likelihood(pending_question, raw_input)
        if heuristic_score >= 0.7:
            answered_pending = True
        elif heuristic_score <= 0.3:
            answered_pending = False
        else:
            answered_pending, _ = llm_orchestrator.classify_answer(
                question=pending_question,
                answer=raw_input,
                request_id=request_id,
                conversation_id=conversation_id,
            )
        if likely_answers_question(pending_question, raw_input):
            answered_pending = True

    tool_results_text = ""
    if tool_results:
        tool_results_text = "Tool results:\n" + "\n".join(
            [f"{result.id}: {result.output}" for result in tool_results]
        )
    context_notes: list[str] = []
    if answered_pending and pending_question:
        context_notes.append(
            f"User answered prior question: {pending_question} Answer: {raw_input}."
        )
    if non_informative and pending_question:
        context_notes.append(
            "User could not provide the requested detail. Provide a best-effort final response and do not repeat the question."
        )
    if pending_question and raw_input and missing_details and not non_informative and not answered_pending:
        missing_text = ", ".join(missing_details)
        context_notes.append(
            "User response did not include the requested detail(s): "
            f"{missing_text}. Ask only for the missing detail(s), rephrase the request, and offer a redacted example "
            "or field list. Do not repeat the prior question verbatim."
        )

    parts = [raw_input] if raw_input else []
    if context_notes:
        note_block = "\n".join([f"- {note}" for note in context_notes])
        parts.append(f"Context notes:\n{note_block}")
    if tool_results_text:
        parts.append(tool_results_text)
    enriched_input = "\n\n".join(parts).strip()
    redacted_input, backend_redaction_hits = redact_sensitive_text_util(enriched_input)

    incoming_frame = parser.parse(redacted_input or raw_input, request_id, conversation_id)
    merged_frame = _merge_frames(frame_obj, incoming_frame)
    frame = merged_frame.model_dump()

    cache_key = cache.get_explain_cache_key(IncidentFrame.model_validate(frame), redacted_input or raw_input)
    cache_hit = cache.lookup(endpoint="explain", query_text=cache_key)
    if cache_hit:
        cached_response = _hydrate_cached_response(
            cache_hit.response,
            request_id=request_id,
            conversation_id=conversation_id,
            similarity=cache_hit.similarity,
        )
        cached_response.metadata["client_redaction_hits"] = client_redaction_hits
        cached_response.metadata["backend_redaction_hits"] = backend_redaction_hits
        _apply_guardrail_session_total(cached_response, conversation_id)
        storage.save_frame(merged_frame)
        storage.save_response(cached_response)
        storage.save_event(
            conversation_id,
            request_id,
            redacted_input or raw_input,
            incoming_frame,
            cached_response,
            input_id=cached_response.request_id,
        )
        storage.update_conversation_state(conversation_id, request_id, merged_frame, cached_response)
        log_event(
            "cache_hit",
            {
                "request_id": request_id,
                "conversation_id": conversation_id,
                "similarity": cache_hit.similarity,
            },
        )
        return ChatResponse(
            request_id=cached_response.request_id,
            timestamp=cached_response.timestamp,
            assistant_message=cached_response.assistant_message or "",
            completion_state=cached_response.completion_state,
            next_question=cached_response.next_question,
            tool_calls=cached_response.tool_calls,
            hypotheses=[_to_chat_hypothesis(hyp) for hyp in cached_response.hypotheses],
            fix_steps=cached_response.fix_steps,
            metadata=_public_metadata(cached_response.metadata),
            conversation_id=cached_response.conversation_id,
        )

    _enforce_budget_or_raise(cache_key)

    try:
        response, _ = llm_orchestrator.explain(
            frame,
            redacted_input or raw_input,
            request_id,
            conversation_id,
        )
    except (ValueError, ValidationError) as exc:
        raise HTTPException(status_code=502, detail="LLM returned invalid JSON") from exc
    response.metadata["client_redaction_hits"] = client_redaction_hits
    response.metadata["backend_redaction_hits"] = backend_redaction_hits
    if tool_results:
        response.metadata["tool_results"] = [result.model_dump() for result in tool_results]
    _apply_guardrail_session_total(response, conversation_id)
    if pending_question and response.next_question and raw_input:
        if _normalize_text(response.next_question) == _normalize_text(pending_question):
            if missing_details:
                response.next_question = rephrase_missing_details(missing_details)
                response.completion_state = "needs_input"
            else:
                response.next_question = None
                if response.completion_state == "needs_input":
                    response.completion_state = "final"
    if answered_pending and pending_question:
        if response.next_question and _normalize_text(response.next_question) == _normalize_text(pending_question):
            response.next_question = None
        message_norm = _normalize_text(response.assistant_message or "")
        if message_norm == _normalize_text(pending_question):
            response.assistant_message = "Thanks - got it. Proceeding with the analysis."
    if pending_question and raw_input and missing_details:
        if not response.next_question:
            response.next_question = rephrase_missing_details(missing_details)
            response.completion_state = "needs_input"
        message_norm = _normalize_text(response.assistant_message or "")
        if message_norm and (
            message_norm == normalize_text(pending_question)
            or message_norm == normalize_text(response.next_question or "")
        ):
            response.assistant_message = "Thanks — I still need one detail to proceed."
    if pending_question and raw_input:
        pending_norm = normalize_text(pending_question)
        message_norm = normalize_text(response.assistant_message or "")
        if message_norm and (message_norm == pending_norm or pending_norm in message_norm):
            if not (response.hypotheses or response.fix_steps):
                response.assistant_message = (
                    "Thanks - proceeding with a best-effort analysis based on the available info."
                )
    storage.save_frame(merged_frame)
    storage.save_response(response)
    storage.save_event(
        conversation_id,
        request_id,
        redacted_input or raw_input,
        incoming_frame,
        response,
        input_id=response.request_id,
    )
    storage.update_conversation_state(conversation_id, request_id, merged_frame, response)
    cache.put(endpoint="explain", query_text=cache_key, response=response)
    return ChatResponse(
        request_id=response.request_id,
        timestamp=response.timestamp,
        assistant_message=response.assistant_message or "",
        completion_state=response.completion_state,
        next_question=response.next_question,
        tool_calls=response.tool_calls,
        hypotheses=[_to_chat_hypothesis(hyp) for hyp in response.hypotheses],
        fix_steps=response.fix_steps,
        metadata=_public_metadata(response.metadata),
        conversation_id=response.conversation_id,
    )


def _public_metadata(metadata: dict) -> dict:
    token_usage = metadata.get("token_usage") if isinstance(metadata, dict) else {}
    total_tokens = 0
    if isinstance(token_usage, dict):
        total_tokens = int(token_usage.get("total_tokens", 0))
    cost_per_1k = float(os.getenv("LLM_COST_PER_1K_TOKENS", "0.002"))
    cost_estimate = round((total_tokens / 1000.0) * cost_per_1k, 6) if total_tokens else None
    guardrails = metadata.get("guardrails") if isinstance(metadata, dict) else {}
    guardrail_missing = None
    guardrail_redactions = None
    guardrail_domain = None
    guardrail_hits = None
    if isinstance(guardrails, dict):
        guardrail_missing = guardrails.get("citation_missing_count")
        guardrail_redactions = guardrails.get("redactions")
        guardrail_domain = guardrails.get("domain_restricted")
        try:
            guardrail_hits = (
                int(guardrail_missing or 0)
                + int(guardrail_redactions or 0)
                + int(guardrail_domain or 0)
            )
        except (TypeError, ValueError):
            guardrail_hits = None
    guardrail_hits_session = metadata.get("guardrail_hits_session") if isinstance(metadata, dict) else None
    client_redaction_hits = metadata.get("client_redaction_hits") if isinstance(metadata, dict) else None
    backend_redaction_hits = metadata.get("backend_redaction_hits") if isinstance(metadata, dict) else None
    return {
        "token_usage": token_usage,
        "cache_hit": metadata.get("cache_hit") if isinstance(metadata, dict) else None,
        "cache_similarity": metadata.get("cache_similarity") if isinstance(metadata, dict) else None,
        "cost_estimate_usd": cost_estimate,
        "guardrail_missing": guardrail_missing,
        "guardrail_redactions": guardrail_redactions,
        "guardrail_domain": guardrail_domain,
        "guardrail_hits": guardrail_hits,
        "guardrail_hits_session": guardrail_hits_session,
        "client_redaction_hits": client_redaction_hits,
        "backend_redaction_hits": backend_redaction_hits,
    }


def _to_chat_hypothesis(hypothesis: Hypothesis) -> ChatHypothesis:
    return ChatHypothesis(
        id=hypothesis.id,
        confidence=hypothesis.confidence,
        explanation=hypothesis.explanation,
    )


def _merge_frames(existing: IncidentFrame, incoming: IncidentFrame) -> IncidentFrame:
    primary = incoming.primary_error_signature or existing.primary_error_signature
    secondary = list({*existing.secondary_signatures, *incoming.secondary_signatures})
    services = list({*existing.services, *incoming.services})
    infra = list({*existing.infra_components, *incoming.infra_components})
    evidence = [*existing.evidence_map, *incoming.evidence_map]
    return IncidentFrame(
        frame_id=incoming.frame_id,
        conversation_id=incoming.conversation_id,
        request_id=incoming.request_id,
        source=incoming.source,
        parser_version=incoming.parser_version,
        parse_confidence=max(existing.parse_confidence, incoming.parse_confidence),
        created_at=incoming.created_at,
        primary_error_signature=primary,
        secondary_signatures=secondary,
        time_window=incoming.time_window or existing.time_window,
        services=services,
        infra_components=infra,
        suspected_failure_domain=incoming.suspected_failure_domain or existing.suspected_failure_domain,
        evidence_map=evidence,
    )


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
    metrics.put_budget_denied()
    rolling_budget_denied.add(1)
    raise HTTPException(
        status_code=402,
        detail={
            "error": "budget_exceeded",
            "message": "Token budget exceeded for this window.",
            "remaining_budget": decision.remaining_budget or 0,
            "retry_after": decision.retry_after,
        },
    )


def _apply_guardrail_session_total(response: CanonicalResponse, conversation_id: str) -> None:
    context = storage.get_conversation_context(conversation_id)
    latest_summary = (context.get("state") or {}).get("latest_response_summary", {})
    previous_total = 0
    if isinstance(latest_summary, dict):
        previous_total = int(latest_summary.get("guardrail_hits_session") or 0)
    current = _compute_guardrail_hits_current(response.metadata)
    response.metadata["guardrail_hits_session"] = previous_total + current


def _compute_guardrail_hits_current(metadata: dict) -> int:
    if not isinstance(metadata, dict):
        return 0
    guardrails = metadata.get("guardrails") or {}
    missing = 0
    redactions = 0
    domain_restricted = 0
    if isinstance(guardrails, dict):
        try:
            missing = int(guardrails.get("citation_missing_count") or 0)
            redactions = int(guardrails.get("redactions") or 0)
            domain_restricted = int(guardrails.get("domain_restricted") or 0)
        except (TypeError, ValueError):
            missing = 0
            redactions = 0
            domain_restricted = 0
    try:
        client_hits = int(metadata.get("client_redaction_hits") or 0)
    except (TypeError, ValueError):
        client_hits = 0
    try:
        backend_hits = int(metadata.get("backend_redaction_hits") or 0)
    except (TypeError, ValueError):
        backend_hits = 0
    return missing + redactions + domain_restricted + client_hits + backend_hits


def redact_sensitive_text(text: str) -> tuple[str, int]:
    return redact_sensitive_text_util(text)


def _normalize_text(value: str) -> str:
    return normalize_text(value)


def _answer_matches_pending(question: str, answer: str) -> bool:
    if not question or not answer:
        return False
    question_norm = _normalize_text(question)
    answer_norm = _normalize_text(answer)
    if "(" not in question_norm or ")" not in question_norm:
        return False
    match = re.search(r"\(([^)]*)\)", question_norm)
    if not match:
        return False
    options_raw = match.group(1)
    options = [item.strip() for item in re.split(r",|/|\bor\b", options_raw) if item.strip()]
    return any(option in answer_norm for option in options)




def _domain_guardrail_response(
    *,
    request_id: str,
    conversation_id: str,
    frame: IncidentFrame,
) -> tuple[CanonicalResponse, IncidentFrame]:
    response = CanonicalResponse(
        request_id=request_id,
        timestamp=datetime.now(timezone.utc),
        assistant_message=(
            "Please ask a coding, infrastructure as code, or CI/CD automation question so I can help."
        ),
        completion_state="final",
        next_question=None,
        tool_calls=[],
        hypotheses=[],
        fix_steps=[],
        metadata={
            "guardrails": {"domain_restricted": 1, "issues": ["domain_restricted"]},
        },
        conversation_id=conversation_id,
    )
    return response, frame
