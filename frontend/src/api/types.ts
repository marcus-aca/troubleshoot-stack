export type EvidenceMapEntry = {
  source_type: string;
  source_id: string;
  line_start: number;
  line_end: number;
  excerpt_hash: string;
};

export type Hypothesis = {
  id: string;
  rank: number;
  confidence: number;
  explanation: string;
  citations: EvidenceMapEntry[];
};

export type RunbookStep = {
  step_number: number;
  description: string;
  command_or_console_path?: string;
  estimated_time_mins?: number;
};

export type CanonicalResponse = {
  request_id: string;
  timestamp: string;
  hypotheses: Hypothesis[];
  runbook_steps: RunbookStep[];
  proposed_fix?: string | null;
  risk_notes: string[];
  rollback: string[];
  next_checks: string[];
  metadata: Record<string, unknown>;
  conversation_id?: string | null;
};

export type StatusResponse = {
  status: string;
  dependencies: string[];
  timestamp: string;
};

export type TriageRequest = {
  request_id?: string;
  conversation_id?: string;
  source?: string;
  raw_text: string;
  timestamp?: string;
};

export type ExplainRequest = {
  request_id?: string;
  conversation_id?: string;
  question: string;
  incident_frame?: Record<string, unknown>;
};
