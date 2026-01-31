import type { BudgetStatus, ChatResponse, ExplainRequest, MetricsSummary, StatusResponse, TriageRequest } from "./types";

export class ApiError extends Error {
  status: number;
  detail: unknown;

  constructor(message: string, status: number, detail: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";
const API_KEY = import.meta.env.VITE_API_KEY ?? "";

const buildUrl = (path: string) => {
  if (!API_BASE_URL) {
    return path;
  }
  return `${API_BASE_URL.replace(/\/$/, "")}${path}`;
};

const uuidv4 = () => {
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (char) => {
    const rand = (Math.random() * 16) | 0;
    const value = char === "x" ? rand : (rand & 0x3) | 0x8;
    return value.toString(16);
  });
};

const request = async <T>(path: string, method: string, body?: unknown) => {
  const requestId = uuidv4();
  const response = await fetch(buildUrl(path), {
    method,
    headers: {
      "Content-Type": "application/json",
      "x-request-id": requestId,
      "x-api-key": API_KEY
    },
    body: body ? JSON.stringify(body) : undefined
  });

  const responseRequestId = response.headers.get("X-Request-Id") ?? requestId;
  const contentType = response.headers.get("content-type") ?? "";
  let data: unknown = null;
  if (contentType.includes("application/json")) {
    data = await response.json();
  } else {
    const text = await response.text();
    data = text ? text : null;
  }

  if (!response.ok) {
    if (typeof data === "string" && data.trim()) {
      throw new ApiError(data.trim(), response.status, data);
    }
    const message = typeof (data as { detail?: string } | null)?.detail === "string"
      ? (data as { detail: string }).detail
      : `Request failed (${response.status}).`;
    throw new ApiError(message, response.status, data);
  }

  return { data: data as T, requestId: responseRequestId };
};

export const api = {
  triage: (payload: TriageRequest) => request<ChatResponse>("/triage", "POST", payload),
  explain: (payload: ExplainRequest) => request<ChatResponse>("/explain", "POST", payload),
  status: () => request<StatusResponse>("/status", "GET"),
  metricsSummary: () => request<MetricsSummary>("/metrics/summary", "GET"),
  budgetStatus: () => request<BudgetStatus>("/budget/status", "GET")
};
