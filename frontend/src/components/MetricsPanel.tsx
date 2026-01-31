import type { CanonicalResponse, StatusResponse } from "../api/types";

const formatTimestamp = (value?: string | null) => {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
};

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
};

export default function MetricsPanel({ status, lastResponse }: MetricsPanelProps) {
  const metadata = lastResponse?.metadata ?? {};
  const latency = toNumber((metadata as Record<string, unknown>).latency_ms);
  const cacheHit = (metadata as Record<string, unknown>).cache_hit === true;
  const guardrails = (metadata as Record<string, unknown>).guardrails as
    | { citation_missing_count?: number; redactions?: number; issues?: string[] }
    | undefined;

  return (
    <aside className="panel metrics">
      <div className="panel-header">
        <h2>Metrics</h2>
        <p className="muted">Live snapshot</p>
      </div>

      <div className="metric-grid">
        <div className="metric-card">
          <span className="metric-label">API status</span>
          <span className={`metric-value ${status?.status === "ok" ? "ok" : "warn"}`}>
            {status?.status ?? "unknown"}
          </span>
        </div>
        <div className="metric-card">
          <span className="metric-label">Dependencies</span>
          <span className="metric-value">
            {status?.dependencies?.length ? status.dependencies.join(", ") : "-"}
          </span>
        </div>
        <div className="metric-card">
          <span className="metric-label">Last response</span>
          <span className="metric-value">{formatTimestamp(lastResponse?.timestamp)}</span>
        </div>
        <div className="metric-card">
          <span className="metric-label">Latency (ms)</span>
          <span className="metric-value">{latency ?? "-"}</span>
        </div>
        <div className="metric-card">
          <span className="metric-label">Cache hit</span>
          <span className={`metric-value ${cacheHit ? "ok" : "muted"}`}>
            {cacheHit ? "true" : "false"}
          </span>
        </div>
        <div className="metric-card">
          <span className="metric-label">Guardrails</span>
          <span className="metric-value">
            {guardrails
              ? `missing citations: ${guardrails.citation_missing_count ?? 0}, redactions: ${guardrails.redactions ?? 0}`
              : "-"}
          </span>
        </div>
      </div>
    </aside>
  );
}
