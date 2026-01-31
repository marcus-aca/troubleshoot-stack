from __future__ import annotations

import json
import logging
import os
import time
from collections import deque
from datetime import datetime, timedelta, timezone
from math import floor
from typing import Deque, Dict, Iterable, Optional

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
                "MetricName": "TokensPerRequest",
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

    def put_cache_metrics(self, *, endpoint: str, hit: bool) -> None:
        if not self.enabled or not self.client:
            return
        dimensions = [{"Name": "Endpoint", "Value": endpoint}]
        metric_data = [
            {
                "MetricName": "CacheHitCount",
                "Dimensions": dimensions,
                "Unit": "Count",
                "Value": 1 if hit else 0,
            },
            {
                "MetricName": "CacheMissCount",
                "Dimensions": dimensions,
                "Unit": "Count",
                "Value": 0 if hit else 1,
            },
            {
                "MetricName": "CacheHitRate",
                "Dimensions": dimensions,
                "Unit": "None",
                "Value": 1 if hit else 0,
            },
        ]
        self.client.put_metric_data(Namespace=self.namespace, MetricData=metric_data)

    def put_budget_denied(self) -> None:
        if not self.enabled or not self.client:
            return
        self.client.put_metric_data(
            Namespace=self.namespace,
            MetricData=[
                {
                    "MetricName": "BudgetDeniedCount",
                    "Unit": "Count",
                    "Value": 1,
                }
            ],
        )

    def put_api_metrics(self, *, endpoint: str, status_code: int, latency_ms: float) -> None:
        if not self.enabled or not self.client:
            return
        dimensions = [
            {"Name": "Endpoint", "Value": endpoint},
            {"Name": "StatusCode", "Value": str(status_code)},
        ]
        metric_data = [
            {
                "MetricName": "APIRequestCount",
                "Dimensions": dimensions,
                "Unit": "Count",
                "Value": 1,
            },
            {
                "MetricName": "APILatencyMs",
                "Dimensions": dimensions,
                "Unit": "Milliseconds",
                "Value": latency_ms,
            },
            {
                "MetricName": "APIErrorCount",
                "Dimensions": dimensions,
                "Unit": "Count",
                "Value": 1 if status_code >= 400 else 0,
            },
        ]
        self.client.put_metric_data(Namespace=self.namespace, MetricData=metric_data)

    def get_api_latency_percentiles(
        self,
        *,
        endpoints: Iterable[str],
        status_code: str = "200",
        minutes: int = 15,
        period: int = 60,
    ) -> Optional[Dict[str, Optional[float]]]:
        if not self.enabled or not self.client:
            return None

        queries = []
        for idx, endpoint in enumerate(endpoints):
            for stat in ("p50", "p95"):
                queries.append(
                    {
                        "Id": f"{stat}_{idx}",
                        "MetricStat": {
                            "Metric": {
                                "Namespace": self.namespace,
                                "MetricName": "APILatencyMs",
                                "Dimensions": [
                                    {"Name": "Endpoint", "Value": endpoint},
                                    {"Name": "StatusCode", "Value": status_code},
                                ],
                            },
                            "Period": period,
                            "Stat": stat,
                        },
                        "ReturnData": True,
                    }
                )

        if not queries:
            return None

        end_time = datetime.now(timezone.utc)
        start_time = end_time - timedelta(minutes=minutes)
        try:
            response = self.client.get_metric_data(
                MetricDataQueries=queries,
                StartTime=start_time,
                EndTime=end_time,
                ScanBy="TimestampDescending",
                MaxDatapoints=100,
            )
            results = response.get("MetricDataResults", [])
        except Exception as exc:
            log_event("metrics_summary_error", {"error": str(exc), "source": "cloudwatch"})
            return None
        p50_values = []
        p95_values = []
        for result in results:
            values = result.get("Values") or []
            if not values:
                continue
            latest = values[0]
            if result.get("Id", "").startswith("p50"):
                p50_values.append(latest)
            elif result.get("Id", "").startswith("p95"):
                p95_values.append(latest)

        if not p50_values and not p95_values:
            return None

        return {
            "p50": max(p50_values) if p50_values else None,
            "p95": max(p95_values) if p95_values else None,
        }

    def get_cache_hit_rate(self, *, endpoint: str = "explain", minutes: int = 15, period: int = 60) -> Optional[float]:
        if not self.enabled or not self.client:
            return None
        end_time = datetime.now(timezone.utc)
        start_time = end_time - timedelta(minutes=minutes)
        try:
            response = self.client.get_metric_data(
                MetricDataQueries=[
                    {
                        "Id": "cache_hit_rate",
                        "MetricStat": {
                            "Metric": {
                                "Namespace": self.namespace,
                                "MetricName": "CacheHitRate",
                                "Dimensions": [{"Name": "Endpoint", "Value": endpoint}],
                            },
                            "Period": period,
                            "Stat": "Average",
                        },
                        "ReturnData": True,
                    }
                ],
                StartTime=start_time,
                EndTime=end_time,
                ScanBy="TimestampDescending",
                MaxDatapoints=50,
            )
            results = response.get("MetricDataResults", [])
        except Exception as exc:
            log_event("metrics_summary_error", {"error": str(exc), "source": "cloudwatch"})
            return None
        if not results:
            return None
        values = results[0].get("Values") or []
        if not values:
            return None
        return values[0]

    def get_api_error_rate(
        self,
        *,
        endpoints: Iterable[str],
        minutes: int = 15,
        period: int = 60,
    ) -> Optional[float]:
        if not self.enabled or not self.client:
            return None
        queries = []
        for idx, endpoint in enumerate(endpoints):
            queries.append(
                {
                    "Id": f"req_{idx}",
                    "MetricStat": {
                        "Metric": {
                            "Namespace": self.namespace,
                            "MetricName": "APIRequestCount",
                            "Dimensions": [{"Name": "Endpoint", "Value": endpoint}],
                        },
                        "Period": period,
                        "Stat": "Sum",
                    },
                    "ReturnData": True,
                }
            )
            queries.append(
                {
                    "Id": f"err_{idx}",
                    "MetricStat": {
                        "Metric": {
                            "Namespace": self.namespace,
                            "MetricName": "APIErrorCount",
                            "Dimensions": [{"Name": "Endpoint", "Value": endpoint}],
                        },
                        "Period": period,
                        "Stat": "Sum",
                    },
                    "ReturnData": True,
                }
            )

        end_time = datetime.now(timezone.utc)
        start_time = end_time - timedelta(minutes=minutes)
        try:
            response = self.client.get_metric_data(
                MetricDataQueries=queries,
                StartTime=start_time,
                EndTime=end_time,
                ScanBy="TimestampDescending",
                MaxDatapoints=100,
            )
            results = response.get("MetricDataResults", [])
        except Exception as exc:
            log_event("metrics_summary_error", {"error": str(exc), "source": "cloudwatch"})
            return None

        if not results:
            return None
        totals = {"req": 0.0, "err": 0.0}
        for result in results:
            values = result.get("Values") or []
            if not values:
                continue
            latest = values[0]
            if result.get("Id", "").startswith("req_"):
                totals["req"] += latest
            elif result.get("Id", "").startswith("err_"):
                totals["err"] += latest
        if totals["req"] <= 0:
            return None
        return totals["err"] / totals["req"]

    def get_budget_denied_count(self, *, minutes: int = 15, period: int = 60) -> Optional[float]:
        if not self.enabled or not self.client:
            return None
        end_time = datetime.now(timezone.utc)
        start_time = end_time - timedelta(minutes=minutes)
        try:
            response = self.client.get_metric_data(
                MetricDataQueries=[
                    {
                        "Id": "budget_denied",
                        "MetricStat": {
                            "Metric": {
                                "Namespace": self.namespace,
                                "MetricName": "BudgetDeniedCount",
                            },
                            "Period": period,
                            "Stat": "Sum",
                        },
                        "ReturnData": True,
                    }
                ],
                StartTime=start_time,
                EndTime=end_time,
                ScanBy="TimestampDescending",
                MaxDatapoints=50,
            )
            results = response.get("MetricDataResults", [])
        except Exception as exc:
            log_event("metrics_summary_error", {"error": str(exc), "source": "cloudwatch"})
            return None
        if not results:
            return None
        values = results[0].get("Values") or []
        if not values:
            return None
        return values[0]

    def get_llm_latency_percentiles(
        self,
        *,
        endpoints: Iterable[str],
        minutes: int = 15,
        period: int = 60,
    ) -> Optional[Dict[str, Optional[float]]]:
        if not self.enabled or not self.client:
            return None

        queries = []
        for idx, endpoint in enumerate(endpoints):
            for stat in ("p50", "p95"):
                queries.append(
                    {
                        "Id": f"{stat}_{idx}",
                        "MetricStat": {
                            "Metric": {
                                "Namespace": self.namespace,
                                "MetricName": "LLMLatencyMs",
                                "Dimensions": [
                                    {"Name": "Endpoint", "Value": endpoint},
                                ],
                            },
                            "Period": period,
                            "Stat": stat,
                        },
                        "ReturnData": True,
                    }
                )

        if not queries:
            return None

        end_time = datetime.now(timezone.utc)
        start_time = end_time - timedelta(minutes=minutes)
        try:
            response = self.client.get_metric_data(
                MetricDataQueries=queries,
                StartTime=start_time,
                EndTime=end_time,
                ScanBy="TimestampDescending",
                MaxDatapoints=100,
            )
            results = response.get("MetricDataResults", [])
        except Exception as exc:
            log_event("metrics_summary_error", {"error": str(exc), "source": "cloudwatch"})
            return None

        p50_values = []
        p95_values = []
        for result in results:
            values = result.get("Values") or []
            if not values:
                continue
            latest = values[0]
            if result.get("Id", "").startswith("p50"):
                p50_values.append(latest)
            elif result.get("Id", "").startswith("p95"):
                p95_values.append(latest)

        if not p50_values and not p95_values:
            return None

        return {
            "p50": max(p50_values) if p50_values else None,
            "p95": max(p95_values) if p95_values else None,
        }


class RollingPercentiles:
    def __init__(self, max_samples: int = 200) -> None:
        self.values: Deque[float] = deque(maxlen=max_samples)

    def add(self, value: float) -> None:
        self.values.append(value)

    def percentiles(self, percentiles: Iterable[int]) -> Dict[str, Optional[float]]:
        data = list(self.values)
        if not data:
            return {f"p{p}": None for p in percentiles}
        data.sort()
        n = len(data)
        results: Dict[str, Optional[float]] = {}
        for p in percentiles:
            if n == 1:
                results[f"p{p}"] = data[0]
                continue
            rank = (p / 100) * (n - 1)
            low = floor(rank)
            high = min(low + 1, n - 1)
            if low == high:
                results[f"p{p}"] = data[low]
            else:
                frac = rank - low
                results[f"p{p}"] = data[low] + (data[high] - data[low]) * frac
        return results

    def count(self) -> int:
        return len(self.values)


class RollingCacheHitRate:
    def __init__(self, max_samples: int = 200) -> None:
        self.values: Deque[int] = deque(maxlen=max_samples)

    def add(self, hit: bool) -> None:
        self.values.append(1 if hit else 0)

    def rate(self) -> Optional[float]:
        if not self.values:
            return None
        return sum(self.values) / len(self.values)

    def count(self) -> int:
        return len(self.values)


class RollingWindowCounter:
    def __init__(self, window_seconds: int = 300) -> None:
        self.window_seconds = window_seconds
        self.values: Deque[float] = deque()

    def add(self, value: int = 1) -> None:
        now = time.time()
        for _ in range(value):
            self.values.append(now)
        self._prune(now)

    def count(self) -> int:
        now = time.time()
        self._prune(now)
        return len(self.values)

    def _prune(self, now: float) -> None:
        cutoff = now - self.window_seconds
        while self.values and self.values[0] < cutoff:
            self.values.popleft()


class RollingRequestWindow:
    def __init__(self, window_seconds: int = 300) -> None:
        self.window_seconds = window_seconds
        self.values: Deque[tuple[float, int]] = deque()

    def add(self, status_code: int) -> None:
        now = time.time()
        is_error = 1 if status_code >= 400 else 0
        self.values.append((now, is_error))
        self._prune(now)

    def error_rate(self) -> Optional[float]:
        now = time.time()
        self._prune(now)
        if not self.values:
            return None
        total = len(self.values)
        errors = sum(value for _, value in self.values)
        return errors / total if total else None

    def _prune(self, now: float) -> None:
        cutoff = now - self.window_seconds
        while self.values and self.values[0][0] < cutoff:
            self.values.popleft()


def log_event(event: str, payload: Dict[str, object]) -> None:
    record = {"event": event, "timestamp_ms": int(time.time() * 1000), **payload}
    LOGGER.info(json.dumps(record, default=str))


def start_timer() -> float:
    return time.perf_counter()


def stop_timer(start: float) -> float:
    return (time.perf_counter() - start) * 1000.0
