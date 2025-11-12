import { useState } from "react";

export default function Home() {
  const [url, setUrl] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);

  async function handleSubmit(e) {
    e.preventDefault();
    setLoading(true);
    setResult(null);
    setError(null);
    try {
      const res = await fetch("http://localhost:8000/readme", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ repo_url: url }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || `HTTP ${res.status}`);
      }
      const data = await res.json();
      setResult(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <main style={{ padding: 24, fontFamily: "Arial, sans-serif" }}>
      <h1>Readme downloader</h1>
      <form onSubmit={handleSubmit} style={{ marginBottom: 12 }}>
        <input
          type="text"
          placeholder="https://github.com/owner/repo"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          style={{ width: "60%", padding: 8, marginRight: 8 }}
        />
        <button type="submit" disabled={loading} style={{ padding: "8px 12px" }}>
          {loading ? "Loading..." : "Fetch README"}
        </button>
      </form>

      {error && (
        <div style={{ color: "#b00020", marginBottom: 12 }}>
          <strong>Error:</strong> {error}
        </div>
      )}

      {result && (
        <section>
          <h2>Result — {result.filename}</h2>
          <div style={{ border: "1px solid #ddd", padding: 12, whiteSpace: "pre-wrap", maxHeight: "60vh", overflow: "auto", background: "#fafafa" }}>
            {result.content}
          </div>
        </section>
      )}
    </main>
  );
}
