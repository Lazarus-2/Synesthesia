# Architecture

A reading order for the code, and the architectural decisions worth knowing
before you change anything load-bearing.

## Plan v2 platform integrations

Submission can come from four sources. The classifier lives in
`backend/ingestion/url_resolver.classify_url`; the dispatcher branches
inside `backend/graph/nodes.ingest_node`.

```
   ┌───────────────────────────────────────────────────────────────┐
   │ submission                                                   │
   ├───────────────────────────────────────────────────────────────┤
   │ File upload    → AcoustID fingerprint (pyacoustid + fpcalc)  │
   │                 → MBID/title/artist enrichment (graceful)    │
   │                                                              │
   │ YouTube URL    → yt-dlp                                      │
   │ YouTube Music  → normalize to www.youtube.com, then yt-dlp   │
   │   yt-dlp 2026 needs:                                         │
   │   - JS runtime (Deno or Node) for the EJS signature solver   │
   │   - remote_components=['ejs:github'] to opt into download    │
   │   - player_client=[web_safari, tv, web] for SABR avoidance   │
   │   - ffmpeg (system or imageio-ffmpeg fallback)               │
   │                                                              │
   │ Spotify URL    → spotipy: title/artist/album/ISRC/cover      │
   │   default (audio_source=spotify_embed): frontend iframe      │
   │   env-gated:    SPOTIFY_ALLOW_YTDLP_FALLBACK=true → ytsearch │
   └───────────────────────────────────────────────────────────────┘

   New public endpoints
   ────────────────────────────────────────────────────────────────
   GET /api/v1/search?q=     Deezer + MusicBrainz, gather, dedup
                              (Spotify Web API is dead for new apps;
                              see docs/research/music-platforms-2026.md)
   GET /api/v1/lyrics        LRCLIB (LRC-format synced + plain text)
   GET /api/v1/midi/{job}/{stem}  full / vocals / drums / bass / other
```

## Request flow (audio → result)

```
client (Next.js)
   │
   │   POST /api/v1/analyze        (multipart)
   ▼
FastAPI (backend/main.py)
   │   - magic-byte + extension validation
   │   - path-traversal guard, size cap
   │   - hash → dedup against song_analyses
   │   - JobStore.cache_response("queued")
   │   - run_analysis_pipeline.kiq(...)   ─┐
   ▼                                        │
returns AnalyzeResponse{job_id, audio_url}  │ Taskiq via Redis
                                            │
                                            ▼
                                  Worker (backend/worker.py)
                                            │
                                            │  run_analysis_pipeline (main.py)
                                            │  ─ idempotency check (song_analyses)
                                            │  ─ JobStore.set_progress(...)
                                            │  ─ get_graph().ainvoke(state, thread_id=job_id)
                                            │
                                            ▼
                                  LangGraph (backend/graph/)
                                  ingest → validate_audio → features
                                       │ retry edge (max 2)
                                       ▼
                                  roman → ┬ theory
                                          ├ instrument
                                          ├ similarity
                                          └ stems
                                       │
                                       ▼
                                       END
                                            │
                                            │  persist to song_analyses
                                            ▼
                                  JobStore.cache_response("done")
                                            │
                                            │  Redis-backed progress
                                            ▼
                                  Frontend reads SSE
                                  GET /api/v1/jobs/{job_id}/progress
                                  event: chunk / done / error
```

Things to know:

- The graph's checkpointer is **MongoDBSaver** (`langgraph-checkpoint-mongodb`).
  Mid-pipeline worker crashes resume from the last completed node when the
  same `thread_id` (=`job_id`) is invoked.
- Progress is **JobStore-backed** (Redis). The SSE endpoint reads
  `get_cached_response` + `is_stale` (heartbeat-driven) so a crashed worker
  fails fast (60 s) instead of waiting on a hardcoded 180 s timeout.
- The Taskiq task has `retry_on_error=True, max_retries=2`. On final
  failure, the original payload + error chain are written to `failed_jobs`
  (DLQ) before re-raising.

## API surface

| Path                                          | Purpose |
|----------------------------------------------|---------|
| `GET /health`                                 | Liveness — cheap, always 200. |
| `GET /health/ready`                           | Readiness — pings Mongo + Redis, 503 if degraded. |
| `POST /api/v1/analyze`                        | Multipart upload **or** `youtube_url`. Returns job id. |
| `GET /api/v1/analyze/{job_id}?instrument=…`   | Cached response; picks the requested instrument's guide. |
| `GET /api/v1/jobs/{job_id}/progress`          | SSE — tagged `event:` frames (`chunk`, `done`, `error`). |
| `GET /api/v1/audio/{job_id}`                  | Streams the staged audio. |
| `GET /api/v1/stems/{job_id}/{stem}`           | One demucs stem WAV. |
| `GET /api/v1/midi/{job_id}/{stem}`            | basic-pitch MIDI for a stem (or `full`). |
| `GET /api/v1/share/{job_id}`                  | Public, read-only analysis. |
| `GET /api/v1/library?limit&offset&user_id`    | Paginated analysis list. |
| `POST /api/v1/auth/{signup,login}`            | JWT issue. |
| `GET /api/v1/auth/me`                         | Echo the bearer principal (or `null`). |
| `GET /api/v1/user/{user_id}/preferences`      | Default instrument/difficulty/capo. |
| `POST /api/v1/chat`, `POST /api/v1/chat/stream` | AURA chat. Optional `analysis_job_id` injects song context. |

Every error path returns a uniform `APIError` envelope:
`{status: "error", code: "UPPER_SNAKE_CASE", message: "...", details?: {...}}`.

During the frontend's migration we double-mount the router at both
`/api/v1/*` and the legacy unprefixed root.

## State management

| Concern               | Store                              | Lifetime |
|----------------------|------------------------------------|----------|
| Final analysis        | MongoDB `song_analyses`            | 90 days (TTL) |
| Job progress + heartbeat | Redis (via `HybridJobStore`)    | 24 h |
| Graph checkpoints     | MongoDB `checkpointing_db`         | per-thread (no TTL) |
| Failed jobs (DLQ)     | MongoDB `failed_jobs`              | 90 days (TTL) |
| HTTP-layer cache (SSE / dedup) | Redis (`HybridCache`)     | per-key TTL |
| Auth principal (client) | `localStorage` (`useAuthStore`)  | until logout |

The `JobStore` Protocol abstracts the read/write surface so endpoints and the
worker task talk to one thing for the lifecycle of a job — see
`backend/services/job_store.py`.

## LLM layer

- `backend/chains/llm_factory.py` is the **single** LLM constructor. It
  supports six providers (OpenAI, Anthropic, Gemini, Groq, OpenRouter,
  Ollama) selected by `LLM_PROVIDER`.
- Fallback wiring uses `_wrap_with_observable_fallback()` so each fallback
  activation logs and increments an in-process counter (visible via
  `get_fallback_stats()`).
- Prompts live in [backend/prompts/templates/](backend/prompts/templates/)
  as versioned YAML. Load with `load_template(name, version="latest")`.
- Structured output: `theory_chain` uses `with_structured_output` for a
  `TheoryExplanation` Pydantic model; `instrument_chain` does the same for
  `LLMInstrumentTips`. Both flatten back to the existing API shape so
  consumers don't break.

## ML modules

Each file in [`backend/ml/`](backend/ml/) is a thin wrapper:

| Module                  | Library      | Role |
|-------------------------|--------------|------|
| `chord_detection.py`    | librosa      | CQT chromagram + template matching |
| `beat_tracking.py`      | madmom→librosa | RNN if available, librosa fallback |
| `key_estimation.py`     | librosa      | Krumhansl-Schmuckler chroma correlation |
| `structure_detection.py` | librosa     | Agglomerative segmentation + cosine clustering |
| `stem_separation.py`    | demucs       | `htdemucs_ft`, lazy-loaded via registry |
| `midi_transcription.py` | basic-pitch  | Spotify's basic-pitch via registry |

Heavy models (demucs, basic-pitch) are loaded once per process via
`backend/ml/registry.py`. Restart the worker to pick up a new model.

## Observability

- **Logs**: stdlib `logging` with a JSON formatter (`LOG_FORMAT=json`).
  `configure_logging()` is called from both the FastAPI lifespan and the
  Taskiq `WORKER_STARTUP` hook.
- **Traces**: OpenTelemetry. `configure_tracing()` no-ops when
  `OTEL_EXPORTER_OTLP_ENDPOINT` is unset, so local dev needs no setup. Use
  the `@trace("stage")` context manager (`backend/observability/tracing.py`)
  for new pipeline stages.
- **Metrics**: only the in-process fallback counter today. Prometheus /
  OTLP metrics export is intentionally deferred.

## Frontend

- Next.js 16, React 19, TypeScript. `app/page.tsx` is a thin **Server
  Component** that renders `<HomeClient>`; the interactive tree lives under
  `HomeClient`. Push `'use client'` to leaves where possible.
- All HTTP traffic goes through
  [`src/lib/apiClient.ts`](frontend/web/src/lib/apiClient.ts) so base URL,
  error envelopes, and SSE consumption stay consistent.
- SSE consumer (`consumeSse`, `openProgressStream`) handles both the new
  tagged-event format (`event: chunk\ndata: …`) and the legacy
  `data: [DONE]` shape so backend + frontend can roll independently.
- Types: `src/types/index.ts` is hand-maintained, `src/types/api.gen.ts` is
  auto-generated by `npm run codegen` (calls
  `python scripts/dump_openapi.py` then `openapi-typescript`). A CI check
  fails the PR if the generated file is stale.

## Deployment

- Three Dockerfile targets (`builder`, `runtime-api`, `runtime-worker`).
- docker-compose pins each service to its target, sets `stop_grace_period:
  130s`, and the api service runs `uvicorn --timeout-graceful-shutdown 120`
  so SSE streams don't get severed during drains.
- `HEALTHCHECK` only on the API image — Taskiq has no built-in HTTP probe;
  the worker should be monitored via Redis queue depth instead.

## What's intentionally deferred

These items have been considered and explicitly punted; see the plan files
for the reasoning:

- **Postgres for `users` / `chat_sessions`** — Mongo is fine at current scale.
- **S3 storage abstraction** — premature; one local-files implementation is
  enough until a cloud target is chosen.
- **Pitch-preserving slowdown** in practice mode — Plan v2 shipped the
  pitch-lock toggle + vendored the SoundTouch AudioWorklet bundle
  (`frontend/web/public/soundtouch-processor.js`). The audio chain
  routing — replacing wavesurfer's playbackRate with a SoundTouchNode
  inserted between the `MediaElementAudioSourceNode` and `destination`
  — ships in the audio-engine follow-up.
- **Pre-computed audio embeddings (CLAP / MERT) for similarity** — the
  current 36-D sequence-aware embedding is the cheap first step.
- **Auto re-enqueue from the DLQ** — `failed_jobs` is visible in Mongo
  today; an `/admin/dlq` endpoint can come later when ops actually needs it.

## Gotchas

- `frontend/web/AGENTS.md` instructs Claude-and-friends to read
  `node_modules/next/dist/docs/` before touching the frontend. Honor that.
- The MongoDB URI **must** include `?replicaSet=rs0` for Taskiq to work.
- The repo includes legacy unprefixed route mounts (`/analyze` etc.) so the
  current frontend keeps working during the `/api/v1/` migration. Remove
  the second `include_router` call once the frontend fully migrates.
