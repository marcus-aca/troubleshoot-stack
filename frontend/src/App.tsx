import { useEffect, useMemo, useState } from "react";
import { api } from "./api/client";
import type { CanonicalResponse, EvidenceMapEntry, StatusResponse } from "./api/types";
import MetricsPanel from "./components/MetricsPanel";

const buildLineIndex = (text: string) => text.split(/\r?\n/);

const buildHighlightMap = (citations: EvidenceMapEntry[]) => {
  const ranges = citations.map((citation) => ({
    start: citation.line_start,
    end: citation.line_end
  }));
  const highlighted = new Set<number>();
  ranges.forEach((range) => {
    for (let i = range.start; i <= range.end; i += 1) {
      highlighted.add(i);
    }
  });
  return highlighted;
};

export default function App() {
  const [rawText, setRawText] = useState("");
  const [question, setQuestion] = useState("");
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [response, setResponse] = useState<CanonicalResponse | null>(null);
  const [status, setStatus] = useState<StatusResponse | null>(null);
  const [requestId, setRequestId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    api
      .status()
      .then(({ data }) => setStatus(data))
      .catch(() => setStatus(null));
  }, []);

  const lineList = useMemo(() => buildLineIndex(rawText), [rawText]);
  const citationSet = useMemo(() => {
    if (!response?.hypotheses?.length) return new Set<number>();
    const allCitations = response.hypotheses.flatMap((hyp) => hyp.citations ?? []);
    return buildHighlightMap(allCitations);
  }, [response]);

  const handleTriage = async () => {
    setError(null);
    if (!rawText.trim()) {
      setError("Paste an error log or trace stack to continue.");
      return;
    }

    setLoading(true);
    try {
      const { data, requestId: rid } = await api.triage({
        raw_text: rawText,
        source: "user",
        conversation_id: conversationId ?? undefined,
        timestamp: new Date().toISOString()
      });
      setResponse(data);
      setConversationId(data.conversation_id ?? null);
      setRequestId(rid);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Request failed.");
    } finally {
      setLoading(false);
    }
  };

  const handleExplain = async () => {
    setError(null);
    if (!question.trim()) {
      setError("Add a follow-up question to continue.");
      return;
    }

    setLoading(true);
    try {
      const { data, requestId: rid } = await api.explain({
        question,
        conversation_id: conversationId ?? undefined,
        request_id: undefined
      });
      setResponse(data);
      setConversationId(data.conversation_id ?? null);
      setRequestId(rid);
      setQuestion("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Request failed.");
    } finally {
      setLoading(false);
    }
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
        <section className="panel primary">
          <div className="panel-header">
            <h2>Live Triage</h2>
            <p className="muted">Paste logs, run triage, then follow up with explain.</p>
          </div>

          <div className="input-block">
            <label htmlFor="rawText">Error log / trace stack</label>
            <textarea
              id="rawText"
              value={rawText}
              onChange={(event) => setRawText(event.target.value)}
              placeholder="Paste logs here..."
              rows={10}
            />
          </div>

          <div className="actions">
            <button className="primary" onClick={handleTriage} disabled={loading}>
              {loading ? "Running triage..." : "Run triage"}
            </button>
            <button
              className="ghost"
              type="button"
              onClick={() => {
                setRawText("");
                setResponse(null);
                setQuestion("");
                setError(null);
              }}
            >
              Clear
            </button>
          </div>

          <div className="input-block">
            <label htmlFor="question">Follow-up question</label>
            <div className="inline-input">
              <input
                id="question"
                value={question}
                onChange={(event) => setQuestion(event.target.value)}
                placeholder="Why is this happening?"
              />
              <button className="secondary" onClick={handleExplain} disabled={loading}>
                Explain
              </button>
            </div>
          </div>

          {error && <div className="alert">{error}</div>}

          <div className="results">
            <div className="result-meta">
              <span className="tag">Request ID</span>
              <span className="mono">{requestId ?? "-"}</span>
              <span className="tag">Timestamp</span>
              <span className="mono">{response?.timestamp ?? "-"}</span>
            </div>

            <div className="result-section">
              <h3>Hypotheses</h3>
              {response?.hypotheses?.length ? (
                response.hypotheses.map((hyp) => (
                  <div key={hyp.id} className="card">
                    <div className="card-header">
                      <span className="rank">#{hyp.rank}</span>
                      <span className="confidence">{Math.round(hyp.confidence * 100)}%</span>
                      <span className="mono">{hyp.id}</span>
                    </div>
                    <p>{hyp.explanation}</p>
                    {hyp.citations?.length ? (
                      <div className="citations">
                        {hyp.citations.map((citation, index) => (
                          <span key={`${hyp.id}-${index}`} className="chip">
                            lines {citation.line_start}-{citation.line_end}
                          </span>
                        ))}
                      </div>
                    ) : null}
                  </div>
                ))
              ) : (
                <p className="muted">Run triage to see hypotheses.</p>
              )}
            </div>

            <div className="result-section">
              <h3>Runbook steps</h3>
              {response?.runbook_steps?.length ? (
                <ol>
                  {response.runbook_steps.map((step) => (
                    <li key={`${step.step_number}-${step.description}`}>
                      <strong>Step {step.step_number}:</strong> {step.description}
                      {step.command_or_console_path ? (
                        <div className="code">{step.command_or_console_path}</div>
                      ) : null}
                    </li>
                  ))}
                </ol>
              ) : (
                <p className="muted">Run triage to see runbook guidance.</p>
              )}
            </div>

            <div className="result-section">
              <h3>Proposed fix</h3>
              <pre className="code">
                {response?.proposed_fix ?? "-"}
              </pre>
            </div>

            <div className="result-section">
              <h3>Risk notes</h3>
              {response?.risk_notes?.length ? (
                <ul>
                  {response.risk_notes.map((note, index) => (
                    <li key={`${note}-${index}`}>{note}</li>
                  ))}
                </ul>
              ) : (
                <p className="muted">-</p>
              )}
            </div>

            <div className="result-section">
              <h3>Next checks</h3>
              {response?.next_checks?.length ? (
                <ul>
                  {response.next_checks.map((note, index) => (
                    <li key={`${note}-${index}`}>{note}</li>
                  ))}
                </ul>
              ) : (
                <p className="muted">-</p>
              )}
            </div>
          </div>
        </section>

        <section className="panel secondary">
          <MetricsPanel status={status} lastResponse={response} />

          <div className="panel log-panel">
            <div className="panel-header">
              <h2>Evidence map</h2>
              <p className="muted">Highlighted log lines referenced in citations.</p>
            </div>
            <div className="log-view">
              {lineList.length ? (
                lineList.map((line, index) => {
                  const lineNumber = index + 1;
                  const highlight = citationSet.has(lineNumber);
                  return (
                    <div key={`${lineNumber}-${line}`} className={highlight ? "log-line highlight" : "log-line"}>
                      <span className="line-number">{lineNumber.toString().padStart(3, "0")}</span>
                      <span className="line-text">{line || " "}</span>
                    </div>
                  );
                })
              ) : (
                <p className="muted">Paste logs to populate evidence references.</p>
              )}
            </div>
          </div>
        </section>
      </main>
    </div>
  );
}
