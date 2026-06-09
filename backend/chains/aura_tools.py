"""AURA agent tools — LangChain @tool wrappers over the deterministic music
tools (voicings, colors, transpose, capo, similarity, stored analysis) plus the
theory glossary. Each wrapper has an explicit pydantic ``args_schema`` so schema
conversion is stable across every LLM provider (see design §4/§7).

These wrappers are deliberately thin: all music math stays deterministic in the
underlying modules — the LLM never computes it.
"""

from __future__ import annotations

from contextvars import ContextVar

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from backend.chains.similarity_chain import find_similar
from backend.database import get_mongodb
from backend.repositories.analysis_repo import AnalysisRepo
from backend.schemas import Instrument
from backend.tools.capo import suggest_capo
from backend.tools.chords import parse_chord
from backend.tools.synesthesia_colors import get_chord_color as _get_chord_color
from backend.tools.theory_glossary import lookup_theory
from backend.tools.transpose import transpose_progression
from backend.tools.voicings import get_chord_diagrams

# ---------------------------------------------------------------------------
# Ownership context variable (I-1)
# ---------------------------------------------------------------------------

current_user_id: ContextVar[str | None] = ContextVar(
    "aura_current_user_id", default=None
)
"""Set by the chat endpoint (Group D) before invoking the agent so the
analysis-reading tools enforce per-user ownership via get_owned; the LLM
cannot influence it.

Usage::

    token = current_user_id.set(authenticated_user.id)
    try:
        result = await agent.ainvoke(...)
    finally:
        current_user_id.reset(token)
"""

# ---------------------------------------------------------------------------
# B.1  get_chord_voicing
# ---------------------------------------------------------------------------


class ChordVoicingArgs(BaseModel):
    chord: str = Field(description="Chord symbol, e.g. 'C', 'Am7', 'G/B'.")
    instrument: Instrument = Field(
        default="guitar",
        description="Instrument: guitar, piano, ukulele, or bass.",
    )


@tool(args_schema=ChordVoicingArgs)
def get_chord_voicing(chord: str, instrument: str = "guitar") -> dict:
    """Look up a playable voicing (fret/finger shape or piano keys) for a single
    chord on the given instrument. Returns the deterministic diagram, never a
    guessed shape. Use this when the user asks how to play a chord."""
    diagrams = get_chord_diagrams([chord], instrument=instrument)  # type: ignore[arg-type]
    # G3.3: get_chord_diagrams always returns a diagram; check no_voicing flag.
    if not diagrams or diagrams[0].no_voicing:
        return {"error": f"No voicing found for '{chord}' on {instrument}."}
    return diagrams[0].model_dump(exclude_none=True)


# ---------------------------------------------------------------------------
# B.2  get_chord_color  (Python symbol: get_chord_color_tool to avoid shadowing
#                        the imported synesthesia_colors.get_chord_color)
# ---------------------------------------------------------------------------


class ChordColorArgs(BaseModel):
    chord: str = Field(description="Chord symbol, e.g. 'Am', 'Cmaj7', 'G/B'.")


@tool("get_chord_color", args_schema=ChordColorArgs)
def get_chord_color_tool(chord: str) -> dict:
    """Map a chord to its Scriabin synesthetic color (a hex string) using the
    deterministic color engine. Returns the parsed root alongside the color so
    the answer can cite which note drove the hue. Use this for 'what color is
    this chord' / mood-color questions."""
    parts = parse_chord(chord)
    color = _get_chord_color(chord)
    return {"chord": chord, "root": parts.root, "quality": parts.quality, "color": color}


# ---------------------------------------------------------------------------
# B.3  get_song_analysis  (read-only; async repo resolved lazily for testing)
# ---------------------------------------------------------------------------


def _resolve_analysis_repo() -> AnalysisRepo:
    """Build an AnalysisRepo bound to the live Mongo handle.

    Isolated in its own function so tests can monkeypatch it without a DB.
    """
    return AnalysisRepo(get_mongodb())


class SongAnalysisArgs(BaseModel):
    job_id: str = Field(description="The analysis job id for the current song.")


@tool(args_schema=SongAnalysisArgs)
async def get_song_analysis(job_id: str) -> dict:
    """Read the deterministic, already-computed analysis facts for a song
    (key, tempo, chord symbols in order, Roman numerals, section names, and the
    analysis trust status). READ-ONLY ground truth — never invent facts the
    analysis didn't detect; if a fact is absent, say so.

    Most analysis facts (key, tempo, chords, Roman numerals) are already in
    the system prompt when a song is loaded; call this tool when you need
    section names, the analysis trust status, or when no analysis context was
    injected.
    """
    repo = _resolve_analysis_repo()
    uid = current_user_id.get()
    doc = await repo.get_owned(job_id, uid) if uid is not None else await repo.get(job_id)
    if not doc:
        return {"error": f"No analysis found for job_id '{job_id}'."}

    raw_chords = doc.get("chords") or []
    chord_syms: list[str] = []
    for c in raw_chords:
        sym = c.get("chord") if isinstance(c, dict) else getattr(c, "chord", None)
        if sym and sym not in chord_syms:
            chord_syms.append(sym)

    roman = doc.get("roman") or {}
    roman_prog = roman.get("progression", []) if isinstance(roman, dict) else []
    sections = [
        (s.get("name") if isinstance(s, dict) else getattr(s, "name", None))
        for s in (doc.get("sections") or [])
    ]

    return {
        "job_id": job_id,
        "title": doc.get("title"),
        "artist": doc.get("artist"),
        "key": doc.get("key"),
        "tempo": doc.get("tempo"),
        "status": doc.get("status", "ok"),
        "chords": chord_syms,
        "roman": roman_prog,
        "sections": [s for s in sections if s],
    }


# ---------------------------------------------------------------------------
# B.4  find_similar_songs  (uses _resolve_analysis_repo + similarity_chain)
# ---------------------------------------------------------------------------


class FindSimilarArgs(BaseModel):
    analysis_job_id: str = Field(
        description=(
            "The analysis job id for the CURRENT song — the same value used by "
            "get_song_analysis. This is injected by the system from the loaded "
            "song context; do NOT ask the user for it."
        )
    )


@tool(args_schema=FindSimilarArgs)
async def find_similar_songs(analysis_job_id: str) -> list[dict] | dict:
    """Find catalog songs whose chord progression is most similar to the CURRENT
    song's, using the deterministic key-aware progression embedding. The
    analysis_job_id is the same id used by get_song_analysis — it identifies the
    currently loaded song and is provided by the system, not the user. Returns a
    ranked list of {title, artist, progression, score}. Use this for
    'what sounds like this?' / 'songs with similar chords' questions."""
    repo = _resolve_analysis_repo()
    uid = current_user_id.get()
    doc = await repo.get_owned(analysis_job_id, uid) if uid is not None else await repo.get(analysis_job_id)
    if not doc:
        return {"error": f"No analysis found for job_id '{analysis_job_id}'."}

    raw_chords = doc.get("chords") or []
    chords: list[str] = []
    for c in raw_chords:
        sym = c.get("chord") if isinstance(c, dict) else getattr(c, "chord", None)
        if sym and sym not in chords:  # dedupe preserving order (m-2)
            chords.append(sym)
    if not chords:
        return {"error": "This analysis has no chords to compare; cannot find similar songs."}

    return find_similar(chords, k=5, key=doc.get("key"))


# ---------------------------------------------------------------------------
# B.5  TOOLS list — canonical AURA tool roster
# ---------------------------------------------------------------------------

# Canonical AURA tool roster. ORDER is part of the contract (cross-group
# references index by name, but the order keeps the system prompt deterministic).
TOOLS = [
    transpose_progression,
    suggest_capo,
    get_chord_voicing,
    get_chord_color_tool,
    find_similar_songs,
    get_song_analysis,
    lookup_theory,
]
