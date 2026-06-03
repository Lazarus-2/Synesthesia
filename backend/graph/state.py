"""
LangGraph shared state.
Vault ref: 04-LangGraph-Core/02-State-Nodes-Edges.md
"""

from __future__ import annotations

from typing import Annotated, TypedDict

from langgraph.graph.message import add_messages

from backend.schemas import (
    BeatEvent,
    ChordEvent,
    Difficulty,
    Instrument,
    InstrumentGuide,
    RomanAnalysis,
    SongSection,
)


class AnalysisState(TypedDict, total=False):
    # --- Input ---
    audio_path: str
    youtube_url: str | None
    instrument: Instrument
    difficulty: Difficulty
    user_id: str | None

    # --- Derived features (Module 4 Lesson 2) ---
    key: str
    tempo: float
    chords: list[ChordEvent]
    beats: list[BeatEvent]
    sections: list[SongSection]
    stems: dict[str, str]  # {stem_name: relative_path_under_stems_dir}

    # --- LLM outputs ---
    roman: RomanAnalysis | None
    theory_explanation: str
    instrument_guide: InstrumentGuide | None
    similar_songs: list[dict]

    # --- Control flow (Module 4 Lesson 3) ---
    errors: list[str]
    retries: int

    # --- Messages (for HITL, Module 4 Lesson 4) ---
    messages: Annotated[list, add_messages]
