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
            table.update_item(
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
                return BudgetDecision(allowed=False, retry_after=retry_after)
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

        return BudgetDecision(allowed=True)


def estimate_tokens(text: str, *, max_tokens: int) -> int:
    prompt_tokens = max(1, int(len(text) / 4))
    return prompt_tokens + max(0, max_tokens)


def _window_start(window_minutes: int) -> datetime:
    now = datetime.now(timezone.utc)
    minute = (now.minute // window_minutes) * window_minutes
    return now.replace(minute=minute, second=0, microsecond=0)
