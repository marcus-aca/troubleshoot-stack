import type { MetricsSummary } from "../api/types";

export type OpsStatsPanelProps = {
  metrics: MetricsSummary | null;
};

const formatMs = (value: number | null) => {
  if (value === null || Number.isNaN(value)) return "-";
  return `${Math.round(value)} ms`;
};

const formatPercent = (value: number | null | undefined) => {
  if (value === null || value === undefined || Number.isNaN(value)) return "-";
  const percent = value <= 1 ? value * 100 : value;
  return `${Math.round(percent * 10) / 10}%`;
};

const formatCount = (value: number | null | undefined) => {
  if (value === null || value === undefined || Number.isNaN(value)) return "-";
  return `${Math.round(value)}`;
};

export default function OpsStatsPanel({ metrics }: OpsStatsPanelProps) {
  return (
    <aside className="panel metrics">
      <div className="panel-header">
        <h2>Ops stats (5 min)</h2>
      </div>
      <div className="metric-grid">
        <div className="metric-card">
          <span className="metric-label">API latency p50</span>
          <span className="metric-value">{formatMs(metrics?.api_latency_p50_ms ?? null)}</span>
        </div>
        <div className="metric-card">
          <span className="metric-label">API latency p95</span>
          <span className="metric-value">{formatMs(metrics?.api_latency_p95_ms ?? null)}</span>
        </div>
        <div className="metric-card">
          <span className="metric-label">LLM latency p50</span>
          <span className="metric-value">{formatMs(metrics?.llm_latency_p50_ms ?? null)}</span>
        </div>
        <div className="metric-card">
          <span className="metric-label">LLM latency p95</span>
          <span className="metric-value">{formatMs(metrics?.llm_latency_p95_ms ?? null)}</span>
        </div>
        <div className="metric-card">
          <span className="metric-label">Cache hit rate</span>
          <span className="metric-value">{formatPercent(metrics?.cache_hit_rate)}</span>
        </div>
        <div className="metric-card">
          <span className="metric-label">Error rate</span>
          <span className="metric-value">{formatPercent(metrics?.api_error_rate)}</span>
        </div>
        <div className="metric-card">
          <span className="metric-label">Budget denials</span>
          <span className="metric-value">{formatCount(metrics?.budget_denied_count)}</span>
        </div>
        <div className="metric-card">
          <span className="metric-label">Source</span>
          <span className="metric-value">{metrics?.source ?? "-"}</span>
        </div>
      </div>
    </aside>
  );
}
