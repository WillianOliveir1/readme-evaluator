import { useState, useEffect, useCallback, useRef } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

const MODEL = "gemini-2.5-flash";
const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

function authHeaders() {
  const key = process.env.NEXT_PUBLIC_API_KEY || "";
  return {
    "Content-Type": "application/json",
    ...(key && { "X-API-Key": key }),
  };
}

/* ============================================================
   Sidebar
   ============================================================ */

function Sidebar({ history, activeIdx, onSelect, theme, onToggleTheme }) {
  return (
    <aside className="sidebar">
      <div className="sidebar-brand">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z" />
          <polyline points="14 2 14 8 20 8" />
          <line x1="16" y1="13" x2="8" y2="13" />
          <line x1="16" y1="17" x2="8" y2="17" />
          <polyline points="10 9 9 9 8 9" />
        </svg>
        README Evaluator
      </div>

      <div className="sidebar-section-title">History</div>
      <ul className="sidebar-list">
        {history.length === 0 && (
          <li className="sidebar-item" style={{ fontStyle: "italic", opacity: 0.6 }}>No evaluations yet</li>
        )}
        {history.map((h, i) => (
          <li
            key={i}
            className={`sidebar-item ${i === activeIdx ? "active" : ""}`}
            onClick={() => onSelect(i)}
            title={h.url}
          >
            📄 {h.label}
          </li>
        ))}
      </ul>

      <div className="sidebar-footer">
        <button className="theme-toggle" onClick={onToggleTheme}>
          {theme === "dark" ? "☀️ Light" : "🌙 Dark"}
        </button>
      </div>
    </aside>
  );
}

/* ============================================================
   Progress Panel
   ============================================================ */

function ProgressPanel({ progress, percentage }) {
  return (
    <div className="card progress-card">
      <div className="card-header">Processing Pipeline</div>
      <div className="card-body">
        <div className="progress-label">
          <span>Progress</span>
          <span>{percentage}%</span>
        </div>
        <div className="progress-bar-wrapper">
          <div className="progress-bar-fill" style={{ width: `${percentage}%` }} />
        </div>
        <div className="stages">
          {progress.map((u, i) => (
            <div key={i} className={`stage-chip stage-${u.stage}`}>
              <div className="stage-name">{u.stage}</div>
              <div className="stage-msg">{u.message}</div>
              {u.elapsed_time != null && (
                <div className="stage-time">⏱ {u.elapsed_time.toFixed(2)}s</div>
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

/* ============================================================
   Report Card
   ============================================================ */

function ReportCard({ renderedText, result, onDownloadPdf }) {
  return (
    <div className="card report-card">
      <div className="card-header">
        <span>Evaluation Report</span>
        <div className="actions-bar">
          {onDownloadPdf && (
            <button className="btn btn-outline btn-sm" onClick={onDownloadPdf}>
              📥 Export PDF
            </button>
          )}
        </div>
      </div>
      <div className="card-body markdown-body">
        {renderedText ? (
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{renderedText}</ReactMarkdown>
        ) : (
          <p style={{ color: "var(--text-muted)" }}>
            No rendered report available. The evaluation JSON is shown below.
          </p>
        )}
      </div>
    </div>
  );
}

/* ============================================================
   Debug Details
   ============================================================ */

function DebugDetails({ result }) {
  return (
    <details className="card debug-details">
      <summary>Show Debug Details (JSON, Prompt, Timing)</summary>
      <div className="debug-content">
        <div className="debug-grid">
          <div className="debug-panel">
            <div className="debug-panel-header">Prompt Built</div>
            <pre>{result.prompt || "No prompt data available."}</pre>
          </div>
          <div className="debug-panel">
            <div className="debug-panel-header">
              Parsed JSON {result.validation_ok ? "✅" : "⚠️"}
            </div>
            <pre className="json-text">
              {result.parsed ? JSON.stringify(result.parsed, null, 2) : "No JSON parsed."}
            </pre>
          </div>
        </div>

        <div className="debug-panel" style={{ marginBottom: 20 }}>
          <div className="debug-panel-header">Raw Model Output</div>
          <pre style={{ maxHeight: 200 }}>
            {result.model_output || "No raw output available."}
          </pre>
        </div>

        {result.timing && Object.keys(result.timing).length > 0 && (
          <div className="timing-bar">
            {Object.entries(result.timing).map(([key, value]) => (
              <div key={key} className="timing-chip">
                <div className="label">{key}</div>
                <div className="value">
                  {typeof value === "number" ? `${value.toFixed(3)}s` : value}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </details>
  );
}

/* ============================================================
   Empty State
   ============================================================ */

function EmptyState() {
  return (
    <div className="empty-state">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="11" cy="11" r="8" />
        <line x1="21" y1="21" x2="16.65" y2="16.65" />
      </svg>
      <h2>Evaluate a README</h2>
      <p>Paste a GitHub repository URL above and click <strong>Evaluate</strong> to get a comprehensive quality report.</p>
    </div>
  );
}

/* ============================================================
   Main Page
   ============================================================ */

export default function Home() {
  /* --- State --- */
  const [url, setUrl] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [progress, setProgress] = useState([]);
  const [percentage, setPercentage] = useState(0);
  const [renderedText, setRenderedText] = useState(null);
  const [pdfLoading, setPdfLoading] = useState(false);

  // History (persisted in localStorage)
  const [history, setHistory] = useState([]);
  const [activeIdx, setActiveIdx] = useState(-1);

  // Theme
  const [theme, setTheme] = useState("light");

  // Refs
  const urlRef = useRef(null);

  /* --- Effects --- */

  // Load history & theme from localStorage on mount
  useEffect(() => {
    try {
      const saved = localStorage.getItem("re_history");
      if (saved) setHistory(JSON.parse(saved));
    } catch { /* ignore */ }

    const savedTheme = localStorage.getItem("re_theme") || "light";
    setTheme(savedTheme);
    document.documentElement.setAttribute("data-theme", savedTheme);
  }, []);

  // Persist history
  useEffect(() => {
    try {
      localStorage.setItem("re_history", JSON.stringify(history.slice(0, 30)));
    } catch { /* ignore */ }
  }, [history]);

  /* --- Handlers --- */

  const toggleTheme = useCallback(() => {
    setTheme((prev) => {
      const next = prev === "light" ? "dark" : "light";
      document.documentElement.setAttribute("data-theme", next);
      localStorage.setItem("re_theme", next);
      return next;
    });
  }, []);

  const selectHistory = useCallback((idx) => {
    const entry = history[idx];
    if (!entry) return;
    setActiveIdx(idx);
    setResult(entry.result);
    setRenderedText(entry.renderedText);
    setUrl(entry.url);
    setError(null);
    setProgress([]);
    setPercentage(100);
    setLoading(false);
  }, [history]);

  async function handleSubmit(e) {
    e.preventDefault();
    if (!url.trim()) return;

    setLoading(true);
    setResult(null);
    setError(null);
    setProgress([]);
    setPercentage(0);
    setRenderedText(null);

    try {
      const headers = authHeaders();

      // 1 — Download README
      const readmeRes = await fetch(`${API_URL}/readme`, {
        method: "POST",
        headers,
        body: JSON.stringify({ repo_url: url }),
      });
      if (!readmeRes.ok) {
        const err = await readmeRes.json().catch(() => ({}));
        throw new Error(err.detail || `HTTP ${readmeRes.status}`);
      }
      const readmeData = await readmeRes.json();

      // 2 — Extract JSON via SSE stream
      const response = await fetch(`${API_URL}/extract-json-stream`, {
        method: "POST",
        headers,
        body: JSON.stringify({ readme_text: readmeData.content, model: MODEL }),
      });
      if (!response.ok) {
        const err = await response.json().catch(() => ({}));
        throw new Error(err.detail || `HTTP ${response.status}`);
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let finalResult = null;
      let finalRendered = null;

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          try {
            const data = JSON.parse(line.slice(6));
            if (data.type === "progress") {
              setProgress((prev) => [...prev, data]);
              setPercentage(data.percentage || 0);
            } else if (data.type === "result") {
              finalResult = { ...data.result, filename: readmeData.filename };
              setResult(finalResult);
              setPercentage(100);
            } else if (data.type === "rendered") {
              const text = typeof data.rendered === "string"
                ? data.rendered
                : data.rendered?.text;
              finalRendered = text;
              setRenderedText(text);
            } else if (data.type === "error") {
              throw new Error(data.error);
            }
          } catch (parseErr) {
            if (parseErr.message.startsWith("HTTP") || parseErr.message.includes("error")) throw parseErr;
          }
        }
      }

      // Save to history
      if (finalResult) {
        const label = url.replace(/^https?:\/\/(www\.)?github\.com\//, "").replace(/\/$/, "") || url;
        const entry = { url, label, result: finalResult, renderedText: finalRendered, ts: Date.now() };
        setHistory((prev) => {
          const updated = [entry, ...prev.filter((h) => h.url !== url)].slice(0, 30);
          return updated;
        });
        setActiveIdx(0);
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  /* --- PDF Export --- */

  const handleDownloadPdf = useCallback(async () => {
    if (!renderedText && !result?.parsed) return;
    setPdfLoading(true);
    try {
      const headers = authHeaders();
      const res = await fetch(`${API_URL}/export-pdf`, {
        method: "POST",
        headers,
        body: JSON.stringify({
          markdown_text: renderedText || null,
          evaluation_json: result?.parsed || null,
          repo_name: url.replace(/^https?:\/\/(www\.)?github\.com\//, "").replace(/\/$/, ""),
        }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || `PDF export failed (${res.status})`);
      }
      const blob = await res.blob();
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = `readme-evaluation-${Date.now()}.pdf`;
      a.click();
      URL.revokeObjectURL(a.href);
    } catch (err) {
      alert(`PDF export error: ${err.message}`);
    } finally {
      setPdfLoading(false);
    }
  }, [renderedText, result, url]);

  /* --- Render --- */

  return (
    <div className="app-layout">
      <Sidebar
        history={history}
        activeIdx={activeIdx}
        onSelect={selectHistory}
        theme={theme}
        onToggleTheme={toggleTheme}
      />

      <main className="main-content">
        <h1 style={{ fontSize: 28, fontWeight: 800, marginBottom: 28, letterSpacing: "-0.02em" }}>
          README Evaluator
        </h1>

        <form className="eval-form" onSubmit={handleSubmit}>
          <input
            ref={urlRef}
            type="text"
            className="eval-input"
            placeholder="https://github.com/owner/repo"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            autoFocus
          />
          <button type="submit" className="btn btn-primary" disabled={loading}>
            {loading ? "Processing…" : "Evaluate"}
          </button>
        </form>

        {error && (
          <div className="error-banner">
            <strong>Error: </strong>{error}
          </div>
        )}

        {loading && progress.length > 0 && (
          <ProgressPanel progress={progress} percentage={percentage} />
        )}

        {result ? (
          <>
            <ReportCard
              renderedText={renderedText}
              result={result}
              onDownloadPdf={handleDownloadPdf}
            />
            <DebugDetails result={result} />
          </>
        ) : (
          !loading && !error && <EmptyState />
        )}
      </main>
    </div>
  );
}
