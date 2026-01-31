import { useEffect, useRef, useState, type FormEvent } from "react";
import { api, ApiError } from "./api/client";
import type {
  BudgetStatus,
  ChatResponse,
  ChatHypothesis,
  MetricsSummary,
  ToolCall
} from "./api/types";
import MetricsPanel from "./components/MetricsPanel";
import OpsStatsPanel from "./components/OpsStatsPanel";

type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: string;
  completion_state?: string;
  next_question?: string | null;
  tool_calls?: ToolCall[];
  hypotheses?: ChatHypothesis[];
  fix_steps?: string[];
  cache_hit?: boolean;
};

type MessageSegment =
  | { type: "text"; value: string }
  | { type: "code"; value: string };

const parseSlackStyleMessage = (content: string): MessageSegment[] => {
  const segments: MessageSegment[] = [];
  const fenceRegex = /```[\s\S]*?```/g;
  let lastIndex = 0;
  let match: RegExpExecArray | null;

  while ((match = fenceRegex.exec(content)) !== null) {
    if (match.index > lastIndex) {
      const textChunk = content.slice(lastIndex, match.index);
      if (textChunk) segments.push({ type: "text", value: textChunk });
    }
    const fenced = match[0];
    const stripped = fenced.replace(/^```[\w-]*\n?/, "").replace(/```$/, "");
    segments.push({ type: "code", value: stripped.trimEnd() });
    lastIndex = match.index + fenced.length;
  }

  if (lastIndex < content.length) {
    segments.push({ type: "text", value: content.slice(lastIndex) });
  }

  return segments;
};

const renderInlineCode = (text: string) => {
  const parts = text.split(/`([^`]+)`/g);
  return parts.map((part, index) =>
    index % 2 === 1 ? (
      <code key={`code-${index}`} className="inline-code">
        {part}
      </code>
    ) : (
      <span key={`text-${index}`}>{part}</span>
    )
  );
};

const fallbackMessage = (response: ChatResponse) =>
  response.assistant_message?.trim()
    ? response.assistant_message
    : "I’ve captured the response and can provide more detail if needed.";

const normalizeMessage = (value: string) =>
  value
    .replace(/\s+/g, " ")
    .trim()
    .toLowerCase();

const redactSensitive = (input: string) => {
  let text = input;
  let hits = 0;

  const replaceAll = (pattern: RegExp, replacement: string) => {
    const result = text.replace(pattern, (match, ...args) => {
      hits += 1;
      if (typeof replacement === "string") return replacement;
      return replacement(match, ...args);
    });
    text = result;
  };

  const luhnCheck = (value: string) => {
    let sum = 0;
    let shouldDouble = false;
    for (let i = value.length - 1; i >= 0; i -= 1) {
      const digit = Number(value[i]);
      if (Number.isNaN(digit)) return false;
      let add = digit;
      if (shouldDouble) {
        add = digit * 2;
        if (add > 9) add -= 9;
      }
      sum += add;
      shouldDouble = !shouldDouble;
    }
    return sum % 10 === 0;
  };

  replaceAll(/-----BEGIN [\s\S]+? PRIVATE KEY-----[\s\S]+?-----END [\s\S]+? PRIVATE KEY-----/g, "[PRIVATE_KEY]");
  replaceAll(/\bAKIA[0-9A-Z]{16}\b/g, "[AWS_ACCESS_KEY_ID]");
  replaceAll(/\bASIA[0-9A-Z]{16}\b/g, "[AWS_ACCESS_KEY_ID]");
  replaceAll(/\barn:aws[a-z-]*:[^\s]+/gi, "[AWS_ARN]");
  replaceAll(/\b\d{12}\b/g, "[ACCOUNT_ID]");
  replaceAll(/\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b/g, "[JWT]");
  replaceAll(
    /\b(?:password|passwd|pwd|secret|token|api[_-]?key|apikey|auth|authorization)\b\s*[:=]\s*([^\s,;]+)/gi,
    (_match, value) => {
      if (!value) return "[SECRET]";
      return _match.replace(value, "[SECRET]");
    }
  );
  replaceAll(/\bAuthorization:\s*Bearer\s+[A-Za-z0-9._\-+/=]+\b/gi, "Authorization: Bearer [BEARER_TOKEN]");
  replaceAll(/\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b/gi, "[EMAIL]");
  replaceAll(
    /\b(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)\b/g,
    "[IP_ADDRESS]"
  );
  replaceAll(/\b([0-9a-f]{0,4}:){2,7}[0-9a-f]{0,4}\b/gi, "[IPV6_ADDRESS]");
  replaceAll(/\b(user(name)?|login|uid|user_id|account|owner)\b\s*[:=]\s*([^\s,;]+)/gi, (match) => {
    const parts = match.split(/[:=]/);
    if (parts.length < 2) return match;
    return `${parts[0].trim()}=${"[USERNAME]"}`;
  });
  replaceAll(/"(user(name)?|login|uid|user_id|account|owner)"\s*:\s*"([^"]+)"/gi, (match, key) => {
    return `"${key}":"[USERNAME]"`;
  });

  text = text.replace(/\b(?:\d[ -]*?){13,19}\b/g, (match) => {
    const digits = match.replace(/[^0-9]/g, "");
    if (digits.length < 13 || digits.length > 19) return match;
    if (luhnCheck(digits)) {
      hits += 1;
      return "[CREDIT_CARD]";
    }
    return match;
  });

  return { text, hits };
};

export default function App() {
  const [rawText, setRawText] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [response, setResponse] = useState<ChatResponse | null>(null);
  const [metricsSummary, setMetricsSummary] = useState<MetricsSummary | null>(null);
  const [budgetStatus, setBudgetStatus] = useState<BudgetStatus | null>(null);
  const [requestId, setRequestId] = useState<string | null>(null);
  const [lastLatencyMs, setLastLatencyMs] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [budgetExceeded, setBudgetExceeded] = useState(false);
  const scrollAnchorRef = useRef<HTMLDivElement | null>(null);
  const inputRef = useRef<HTMLTextAreaElement | null>(null);


  useEffect(() => {
    let isMounted = true;
    const fetchSummary = () => {
      api
        .metricsSummary()
        .then(({ data }) => {
          if (isMounted) setMetricsSummary(data);
        })
        .catch(() => {
          if (isMounted) setMetricsSummary(null);
        });
      api
        .budgetStatus()
        .then(({ data }) => {
          if (isMounted) setBudgetStatus(data);
        })
        .catch(() => {
          if (isMounted) setBudgetStatus(null);
        });
    };
    fetchSummary();
    const interval = window.setInterval(fetchSummary, 15000);
    return () => {
      isMounted = false;
      window.clearInterval(interval);
    };
  }, []);

  useEffect(() => {
    if (!scrollAnchorRef.current) return;
    scrollAnchorRef.current.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  useEffect(() => {
    if (!loading) {
      inputRef.current?.focus();
    }
  }, [loading]);

  const submitMessage = async () => {
    setError(null);
    if (!rawText.trim()) {
      setError("Type your log or response to continue.");
      return;
    }

    const messageText = rawText.trim();
    const redactedResult = redactSensitive(messageText);
    const redactedMessage = redactedResult.text;
    const redactionHits = redactedResult.hits;
    const lastAssistant = [...messages].reverse().find((msg) => msg.role === "assistant");
    const pendingToolCall = lastAssistant?.tool_calls?.length ? lastAssistant.tool_calls[0] : null;
    const userMessage: ChatMessage = {
      id: `${Date.now()}-${Math.random().toString(16).slice(2)}`,
      role: "user",
      content: redactedMessage,
      timestamp: new Date().toISOString()
    };
    setMessages((prev) => [...prev, userMessage]);
    setRawText("");
    setLoading(true);

    const startedAt = performance.now();
    try {
      const isFirstMessage = !conversationId;
      const { data, requestId: rid } = isFirstMessage
        ? await api.triage({
            raw_text: redactedMessage,
            redaction_hits: redactionHits,
            source: "user",
            conversation_id: conversationId ?? undefined,
            timestamp: new Date().toISOString()
          })
        : await api.explain({
            response: pendingToolCall ? "Tool output provided." : redactedMessage,
            redaction_hits: redactionHits,
            conversation_id: conversationId ?? undefined,
            request_id: undefined,
            tool_results: pendingToolCall
              ? [
                  {
                    id: pendingToolCall.id,
                    output: redactedMessage
                  }
                ]
              : undefined
          });

      const assistantMessage = data.assistant_message?.trim() || fallbackMessage(data);
      const nextQuestion = data.next_question?.trim() ?? null;
      const lastAssistantContent = lastAssistant?.content ?? "";
      const isDuplicate =
        lastAssistantContent &&
        normalizeMessage(lastAssistantContent) === normalizeMessage(assistantMessage);
      const suppressContent = isDuplicate && Boolean(nextQuestion);

      const reply: ChatMessage = {
        id: `${Date.now()}-${Math.random().toString(16).slice(2)}`,
        role: "assistant",
        content: suppressContent ? "" : assistantMessage,
        timestamp: new Date().toISOString(),
        completion_state: data.completion_state,
        next_question: nextQuestion,
        tool_calls: data.tool_calls ?? [],
        hypotheses: data.hypotheses ?? [],
        fix_steps: data.fix_steps ?? [],
        cache_hit: Boolean((data.metadata as { cache_hit?: boolean } | undefined)?.cache_hit)
      };

      setResponse(data);
      setConversationId(data.conversation_id ?? null);
      setRequestId(rid);
      setBudgetExceeded(false);
      setMessages((prev) => [...prev, reply]);
      setLastLatencyMs(Math.round(performance.now() - startedAt));
    } catch (err) {
      let message = "Request failed.";
      let showInlineError = false;
      if (err instanceof ApiError) {
        message = formatBudgetError(err.detail) ?? err.message;
        showInlineError = false;
      } else if (err instanceof Error) {
        message = err.message;
        showInlineError = false;
      }
      const isBudgetError = message.startsWith("Token budget exceeded");
      setBudgetExceeded(isBudgetError);
      setError(showInlineError ? message : null);
      setMessages((prev) => [
        ...prev,
        {
          id: `${Date.now()}-${Math.random().toString(16).slice(2)}`,
          role: "assistant",
          content: isBudgetError
            ? message
            : `I couldn't complete that request. ${message}`,
          timestamp: new Date().toISOString()
        }
      ]);
    } finally {
      setLoading(false);
    }
  };
  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    await submitMessage();
  };

  const stripLeadingNumber = (value: string) =>
    value.replace(/^\s*\d+[\.\)]\s+/, "");

  return (
    <div className="app-shell">
      <header className="app-header">
        <div>
          <h1>Troubleshoot Stack</h1>
          <p className="muted">Interactive log triage with evidence-backed responses.</p>
        </div>
        <div className="header-meta">
          <span className="tag">Conversation</span>
          <span className="mono">{conversationId ?? "new"}</span>
        </div>
      </header>

      <main className="app-grid">
        <section
          className="panel primary chat-panel"
          onClick={() => {
            inputRef.current?.focus();
          }}
        >
          <div
            className="chat-window"
            onClick={() => {
              inputRef.current?.focus();
            }}
          >
            {messages.length ? (
              messages.map((message) => {
                const timestamp = new Date(message.timestamp).toLocaleTimeString();
                const hasContent = Boolean(message.content.trim());
                const hasToolCalls = Boolean(message.tool_calls?.length);
                const hasHypotheses = Boolean(message.hypotheses?.length);
                const hasFixSteps = Boolean(message.fix_steps?.length);
                const showPrimaryPanel =
                  message.role === "user" ||
                  hasContent ||
                  hasToolCalls ||
                  (message.completion_state === "final" && (hasHypotheses || hasFixSteps));

                return (
                  <div key={message.id} className="message-group">
                    {showPrimaryPanel && (
                      <div className={`message ${message.role}`}>
                        <div className="message-meta">
                          <span className="tag">
                            {message.role === "user" ? "You" : "Assistant"}
                          </span>
                          <span className="mono">{timestamp}</span>
                          {message.role === "assistant" && message.cache_hit ? (
                            <span className="tag cached">Cached</span>
                          ) : null}
                        </div>
                        {hasContent && (
                          <div className="message-content">
                            {parseSlackStyleMessage(message.content).map((segment, index) =>
                              segment.type === "code" ? (
                                <pre key={`${message.id}-code-${index}`} className="code-block">
                                  <code>{segment.value}</code>
                                </pre>
                              ) : (
                                <p key={`${message.id}-text-${index}`}>
                                  {renderInlineCode(segment.value)}
                                </p>
                              )
                            )}
                          </div>
                        )}
                        {hasToolCalls ? (
                          <div className="message-meta-block">
                            <span className="tag">Tool call</span>
                            {message.tool_calls?.slice(0, 1).map((call) => (
                              <div key={call.id} className="tool-call">
                                <div className="tool-call-header">
                                  <span>{call.title}</span>
                                  <button
                                    type="button"
                                    className="ghost"
                                    onClick={() => navigator.clipboard.writeText(call.command)}
                                  >
                                    Copy
                                  </button>
                                </div>
                                <pre className="code-block">
                                  <code>{call.command}</code>
                                </pre>
                                {call.expected_output ? (
                                  <p className="muted">Expected: {call.expected_output}</p>
                                ) : null}
                              </div>
                            ))}
                          </div>
                        ) : null}
                        {message.completion_state === "final" && hasHypotheses ? (
                          <div className="message-meta-block">
                            <span className="tag">Most likely explanations</span>
                            <ul>
                              {message.hypotheses?.map((hyp) => (
                                <li key={hyp.id}>
                                  {hyp.explanation} ({Math.round(hyp.confidence * 100)}%)
                                </li>
                              ))}
                            </ul>
                          </div>
                        ) : null}
                        {message.completion_state === "final" && hasFixSteps ? (
                          <div className="message-meta-block">
                            <span className="tag">Fix steps</span>
                            <ol>
                              {message.fix_steps?.map((step, index) => (
                                <li key={`${message.id}-fix-${index}`}>{stripLeadingNumber(step)}</li>
                              ))}
                            </ol>
                          </div>
                        ) : null}
                      </div>
                    )}
                    {message.role === "assistant" && message.next_question ? (
                      <div className="message assistant next-question">
                        <div className="message-meta">
                          <span className="tag">Next question</span>
                          <span className="mono">{timestamp}</span>
                        </div>
                        <div className="message-content">
                          <p>{message.next_question}</p>
                        </div>
                      </div>
                    ) : null}
                  </div>
                );
              })
            ) : null}
            {loading && (
              <div className="message assistant typing">
                <div className="message-meta">
                  <span className="tag">Assistant</span>
                  <span className="mono">typing…</span>
                </div>
                <div className="message-content">Analyzing and building a response.</div>
              </div>
            )}
            <div ref={scrollAnchorRef} />
          </div>

          {error && <div className="alert">{error}</div>}

          <form className="chat-input" onSubmit={handleSubmit}>
            <textarea
              id="rawText"
              value={rawText}
              onChange={(event) => setRawText(event.target.value)}
              placeholder="Share your response or question..."
              rows={4}
              disabled={loading}
              ref={inputRef}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.altKey && !event.shiftKey) {
                  event.preventDefault();
                  void submitMessage();
                }
              }}
            />
            <div className="actions">
              <button className="primary" type="submit" disabled={loading || !rawText.trim()}>
                {loading ? "Waiting for response..." : "Send"}
              </button>
              <button
                className="ghost"
                type="button"
                onClick={() => {
                  setRawText("");
                  setResponse(null);
                  setMessages([]);
                  setConversationId(null);
                  setRequestId(null);
                  setError(null);
                }}
                disabled={loading}
              >
                New conversation
              </button>
            </div>
          </form>
        </section>

        <section className="panel secondary">
          <MetricsPanel
            lastResponse={response}
            lastLatencyMs={lastLatencyMs}
            requestId={requestId}
            tokenUnavailable={budgetExceeded}
            budgetStatus={budgetStatus}
          />
          <OpsStatsPanel metrics={metricsSummary} />
        </section>
      </main>
    </div>
  );
}
const formatBudgetError = (detail: unknown) => {
  if (!detail || typeof detail !== "object") return null;
  const root = detail as Record<string, unknown>;
  const payload =
    (root.detail as {
      error?: string;
      message?: string;
      remaining_budget?: number;
      retry_after?: string;
    }) ??
    (root as {
      error?: string;
      message?: string;
      remaining_budget?: number;
      retry_after?: string;
    });
  if (payload.error !== "budget_exceeded") return null;
  if (payload.retry_after) {
    return `Token budget exceeded, retry after ${payload.retry_after}`;
  }
  return "Token budget exceeded, please try again later";
};
