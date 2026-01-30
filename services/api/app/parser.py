from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterable, List, Optional
from uuid import uuid4

from .schemas import EvidenceMapEntry, IncidentFrame, TimeWindow


class ParserAdapter:
    def parse(self, raw_text: str, request_id: str, conversation_id: Optional[str] = None) -> IncidentFrame:
        raise NotImplementedError


@dataclass
class NormalizedLine:
    number: int
    text: str
    lowered: str


@dataclass
class NormalizedLog:
    raw_text: str
    lines: List[NormalizedLine]
    timestamps: List[str] = field(default_factory=list)


@dataclass
class ParserResult:
    primary_error_signature: Optional[str] = None
    secondary_signatures: List[str] = field(default_factory=list)
    evidence_map: List[EvidenceMapEntry] = field(default_factory=list)
    services: List[str] = field(default_factory=list)
    infra_components: List[str] = field(default_factory=list)
    suspected_failure_domain: Optional[str] = None
    time_window: Optional[TimeWindow] = None


class BaseLogFamilyParser:
    family: str = "generic"

    def match_score(self, normalized: NormalizedLog) -> int:
        raise NotImplementedError

    def extract(self, normalized: NormalizedLog) -> ParserResult:
        raise NotImplementedError


class TerraformParser(BaseLogFamilyParser):
    family = "terraform"

    def match_score(self, normalized: NormalizedLog) -> int:
        score = 0
        for line in normalized.lines:
            if "terraform" in line.lowered:
                score += 2
            if "error:" in line.lowered:
                score += 1
            if ".tf" in line.lowered and "line" in line.lowered:
                score += 2
            if "module." in line.lowered:
                score += 1
        return score

    def extract(self, normalized: NormalizedLog) -> ParserResult:
        result = ParserResult()
        for line in normalized.lines:
            if line.lowered.startswith("error:"):
                result.primary_error_signature = line.text.strip()[:256]
                result.evidence_map.append(_make_evidence("raw-input", line.number, line.number, line.text))
                break
        if result.primary_error_signature is None:
            for line in normalized.lines:
                if "error:" in line.lowered:
                    result.primary_error_signature = line.text.strip()[:256]
                    result.evidence_map.append(_make_evidence("raw-input", line.number, line.number, line.text))
                    break
        for line in normalized.lines:
            if len(result.secondary_signatures) >= 3:
                break
            if "on" in line.lowered and ".tf" in line.lowered and "line" in line.lowered:
                result.secondary_signatures.append(line.text.strip()[:256])
                result.evidence_map.append(_make_evidence("raw-input", line.number, line.number, line.text))
        result.infra_components = ["terraform"]
        return result


class CloudWatchParser(BaseLogFamilyParser):
    family = "cloudwatch"

    def match_score(self, normalized: NormalizedLog) -> int:
        score = 0
        for line in normalized.lines:
            if "cloudwatch" in line.lowered:
                score += 2
            if "log group" in line.lowered or "log stream" in line.lowered:
                score += 2
            if "eventid" in line.lowered or "event id" in line.lowered:
                score += 1
            if "awslogs" in line.lowered:
                score += 1
        return score

    def extract(self, normalized: NormalizedLog) -> ParserResult:
        result = ParserResult()
        for line in normalized.lines:
            if _looks_like_error(line.lowered):
                result.primary_error_signature = line.text.strip()[:256]
                result.evidence_map.append(_make_evidence("raw-input", line.number, line.number, line.text))
                break
        result.infra_components = ["cloudwatch"]
        return result


class PythonTracebackParser(BaseLogFamilyParser):
    family = "python-traceback"

    def match_score(self, normalized: NormalizedLog) -> int:
        score = 0
        for line in normalized.lines:
            if "traceback (most recent call last):" in line.lowered:
                score += 4
            if line.lowered.strip().startswith("file \"") and ", line" in line.lowered:
                score += 1
            if "exception" in line.lowered or "error" in line.lowered:
                score += 1
        return score

    def extract(self, normalized: NormalizedLog) -> ParserResult:
        result = ParserResult()
        traceback_lines = []
        for line in normalized.lines:
            if "traceback (most recent call last):" in line.lowered:
                traceback_lines.append(line)
            elif traceback_lines:
                traceback_lines.append(line)
                if line.text.strip() and not line.text.startswith(" "):
                    if len(traceback_lines) > 6:
                        break
        if traceback_lines:
            last_line = traceback_lines[-1]
            result.primary_error_signature = last_line.text.strip()[:256]
            result.evidence_map.append(_make_evidence("raw-input", last_line.number, last_line.number, last_line.text))
            for line in traceback_lines[:3]:
                if len(result.secondary_signatures) >= 3:
                    break
                if "file \"" in line.lowered:
                    result.secondary_signatures.append(line.text.strip()[:256])
                    result.evidence_map.append(_make_evidence("raw-input", line.number, line.number, line.text))
        return result


class GenericParser(BaseLogFamilyParser):
    family = "generic"

    def match_score(self, normalized: NormalizedLog) -> int:
        for line in normalized.lines:
            if _looks_like_error(line.lowered):
                return 1
        return 0

    def extract(self, normalized: NormalizedLog) -> ParserResult:
        result = ParserResult()
        for line in normalized.lines:
            if _looks_like_error(line.lowered):
                result.primary_error_signature = line.text.strip()[:256]
                result.evidence_map.append(_make_evidence("raw-input", line.number, line.number, line.text))
                break
        if result.primary_error_signature is None and normalized.lines:
            first_line = normalized.lines[0]
            result.primary_error_signature = first_line.text.strip()[:256]
            result.evidence_map.append(_make_evidence("raw-input", first_line.number, first_line.number, first_line.text))
        return result


class RuleBasedLogParser(ParserAdapter):
    parser_version = "v0.2"

    def __init__(self) -> None:
        self.parsers: List[BaseLogFamilyParser] = [
            TerraformParser(),
            CloudWatchParser(),
            PythonTracebackParser(),
            GenericParser(),
        ]

    def parse(self, raw_text: str, request_id: str, conversation_id: Optional[str] = None) -> IncidentFrame:
        normalized = _normalize(raw_text)
        best_parser, best_score = _select_parser(self.parsers, normalized)
        result = best_parser.extract(normalized)

        if normalized.timestamps:
            result.time_window = TimeWindow(
                start=normalized.timestamps[0],
                end=normalized.timestamps[-1],
            )

        result.services = _extract_services(raw_text)
        result.infra_components = list({*result.infra_components, *_extract_infra_components(raw_text)})
        result.suspected_failure_domain = _guess_domain(raw_text)

        parse_confidence = _score_to_confidence(best_score, result.primary_error_signature)

        return IncidentFrame(
            frame_id=str(uuid4()),
            conversation_id=conversation_id,
            request_id=request_id,
            source="user_input",
            parser_version=self.parser_version,
            parse_confidence=parse_confidence,
            created_at=datetime.now(timezone.utc),
            primary_error_signature=result.primary_error_signature,
            secondary_signatures=result.secondary_signatures,
            time_window=result.time_window,
            services=result.services,
            infra_components=result.infra_components,
            suspected_failure_domain=result.suspected_failure_domain,
            evidence_map=result.evidence_map,
        )


def _normalize(raw_text: str) -> NormalizedLog:
    lines: List[NormalizedLine] = []
    timestamps: List[str] = []
    for idx, line in enumerate(raw_text.splitlines(), start=1):
        lowered = line.lower()
        lines.append(NormalizedLine(number=idx, text=line, lowered=lowered))
        ts = _extract_timestamp(line)
        if ts:
            timestamps.append(ts)
    return NormalizedLog(raw_text=raw_text, lines=lines, timestamps=timestamps)


def _select_parser(
    parsers: Iterable[BaseLogFamilyParser],
    normalized: NormalizedLog,
) -> tuple[BaseLogFamilyParser, int]:
    best_parser: Optional[BaseLogFamilyParser] = None
    best_score = -1
    for parser in parsers:
        score = parser.match_score(normalized)
        if score > best_score:
            best_parser = parser
            best_score = score
    if best_parser is None:
        return GenericParser(), 0
    return best_parser, best_score


def _score_to_confidence(score: int, has_primary: Optional[str]) -> float:
    if score <= 0:
        return 0.25 if has_primary else 0.15
    if score >= 6:
        return 0.85
    if score >= 3:
        return 0.7
    return 0.5


def _looks_like_error(lowered: str) -> bool:
    return any(token in lowered for token in ["error", "exception", "traceback", "fatal", "panic", "failed"])


def _extract_timestamp(line: str) -> Optional[str]:
    match = re.search(r"\d{4}-\d{2}-\d{2}[T\s]\d{2}:\d{2}:\d{2}(?:\.\d+)?Z?", line)
    if match:
        return match.group(0)
    return None


def _make_evidence(source_id: str, line_start: int, line_end: int, text: str) -> EvidenceMapEntry:
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return EvidenceMapEntry(
        source_type="log",
        source_id=source_id,
        line_start=line_start,
        line_end=line_end,
        excerpt_hash=digest,
    )


def _extract_services(raw_text: str) -> List[str]:
    candidates = ["api", "worker", "gateway", "frontend", "backend"]
    found = []
    lowered = raw_text.lower()
    for name in candidates:
        if name in lowered:
            found.append(name)
    return found


def _extract_infra_components(raw_text: str) -> List[str]:
    candidates = ["ecs", "alb", "lambda", "dynamodb", "s3", "rds", "redis", "cloudwatch"]
    found = []
    lowered = raw_text.lower()
    for name in candidates:
        if name in lowered:
            found.append(name)
    return found


def _guess_domain(raw_text: str) -> Optional[str]:
    lowered = raw_text.lower()
    if "timeout" in lowered or "latency" in lowered:
        return "performance"
    if "permission" in lowered or "access denied" in lowered:
        return "security"
    if "connection" in lowered or "dns" in lowered:
        return "network"
    if "null" in lowered or "exception" in lowered:
        return "application"
    return None
