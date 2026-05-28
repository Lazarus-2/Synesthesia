# Synesthesia — Project Status

> **Last updated:** 2026-05-28  
> **Status:** Core MVP Complete ✅ — Polish & Production Hardening Remaining

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    Next.js Frontend (:3000)                  │
│  ┌─────────┐  ┌───────────┐  ┌──────────┐  ┌────────────┐  │
│  │ Upload  │  │ Analyzing │  │  Player  │  │   Chat     │  │
│  │ Modal   │  │   View    │  │  View    │  │   Panel    │  │
│  └────┬────┘  └─────┬─────┘  └────┬─────┘  └─────┬──────┘  │
│       │             │ SSE         │               │         │
│       │  Zustand Stores (Analysis, Player, Chat, App)       │
└───────┼─────────────┼─────────────┼───────────────┼─────────┘
        │             │             │               │
        ▼             ▼             ▼               ▼
┌─────────────────────────────────────────────────────────────┐
│                  FastAPI Backend (:8000)                     │
│  POST /analyze  │  GET /jobs/{id}/progress (SSE)            │
│  POST /chat/stream  │  GET /analyze/{id}                    │
│  GET /chat/history/{id}  │  POST /user                      │
└───────┬─────────────┬───────────────────────────────────────┘
        │             │
   ┌────▼────┐   ┌────▼──────────────────────────┐
   │  Redis  │   │  Taskiq Worker (Background)    │
   │ Cache + │   │  ┌──────────────────────────┐  │
   │ Queue   │◄──│  │  LangGraph Pipeline      │  │
   └────┬────┘   │  │  ingest → detect_chords  │  │
        │        │  │  → theory → instrument   │  │
        │        │  └──────────┬───────────────┘  │
        │        └─────────────┼──────────────────┘
        │                      │
   ┌────▼────┐           ┌─────▼──────┐
   │ MongoDB │           │  Ollama    │
   │ Storage │           │  llama3.2  │
   └─────────┘           └────────────┘
```

### Tech Stack

| Layer             | Technology                                      |
|-------------------|-------------------------------------------------|
| **Frontend**      | Next.js 15 + React 19 + TypeScript + Tailwind   |
| **State Mgmt**    | Zustand (4 stores)                               |
| **Backend API**   | FastAPI + Uvicorn                                |
| **Task Queue**    | Taskiq + Redis (ListQueueBroker)                 |
| **AI Pipeline**   | LangGraph (4-node DAG)                           |
| **LLM**          | Ollama (llama3.2, local inference)                |
| **Audio ML**      | librosa (chords/beats), basic-pitch, demucs       |
| **Database**      | MongoDB (Motor async driver)                     |
| **Cache**         | Redis (HybridCache wrapper)                      |
| **Audio Waveform**| WaveSurfer.js                                    |

---

## ✅ Completed Work

### Backend — Core Pipeline

- [x] **LangGraph Analysis Pipeline** — 4-node DAG: `ingest_node` → `detect_chords_node` → `theory_node` → `instrument_node`
- [x] **Audio Feature Extraction** — librosa-based chord detection, beat tracking, key/tempo estimation
- [x] **LLM Theory Analysis** — Structured output via Ollama (llama3.2) for roman numeral analysis, theory explanation, and instrument guides
- [x] **File Upload + Deduplication** — SHA-1 hash-based dedup, streaming upload with size validation
- [x] **MongoDB Persistence** — Song analyses stored permanently with Motor async driver
- [x] **Redis Caching** — HybridCache layer for session data and analysis results (24h TTL)
- [x] **SSE Progress Streaming** — Real-time progress events from worker → frontend via `GET /jobs/{id}/progress`
- [x] **Chat/AI Assistant** — Streaming SSE chat with conversation history in MongoDB
- [x] **User Profiles** — CRUD for user preferences (instrument, difficulty)
- [x] **Worker Error Recovery** — `RedisAsyncResultBackend` + try-except in pipeline + 180s SSE timeout
- [x] **Incremental Progress Updates** — Pipeline reports 0% → 5% → 80% → 90% → 100% stages

### Backend — Bug Fixes Applied

- [x] **Bug 1:** `file_hash_val` NameError — initialized to `None` at top of `/analyze`
- [x] **Bug 2:** Chat payload mismatch — frontend now sends `{ message, history }` matching `ChatRequest`
- [x] **Bug 3:** Incremental progress — `_progress()` helper added in `run_analysis_pipeline`
- [x] **Bug 4:** Missing TypeScript fields — `SongAnalysis` type updated with `beats`, `time_signature`, `instrument_guides`
- [x] **Bug 5:** Worker crash recovery — `RedisAsyncResultBackend` + SSE timeout fallback

### Frontend — Stitch UI Rebuild

- [x] **Design System** — `globals.css` with full Stitch tokens: amber `#ffb547` primary, violet `#571bc1` secondary, navy `#0f131e` background, glassmorphism panels
- [x] **Landing Page** — Full-screen hero with gradient headline, glassmorphic upload zone, drag-and-drop + YouTube URL input, sample song cards
- [x] **Analyzing View** — Step-by-step animated progress (Listening → Detecting Chords → Separating Stems → Generating Guide) with checkmarks
- [x] **Player Layout** — 12-column grid: 8-col waveform/chords left, 4-col tabbed panel right
- [x] **Header** — Song title, artist, key/BPM/time-signature badges
- [x] **Waveform Player** — WaveSurfer.js with transport controls (play/pause, time display)
- [x] **Chord Timeline** — Glassmorphic chord cards with active highlight and color coding
- [x] **PlayPanel + Fretboard** — SVG-based guitar fretboard with dynamic finger dots, X/O markers, capo badge, strum pattern visualization
- [x] **Theory Panel** — Roman numeral progression display + AI Insight callout
- [x] **Stem Mixer** — Interactive vertical sliders with mute toggles for Vocals/Drums/Bass/Other
- [x] **Chat Panel** — Streaming AI assistant with markdown support
- [x] **Settings Panel** — LLM provider selection, instrument/difficulty preferences
- [x] **Bottom Bar** — Fixed transport controls: speed (0.5x–2.0x), pitch shift, rewind/loop/forward, Practice Mode toggle
- [x] **TypeScript Type Safety** — All interfaces aligned with backend Pydantic schemas

### Verification

- [x] **`npm run build`** — Passes cleanly with no TypeScript errors
- [x] **End-to-end test** — File upload → Taskiq worker → Ollama inference → MongoDB save → SSE completion (verified 2× with `test_api.py`)
- [x] **Mock worker test** — Browser subagent verified fretboard rendering with hard-coded data
- [x] **Real Ollama test** — llama3.2 correctly generated chord diagrams (`F: [1,3,3,2,1,1]`, `A: [-1,0,2,2,2,0]`), strum patterns (`D DU UDU`), and theory explanations

---

## 🔲 Pending / Not Yet Done

### High Priority

| Item | Description | Effort |
|------|-------------|--------|
| **YouTube URL support** | Backend has `youtube_url` param but no `yt-dlp` download logic in the pipeline — submitting a YouTube URL currently fails | Medium |
| **Stem separation (Demucs)** | `demucs` is in requirements but never called in the pipeline — stems are not actually split | Medium |
| **Audio playback from server** | Frontend doesn't fetch the uploaded audio file back — `WaveformPlayer` needs a URL to the stored file from the backend (e.g. `/storage/uploads/{filename}`) | Small |
| **SSE `done` payload parsing** | `useAnalysisStore` reads `data.analysis` from SSE but the SSE `done` event is a full `AnalyzeResponse` JSON — need to verify the nested `analysis` object deserializes correctly on the frontend | Small |
| **Practice Mode** | Bottom bar has a "Practice Mode" toggle button but no functionality behind it (metronome, loop section, slow-down) | Large |

### Medium Priority

| Item | Description | Effort |
|------|-------------|--------|
| **Waveform gradient styling** | Current WaveSurfer uses default colors — Stitch design calls for amber→coral gradient bars with purple glow playhead | Small |
| **Song structure ribbon** | Stitch design shows Intro/Verse/Chorus/Outro colored ribbon above waveform — `sections` data exists in schema but not visualized | Medium |
| **Chord timeline polish** | Current timeline is functional but lacks the Stitch "past/current/future" size scaling effect on active chords | Small |
| **Chat context injection** | Chat doesn't send the current analysis context to the LLM — responses are generic, not song-aware | Medium |
| **Error state recovery in UI** | When SSE reports `error`, the `AnalyzingView` shows it but there's no "Retry" button to re-submit | Small |

### Low Priority / Nice-to-Have

| Item | Description | Effort |
|------|-------------|--------|
| **Multi-instrument support** | Fretboard only renders guitar — piano/ukulele/bass chord diagrams need separate SVG templates | Large |
| **Library/history page** | No way to browse previously analyzed songs | Medium |
| **User authentication** | User profiles exist but no auth — anyone can create/read any user | Medium |
| **CI/CD pipeline** | No GitHub Actions, no automated tests beyond `test_api.py` | Medium |
| **Docker compose** | `docker-compose.yml` exists but hasn't been tested end-to-end | Small |
| **Production deployment** | No Cloud Run / deployment config verified | Medium |
| **Rate limiting** | No API rate limiting on `/analyze` or `/chat` | Small |
| **README update** | Current README still references "SoundBreak Starter" boilerplate | Small |

---

## ⚠️ Known Issues

1. **YouTube analysis fails silently** — The `youtube_url` field is accepted by the API but no download handler exists in `ingest_node`. Submitting a URL will cause an error in the worker.

2. **Audio file not served back to frontend** — After uploading, the file is saved to `./storage/uploads/` but there's no static file serving endpoint. The `WaveformPlayer` component needs a URL to play the audio.

3. **SSE progress stays at 5%** — The LangGraph `ainvoke()` call is a single blocking operation. Progress jumps from 5% ("Loading audio file") to 80% ("Building results") with no intermediate updates during the actual LLM inference (which can take 30-60 seconds).

4. **`beats` type mismatch** — Backend sends `BeatEvent` objects (`{ time, beat_number }`), but frontend `SongAnalysis.beats` is typed as `number[]`. The data arrives but may not render correctly.

5. **Stitch "Newsreader" font** — The original Stitch design used Newsreader serif for headlines. Currently only Inter is loaded. The `font-headline` class is defined in CSS but points to Inter.

---

## 🚀 Running the Project

### Prerequisites
- Python 3.12+, Node.js 18+
- Redis server running on `localhost:6379`
- MongoDB running on `localhost:27017`
- Ollama installed with `llama3.2` model pulled

### Start All Services

```bash
# Terminal 1 — Ollama
ollama serve

# Terminal 2 — Backend API
cd Synesthesia
source .venv/bin/activate
uvicorn backend.main:app --port 8000

# Terminal 3 — Taskiq Worker
cd Synesthesia
source .venv/bin/activate
taskiq worker backend.worker:broker backend.main

# Terminal 4 — Frontend
cd Synesthesia/frontend/web
npm run dev
```

### Quick API Test

```bash
cd Synesthesia
source .venv/bin/activate
python test_api.py
```

---

## File Map

```
Synesthesia/
├── backend/
│   ├── main.py                  # FastAPI app + endpoints + Taskiq task
│   ├── worker.py                # Taskiq broker config (Redis)
│   ├── config.py                # Settings (env vars, paths, model config)
│   ├── schemas.py               # Pydantic models (ChordEvent, SongAnalysis, InstrumentGuide, etc.)
│   ├── models.py                # MongoDB document models
│   ├── database.py              # Motor (async MongoDB) connection
│   ├── graph/
│   │   ├── state.py             # LangGraph state definition
│   │   ├── nodes.py             # Pipeline nodes (ingest, chords, theory, instrument)
│   │   └── graph.py             # Graph assembly + routing
│   ├── chains/
│   │   └── chat_chain.py        # LLM chat with streaming
│   ├── tools/
│   │   └── synesthesia_colors.py # Chord-to-color mapping
│   ├── services/
│   │   └── cache.py             # HybridCache (Redis wrapper)
│   ├── prompts/                 # Prompt templates for LLM
│   ├── ml/                      # Pre-trained model configs
│   └── observability/           # Tracing/logging setup
│
├── frontend/web/
│   └── src/
│       ├── app/
│       │   ├── page.tsx         # Main page (routing: Upload → Analyzing → Player)
│       │   ├── layout.tsx       # Root layout (fonts, meta)
│       │   └── globals.css      # Full Stitch design system tokens
│       ├── components/
│       │   ├── Upload/
│       │   │   └── UploadModal.tsx     # Landing page hero + file upload
│       │   ├── Analysis/
│       │   │   ├── AnalyzingView.tsx   # Animated step-by-step progress
│       │   │   ├── ChordTimeline.tsx   # Chord card strip
│       │   │   └── TheoryPanel.tsx     # Roman numerals + AI insight
│       │   ├── Player/
│       │   │   ├── WaveformPlayer.tsx  # WaveSurfer.js waveform
│       │   │   ├── PlayPanel.tsx       # Fretboard + strum pattern
│       │   │   ├── StemMixer.tsx       # Stem volume sliders
│       │   │   └── BottomBar.tsx       # Transport controls
│       │   ├── Chat/
│       │   │   └── ChatPanel.tsx       # AI assistant chat
│       │   ├── Layout/
│       │   │   └── Header.tsx          # Top nav bar
│       │   └── Settings/
│       │       └── SettingsPanel.tsx    # Preferences panel
│       ├── store/
│       │   ├── useAnalysisStore.ts     # Analysis job + SSE state
│       │   ├── usePlayerStore.ts       # Audio playback state
│       │   ├── useChatStore.ts         # Chat messages + streaming
│       │   └── useAppStore.ts          # UI state (tabs, preferences)
│       └── types/
│           └── index.ts               # All TypeScript interfaces
│
├── storage/                     # Runtime: uploaded files + stems
├── test.wav                     # Test audio file
├── test_api.py                  # API integration test script
├── .env                         # Environment config
├── requirements.txt             # Python dependencies
├── docker-compose.yml           # Docker setup (Redis + MongoDB + App)
└── Dockerfile                   # Backend container
```
