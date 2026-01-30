from __future__ import annotations

import json
import logging
import os
import time
from typing import Dict, Optional

import boto3


LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
LOGGER = logging.getLogger("troubleshooter")
if not LOGGER.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(message)s"))
    LOGGER.addHandler(handler)
LOGGER.setLevel(LOG_LEVEL)


class CloudWatchMetrics:
    def __init__(self) -> None:
        self.enabled = os.getenv("CW_METRICS_ENABLED", "false").lower() == "true"
        self.namespace = os.getenv("CW_METRICS_NAMESPACE", "Troubleshooter/LLM")
        self.client = boto3.client("cloudwatch") if self.enabled else None

    def put_llm_metrics(
        self,
        *,
        endpoint: str,
        model_id: str,
        latency_ms: float,
        tokens_total: int,
        success: bool,
        guardrail_missing: int = 0,
        guardrail_redactions: int = 0,
    ) -> None:
        if not self.enabled or not self.client:
            return
        dimensions = [
            {"Name": "Endpoint", "Value": endpoint},
            {"Name": "ModelId", "Value": model_id},
        ]
        metric_data = [
            {
                "MetricName": "LLMRequests",
                "Dimensions": dimensions,
                "Unit": "Count",
                "Value": 1,
            },
            {
                "MetricName": "LLMLatencyMs",
                "Dimensions": dimensions,
                "Unit": "Milliseconds",
                "Value": latency_ms,
            },
            {
                "MetricName": "LLMTokensTotal",
                "Dimensions": dimensions,
                "Unit": "Count",
                "Value": tokens_total,
            },
            {
                "MetricName": "LLMErrors",
                "Dimensions": dimensions,
                "Unit": "Count",
                "Value": 0 if success else 1,
            },
            {
                "MetricName": "GuardrailCitationMissing",
                "Dimensions": dimensions,
                "Unit": "Count",
                "Value": guardrail_missing,
            },
            {
                "MetricName": "GuardrailRedactions",
                "Dimensions": dimensions,
                "Unit": "Count",
                "Value": guardrail_redactions,
            },
        ]
        self.client.put_metric_data(Namespace=self.namespace, MetricData=metric_data)


def log_event(event: str, payload: Dict[str, object]) -> None:
    record = {"event": event, "timestamp_ms": int(time.time() * 1000), **payload}
    LOGGER.info(json.dumps(record, default=str))


def start_timer() -> float:
    return time.perf_counter()


def stop_timer(start: float) -> float:
    return (time.perf_counter() - start) * 1000.0
