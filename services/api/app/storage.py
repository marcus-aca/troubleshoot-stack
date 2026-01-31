from __future__ import annotations

import os
import time
from decimal import Decimal
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import uuid4

import boto3
from boto3.dynamodb.conditions import Key

from .schemas import CanonicalResponse, IncidentFrame


class StorageAdapter:
    def save_input(self, conversation_id: Optional[str], request_id: str, raw_text: str) -> str:
        raise NotImplementedError

    def save_frame(self, frame: IncidentFrame) -> None:
        raise NotImplementedError

    def save_response(self, response: CanonicalResponse) -> None:
        raise NotImplementedError

    def save_event(
        self,
        conversation_id: str,
        request_id: str,
        raw_text: str,
        frame: IncidentFrame,
        response: CanonicalResponse,
        input_id: str,
    ) -> Optional[str]:
        raise NotImplementedError

    def update_conversation_state(
        self,
        conversation_id: str,
        request_id: str,
        frame: IncidentFrame,
        response: CanonicalResponse,
    ) -> None:
        raise NotImplementedError

    def get_conversation_context(self, conversation_id: str, limit: int = 5) -> Dict[str, object]:
        raise NotImplementedError


class InMemoryStorage(StorageAdapter):
    def __init__(self) -> None:
        self.inputs: Dict[str, Dict[str, str]] = {}
        self.frames: Dict[str, IncidentFrame] = {}
        self.responses: Dict[str, CanonicalResponse] = {}
        self.events: Dict[str, List[Dict[str, object]]] = {}
        self.state: Dict[str, Dict[str, object]] = {}

    def save_input(self, conversation_id: Optional[str], request_id: str, raw_text: str) -> str:
        input_id = str(uuid4())
        self.inputs[input_id] = {
            "conversation_id": conversation_id or "",
            "request_id": request_id,
            "raw_text": raw_text,
        }
        return input_id

    def save_frame(self, frame: IncidentFrame) -> None:
        self.frames[frame.frame_id] = frame

    def save_response(self, response: CanonicalResponse) -> None:
        self.responses[response.request_id] = response

    def save_event(
        self,
        conversation_id: str,
        request_id: str,
        raw_text: str,
        frame: IncidentFrame,
        response: CanonicalResponse,
        input_id: str,
    ) -> Optional[str]:
        event_id = f"{int(time.time())}#{request_id}"
        event = {
            "event_id": event_id,
            "conversation_id": conversation_id,
            "request_id": request_id,
            "input_id": input_id,
            "raw_text": raw_text,
            "incident_frame": frame.model_dump(),
            "canonical_response": response.model_dump(),
            "created_at": int(time.time()),
        }
        self.events.setdefault(conversation_id, []).append(event)
        return event_id

    def update_conversation_state(
        self,
        conversation_id: str,
        request_id: str,
        frame: IncidentFrame,
        response: CanonicalResponse,
    ) -> None:
        self.state[conversation_id] = {
            "conversation_id": conversation_id,
            "latest_request_id": request_id,
            "latest_incident_frame": frame.model_dump(),
            "latest_response_summary": _build_response_summary(response),
            "updated_at": int(time.time()),
        }

    def get_conversation_context(self, conversation_id: str, limit: int = 5) -> Dict[str, object]:
        events = self.events.get(conversation_id, [])
        return {
            "conversation_id": conversation_id,
            "state": self.state.get(conversation_id),
            "recent_events": events[-limit:],
        }


class DynamoDBStorage(StorageAdapter):
    def __init__(self) -> None:
        self.session_table = os.getenv("SESSION_TABLE", "troubleshooter-sessions")
        self.inputs_table = os.getenv("INPUTS_TABLE", "troubleshooter-inputs")
        self.events_table = os.getenv("CONVERSATION_EVENTS_TABLE", "troubleshooter-conversation-events")
        self.state_table = os.getenv("CONVERSATION_STATE_TABLE", "troubleshooter-conversation-state")
        self.ttl_seconds = int(os.getenv("INPUT_TTL_SECONDS", "86400"))
        self.conversation_ttl_seconds = int(os.getenv("CONVERSATION_TTL_SECONDS", "604800"))
        self.client = boto3.resource("dynamodb")

    def save_input(self, conversation_id: Optional[str], request_id: str, raw_text: str) -> str:
        input_id = str(uuid4())
        expires_at = int(time.time()) + self.ttl_seconds
        inputs = self.client.Table(self.inputs_table)
        inputs.put_item(
            Item=_to_dynamodb(
                {
                    "input_id": input_id,
                    "conversation_id": conversation_id or "",
                    "request_id": request_id,
                    "raw_text": raw_text,
                    "created_at": int(time.time()),
                    "expires_at": expires_at,
                }
            )
        )

        if conversation_id:
            sessions = self.client.Table(self.session_table)
            sessions.put_item(
                Item=_to_dynamodb(
                    {
                        "conversation_id": conversation_id,
                        "last_request_id": request_id,
                        "last_input_id": input_id,
                        "updated_at": int(time.time()),
                        "expires_at": expires_at,
                    }
                )
            )
        return input_id

    def save_frame(self, frame: IncidentFrame) -> None:
        inputs = self.client.Table(self.inputs_table)
        inputs.put_item(
            Item=_to_dynamodb(
                {
                    "input_id": frame.frame_id,
                    "item_type": "incident_frame",
                    "request_id": frame.request_id,
                    "conversation_id": frame.conversation_id or "",
                    "parser_version": frame.parser_version,
                    "parse_confidence": frame.parse_confidence,
                    "created_at": int(frame.created_at.timestamp()),
                    "primary_error_signature": frame.primary_error_signature or "",
                    "frame": frame.model_dump(),
                }
            )
        )

    def save_response(self, response: CanonicalResponse) -> None:
        inputs = self.client.Table(self.inputs_table)
        inputs.put_item(
            Item=_to_dynamodb(
                {
                    "input_id": response.request_id,
                    "item_type": "canonical_response",
                    "request_id": response.request_id,
                    "conversation_id": response.conversation_id or "",
                    "created_at": int(response.timestamp.timestamp()),
                    "response": response.model_dump(),
                }
            )
        )

    def save_event(
        self,
        conversation_id: str,
        request_id: str,
        raw_text: str,
        frame: IncidentFrame,
        response: CanonicalResponse,
        input_id: str,
    ) -> Optional[str]:
        if not conversation_id:
            return None
        events = self.client.Table(self.events_table)
        expires_at = int(time.time()) + self.conversation_ttl_seconds
        event_id = f"{int(time.time())}#{request_id}"
        events.put_item(
            Item=_to_dynamodb(
                {
                    "conversation_id": conversation_id,
                    "event_id": event_id,
                    "request_id": request_id,
                    "input_id": input_id,
                    "raw_text": raw_text,
                    "incident_frame": frame.model_dump(),
                    "canonical_response": response.model_dump(),
                    "created_at": int(time.time()),
                    "expires_at": expires_at,
                }
            )
        )
        return event_id

    def update_conversation_state(
        self,
        conversation_id: str,
        request_id: str,
        frame: IncidentFrame,
        response: CanonicalResponse,
    ) -> None:
        if not conversation_id:
            return
        state = self.client.Table(self.state_table)
        expires_at = int(time.time()) + self.conversation_ttl_seconds
        state.put_item(
            Item=_to_dynamodb(
                {
                    "conversation_id": conversation_id,
                    "latest_request_id": request_id,
                    "latest_incident_frame": frame.model_dump(),
                    "latest_response_summary": _build_response_summary(response),
                    "updated_at": int(time.time()),
                    "expires_at": expires_at,
                }
            )
        )

    def get_conversation_context(self, conversation_id: str, limit: int = 5) -> Dict[str, object]:
        events = self.client.Table(self.events_table)
        state = self.client.Table(self.state_table)

        state_item = state.get_item(Key={"conversation_id": conversation_id}).get("Item")
        events_resp = events.query(
            KeyConditionExpression=Key("conversation_id").eq(conversation_id),
            ScanIndexForward=False,
            Limit=limit,
        )
        return {
            "conversation_id": conversation_id,
            "state": state_item,
            "recent_events": list(reversed(events_resp.get("Items", []))),
        }


def get_storage() -> StorageAdapter:
    if os.getenv("USE_DYNAMODB", "false").lower() == "true":
        return DynamoDBStorage()
    return InMemoryStorage()


def _build_response_summary(response: CanonicalResponse) -> Dict[str, object]:
    top_hypothesis = response.hypotheses[0] if response.hypotheses else None
    return {
        "request_id": response.request_id,
        "timestamp": response.timestamp.isoformat(),
        "top_hypothesis": top_hypothesis.model_dump() if top_hypothesis else None,
        "assistant_message": response.assistant_message,
        "completion_state": response.completion_state,
        "next_question": response.next_question,
        "tool_calls": [call.model_dump() for call in response.tool_calls],
        "fix_steps": response.fix_steps,
        "metadata": response.metadata,
        "guardrail_hits_session": response.metadata.get("guardrail_hits_session")
        if isinstance(response.metadata, dict)
        else None,
    }


def _to_dynamodb(value: Any) -> Any:
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _to_dynamodb(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_to_dynamodb(item) for item in value]
    return value


def build_llm_context(storage: StorageAdapter, conversation_id: str, limit: int = 5) -> Dict[str, object]:
    context = storage.get_conversation_context(conversation_id, limit=limit)
    state = context.get("state") or {}
    recent_events = context.get("recent_events") or []

    compact_events = []
    recent_messages = []
    for event in recent_events:
        frame = event.get("incident_frame") or {}
        response = event.get("canonical_response") or {}
        hypotheses = response.get("hypotheses") or []
        top_hypothesis = hypotheses[0] if hypotheses else None
        raw_input = (event.get("raw_text") or event.get("raw_input") or "")[:800]
        compact_events.append(
            {
                "request_id": event.get("request_id"),
                "primary_error_signature": frame.get("primary_error_signature"),
                "secondary_signatures": frame.get("secondary_signatures", [])[:3],
                "services": frame.get("services", []),
                "infra_components": frame.get("infra_components", []),
                "suspected_failure_domain": frame.get("suspected_failure_domain"),
                "top_hypothesis": top_hypothesis,
                "assistant_message": response.get("assistant_message"),
                "completion_state": response.get("completion_state"),
                "next_question": response.get("next_question"),
                "tool_calls": response.get("tool_calls"),
                "fix_steps": response.get("fix_steps"),
            }
        )
        if raw_input:
            recent_messages.append({"request_id": event.get("request_id"), "raw_input": raw_input})

    latest_frame = state.get("latest_incident_frame") or {}
    latest_summary = state.get("latest_response_summary") or {}

    prompt = (
        "You are an expert troubleshooting assistant. Use the conversation context to decide the next action. "
        "Ask one question at a time or request a single tool command if needed. When enough context exists, "
        "return the most likely explanations and fix steps. Ground your response in provided evidence.\n\n"
        f"Conversation ID: {conversation_id}\n"
        f"Latest error signature: {latest_frame.get('primary_error_signature')}\n"
        f"Services: {', '.join(latest_frame.get('services', []))}\n"
        f"Infra components: {', '.join(latest_frame.get('infra_components', []))}\n"
        f"Suspected failure domain: {latest_frame.get('suspected_failure_domain')}\n"
        f"Top hypothesis: {latest_summary.get('top_hypothesis')}\n"
        f"Pending question: {latest_summary.get('next_question')}\n"
        f"Pending tool calls: {latest_summary.get('tool_calls')}\n"
        f"Recent events: {compact_events}\n"
        f"Recent user inputs: {recent_messages}\n"
    )

    return {
        "conversation_id": conversation_id,
        "latest_incident_frame": latest_frame,
        "latest_response_summary": latest_summary,
        "recent_events": compact_events,
        "recent_messages": recent_messages,
        "prompt": prompt,
        "bedrock_input": {"inputText": prompt},
    }
