from __future__ import annotations

import os
import time
from typing import Dict, Optional
from uuid import uuid4

import boto3

from .schemas import IncidentFrame


class StorageAdapter:
    def save_input(self, conversation_id: Optional[str], request_id: str, raw_text: str) -> str:
        raise NotImplementedError

    def save_frame(self, frame: IncidentFrame) -> None:
        raise NotImplementedError


class InMemoryStorage(StorageAdapter):
    def __init__(self) -> None:
        self.inputs: Dict[str, Dict[str, str]] = {}
        self.frames: Dict[str, IncidentFrame] = {}

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


class DynamoDBStorage(StorageAdapter):
    def __init__(self) -> None:
        self.session_table = os.getenv("SESSION_TABLE", "troubleshooter-sessions")
        self.inputs_table = os.getenv("INPUTS_TABLE", "troubleshooter-inputs")
        self.ttl_seconds = int(os.getenv("INPUT_TTL_SECONDS", "86400"))
        self.client = boto3.resource("dynamodb")

    def save_input(self, conversation_id: Optional[str], request_id: str, raw_text: str) -> str:
        input_id = str(uuid4())
        expires_at = int(time.time()) + self.ttl_seconds
        inputs = self.client.Table(self.inputs_table)
        inputs.put_item(
            Item={
                "input_id": input_id,
                "conversation_id": conversation_id or "",
                "request_id": request_id,
                "raw_text": raw_text,
                "created_at": int(time.time()),
                "expires_at": expires_at,
            }
        )

        if conversation_id:
            sessions = self.client.Table(self.session_table)
            sessions.put_item(
                Item={
                    "conversation_id": conversation_id,
                    "last_request_id": request_id,
                    "last_input_id": input_id,
                    "updated_at": int(time.time()),
                    "expires_at": expires_at,
                }
            )
        return input_id

    def save_frame(self, frame: IncidentFrame) -> None:
        inputs = self.client.Table(self.inputs_table)
        inputs.put_item(
            Item={
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


def get_storage() -> StorageAdapter:
    if os.getenv("USE_DYNAMODB", "false").lower() == "true":
        return DynamoDBStorage()
    return InMemoryStorage()
