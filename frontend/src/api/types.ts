export type EvidenceMapEntry = {
  source_type: string;
  source_id: string;
  line_start: number;
  line_end: number;
  excerpt_hash: string;
  excerpt?: string | null;
};

export type Hypothesis = {
  id: string;
  rank: number;
  confidence: number;
  explanation: string;
  citations: EvidenceMapEntry[];
};

export type ToolCall = {
  id: string;
  title: string;
  command: string;
  expected_output?: string | null;
};

export type ToolResult = {
  id: string;
  output: string;
};

export type ChatHypothesis = {
  id: string;
  confidence: number;
  explanation: string;
};

export type ChatResponse = {
  request_id: string;
  timestamp: string;
  assistant_message: string;
  completion_state: string;
  next_question?: string | null;
  tool_calls?: ToolCall[];
  hypotheses?: ChatHypothesis[];
  fix_steps?: string[];
  metadata: Record<string, unknown>;
  conversation_id?: string | null;
};

export type StatusResponse = {
  status: string;
  dependencies: string[];
  timestamp: string;
};

export type MetricsSummary = {
  timestamp: string;
  api_latency_p50_ms: number | null;
  api_latency_p95_ms: number | null;
  llm_latency_p50_ms?: number | null;
  llm_latency_p95_ms?: number | null;
  source: "cloudwatch" | "memory";
  sample_count?: number;
  cache_hit_rate?: number | null;
  api_error_rate?: number | null;
  budget_denied_count?: number | null;
};

export type BudgetStatus = {
  usage_window: string;
  retry_after: string;
  token_limit: number;
  tokens_used: number;
  remaining_budget: number;
};

export type TriageRequest = {
  request_id?: string;
  conversation_id?: string;
  source?: string;
  raw_text: string;
  redaction_hits?: number;
  timestamp?: string;
};

export type ExplainRequest = {
  request_id?: string;
  conversation_id?: string;
  response: string;
  redaction_hits?: number;
  incident_frame?: Record<string, unknown>;
  tool_results?: ToolResult[];
};
