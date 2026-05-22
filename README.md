# SoundBreak Starter -- Code Along With The Vault

This is the boilerplate scaffolding for the **SoundBreak** project.
You fill in each file as you complete the corresponding lesson in the vault.

See the project spec: [[../06-Projects/05-Project-SoundBreak]]

---

## Setup

```bash
# 1. Create virtual environment
python -m venv .venv
source .venv/bin/activate       # macOS/Linux
# .venv\Scripts\activate        # Windows

# 2. Install dependencies (heavy! takes a few minutes)
pip install -r requirements.txt

# 3. Install ffmpeg (system dependency for audio)
# macOS:  brew install ffmpeg
# Ubuntu: sudo apt install ffmpeg
# Windows: download from ffmpeg.org

# 4. Copy environment template and fill in your keys
cp .env.example .env
# Edit .env and add OPENAI_API_KEY

# 5. Run the API (once main.py has code)
uvicorn backend.main:app --reload
```

---

## Folder Structure

```
soundbreak-starter/
├── backend/
│   ├── main.py               # FastAPI entry -- Module 5
│   ├── config.py             # Env loading -- Module 5
│   ├── schemas.py            # Pydantic models -- Module 1
│   ├── prompts/              # Prompt templates -- Module 1
│   ├── ml/                   # Pre-trained ML models -- Module 1/2
│   ├── chains/               # LangChain LCEL chains -- Module 3
│   ├── tools/                # Music theory tools -- Module 3
│   ├── graph/                # LangGraph pipeline -- Module 4
│   ├── observability/        # Tracing + logging -- Module 2
│   └── cache/                # Redis caching -- Module 5
├── tests/
│   ├── golden_songs.json     # Eval dataset -- Module 1
│   ├── test_tools.py         # Unit tests -- Module 3
│   ├── test_pipeline.py      # Integration -- Module 3
│   └── eval_runner.py        # CI eval -- Module 5
└── frontend/                 # Next.js app (Phase 4)
```

---

## What To Build When

Every file has a `TODO` comment pointing to the vault lesson where you fill it in.
Follow this order:

| # | Vault Lesson | Files to Fill |
|---|---|---|
| 1 | 01/02 Tokens & Embeddings | `backend/schemas.py` (partial) |
| 2 | 01/03 Prompting | `backend/prompts/*.py` |
| 3 | 01/04 Sampling | `backend/config.py` (sampling configs) |
| 4 | 01/05 Evaluation | `tests/golden_songs.json`, `tests/eval_runner.py` |
| 5 | 02/02 RAG | `backend/chains/similarity_chain.py` (design) |
| 6 | 02/03 Agent Patterns | `backend/graph/nodes.py` (tool registry) |
| 7 | 02/04 Memory | `backend/schemas.py` (UserProfile) |
| 8 | 02/05 Observability | `backend/observability/tracing.py` |
| 9 | 03/02 LCEL | `backend/chains/theory_chain.py`, `instrument_chain.py` |
| 10 | 03/03 Retrieval | `backend/chains/similarity_chain.py` |
| 11 | 03/04 Tools | `backend/tools/*.py` |
| 12 | 03/05 Testing | `tests/test_tools.py`, `test_pipeline.py` |
| 13 | 04/02 State & Nodes | `backend/graph/state.py`, `nodes.py` |
| 14 | 04/03 Routing | `backend/graph/graph.py` (conditional edges) |
| 15 | 04/04 Checkpoints | `backend/graph/graph.py` (checkpointer) |
| 16 | 04/05 Patterns | Refactor full `backend/graph/` to use patterns |
| 17 | 05/02 Cost/Latency | `backend/config.py` (budgets) |
| 18 | 05/03 Deployment | `backend/main.py`, `Dockerfile` |
| 19 | 05/04 Security | `backend/main.py` (validation middleware) |
| 20 | 05/05 CI | `.github/workflows/eval.yml` |

---

## First Steps (Before Starting Module 1)

1. Run `pip install -r requirements.txt` (grab a coffee)
2. Put a test song file in `tests/audio/test_song.mp3`
3. Verify: `python -c "import madmom, librosa, demucs, basic_pitch; print('ok')"`
4. Open Module 1 Lesson 2 and start filling in `backend/schemas.py`
