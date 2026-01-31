import { useEffect, useRef, useState, type FormEvent } from "react";
import { api } from "./api/client";
import type { CanonicalResponse, StatusResponse } from "./api/types";
import MetricsPanel from "./components/MetricsPanel";

type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: string;
};

const buildEvidenceLineSummary = (citations: CanonicalResponse["hypotheses"][number]["citations"]) => {
  const lineRanges = (citations ?? []).map((citation) => `${citation.line_start}-${citation.line_end}`);
  if (!lineRanges.length) return "";
  const unique = Array.from(new Set(lineRanges));
  return ` (evidence lines ${unique.slice(0, 4).join(", ")}${unique.length > 4 ? ", ..." : ""})`;
};

const buildChatResponse = (response: CanonicalResponse) => {
  const lines: string[] = [];
  lines.push("Here’s a concise triage summary based on what you shared.");

  if (response.hypotheses?.length) {
    lines.push("");
    lines.push("Top hypotheses:");
    response.hypotheses.slice(0, 3).forEach((hypothesis) => {
      const confidence = Math.round(hypothesis.confidence * 100);
      const evidence = hypothesis.citations?.length ? buildEvidenceLineSummary(hypothesis.citations) : "";
      lines.push(`- ${hypothesis.explanation} — ${confidence}% confidence${evidence}.`);
    });
  }

  if (response.runbook_steps?.length) {
    lines.push("");
    lines.push("Recommended runbook steps:");
    response.runbook_steps.forEach((step) => {
      const command = step.command_or_console_path
        ? `\n  Command: ${step.command_or_console_path}`
        : "";
      lines.push(`${step.step_number}. ${step.description}${command}`);
    });
  }

  if (response.proposed_fix) {
    lines.push("");
    lines.push("Proposed fix:");
    lines.push(response.proposed_fix);
  }

  if (response.risk_notes?.length) {
    lines.push("");
    lines.push("Risk notes:");
    response.risk_notes.forEach((note) => lines.push(`- ${note}`));
  }

  if (response.rollback?.length) {
    lines.push("");
    lines.push("Rollback guidance:");
    response.rollback.forEach((note) => lines.push(`- ${note}`));
  }

  if (response.next_checks?.length) {
    lines.push("");
    lines.push("Next checks:");
    response.next_checks.forEach((note) => lines.push(`- ${note}`));
  }

  return lines.join("\n");
};

export default function App() {
  const [rawText, setRawText] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [response, setResponse] = useState<CanonicalResponse | null>(null);
  const [status, setStatus] = useState<StatusResponse | null>(null);
  const [requestId, setRequestId] = useState<string | null>(null);
  const [lastLatencyMs, setLastLatencyMs] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const scrollAnchorRef = useRef<HTMLDivElement | null>(null);
  const inputRef = useRef<HTMLTextAreaElement | null>(null);

  useEffect(() => {
    api
      .status()
      .then(({ data }) => setStatus(data))
      .catch(() => setStatus(null));
  }, []);

  useEffect(() => {
    if (!scrollAnchorRef.current) return;
    scrollAnchorRef.current.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  const submitMessage = async () => {
    setError(null);
    if (!rawText.trim()) {
      setError("Type your log or question to continue.");
      return;
    }

    const userMessage: ChatMessage = {
      id: `${Date.now()}-${Math.random().toString(16).slice(2)}`,
      role: "user",
      content: rawText.trim(),
      timestamp: new Date().toISOString()
    };
    setMessages((prev) => [...prev, userMessage]);
    setLoading(true);

    const startedAt = performance.now();
    try {
      const isFirstMessage = !conversationId;
      const { data, requestId: rid } = isFirstMessage
        ? await api.triage({
            raw_text: rawText,
            source: "user",
            conversation_id: conversationId ?? undefined,
            timestamp: new Date().toISOString()
          })
        : await api.explain({
            question: rawText,
            conversation_id: conversationId ?? undefined,
            request_id: undefined
          });

      const reply: ChatMessage = {
        id: `${Date.now()}-${Math.random().toString(16).slice(2)}`,
        role: "assistant",
        content: buildChatResponse(data),
        timestamp: new Date().toISOString()
      };

      setResponse(data);
      setConversationId(data.conversation_id ?? null);
      setRequestId(rid);
      setMessages((prev) => [...prev, reply]);
      setRawText("");
      setLastLatencyMs(Math.round(performance.now() - startedAt));
    } catch (err) {
      const message = err instanceof Error ? err.message : "Request failed.";
      setError(message);
      setMessages((prev) => [
        ...prev,
        {
          id: `${Date.now()}-${Math.random().toString(16).slice(2)}`,
          role: "assistant",
          content: `I couldn't complete that request. ${message}`,
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
              messages.map((message) => (
                <div key={message.id} className={`message ${message.role}`}>
                  <div className="message-meta">
                    <span className="tag">{message.role === "user" ? "You" : "Assistant"}</span>
                    <span className="mono">{new Date(message.timestamp).toLocaleTimeString()}</span>
                  </div>
                  <div className="message-content">{message.content}</div>
                </div>
              ))
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
              placeholder="Ask your question..."
              rows={4}
              disabled={loading}
              ref={inputRef}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.altKey) {
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
            status={status}
            lastResponse={response}
            lastLatencyMs={lastLatencyMs}
            requestId={requestId}
          />
        </section>
      </main>
    </div>
  );
}
