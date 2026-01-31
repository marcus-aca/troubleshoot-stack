import { useEffect, useState } from "react";
import type { BudgetStatus, ChatResponse } from "../api/types";

const toNumber = (value: unknown) => {
  if (typeof value === "number") return value;
  if (typeof value === "string" && value.trim() !== "") {
    const parsed = Number(value);
    return Number.isNaN(parsed) ? null : parsed;
  }
  return null;
};

export type MetricsPanelProps = {
  lastResponse: ChatResponse | null;
  lastLatencyMs: number | null;
  requestId: string | null;
  tokenUnavailable?: boolean;
  budgetStatus?: BudgetStatus | null;
};

const formatNumber = (value: number | null, suffix = "") => {
  if (value === null || Number.isNaN(value)) return "-";
  return `${value}${suffix}`;
};

const getTokenUsage = (metadata: Record<string, unknown>) => {
  const direct =
    toNumber(metadata.total_tokens) ??
    toNumber(metadata.token_usage_total) ??
    toNumber(metadata.tokens_total);
  if (direct !== null) return direct;
  const usage =
    (metadata.token_usage as { total_tokens?: number } | undefined) ??
    (metadata.usage as { total_tokens?: number } | undefined);
  return usage?.total_tokens !== undefined ? toNumber(usage.total_tokens) : null;
};

const formatUsd = (value: number | null | undefined) => {
  if (value === null || value === undefined || Number.isNaN(value)) return "-";
  return `$${value.toFixed(4)}`;
};

const formatBudgetWindow = (status: BudgetStatus | null | undefined, nowMs: number) => {
  if (!status?.retry_after || status.retry_after === "unknown") return "-";
  const retryAt = Date.parse(status.retry_after);
  if (Number.isNaN(retryAt)) return "-";
  const deltaMs = retryAt - nowMs;
  if (deltaMs <= 0) {
    return "resetting...";
  }
  const minutes = Math.floor(deltaMs / 60000);
  const seconds = Math.floor((deltaMs % 60000) / 1000);
  if (minutes <= 0) {
    return `${seconds}s`;
  }
  return `${minutes}m ${seconds}s`;
};

export default function MetricsPanel({
  lastResponse,
  lastLatencyMs,
  requestId,
  tokenUnavailable,
  budgetStatus
}: MetricsPanelProps) {
  const [nowMs, setNowMs] = useState(() => Date.now());
  const metadata = lastResponse?.metadata ?? {};
  const latency = lastLatencyMs;
  const tokenUsage = tokenUnavailable ? null : getTokenUsage(metadata);
  const costEstimate = toNumber(metadata.cost_estimate_usd);
  const remainingBudget = budgetStatus?.remaining_budget ?? null;
  const guardrailHits =
    toNumber(metadata.guardrail_hits_session) ?? toNumber(metadata.guardrail_hits);
  const budgetWindow = formatBudgetWindow(budgetStatus, nowMs);

  useEffect(() => {
    if (!budgetStatus?.retry_after || budgetStatus.retry_after === "unknown") {
      return;
    }
    const interval = window.setInterval(() => {
      setNowMs(Date.now());
    }, 1000);
    return () => window.clearInterval(interval);
  }, [budgetStatus?.retry_after]);

  return (
    <aside className="panel metrics">
      <div className="panel-header">
        <h2>Session stats</h2>
      </div>

      <div className="metric-grid">
        <div className="metric-card">
          <span className="metric-label">Tokens consumed</span>
          <span className="metric-value">{formatNumber(tokenUsage)}</span>
        </div>
        <div className="metric-card">
          <span className="metric-label">Cost estimate</span>
          <span className="metric-value">{formatUsd(costEstimate)}</span>
        </div>
        <div className="metric-card">
          <span className="metric-label">Budget remaining</span>
          <span className="metric-value">{formatNumber(remainingBudget)}</span>
        </div>
        <div className="metric-card">
          <span className="metric-label">Budget window</span>
          <span className="metric-value">{budgetWindow}</span>
        </div>
        <div className="metric-card">
          <span className="metric-label">Guardrail hits</span>
          <span className="metric-value">{formatNumber(guardrailHits)}</span>
        </div>
        <div className="metric-card">
          <span className="metric-label">E2E latency (ms)</span>
          <span className="metric-value">{formatNumber(latency)}</span>
        </div>
      </div>
    </aside>
  );
}
