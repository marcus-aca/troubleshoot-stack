import type { CanonicalResponse, StatusResponse } from "../api/types";

const toNumber = (value: unknown) => {
  if (typeof value === "number") return value;
  if (typeof value === "string" && value.trim() !== "") {
    const parsed = Number(value);
    return Number.isNaN(parsed) ? null : parsed;
  }
  return null;
};

export type MetricsPanelProps = {
  status: StatusResponse | null;
  lastResponse: CanonicalResponse | null;
  lastLatencyMs: number | null;
  requestId: string | null;
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
  const usage = metadata.usage as { total_tokens?: number } | undefined;
  return usage?.total_tokens !== undefined ? toNumber(usage.total_tokens) : null;
};

const getCacheHitRate = (metadata: Record<string, unknown>) => {
  const raw = toNumber(metadata.cache_hit_rate);
  if (raw === null) return null;
  if (raw <= 1) return Math.round(raw * 1000) / 10;
  return Math.round(raw * 10) / 10;
};

export default function MetricsPanel({
  status,
  lastResponse,
  lastLatencyMs,
  requestId
}: MetricsPanelProps) {
  const metadata = lastResponse?.metadata ?? {};
  const latency = toNumber(metadata.latency_ms) ?? lastLatencyMs;
  const cacheHitRate = getCacheHitRate(metadata);
  const tokenUsage = getTokenUsage(metadata);

  return (
    <aside className="panel metrics">
      <div className="panel-header">
        <h2>Live stats</h2>
      </div>

      <div className="metric-grid">
        <div className="metric-card">
          <span className="metric-label">API status</span>
          <span className={`metric-value ${status?.status === "ok" ? "ok" : "warn"}`}>
            {status?.status ?? "unknown"}
          </span>
        </div>
        <div className="metric-card">
          <span className="metric-label">Cache hit rate</span>
          <span className="metric-value">{formatNumber(cacheHitRate, "%")}</span>
        </div>
        <div className="metric-card">
          <span className="metric-label">Total tokens</span>
          <span className="metric-value">{formatNumber(tokenUsage)}</span>
        </div>
        <div className="metric-card">
          <span className="metric-label">Latency (ms)</span>
          <span className="metric-value">{formatNumber(latency)}</span>
        </div>
        <div className="metric-card">
          <span className="metric-label">Request ID</span>
          <span className="metric-value mono">{requestId ?? "-"}</span>
        </div>
      </div>
    </aside>
  );
}
