# README Evaluator

[![CI](https://github.com/WillianOliveir1/readme-evaluator/actions/workflows/ci.yml/badge.svg)](https://github.com/WillianOliveir1/readme-evaluator/actions/workflows/ci.yml)

**README Evaluator** is an AI-powered tool that analyses and evaluates GitHub repository README files. It leverages LLMs (Google Gemini or local models via Ollama) to extract structured data based on a comprehensive taxonomy and generates a human-readable quality report with optional PDF export, helping developers improve their project documentation.

## ❓ Why README Evaluator?

Documentation is often the first interaction a user has with a project. A poor README can turn away potential users and contributors. This tool provides:

- **Automated Quality Assessment** — objective evaluation against a strict JSON schema.
- **Structured Feedback** — identifies missing sections (Installation, Usage, License, …).
- **Actionable Improvements** — suggests specific changes to enhance clarity and completeness.
- **Real-time Progress** — Server-Sent Events stream lets you follow each evaluation step live.
- **PDF Export** — download polished PDF reports directly from the UI.
- **Multi-LLM Support** — use Google Gemini (cloud) or Ollama (local) with a single env var switch.
- **Dark / Light Theme** — sidebar with evaluation history and theme toggle.

## 🏗️ Architecture

```
┌──────────────┐        ┌────────────────────────────────────┐
│  Next.js UI  │──SSE──▶│  FastAPI Backend (Uvicorn)         │
│  :3000       │        │  ├─ /readme         (download)     │
│  ┌─────────┐ │        │  ├─ /extract-json   (evaluate)     │
│  │Dark/Light│ │        │  ├─ /extract-json-stream (SSE)     │
│  │ Theme    │ │        │  ├─ /render          (report)      │
│  │History   │ │        │  ├─ /generate        (LLM call)    │
│  │Sidebar   │ │        │  ├─ /export-pdf      (PDF export)  │
│  │PDF Export│ │        │  ├─ /jobs            (pipeline)    │
│  └─────────┘ │        │  ├─ /cache           (management)  │
└──────────────┘        │  └─ /files           (artifacts)   │
                        └───────────┬────────────────────────┘
                                    │
                        ┌───────────▼───────────┐
                        │  LLM Provider         │
                        │  (factory pattern)    │
                        ├───────────────────────┤
                        │  Gemini API (default) │
                        │  Ollama (local LLMs)  │
                        └───────────┬───────────┘
                                    │
                        ┌───────────▼───────────┐
                        │  MongoDB Atlas        │
                        │  (optional)           │
                        └───────────────────────┘
```

| Layer    | Tech                             |
|----------|----------------------------------|
| Frontend | Next.js 16, React 18, react-markdown, dark/light theme |
| Backend  | Python 3.13, FastAPI, Uvicorn, slowapi (rate limiting) |
| AI       | Google Gemini (`google-genai`) **or** Ollama (local LLMs) |
| PDF      | xhtml2pdf, markdown              |
| Database | MongoDB Atlas (optional — falls back to local JSON) |

## 🚀 Getting Started

### Prerequisites

- **Python 3.10+**
- **Node.js 18+** & npm
- **LLM Provider** (one of):
  - **Google Gemini API Key** — get one at [Google AI Studio](https://aistudio.google.com/) *(default)*
  - **Ollama** — install from [ollama.ai](https://ollama.ai/) for local LLM inference

### 1 — Clone & configure

```bash
git clone https://github.com/WillianOliveir1/readme-evaluator.git
cd readme-evaluator
cp .env.example .env          # edit .env and set GEMINI_API_KEY
```

### 2 — Backend

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux / macOS
source .venv/bin/activate

pip install --upgrade pip
pip install -r backend/requirements.txt
```

### 3 — Frontend

```bash
cd frontend
npm install
cd ..
```

### 4 — Run

```bash
# Terminal 1 — backend
python -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000

# Terminal 2 — frontend
cd frontend && npm run dev
```

Open **http://localhost:3000**, paste a GitHub repo URL, and click **Evaluate README**.

## 🐳 Docker

The quickest way to run the whole stack:

```bash
cp .env.example .env           # set at least GEMINI_API_KEY
docker compose up --build
```

| Service  | URL                     |
|----------|-------------------------|
| Backend  | http://localhost:8000   |
| Frontend | http://localhost:3000   |

See [docker-compose.yml](docker-compose.yml) for all configurable environment variables.

## ⚙️ Configuration

All configuration is done via environment variables (or the `.env` file).  
Copy `.env.example` for a documented list of every option:

| Variable            | Required | Default              | Description |
|---------------------|----------|----------------------|-------------|
| `GEMINI_API_KEY`    | **Yes**¹ | —                    | Google Gemini API key |
| `LLM_PROVIDER`      | No       | `gemini`             | LLM backend: `gemini` or `ollama` |
| `OLLAMA_BASE_URL`   | No       | `http://localhost:11434` | Ollama API URL (when `LLM_PROVIDER=ollama`) |
| `OLLAMA_MODEL`      | No       | `llama3`             | Default Ollama model name |
| `GITHUB_TOKEN`      | No       | —                    | Raises GitHub rate limit to 5 000 req/h |
| `API_KEY`           | No       | —                    | When set, every request must include `X-API-Key` header |
| `MONGODB_URI`       | No       | —                    | MongoDB connection string; unset = local JSON storage |
| `MONGODB_DB`        | No       | `readme_evaluator`   | MongoDB database name |
| `LOG_LEVEL`         | No       | `INFO`               | `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `LOG_FORMAT`        | No       | `json`               | `json` or `text` |
| `CORS_ORIGINS`      | No       | `localhost:3000`     | Comma-separated allowed origins |
| `DEFAULT_RATE_LIMIT`| No       | `60/minute`          | Global rate limit per client IP |
| `EXPENSIVE_RATE_LIMIT`| No     | `10/minute`          | Rate limit for AI/PDF endpoints |
| `MAX_CONCURRENT_PIPELINES` | No | `3`                | Max pipeline jobs running in parallel |

> ¹ Required only when `LLM_PROVIDER=gemini` (default).

## 🧪 Testing

```bash
# Run the full test suite (314 tests)
python -m pytest tests/ -q

# Type-checking
python -m mypy backend/ --ignore-missing-imports
```

The CI pipeline (GitHub Actions) runs both on every push and pull request to `main`.

## 📂 Project Structure

```
readme-evaluator/
├── backend/
│   ├── main.py               # FastAPI entrypoint + middleware
│   ├── config.py              # Centralised settings
│   ├── logging_config.py      # Structured JSON / text logging
│   ├── models.py              # Pydantic request/response models
│   ├── pipeline.py            # Multi-step evaluation pipeline (semaphore + locks)
│   ├── llm_base.py            # Abstract LLMClient base class
│   ├── gemini_client.py       # Gemini LLM client (with retry)
│   ├── ollama_client.py       # Ollama local LLM client (with retry)
│   ├── llm_factory.py         # Factory: get_llm_client() by LLM_PROVIDER
│   ├── rate_limit.py          # slowapi rate limiting config
│   ├── cache_manager.py       # Temp file lifecycle
│   ├── prompt_builder.py      # Prompt construction
│   ├── routers/               # 8 API routers
│   │   ├── readme.py          # POST /readme
│   │   ├── extract.py         # POST /extract-json, /extract-json-stream
│   │   ├── render.py          # POST /render, /render-evaluation
│   │   ├── generate.py        # POST /generate
│   │   ├── export_pdf.py      # POST /export-pdf
│   │   ├── jobs.py            # GET /jobs, POST /jobs, GET /jobs/{id}
│   │   ├── cache.py           # GET /cache/stats, POST /cache/cleanup
│   │   └── files.py           # GET /files/{path}
│   ├── download/              # GitHub README downloader
│   ├── evaluate/              # JSON extraction & validation
│   ├── present/               # Report renderer
│   ├── db/                    # MongoDB persistence layer
│   └── prompts/               # System prompt templates
├── frontend/
│   ├── pages/
│   │   ├── _app.js            # Custom App (global CSS)
│   │   └── index.js           # Main page (Sidebar, Progress, Report, PDF)
│   └── styles/
│       └── globals.css        # Global styles (dark/light theme, 654 lines)
├── schemas/                   # JSON Schema taxonomy
├── tests/                     # pytest suite (314 tests)
├── tools/                     # CLI utilities & analysis scripts
├── Dockerfile.backend
├── Dockerfile.frontend
├── docker-compose.yml
├── .env.example
├── pyproject.toml             # mypy configuration
└── .github/workflows/ci.yml   # GitHub Actions CI
```

## 📅 Status & Roadmap

**Current Status:** Active Development (Beta)

- [x] Core extraction pipeline with Gemini
- [x] Streaming response (SSE) for real-time feedback
- [x] MongoDB integration for persistence
- [x] REST API with authentication (X-API-Key)
- [x] Structured logging (JSON / text)
- [x] Type-checked codebase (mypy strict, 0 errors)
- [x] 314 unit & integration tests with pytest
- [x] Docker support (docker compose)
- [x] CI/CD with GitHub Actions
- [x] Rate limiting (slowapi) & concurrency control
- [x] Retry with exponential backoff (tenacity)
- [x] Ollama / local LLM support (factory pattern)
- [x] PDF export of evaluation reports
- [x] Frontend redesign (dark/light theme, sidebar history, progress bar)
- [ ] Batch processing for multiple repositories
- [ ] Comparative analysis between multiple READMEs

## 👥 Authors

- **Willian Oliveira** — *Initial work* — [WillianOliveir1](https://github.com/WillianOliveir1)

## 🤝 Contributing

Contributions are welcome! Please follow these steps:

1. Fork the repository.
2. Create a feature branch (`git checkout -b feature/AmazingFeature`).
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`).
4. Push to the branch (`git push origin feature/AmazingFeature`).
5. Open a Pull Request.

## 📄 License

This project is licensed under the **MIT License** — see [LICENSE](LICENSE) for details.

## 📚 References

- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [Next.js Documentation](https://nextjs.org/docs)
- [Google AI Studio](https://aistudio.google.com/)
- [Google GenAI Python SDK](https://github.com/googleapis/python-genai)

