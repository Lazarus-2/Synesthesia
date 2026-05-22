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

class RomanAnalysis(BaseModel):
    """Roman-numeral analysis of the progression."""
    key: str
    progression: list[str] = Field(description="e.g. ['I', 'V', 'vi', 'IV']")
    function: list[str] = Field(description="e.g. ['tonic', 'dominant', 'submediant', 'subdominant']")


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

    theory_explanation: str | None = None
    instrument_guides: dict[str, InstrumentGuide] = Field(default_factory=dict)


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
