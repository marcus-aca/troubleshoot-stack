from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

import boto3
from botocore.exceptions import ClientError

from .observability import CloudWatchMetrics, log_event


@dataclass(frozen=True)
class BudgetDecision:
    allowed: bool
    retry_after: Optional[str] = None
    remaining_budget: Optional[int] = None


class BudgetEnforcer:
    def __init__(self) -> None:
        self.enabled = os.getenv("BUDGET_ENABLED", "true").lower() == "true"
        self.table_name = os.getenv("BUDGET_TABLE_NAME", "troubleshooter-budgets")
        self.token_limit = int(os.getenv("BUDGET_TOKEN_LIMIT", "20000"))
        self.window_minutes = int(os.getenv("BUDGET_WINDOW_MINUTES", "15"))
        self.user_id = os.getenv("BUDGET_USER_ID", "demo")
        self.client = boto3.resource("dynamodb") if self.enabled else None
        self.metrics = CloudWatchMetrics()

    def enforce(self, *, estimated_tokens: int) -> BudgetDecision:
        if not self.enabled or not self.client:
            return BudgetDecision(allowed=True)

        window_start = _window_start(self.window_minutes)
        window_key = window_start.strftime("%Y-%m-%dT%H:%MZ")
        retry_after = (window_start + timedelta(minutes=self.window_minutes)).strftime("%Y-%m-%dT%H:%MZ")

        table = self.client.Table(self.table_name)
        limit_remaining = self.token_limit - estimated_tokens
        try:
            response = table.update_item(
                Key={"user_id": self.user_id, "usage_window": window_key},
                UpdateExpression=(
                    "SET tokens_used = if_not_exists(tokens_used, :zero) + :tokens, "
                    "last_updated_at = :now"
                ),
                ConditionExpression="attribute_not_exists(tokens_used) OR tokens_used <= :limit_remaining",
                ExpressionAttributeValues={
                    ":zero": 0,
                    ":tokens": estimated_tokens,
                    ":limit_remaining": limit_remaining,
                    ":now": datetime.now(timezone.utc).isoformat(),
                },
                ReturnValues="UPDATED_NEW",
            )
        except ClientError as exc:
            error_code = exc.response.get("Error", {}).get("Code")
            if error_code == "ConditionalCheckFailedException":
                log_event(
                    "budget_denied",
                    {
                        "user_id": self.user_id,
                        "usage_window": window_key,
                        "estimated_tokens": estimated_tokens,
                        "token_limit": self.token_limit,
                    },
                )
                self.metrics.put_budget_denied()
                return BudgetDecision(allowed=False, retry_after=retry_after, remaining_budget=0)
            log_event(
                "budget_error",
                {
                    "user_id": self.user_id,
                    "usage_window": window_key,
                    "estimated_tokens": estimated_tokens,
                    "error": str(exc),
                },
            )
            return BudgetDecision(allowed=True)

        tokens_used = int(response.get("Attributes", {}).get("tokens_used", 0))
        remaining_budget = max(self.token_limit - tokens_used, 0)
        return BudgetDecision(allowed=True, remaining_budget=remaining_budget)

    def get_status(self) -> Optional[dict]:
        if not self.enabled or not self.client:
            return None
        window_start = _window_start(self.window_minutes)
        window_key = window_start.strftime("%Y-%m-%dT%H:%MZ")
        retry_after = (window_start + timedelta(minutes=self.window_minutes)).strftime("%Y-%m-%dT%H:%MZ")
        table = self.client.Table(self.table_name)
        try:
            response = table.get_item(Key={"user_id": self.user_id, "usage_window": window_key})
        except ClientError:
            return None
        item = response.get("Item") or {}
        tokens_used = int(item.get("tokens_used", 0)) if item else 0
        remaining_budget = max(self.token_limit - tokens_used, 0)
        return {
            "user_id": self.user_id,
            "usage_window": window_key,
            "retry_after": retry_after,
            "token_limit": self.token_limit,
            "tokens_used": tokens_used,
            "remaining_budget": remaining_budget,
        }


def estimate_tokens(text: str, *, max_tokens: int) -> int:
    prompt_tokens = max(1, int(len(text) / 4))
    completion_cap = int(os.getenv("LLM_BUDGET_COMPLETION_TOKENS", "400"))
    completion_estimate = max(0, min(max_tokens, completion_cap))
    return prompt_tokens + completion_estimate


def _window_start(window_minutes: int) -> datetime:
    now = datetime.now(timezone.utc)
    minute = (now.minute // window_minutes) * window_minutes
    return now.replace(minute=minute, second=0, microsecond=0)
