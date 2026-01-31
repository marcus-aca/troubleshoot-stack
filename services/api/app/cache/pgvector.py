from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass
from typing import Optional, Tuple
from uuid import uuid4

import boto3
import psycopg

from ..observability import CloudWatchMetrics, log_event
from ..schemas import CanonicalResponse, IncidentFrame

EMBED_MODEL_ID = "amazon.titan-embed-text-v2:0"
EMBED_DIMENSIONS = 256
DEFAULT_SIMILARITY_THRESHOLD = 0.95
DEFAULT_TTL_SECONDS = 86400


@dataclass(frozen=True)
class CacheHit:
    response: CanonicalResponse
    similarity: float


class PgVectorCache:
    def __init__(self) -> None:
        self.enabled = os.getenv("PGVECTOR_ENABLED", "false").lower() == "true"
        self.host = os.getenv("PGVECTOR_HOST", "127.0.0.1")
        self.port = int(os.getenv("PGVECTOR_PORT", "5432"))
        self.database = os.getenv("PGVECTOR_DB", os.getenv("POSTGRES_DB", "troubleshooter_cache"))
        self.user = os.getenv("PGVECTOR_USER", os.getenv("POSTGRES_USER", "postgres"))
        self.password = os.getenv("PGVECTOR_PASSWORD", os.getenv("POSTGRES_PASSWORD", "postgres"))
        self.similarity_threshold = float(
            os.getenv("PGVECTOR_SIMILARITY_THRESHOLD", str(DEFAULT_SIMILARITY_THRESHOLD))
        )
        self.ttl_seconds = int(os.getenv("PGVECTOR_TTL_SECONDS", str(DEFAULT_TTL_SECONDS)))
        self.metrics = CloudWatchMetrics()
        self._client = None
        self._embedding_client = None

        if self.enabled:
            self._client = boto3.client("bedrock-runtime")
            self._embedding_client = self._client

    def bootstrap(self, *, max_attempts: int = 10, sleep_seconds: float = 1.0) -> None:
        if not self.enabled:
            return
        for attempt in range(1, max_attempts + 1):
            try:
                with self._connect() as conn:
                    with conn.cursor() as cur:
                        cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
                        cur.execute(
                            """
                            CREATE TABLE IF NOT EXISTS cache_entries (
                                id uuid PRIMARY KEY,
                                embedding vector(256) NOT NULL,
                                response jsonb NOT NULL,
                                created_at timestamptz NOT NULL DEFAULT NOW(),
                                expires_at timestamptz NOT NULL
                            );
                            """
                        )
                        cur.execute(
                            """
                            CREATE INDEX IF NOT EXISTS cache_entries_embedding_idx
                            ON cache_entries USING hnsw (embedding vector_cosine_ops);
                            """
                        )
                    conn.commit()
                log_event("cache_bootstrap", {"status": "ok"})
                return
            except Exception as exc:
                log_event(
                    "cache_bootstrap_error",
                    {"attempt": attempt, "error": str(exc)},
                )
                if attempt == max_attempts:
                    return
                time.sleep(sleep_seconds)

    def get_explain_cache_key(self, frame: IncidentFrame, question: str) -> str:
        parts = [
            question.strip(),
            frame.primary_error_signature or "",
            " ".join(frame.services or []),
            " ".join(frame.infra_components or []),
        ]
        return "\n".join(part for part in parts if part)

    def lookup(self, *, endpoint: str, query_text: str) -> Optional[CacheHit]:
        if not self.enabled:
            return None
        try:
            sanitized = sanitize_text(query_text)
            embedding = self._embed(sanitized)
            vector_literal = _format_vector_literal(embedding)
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT response, 1 - (embedding <=> %s::vector) AS similarity
                        FROM cache_entries
                        WHERE expires_at > NOW()
                        ORDER BY embedding <=> %s::vector
                        LIMIT 1;
                        """,
                        (vector_literal, vector_literal),
                    )
                    row = cur.fetchone()
            if not row:
                self._emit_cache_metric(endpoint=endpoint, hit=False)
                return None
            response_payload, similarity = row
            if isinstance(response_payload, (str, bytes, bytearray)):
                response_payload = json.loads(response_payload)
            if similarity is None or similarity < self.similarity_threshold:
                self._emit_cache_metric(endpoint=endpoint, hit=False)
                return None
            response = CanonicalResponse.model_validate(response_payload)
            self._emit_cache_metric(endpoint=endpoint, hit=True)
            return CacheHit(response=response, similarity=float(similarity))
        except Exception as exc:
            log_event("cache_lookup_error", {"endpoint": endpoint, "error": str(exc)})
            return None

    def put(self, *, endpoint: str, query_text: str, response: CanonicalResponse) -> None:
        if not self.enabled:
            return
        try:
            sanitized = sanitize_text(query_text)
            embedding = self._embed(sanitized)
            vector_literal = _format_vector_literal(embedding)
            payload = response.model_dump(mode="json")
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO cache_entries (id, embedding, response, expires_at)
                        VALUES (%s, %s::vector, %s::jsonb, NOW() + (%s || ' seconds')::interval);
                        """,
                        (
                            str(uuid4()),
                            vector_literal,
                            json.dumps(payload),
                            self.ttl_seconds,
                        ),
                    )
                conn.commit()
        except Exception as exc:
            log_event("cache_write_error", {"endpoint": endpoint, "error": str(exc)})

    def _embed(self, text: str) -> list[float]:
        mode = os.getenv("LLM_MODE", "stub").lower()
        if mode != "bedrock":
            return _pseudo_embedding(text)
        if not self._embedding_client:
            raise RuntimeError("Bedrock runtime client not initialized")
        payload = {
            "inputText": text,
            "dimensions": EMBED_DIMENSIONS,
            "normalize": True,
        }
        response = self._embedding_client.invoke_model(
            modelId=EMBED_MODEL_ID,
            body=json.dumps(payload).encode("utf-8"),
            accept="application/json",
            contentType="application/json",
        )
        raw_body = response.get("body")
        if hasattr(raw_body, "read"):
            raw_body = raw_body.read()
        data = json.loads(raw_body)
        embedding = data.get("embedding") or []
        if len(embedding) != EMBED_DIMENSIONS:
            raise ValueError(f"Unexpected embedding size: {len(embedding)}")
        return embedding

    def _connect(self) -> psycopg.Connection:
        return psycopg.connect(
            host=self.host,
            port=self.port,
            dbname=self.database,
            user=self.user,
            password=self.password,
            autocommit=False,
        )

    def _emit_cache_metric(self, *, endpoint: str, hit: bool) -> None:
        self.metrics.put_cache_metrics(endpoint=endpoint, hit=hit)


def _format_vector_literal(embedding: list[float]) -> str:
    return "[" + ",".join(f"{value:.6f}" for value in embedding) + "]"


def _pseudo_embedding(text: str) -> list[float]:
    seed = sum(ord(ch) for ch in text) or 1
    values = []
    for idx in range(EMBED_DIMENSIONS):
        seed = (seed * 1103515245 + 12345) & 0x7FFFFFFF
        values.append((seed % 1000) / 1000.0)
    return values


_EMAIL_RE = re.compile(r"([A-Za-z0-9._%+-]+)@([A-Za-z0-9.-]+\\.[A-Za-z]{2,})")
_UUID_RE = re.compile(r"\\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}\\b")
_IP_RE = re.compile(r"\\b(\\d{1,3}\\.){3}\\d{1,3}\\b")
_HEX_RE = re.compile(r"\\b[0-9a-fA-F]{32,}\\b")
_AWS_KEY_RE = re.compile(r"\\b(AKIA|ASIA)[0-9A-Z]{16}\\b")
_BEARER_RE = re.compile(r"(?i)bearer\\s+[A-Za-z0-9._\\-]+")
_PASSWORD_RE = re.compile(r"(?i)(password|passwd|pwd|secret|token|api_key|apikey)\\s*[:=]\\s*[^\\s]+")


def sanitize_text(text: str) -> str:
    if not text:
        return text
    cleaned = text
    cleaned = _EMAIL_RE.sub("<email>", cleaned)
    cleaned = _UUID_RE.sub("<uuid>", cleaned)
    cleaned = _IP_RE.sub("<ip>", cleaned)
    cleaned = _HEX_RE.sub("<hex>", cleaned)
    cleaned = _AWS_KEY_RE.sub("<aws_access_key>", cleaned)
    cleaned = _BEARER_RE.sub("bearer <token>", cleaned)
    cleaned = _PASSWORD_RE.sub(r"\\1=<redacted>", cleaned)
    cleaned = re.sub(r"\\s+", " ", cleaned).strip()
    return cleaned
