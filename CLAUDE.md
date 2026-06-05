# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Synesthesia (formerly "SoundBreak") is a music-analysis + education platform. A user submits an audio file or YouTube URL; the backend runs a LangGraph pipeline that performs ML-based audio analysis (chords, key, tempo, beats, stems), generates Roman-numeral harmonic analysis deterministically, and then fans out to parallel LLM chains that produce a theory explanation, instrument-specific learning guide, and similar-song recommendations. The README still describes the project as a "code along with the vault" curriculum scaffold; that framing is stale — most modules are now implemented.

## Commands

Backend (Python 3.12; venv lives at `backend/.venv/`):

```bash
pip install -e "./backend[dev]"                   # editable install + dev extras (ruff/mypy/pytest)
uvicorn backend.main:app --reload                 # API on :8001
taskiq worker backend.worker:broker backend.main  # background analysis worker (needs Redis)
```

Full stack (canonical):

```bash
docker-compose up -d   # mongo (replica set rs0), redis, api:8001, worker
```

MongoDB **must** run as a replica set — Taskiq transactions require it. The `mongodb-setup` service in `docker-compose.yml` initiates `rs0` automatically; for a local non-docker mongo you must `rs.initiate()` manually.

Tests live under `backend/tests/`:

```bash
pytest backend/tests/                                  # all
pytest backend/tests/test_tools.py                     # one file
pytest backend/tests/test_tools.py::TestTranspose -v   # one class/test
python -m backend.tests.eval_runner                    # golden-songs eval harness
```

`backend/tests/test_pipeline.py` needs `backend/tests/audio/test_song.mp3` to exist; it is skipped otherwise.

Frontend (Next.js 16 — see warning below):

```bash
cd frontend/web
npm run dev      # :3001
npm run build
npm run lint
```

## Architecture

### Music platform integrations (Plan v2)

Ingestion supports four submission modes; the dispatch is in
`backend/ingestion/url_resolver.classify_url`:

| Mode | Path |
|---|---|
| **File upload** | Saved to disk → AcoustID fingerprint → MBID/title/artist enrichment via `backend/ingestion/acoustid_enrich`. Free, graceful no-op if `fpcalc` or `ACOUSTID_API_KEY` missing. |
| **YouTube / youtu.be** | yt-dlp with `player_client=[web_safari,tv,web]` + EJS challenge solver via Deno (or Node) + `imageio-ffmpeg` bundled binary as fallback. Pulls `info.title` + `info.uploader` for the player header. |
| **YouTube Music** | `music.youtube.com` normalized to `www.youtube.com` first (avoids `web_music` client's PO-token gymnastics), then the regular YouTube path. |
| **Spotify** | spotipy fetches title/artist/album/ISRC/cover. Audio path forks on `SPOTIFY_ALLOW_YTDLP_FALLBACK`: default `false` sets `audio_source=spotify_embed` (frontend renders the official iframe); `true` runs a `ytsearch1:` lookup and falls through to the yt-dlp branch (ToS gray area, log warning at startup). |

The merged search endpoint (`GET /api/v1/search`) hits Deezer
(no auth) + MusicBrainz (1 req/sec/IP) in parallel via
`asyncio.gather`, dedups by `(title.lower, artist.lower)`. Spotify is
NOT used for search — `/audio-features` and friends were dropped for
new apps in Nov 2024 + Feb 2026 changelog ([docs/research/music-platforms-2026.md](docs/research/music-platforms-2026.md)).

Synced lyrics come from LRCLIB (`GET /api/v1/lyrics`) — free, no
auth, returns LRC-format `synced_lyrics` + `plain_lyrics`. Cached 6h.

### Request flow (audio → output)

1. `backend/main.py` — FastAPI endpoint accepts upload or URL, hashes the file, enqueues a Taskiq job, returns a `job_id`.
2. Worker runs the LangGraph pipeline defined in `backend/graph/graph.py`:
   - `ingest` → download/validate audio
   - `features` → parallel ML extraction (librosa/madmom/demucs)
   - conditional retry edge (`should_retry`, max 2) before proceeding
   - `roman` → deterministic pitch-class → Roman numeral mapping
   - fan-out: `theory`, `instrument`, `similarity` run in **parallel**
3. Worker pushes progress JSON to Redis under the job_id; main API streams it back over SSE on `/chat` and related endpoints.
4. Final `AnalysisState` is persisted to MongoDB.

State shape lives in `backend/graph/state.py` (`AnalysisState` TypedDict). Checkpointer is `InMemorySaver` — graph state is **not** resumable across restarts; only the final result is persisted.

### LLM layer

`backend/chains/llm_factory.py` is the single source of LLM construction. It supports OpenAI, Anthropic, Gemini, Groq, OpenRouter, and Ollama, selected by `LLM_PROVIDER` env var. It wires `.with_fallbacks([fallback])` so a failed primary call automatically retries on the fallback provider (`FALLBACK_PROVIDER`/`FALLBACK_MODEL`). Always go through this factory — do not instantiate `ChatOpenAI`/`ChatAnthropic` directly in chains.

Chains compose LLM + prompt + parser:
- `theory_chain.py` — text explanation (StrOutputParser)
- `instrument_chain.py` — uses `.with_structured_output(LLMInstrumentTips)`; merges LLM tips with deterministic chord diagrams from `tools/voicings.py` in parallel
- `similarity_chain.py` — no LLM; pure 12-D chromagram cosine similarity against `backend/tests/golden_songs.json`
- `chat_chain.py` — has an explicit offline-fallback branch that returns hardcoded Scriabin color guidance if no LLM is reachable

### Deterministic tools vs. LLM output

`backend/tools/voicings.py` (chord shapes) and `backend/tools/synesthesia_colors.py` (Scriabin Circle-of-Fifths color mapping) are lookup tables, **not** LLM-generated. This is intentional — LLMs hallucinate impossible fret positions. When adding new chord data or color logic, keep it deterministic and add it here, not in a prompt.

### ML modules (`backend/ml/`)

Wrappers over external libraries — keep them thin:
- `beat_tracking.py` — madmom RNN, falls back to librosa
- `chord_detection.py` — librosa CQT chromagram + template matching against 24 major/minor templates
- `key_estimation.py` — Krumhansl-Schmuckler chroma correlation
- `stem_separation.py` — demucs `htdemucs_ft`
- `midi_transcription.py` — basic-pitch

### Observability

`backend/observability/tracing.py` provides a `@trace` context manager that emits to LangSmith when `LANGCHAIN_TRACING_V2=true`. Wrap new pipeline stages in it for consistent stage timing.

## Frontend

`frontend/web/` is **Next.js 16** + React 19 + TypeScript + Tailwind 4. Audio: Tone.js, WaveSurfer.js. State: Zustand. Next.js 16 has breaking changes vs. earlier versions — `frontend/web/AGENTS.md` instructs to read `node_modules/next/dist/docs/` before writing code there. Honor that.

## Config & env

`backend/config.py` loads via Pydantic Settings from `.env`. ~38 vars; the load-bearing ones:

- `LLM_PROVIDER`, `MODEL_NAME`, `FALLBACK_PROVIDER`, `FALLBACK_MODEL` + matching API keys
- `MONGO_URI` (must include `?replicaSet=rs0` for Taskiq), `MONGO_DB_NAME`
- `REDIS_URL` — used both as cache and Taskiq broker backend
- `AUDIO_UPLOAD_DIR`, `STEMS_DIR`, `MAX_UPLOAD_MB`
- `THEORY_TEMPERATURE`, `INSTRUMENT_TEMPERATURE`, `CREATIVE_TEMPERATURE` — per-chain sampling

## Gotchas

- The README's "What To Build When" table is curriculum scaffolding from when this repo was empty boilerplate. Don't treat it as a roadmap of what still needs implementing — most of it exists.
- `backend/cache/` is deleted in the working tree; cache logic moved to `backend/services/`. Don't recreate `backend/cache/`.
- `frontend/stitch-prompts.md` is also deleted — frontend prompts no longer live there.
- System dep: `ffmpeg` must be installed (`apt install ffmpeg` / `brew install ffmpeg`). The Dockerfile handles this; local devs must install manually.
