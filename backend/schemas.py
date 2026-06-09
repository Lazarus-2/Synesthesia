"""
Pydantic schemas -- the "types" of the system.
Vault refs:
  - 01-LLM-Foundations/03-Prompting-Patterns.md (structured output)
  - 02-LLM-Architecture/04-Memory-Context-Strategy.md (UserProfile)
  - 03-LangChain-Core/02-Models-Prompts-LCEL.md (with_structured_output)

You will add/refine fields as you progress. Start with ChordEvent + SongAnalysis.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

# =============================================================================
# Core music primitives -- Module 1
# =============================================================================


class ChordEvent(BaseModel):
    """A single chord at a point in time."""

    start: float = Field(description="Start time in seconds")
    end: float = Field(description="End time in seconds")
    chord: str = Field(description="Chord symbol, e.g. 'Cmaj7', 'Am', 'G/B'")
    confidence: float = Field(ge=0.0, le=1.0, default=1.0)
    color: str = Field(default="#8B5CF6", description="Synesthetic color mapped to this chord")


class BeatEvent(BaseModel):
    time: float
    beat_number: int = Field(description="1, 2, 3, 4 for 4/4 time")


class SongSection(BaseModel):
    """Intro, verse, chorus, bridge, outro, etc."""

    name: str
    start: float
    end: float


# =============================================================================
# Analysis output -- Module 1/3
# =============================================================================


class RomanEntry(BaseModel):
    """Time-aligned per-chord Roman-numeral entry."""

    chord: str = Field(description="Original chord symbol, e.g. 'G7'")
    numeral: str = Field(description="Figured-bass Roman numeral, e.g. 'V7', 'V7/V', 'I6'")
    function: str = Field(
        description="Harmonic function: tonic/dominant/subdominant/supertonic/"
                    "submediant/mediant/leading_tone/secondary_dominant/chromatic"
    )
    inversion: int = Field(default=0, description="Inversion number (0=root, 1=1st, etc.)")
    is_secondary: bool = Field(default=False, description="True if secondary dominant (V/V etc.)")
    is_borrowed: bool = Field(default=False, description="True if borrowed / modal-mixture chord")
    cadence: str | None = Field(
        default=None,
        description="Cadence type ending on this chord: PAC/IAC/half/deceptive/plagal or None",
    )
    start: float = Field(description="Start time in seconds")
    end: float = Field(description="End time in seconds")


class RomanAnalysis(BaseModel):
    """Roman-numeral analysis of the progression."""

    key: str
    # Legacy fields — kept for back-compat; populated from entries.
    progression: list[str] = Field(
        default_factory=list,
        description="Full per-chord numeral list (no dedup, no truncation). e.g. ['I', 'V7', 'vi', 'IV']",
    )
    function: list[str] = Field(
        default_factory=list,
        description="Per-chord function list aligned with progression.",
    )
    # Optional ≤8-item summary for UI chips that need brevity
    summary_progression: list[str] | None = Field(
        default=None,
        description="Deduped + truncated to ≤8 numerals for compact UI display.",
    )
    # Enriched per-chord entries (music21 path)
    entries: list[RomanEntry] = Field(
        default_factory=list,
        description="Time-aligned per-chord entries with full figured-bass data.",
    )
    cadences: list[dict] = Field(
        default_factory=list,
        description="Detected cadences: {type: PAC|IAC|half|deceptive|plagal, index: int}",
    )
    modulations: list[dict] = Field(
        default_factory=list,
        description="Detected key modulations: {to_key: str, at_index: int}",
    )


class SongAnalysis(BaseModel):
    """Top-level result returned to the client."""

    title: str | None = None
    artist: str | None = None
    duration: float

    key: str = Field(description="e.g. 'C major', 'A minor'")
    tempo: float = Field(description="BPM")
    time_signature: str = Field(default="4/4")

    chords: list[ChordEvent]
    beats: list[BeatEvent] = []
    sections: list[SongSection] = []

    roman: RomanAnalysis | None = None
    vibe_palette: list[str] = Field(
        default_factory=list,
        description="Synesthetic color palette representing the song's key/vibe",
    )

    theory_explanation: str | None = None
    instrument_guides: dict[str, InstrumentGuide] = Field(default_factory=dict)

    # Relative paths to separated stems (vocals/drums/bass/other), keyed by
    # stem name. Empty when stem separation was disabled or unavailable.
    # Frontend builds the URL as ``/api/v1/stems/{job_id}/{stem_name}``.
    stems: dict[str, str] = Field(default_factory=dict)


# =============================================================================
# Instrument guides -- Module 3
# =============================================================================

Instrument = Literal["guitar", "piano", "ukulele", "bass"]
Difficulty = Literal["beginner", "intermediate", "advanced"]


class ChordDiagram(BaseModel):
    """One chord shape for one instrument."""

    chord: str
    instrument: Instrument
    # Guitar: list of 6 fret numbers (low-E to high-E); -1 = mute, 0 = open
    frets: list[int] | None = None
    fingers: list[int] | None = None
    # Piano: list of note names the left/right hand plays
    right_hand: list[str] | None = None
    left_hand: list[str] | None = None


class InstrumentGuide(BaseModel):
    instrument: Instrument
    difficulty: Difficulty
    chord_diagrams: list[ChordDiagram]
    strum_pattern: str | None = None
    tips: list[str] = Field(default_factory=list)
    capo: int | None = Field(default=None, description="Capo fret (guitar/uke)")


# =============================================================================
# User & session -- Module 2/4
# =============================================================================


class UserProfile(BaseModel):
    """Semantic memory for personalization. Module 2 Lesson 4."""

    user_id: str
    instrument: Instrument = "guitar"
    skill_level: Difficulty = "beginner"
    preferred_keys: list[str] = Field(default_factory=list)
    songs_learned: list[str] = Field(default_factory=list)
    struggles_with: list[str] = Field(default_factory=list)


# =============================================================================
# API request/response -- Module 5
# =============================================================================


class AnalyzeRequest(BaseModel):
    """Client uploads or pastes URL."""

    youtube_url: str | None = None
    instrument: Instrument = "guitar"
    difficulty: Difficulty = "beginner"
    user_id: str | None = None


class AnalyzeResponse(BaseModel):
    job_id: str
    status: Literal["queued", "processing", "done", "error"]
    analysis: SongAnalysis | None = None
    instrument_guide: InstrumentGuide | None = None
    error: str | None = None
    # Relative URL the client uses to fetch the staged audio file
    # (e.g. ``/api/v1/audio/{job_id}``). Populated when the upload path is
    # known; null for YouTube-only flows during the download phase or for
    # cached analyses we never re-staged.
    audio_url: str | None = None


# =============================================================================
# Chat (AURA, Phase 2)
# =============================================================================


class ChatRequest(BaseModel):
    """Client → /chat payload.

    Phase-2 hardening: identity (``user_id``) comes from the JWT, never the
    body; conversation ``history`` is reconstructed server-side from Mongo
    ``chat_sessions`` (a forged body history could otherwise rewrite context).
    Those two fields are intentionally absent.
    """

    message: str
    analysis_job_id: str | None = None
    session_id: str | None = None
    tutor_mode: bool = False


class ChatResponse(BaseModel):
    """Non-stream /chat reply. ``session_id`` echoes the server-owned id so a
    client that omitted it learns which session its turn was persisted to."""

    reply: str
    session_id: str | None = None
