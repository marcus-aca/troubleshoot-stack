from __future__ import annotations

from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field


class EvidenceMapEntry(BaseModel):
    source_type: str = Field(..., description="log|tool")
    source_id: str
    line_start: int
    line_end: int
    excerpt_hash: str
    excerpt: Optional[str] = None


class TimeWindow(BaseModel):
    start: Optional[str] = None
    end: Optional[str] = None


class IncidentFrame(BaseModel):
    frame_id: str
    conversation_id: Optional[str] = None
    request_id: str
    source: str = "user_input"
    parser_version: str
    parse_confidence: float
    created_at: datetime

    primary_error_signature: Optional[str] = None
    secondary_signatures: List[str] = Field(default_factory=list)
    time_window: Optional[TimeWindow] = None
    services: List[str] = Field(default_factory=list)
    infra_components: List[str] = Field(default_factory=list)
    suspected_failure_domain: Optional[str] = None
    evidence_map: List[EvidenceMapEntry] = Field(default_factory=list)


class TriageRequest(BaseModel):
    request_id: Optional[str] = None
    conversation_id: Optional[str] = None
    source: Optional[str] = "user"
    raw_text: str
    redaction_hits: Optional[int] = None
    timestamp: Optional[datetime] = None


class ExplainRequest(BaseModel):
    request_id: Optional[str] = None
    conversation_id: Optional[str] = None
    response: str
    redaction_hits: Optional[int] = None
    incident_frame: Optional[IncidentFrame] = None
    tool_results: Optional[List["ToolResult"]] = None


class Hypothesis(BaseModel):
    id: str
    rank: int
    confidence: float
    explanation: str
    citations: List[EvidenceMapEntry] = Field(default_factory=list)


class ToolCall(BaseModel):
    id: str
    title: str
    command: str
    expected_output: Optional[str] = None


class ToolResult(BaseModel):
    id: str
    output: str


class ChatHypothesis(BaseModel):
    id: str
    confidence: float
    explanation: str


class CanonicalResponse(BaseModel):
    request_id: str
    timestamp: datetime
    assistant_message: str
    completion_state: str
    next_question: Optional[str] = None
    tool_calls: List[ToolCall] = Field(default_factory=list)
    hypotheses: List[Hypothesis] = Field(default_factory=list)
    fix_steps: List[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)
    conversation_id: Optional[str] = None


class ChatResponse(BaseModel):
    request_id: str
    timestamp: datetime
    assistant_message: str
    completion_state: str
    next_question: Optional[str] = None
    tool_calls: List[ToolCall] = Field(default_factory=list)
    hypotheses: List[ChatHypothesis] = Field(default_factory=list)
    fix_steps: List[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)
    conversation_id: Optional[str] = None


class StatusResponse(BaseModel):
    status: str
    dependencies: List[str]
    timestamp: datetime


class BudgetStatusResponse(BaseModel):
    usage_window: str
    retry_after: str
    token_limit: int
    tokens_used: int
    remaining_budget: int


class MetricsSummaryResponse(BaseModel):
    timestamp: datetime
    api_latency_p50_ms: Optional[float] = None
    api_latency_p95_ms: Optional[float] = None
    llm_latency_p50_ms: Optional[float] = None
    llm_latency_p95_ms: Optional[float] = None
    source: str
    sample_count: Optional[int] = None
    cache_hit_rate: Optional[float] = None
    api_error_rate: Optional[float] = None
    budget_denied_count: Optional[float] = None


class TriageLLMOutput(BaseModel):
    category: str
    assistant_message: str
    completion_state: str
    next_question: Optional[str] = None
    tool_calls: List[ToolCall] = Field(default_factory=list)
    hypotheses: List[Hypothesis] = Field(default_factory=list)
    fix_steps: List[str] = Field(default_factory=list)


class ExplainLLMOutput(BaseModel):
    assistant_message: str
    completion_state: str
    next_question: Optional[str] = None
    tool_calls: List[ToolCall] = Field(default_factory=list)
    hypotheses: List[Hypothesis] = Field(default_factory=list)
    fix_steps: List[str] = Field(default_factory=list)
