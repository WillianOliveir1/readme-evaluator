import { useState } from "react";

export default function Home() {
  const [url, setUrl] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [progress, setProgress] = useState([]);
  const [currentPercentage, setCurrentPercentage] = useState(0);
  const [renderedText, setRenderedText] = useState(null);
  
  const MODEL = "gemini-2.5-flash"; // Fixed model

  async function handleSubmit(e) {
    e.preventDefault();
    setLoading(true);
    setResult(null);
    setError(null);
    setProgress([]);
    setCurrentPercentage(0);
    setRenderedText(null);

    try {
      // Step 1: Download README
      const readmeRes = await fetch("http://localhost:8000/readme", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ repo_url: url }),
      });
      if (!readmeRes.ok) {
        const err = await readmeRes.json().catch(() => ({}));
        throw new Error(err.detail || `HTTP ${readmeRes.status}`);
      }
      const readmeData = await readmeRes.json();

      // Step 2: Call /extract-json-stream with Server-Sent Events
      const body = { 
        readme_text: readmeData.content,
        model: MODEL
      };

      const response = await fetch("http://localhost:8000/extract-json-stream", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });

      if (!response.ok) {
        const err = await response.json().catch(() => ({}));
        throw new Error(err.detail || `HTTP ${response.status}`);
      }

      // Handle SSE streaming
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          if (line.startsWith("data: ")) {
            try {
              const data = JSON.parse(line.slice(6));
              console.log("SSE received:", data.type, data);

              if (data.type === "progress") {
                setProgress((prev) => [...prev, data]);
                setCurrentPercentage(data.percentage || 0);
              } else if (data.type === "result") {
                const merged = {
                  ...data.result,
                  filename: readmeData.filename,
                };
                setResult(merged);
                setCurrentPercentage(100);
              } else if (data.type === "rendered") {
                console.log("Rendered data received:", data.rendered);
                // Handle both string (legacy) and object (new) formats
                const text = typeof data.rendered === 'string' 
                  ? data.rendered 
                  : data.rendered.text;
                setRenderedText(text);
              } else if (data.type === "error") {
                throw new Error(data.error);
              }
            } catch (parseErr) {
              console.error("Failed to parse SSE data:", parseErr);
            }
          }
        }
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  const getStageColor = (stage) => {
    const colors = {
      BUILDING_PROMPT: "#1976d2",
      CALLING_MODEL: "#2196f3",
      PARSING_JSON: "#03a9f4",
      VALIDATING: "#00bcd4",
      COMPLETED: "#4caf50",
    };
    return colors[stage] || "#9e9e9e";
  };

  // Simple Markdown Renderer (Dependency-free)
  const renderMarkdown = (text) => {
    if (!text) return null;
    
    // Escape HTML to prevent XSS (basic)
    let html = text
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");

    // Headers
    html = html.replace(/^### (.*$)/gim, '<h3>$1</h3>');
    html = html.replace(/^## (.*$)/gim, '<h2>$1</h2>');
    html = html.replace(/^# (.*$)/gim, '<h1>$1</h1>');

    // Bold
    html = html.replace(/\*\*(.*?)\*\*/gim, '<strong>$1</strong>');
    
    // Lists (basic)
    html = html.replace(/^\* (.*$)/gim, '<li>$1</li>');
    html = html.replace(/^- (.*$)/gim, '<li>$1</li>');
    
    // Wrap lists (naive)
    html = html.replace(/(<li>.*<\/li>)/gim, '<ul>$1</ul>');
    // Fix multiple ul tags
    html = html.replace(/<\/ul><ul>/gim, '');

    // Line breaks
    html = html.replace(/\n/gim, '<br>');

    return <div dangerouslySetInnerHTML={{ __html: html }} />;
  };

  return (
    <main style={{ padding: "40px 24px", fontFamily: "'Segoe UI', Roboto, Helvetica, Arial, sans-serif", maxWidth: "1000px", margin: "0 auto", color: "#333", lineHeight: "1.6" }}>
      <h1 style={{ textAlign: "center", marginBottom: "40px", color: "#2c3e50" }}>README Evaluator</h1>
      
      <form onSubmit={handleSubmit} style={{ marginBottom: 32, display: "flex", gap: "12px", justifyContent: "center" }}>
        <input
          type="text"
          placeholder="https://github.com/owner/repo"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          style={{ 
            width: "60%", 
            padding: "12px 16px", 
            fontSize: "16px", 
            border: "1px solid #ddd", 
            borderRadius: "8px",
            outline: "none",
            boxShadow: "0 2px 4px rgba(0,0,0,0.05)"
          }}
        />
        <button 
          type="submit" 
          disabled={loading} 
          style={{ 
            padding: "12px 24px", 
            fontSize: "16px", 
            fontWeight: "600",
            cursor: loading ? "not-allowed" : "pointer",
            background: loading ? "#b0bec5" : "#1976d2",
            color: "white",
            border: "none",
            borderRadius: "8px",
            boxShadow: "0 2px 4px rgba(0,0,0,0.1)",
            transition: "background 0.2s"
          }}
        >
          {loading ? "Processing..." : "Evaluate"}
        </button>
      </form>

      {error && (
        <div style={{ color: "#d32f2f", marginBottom: 24, padding: "16px", background: "#ffebee", border: "1px solid #ef5350", borderRadius: "8px" }}>
          <strong>Error:</strong> {error}
        </div>
      )}

      {/* Real-time Progress Display */}
      {loading && (
        <div style={{ marginBottom: 40, padding: "24px", background: "#fff", border: "1px solid #e0e0e0", borderRadius: "12px", boxShadow: "0 4px 12px rgba(0,0,0,0.05)" }}>
          <h3 style={{ marginTop: 0, marginBottom: 16, fontSize: "18px", color: "#555" }}>Processing Pipeline</h3>

          {/* Progress Bar */}
          <div style={{ marginBottom: 24 }}>
            <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 8 }}>
              <span style={{ fontSize: "14px", fontWeight: "600", color: "#666" }}>Progress</span>
              <span style={{ fontSize: "14px", fontWeight: "600", color: "#1976d2" }}>{currentPercentage}%</span>
            </div>
            <div style={{ width: "100%", height: "8px", background: "#f0f0f0", borderRadius: "4px", overflow: "hidden" }}>
              <div
                style={{
                  width: `${currentPercentage}%`,
                  height: "100%",
                  background: `linear-gradient(90deg, #1976d2 0%, #42a5f5 100%)`,
                  transition: "width 0.3s ease",
                }}
              />
            </div>
          </div>

          {/* Stage Timeline */}
          <div style={{ display: "flex", gap: "12px", overflowX: "auto", paddingBottom: "8px" }}>
            {progress.map((update, idx) => (
              <div
                key={idx}
                style={{
                  minWidth: "140px",
                  padding: "12px",
                  background: "#f8f9fa",
                  borderLeft: `4px solid ${getStageColor(update.stage)}`,
                  borderRadius: "4px",
                  fontSize: "13px",
                }}
              >
                <div style={{ fontWeight: "700", color: getStageColor(update.stage), marginBottom: 4, fontSize: "11px", textTransform: "uppercase" }}>
                  {update.stage}
                </div>
                <div style={{ color: "#333", marginBottom: 4 }}>{update.message}</div>
                {update.elapsed_time && (
                  <div style={{ color: "#757575", fontSize: "11px" }}>
                    ⏱ {update.elapsed_time.toFixed(2)}s
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Result Display */}
      {result && (
        <section>
          {/* 1. Main Report (Rendered) */}
          {renderedText && typeof renderedText === "string" && (
            <div style={{ 
              marginBottom: 40, 
              padding: "40px", 
              background: "#fff", 
              borderRadius: "12px", 
              boxShadow: "0 8px 24px rgba(0,0,0,0.08)",
              border: "1px solid #eee"
            }}>
              <div style={{ 
                fontSize: "16px", 
                lineHeight: "1.8", 
                color: "#2c3e50" 
              }} className="markdown-body">
                {renderMarkdown(renderedText)}
              </div>
            </div>
          )}

          {/* 2. Debug Details (Collapsible) */}
          <details style={{ 
            background: "#f8f9fa", 
            borderRadius: "8px", 
            border: "1px solid #e0e0e0",
            overflow: "hidden"
          }}>
            <summary style={{ 
              padding: "16px 24px", 
              cursor: "pointer", 
              fontWeight: "600", 
              color: "#555",
              userSelect: "none",
              outline: "none"
            }}>
              Show Debug Details (JSON, Prompt, Timing)
            </summary>
            
            <div style={{ padding: "24px", borderTop: "1px solid #e0e0e0" }}>
              <h2 style={{ marginTop: 0, fontSize: "18px", marginBottom: 16 }}>Technical Details — {result.filename || "README"}</h2>
              
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 24, marginBottom: 24 }}>
                {/* Left: Prompt */}
                <div style={{ border: "1px solid #ddd", borderRadius: "6px", background: "#fff", overflow: "hidden" }}>
                  <div style={{ padding: "8px 12px", background: "#f5f5f5", borderBottom: "1px solid #ddd", fontWeight: "600", fontSize: "12px", color: "#666" }}>PROMPT BUILT</div>
                  <pre
                    style={{
                      margin: 0,
                      whiteSpace: "pre-wrap",
                      maxHeight: "400px",
                      overflow: "auto",
                      padding: "12px",
                      fontSize: "12px",
                      fontFamily: "Consolas, monospace",
                      color: "#444"
                    }}
                  >
                    {result.prompt || "No prompt data available."}
                  </pre>
                </div>

                {/* Right: Parsed JSON */}
                <div style={{ border: "1px solid #ddd", borderRadius: "6px", background: "#fff", overflow: "hidden" }}>
                  <div style={{ padding: "8px 12px", background: "#f5f5f5", borderBottom: "1px solid #ddd", fontWeight: "600", fontSize: "12px", color: "#666" }}>
                    PARSED JSON {result.validation_ok ? "✅" : "⚠️"}
                  </div>
                  <pre
                    style={{
                      margin: 0,
                      whiteSpace: "pre-wrap",
                      maxHeight: "400px",
                      overflow: "auto",
                      padding: "12px",
                      fontSize: "12px",
                      fontFamily: "Consolas, monospace",
                      color: "#2e7d32"
                    }}
                  >
                    {result.parsed ? JSON.stringify(result.parsed, null, 2) : "No JSON parsed."}
                  </pre>
                </div>
              </div>

              {/* Model Output (Raw) */}
              <div style={{ marginBottom: 24, border: "1px solid #ddd", borderRadius: "6px", background: "#fff", overflow: "hidden" }}>
                 <div style={{ padding: "8px 12px", background: "#f5f5f5", borderBottom: "1px solid #ddd", fontWeight: "600", fontSize: "12px", color: "#666" }}>RAW MODEL OUTPUT</div>
                 <pre
                    style={{
                      margin: 0,
                      whiteSpace: "pre-wrap",
                      maxHeight: "200px",
                      overflow: "auto",
                      padding: "12px",
                      fontSize: "12px",
                      fontFamily: "Consolas, monospace",
                      color: "#555"
                    }}
                  >
                    {result.model_output || "No raw output available."}
                  </pre>
              </div>

              {/* Timing Summary */}
              {result.timing && Object.keys(result.timing).length > 0 && (
                <div style={{ padding: "16px", background: "#e3f2fd", border: "1px solid #90caf9", borderRadius: "6px" }}>
                  <h4 style={{ marginTop: 0, marginBottom: 12, color: "#1565c0" }}>Timing Summary</h4>
                  <div style={{ display: "flex", gap: "16px", flexWrap: "wrap" }}>
                    {Object.entries(result.timing).map(([key, value]) => (
                      <div key={key} style={{ padding: "8px 16px", background: "#fff", borderRadius: "4px", textAlign: "center", boxShadow: "0 1px 2px rgba(0,0,0,0.1)" }}>
                        <div style={{ fontSize: "11px", color: "#666", textTransform: "uppercase", marginBottom: 4 }}>{key}</div>
                        <div style={{ fontSize: "16px", fontWeight: "bold", color: "#1976d2" }}>
                          {typeof value === "number" ? `${value.toFixed(3)}s` : value}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </details>
        </section>
      )}
    </main>
  );
}
