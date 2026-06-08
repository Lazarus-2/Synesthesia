"""AURA agent tools — LangChain @tool wrappers over the deterministic music
tools (voicings, colors, transpose, capo, similarity, stored analysis) plus the
theory glossary. Each wrapper has an explicit pydantic ``args_schema`` so schema
conversion is stable across every LLM provider (see design §4/§7).

These wrappers are deliberately thin: all music math stays deterministic in the
underlying modules — the LLM never computes it.
"""

from __future__ import annotations

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from backend.database import get_mongodb
from backend.repositories.analysis_repo import AnalysisRepo
from backend.schemas import Instrument
from backend.tools.synesthesia_colors import get_chord_color as _get_chord_color
from backend.tools.voicings import get_chord_diagrams

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
    if not diagrams:
        return {"error": f"No voicing found for '{chord}' on {instrument}."}
    return diagrams[0].model_dump(exclude_none=True)


# ---------------------------------------------------------------------------
# B.2  get_chord_color  (Python symbol: get_chord_color_tool to avoid shadowing
#                        the imported synesthesia_colors.get_chord_color)
# ---------------------------------------------------------------------------

from backend.tools.chords import parse_chord  # noqa: E402


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
    analysis didn't detect; if a fact is absent, say so."""
    doc = await _resolve_analysis_repo().get(job_id)
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

from backend.chains.similarity_chain import find_similar  # noqa: E402


class FindSimilarArgs(BaseModel):
    analysis_job_id: str = Field(
        description="The analysis job id whose chord progression to match against the catalog."
    )


@tool(args_schema=FindSimilarArgs)
async def find_similar_songs(analysis_job_id: str) -> list[dict] | dict:
    """Find catalog songs whose chord progression is most similar to the current
    song's, using the deterministic key-aware progression embedding. Returns a
    ranked list of {title, artist, progression, score}. Use this for
    'what sounds like this?' / 'songs with similar chords' questions."""
    doc = await _resolve_analysis_repo().get(analysis_job_id)
    if not doc:
        return {"error": f"No analysis found for job_id '{analysis_job_id}'."}

    raw_chords = doc.get("chords") or []
    chords: list[str] = []
    for c in raw_chords:
        sym = c.get("chord") if isinstance(c, dict) else getattr(c, "chord", None)
        if sym:
            chords.append(sym)
    if not chords:
        return {"error": "This analysis has no chords to compare; cannot find similar songs."}

    return find_similar(chords, k=5, key=doc.get("key"))


# ---------------------------------------------------------------------------
# B.5  TOOLS list — canonical AURA tool roster
# ---------------------------------------------------------------------------

from backend.tools.capo import suggest_capo  # noqa: E402
from backend.tools.theory_glossary import lookup_theory  # noqa: E402  (Group A)
from backend.tools.transpose import transpose_progression  # noqa: E402

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
