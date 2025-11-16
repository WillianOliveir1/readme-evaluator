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
                console.log("Rendered text type:", typeof data.rendered);
                setRenderedText(data.rendered);
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

  return (
    <main style={{ padding: 24, fontFamily: "Arial, sans-serif", maxWidth: "1200px", margin: "0 auto" }}>
      <h1>README Evaluator</h1>
      <form onSubmit={handleSubmit} style={{ marginBottom: 12 }}>
        <input
          type="text"
          placeholder="https://github.com/owner/repo"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          style={{ width: "60%", padding: 8, marginRight: 8 }}
        />
        <button type="submit" disabled={loading} style={{ padding: "8px 12px", cursor: loading ? "not-allowed" : "pointer" }}>
          {loading ? "Processing..." : "Evaluate README"}
        </button>
      </form>

      {error && (
        <div style={{ color: "#b00020", marginBottom: 12, padding: 12, background: "#ffebee", border: "1px solid #ef5350" }}>
          <strong>Error:</strong> {error}
        </div>
      )}

      {/* Real-time Progress Display */}
      {loading && (
        <div style={{ marginBottom: 24, padding: 16, background: "#f5f5f5", border: "1px solid #ddd", borderRadius: "4px" }}>
          <h3 style={{ marginTop: 0, marginBottom: 12 }}>Processing Progress</h3>

          {/* Progress Bar */}
          <div style={{ marginBottom: 16 }}>
            <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
              <span style={{ fontSize: "14px", fontWeight: "bold" }}>Progress</span>
              <span style={{ fontSize: "14px" }}>{currentPercentage}%</span>
            </div>
            <div style={{ width: "100%", height: "24px", background: "#e0e0e0", borderRadius: "4px", overflow: "hidden" }}>
              <div
                style={{
                  width: `${currentPercentage}%`,
                  height: "100%",
                  background: `linear-gradient(90deg, #1976d2 0%, #2196f3 50%, #03a9f4 100%)`,
                  transition: "width 0.3s ease",
                }}
              />
            </div>
          </div>

          {/* Stage Timeline */}
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))", gap: 8 }}>
            {progress.map((update, idx) => (
              <div
                key={idx}
                style={{
                  padding: 12,
                  background: "#fff",
                  border: `2px solid ${getStageColor(update.stage)}`,
                  borderRadius: "4px",
                  fontSize: "12px",
                }}
              >
                <div style={{ fontWeight: "bold", color: getStageColor(update.stage), marginBottom: 4 }}>
                  {update.stage}
                </div>
                <div style={{ color: "#555", marginBottom: 4 }}>{update.message}</div>
                {update.elapsed_time && (
                  <div style={{ color: "#999", fontSize: "11px" }}>
                    ⏱ {update.elapsed_time.toFixed(2)}s
                  </div>
                )}
                {update.estimated_remaining_time && (
                  <div style={{ color: "#999", fontSize: "11px" }}>
                    ⏳ ~{update.estimated_remaining_time.toFixed(1)}s left
                  </div>
                )}
              </div>
            ))}
          </div>

          {/* Latest Status */}
          {progress.length > 0 && (
            <div style={{ marginTop: 12, padding: 8, background: "#fff", borderRadius: "4px", fontSize: "13px", color: "#333" }}>
              <strong>Latest:</strong> {progress[progress.length - 1].message}
            </div>
          )}
        </div>
      )}

      {/* Result Display */}
      {result && (
        <section>
          <h2>Result — {result.filename || "README"}</h2>

          {/* Rendered Evaluation (Main Display) */}
          {renderedText && typeof renderedText === "string" && (
            <div style={{ marginBottom: 24, padding: 16, background: "#e8f5e9", border: "2px solid #4caf50", borderRadius: "4px" }}>
              <h3 style={{ marginTop: 0, marginBottom: 12, color: "#2e7d32" }}>📋 Evaluation Summary</h3>
              <div
                style={{
                  whiteSpace: "pre-wrap",
                  wordWrap: "break-word",
                  background: "#fff",
                  padding: 12,
                  borderRadius: "4px",
                  fontSize: "14px",
                  lineHeight: "1.6",
                  color: "#333",
                }}
              >
                {renderedText}
              </div>
            </div>
          )}

          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginBottom: 12 }}>
            {/* Left: Prompt */}
            <div style={{ border: "1px solid #ddd", padding: 12, background: "#fff", borderRadius: "4px" }}>
              <h3 style={{ marginTop: 0 }}>Prompt Built</h3>
              {result.prompt ? (
                <pre
                  style={{
                    whiteSpace: "pre-wrap",
                    maxHeight: "50vh",
                    overflow: "auto",
                    background: "#f5f5f5",
                    padding: 8,
                    borderRadius: "4px",
                    fontSize: "12px",
                  }}
                >
                  {result.prompt}
                </pre>
              ) : (
                <div style={{ color: "#666" }}>No prompt generated</div>
              )}
            </div>

            {/* Right: Model Output / Parsed JSON */}
            <div style={{ border: "1px solid #ddd", padding: 12, background: "#fafafa", borderRadius: "4px" }}>
              <h3 style={{ marginTop: 0 }}>Extraction Result</h3>

              {result.model_output ? (
                <>
                  <h4 style={{ marginBottom: 6, marginTop: 0 }}>Model Response</h4>
                  <pre
                    style={{
                      whiteSpace: "pre-wrap",
                      maxHeight: "30vh",
                      overflow: "auto",
                      background: "#fff",
                      padding: 8,
                      borderRadius: "4px",
                      fontSize: "12px",
                    }}
                  >
                    {result.model_output}
                  </pre>
                </>
              ) : (
                <div style={{ color: "#666" }}>Model failed to produce output (check server logs or API key)</div>
              )}

              {result.parsed ? (
                <>
                  <h4 style={{ marginTop: 12, marginBottom: 6 }}>
                    Parsed JSON {result.validation_ok === true && "✓"}
                    {result.validation_ok === false && "✗"}
                  </h4>
                  <pre
                    style={{
                      whiteSpace: "pre-wrap",
                      maxHeight: "25vh",
                      overflow: "auto",
                      background: "#fff",
                      padding: 8,
                      borderRadius: "4px",
                      fontSize: "12px",
                    }}
                  >
                    {JSON.stringify(result.parsed, null, 2)}
                  </pre>
                </>
              ) : (
                <div style={{ color: "#666" }}>
                  No JSON parsed. Check the model output above for errors.
                </div>
              )}

              {result.validation_errors && (
                <div style={{ marginTop: 12, padding: 8, background: "#ffebee", border: "1px solid #ef5350", borderRadius: "4px" }}>
                  <strong>Validation Error:</strong>
                  <div style={{ fontSize: "12px", marginTop: 4 }}>{result.validation_errors.message}</div>
                  {result.validation_errors.path && (
                    <div style={{ fontSize: "12px", color: "#666" }}>Path: {result.validation_errors.path.join(".")}</div>
                  )}
                </div>
              )}

              {result.recovery_suggestions && result.recovery_suggestions.length > 0 && (
                <div style={{ marginTop: 12, padding: 8, background: "#fff3e0", border: "1px solid #ffb74d", borderRadius: "4px" }}>
                  <strong>Suggestions:</strong>
                  <ul style={{ margin: "4px 0 0 20px", padding: 0 }}>
                    {result.recovery_suggestions.map((sug, i) => (
                      <li key={i} style={{ fontSize: "12px", marginBottom: 4 }}>
                        {sug}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          </div>

          {/* Timing Summary */}
          {result.timing && Object.keys(result.timing).length > 0 && (
            <div style={{ marginTop: 12, padding: 12, background: "#e3f2fd", border: "1px solid #90caf9", borderRadius: "4px" }}>
              <h4 style={{ marginTop: 0 }}>Timing Summary</h4>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(120px, 1fr))", gap: 8 }}>
                {Object.entries(result.timing).map(([key, value]) => (
                  <div key={key} style={{ padding: 8, background: "#fff", borderRadius: "4px", textAlign: "center" }}>
                    <div style={{ fontSize: "12px", color: "#666" }}>{key}</div>
                    <div style={{ fontSize: "14px", fontWeight: "bold", color: "#1976d2" }}>
                      {typeof value === "number" ? `${value.toFixed(3)}s` : value}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </section>
      )}
    </main>
  );
}
