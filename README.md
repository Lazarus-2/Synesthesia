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
# Python 3.12 — venv lives at backend/.venv after the layout refactor
python -m venv backend/.venv
source backend/.venv/bin/activate
pip install -e ./backend[dev]
# Optionally pull the heavy ML deps:
#   pip install -e "./backend[dev,audio-heavy,providers]"

cp .env.example .env
# Edit .env — at minimum set LLM_PROVIDER (default ``ollama``).

# Bring up Mongo (replica set) + Redis from the compose file:
docker compose up -d mongodb mongodb-setup redis

# API
uvicorn backend.main:app --reload                       # http://localhost:8001

# Worker (separate terminal)
taskiq worker backend.worker:broker backend.main

# Frontend (separate terminal)
cd frontend/web
npm install
npm run dev                                             # http://localhost:3001
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
| `api`          | 8001  | `runtime-api`         |
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

### Music platform integrations (Plan v2)

The ingestion + search layer pulls from several free / freemium services.
**All are optional** — the analysis pipeline degrades gracefully when
their credentials are missing.

| Env var | Used by | What it unlocks |
|---|---|---|
| `SPOTIFY_CLIENT_ID` + `SPOTIFY_CLIENT_SECRET` | `/analyze` (Spotify URL branch) | Track metadata when the user pastes an `open.spotify.com/...` URL. Without these, Spotify URLs return a 400 with a friendly "Spotify integration disabled" message. |
| `SPOTIFY_ALLOW_YTDLP_FALLBACK` | Same as above | **Default off (ToS-clean).** When set to `true`, the backend bridges Spotify metadata → ytsearch1 → YouTube download. Spotify Developer ToS §III.2.a.i is at minimum ambiguous about this; you own the legal risk. |
| `ACOUSTID_API_KEY` | `/analyze` (file upload branch) | AcoustID fingerprint → MBID enrichment. Without it, uploaded files keep their browser-supplied title. Get a free key at https://acoustid.org/new-application. |
| `YTDLP_COOKIES_FILE` | yt-dlp ingest | Path to a Netscape-format cookie file; lets yt-dlp pull age-gated tracks. |

### System dependencies for ingest

- **Deno or Node.js** as a JavaScript runtime for yt-dlp's EJS signature
  solver (yt-dlp ≥ 2026.03 requires this; YouTube ships a new challenge
  most weeks). Install Deno via `npm i -g deno-bin` (no sudo) or
  https://deno.land/install. Node.js 18+ is also acceptable.
- **ffmpeg + ffprobe** for audio postprocessing. A static binary is
  bundled via the `imageio-ffmpeg` wheel so the worker keeps running on
  machines without a system ffmpeg — but for the best library
  compatibility, `apt install ffmpeg` (or `brew install ffmpeg`) is
  recommended.
- **fpcalc** (Chromaprint) for AcoustID fingerprinting. Install via
  `apt install libchromaprint-tools`. Without it, AcoustID enrichment
  silently no-ops.

## Test, lint, type-check

```bash
pytest backend/tests/                          # ~60+ tests, no Mongo required
pytest backend/tests/test_ml.py -v             # ML wrappers against synthetic audio
ruff check backend/                            # style + bug rules
mypy --config-file backend/pyproject.toml      # strict-first scope
cd frontend/web && npm run lint                # ESLint + react-hooks rules
```

The OpenAPI spec doubles as the TypeScript source of truth:

```bash
cd frontend/web
npm run codegen                          # dump openapi.json + regenerate types
```

CI (`.github/workflows/`) runs lint, test, codegen-check, an `e2e`
Playwright suite against a freshly-built stack, and a weekly
golden-songs eval against the LangGraph pipeline.

## API surface (Plan v2 additions)

| Endpoint | What it does |
|---|---|
| `POST /api/v1/analyze` | Upload an audio file or paste a URL. Accepts YouTube, YouTube Music, and Spotify URLs (Spotify metadata-only by default; env-gated yt-dlp bridge for full track). |
| `GET /api/v1/search?q=&limit=` | Merged Deezer + MusicBrainz catalog search. 30/min per IP. Cached 1h. |
| `GET /api/v1/lyrics?track_name=&artist_name=&duration=` | LRCLIB synced + plain lyrics. 60/min per IP. Cached 6h. Empty strings on no-match (the frontend treats that as "lyrics not available"). |
| `GET /api/v1/midi/{job_id}/{stem}` | Download a stem-isolated MIDI for `full / vocals / drums / bass / other`. |
| `GET /api/v1/library?limit=&offset=` | Paginated list of completed analyses. |
| `GET /api/v1/share/{job_id}` | Read-only public view of a single analysis. |

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
