# Synesthesia

An AI music-analysis and learning platform. Upload an audio file or paste a
YouTube URL; Synesthesia runs a LangGraph pipeline that does ML-based audio
analysis (chords, key, tempo, beats, sections, stems) and then fans out to
LLM chains that produce a theory explanation, instrument-specific learning
guide, and similar-song recommendations.

This README is a quick-start; the deeper "how does this fit together"
discussion lives in [docs/architecture.md](docs/architecture.md).

---

## Quick start (local, no Docker)

```bash
# Python 3.12
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
# Optionally pull the heavy ML deps:
#   pip install -e ".[dev,audio-heavy,providers]"

cp .env.example .env
# Edit .env — at minimum set LLM_PROVIDER (default ``ollama``).

# Bring up Mongo (replica set) + Redis from the compose file:
docker compose up -d mongodb mongodb-setup redis

# API
uvicorn backend.main:app --reload                       # http://localhost:8000

# Worker (separate terminal)
taskiq worker backend.worker:broker backend.main

# Frontend (separate terminal)
cd frontend/web
npm install
npm run dev                                             # http://localhost:3000
```

## Quick start (Docker, canonical)

```bash
docker compose up -d
```

Containers:

| service        | port  | image-target          |
|----------------|-------|-----------------------|
| `mongodb`      | 27017 | `mongo:6.0` (rs0)     |
| `redis`        | 6379  | `redis:7`             |
| `api`          | 8000  | `runtime-api`         |
| `worker`       | —     | `runtime-worker`      |

The MongoDB replica set is **required** — Taskiq transactions need it.
`mongodb-setup` initiates `rs0` automatically.

## Configuration

Settings live in `backend/config.py` and are loaded from `.env` via Pydantic
Settings. The validators fail-fast at startup when:

- The selected `LLM_PROVIDER` is missing its API key.
- `REQUIRE_AUTH=true` but `AUTH_SECRET_KEY` is empty.

Key env vars: `LLM_PROVIDER`, `MODEL_NAME`, `LLM_FALLBACK_PROVIDER`,
`MONGO_URI`, `REDIS_URL`, `AUDIO_UPLOAD_DIR`, `STEMS_DIR`, `MAX_UPLOAD_MB`,
`ALLOWED_ORIGINS` (CSV), `ANALYZE_RATE_LIMIT`, `CHAT_RATE_LIMIT`,
`REQUIRE_AUTH`, `AUTH_SECRET_KEY`, `OTEL_EXPORTER_OTLP_ENDPOINT`,
`LOG_FORMAT` (`json` | `plain`).

## Test, lint, type-check

```bash
pytest                                  # ~60+ tests, no Mongo required
pytest tests/test_ml.py -v              # ML wrappers against synthetic audio
ruff check backend/                     # style + bug rules
mypy --config-file pyproject.toml       # strict-first scope
cd frontend/web && npm run lint         # ESLint + react-hooks rules
```

The OpenAPI spec doubles as the TypeScript source of truth:

```bash
cd frontend/web
npm run codegen                          # dump openapi.json + regenerate types
```

CI (`.github/workflows/`) runs lint, test, codegen-check, and a weekly
golden-songs eval against the LangGraph pipeline.

## Where to look first

- [`backend/main.py`](backend/main.py) — FastAPI app, routes, lifespan, error
  envelope, rate limiting.
- [`backend/graph/`](backend/graph/) — the LangGraph pipeline that orchestrates
  ingest → validate → features → roman → (theory, instrument, similarity,
  stems) → END.
- [`backend/chains/`](backend/chains/) — LangChain LCEL chains. Always
  construct LLMs via `llm_factory.build_llm()` so observability + fallback
  wrapping stay consistent.
- [`backend/services/job_store.py`](backend/services/job_store.py) — the
  process-shared progress + heartbeat surface used by the SSE endpoint.
- [`backend/observability/`](backend/observability/) — JSON logging +
  OpenTelemetry tracing.
- [`frontend/web/src/lib/apiClient.ts`](frontend/web/src/lib/apiClient.ts) —
  the single fetch / SSE wrapper every store and component should use.

## Plans

The `plans/` directory contains the rolling implementation plans:

- [plans/01-cleanup-and-optimization.md](plans/01-cleanup-and-optimization.md)
- [plans/02-architecture-and-improvements.md](plans/02-architecture-and-improvements.md)
- [plans/03-pending-work-and-features.md](plans/03-pending-work-and-features.md)
- [plans/00-verification-and-corrections.md](plans/00-verification-and-corrections.md)

Plans 1 and 2 are complete; Plan 3 is almost complete (see the file for the
deferred parking-lot items).
