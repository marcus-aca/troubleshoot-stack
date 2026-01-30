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
    timestamp: Optional[datetime] = None


class ExplainRequest(BaseModel):
    request_id: Optional[str] = None
    conversation_id: Optional[str] = None
    question: str
    incident_frame: Optional[IncidentFrame] = None


class Hypothesis(BaseModel):
    id: str
    rank: int
    confidence: float
    explanation: str
    citations: List[EvidenceMapEntry] = Field(default_factory=list)


class RunbookStep(BaseModel):
    step_number: int
    description: str
    command_or_console_path: Optional[str] = None
    estimated_time_mins: Optional[int] = None


class CanonicalResponse(BaseModel):
    request_id: str
    timestamp: datetime
    hypotheses: List[Hypothesis]
    runbook_steps: List[RunbookStep]
    proposed_fix: Optional[str] = None
    risk_notes: List[str] = Field(default_factory=list)
    rollback: List[str] = Field(default_factory=list)
    next_checks: List[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)
    conversation_id: Optional[str] = None


class StatusResponse(BaseModel):
    status: str
    dependencies: List[str]
    timestamp: datetime
