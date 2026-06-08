"""
LangGraph shared state.
Vault ref: 04-LangGraph-Core/02-State-Nodes-Edges.md
"""

from __future__ import annotations

import operator
from typing import Annotated, Literal, TypedDict

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


# Shared constant that couples features_node (message builder) and
# derive_status (message filter).  Defined here so both modules can import
# from backend.graph.state without introducing a circular import.
FEATURE_ERROR_PREFIX = "Feature extraction failed"

# Message appended to errors when feature extraction succeeds but chord
# detection returns an empty list (speech, silence, or non-harmonic audio).
NO_CHORDS_MESSAGE = (
    "No chords detected — the track may be speech, silence, or non-harmonic audio."
)


class AnalysisState(TypedDict, total=False):
    # --- Input ---
    audio_path: str
    youtube_url: str | None
    instrument: Instrument
    difficulty: Difficulty
    user_id: str | None

    # --- Source metadata (filled by ingest_node from yt-dlp info, AcoustID
    # match for uploads, or Spotify metadata fetch) ---
    title: str
    artist: str
    album: str
    album_art_url: str
    mbid: str  # MusicBrainz Recording ID
    spotify_id: str
    isrc: str
    audio_source: str  # "youtube" | "spotify_embed" | "upload" | "deezer_preview"

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
    # ``errors`` is an append-only degradation log: every node that degrades
    # gracefully (LLM down, demucs missing, etc.) appends a human-readable
    # string. The operator.add reducer concatenates concurrent fan-out
    # appends instead of raising InvalidUpdateError.
    errors: Annotated[list[str], operator.add]
    # ``feature_error`` is last-write-wins (NO reducer): it reflects ONLY the
    # most recent features_node attempt. ``should_retry`` reads this — not the
    # accumulated ``errors`` log — so a fail-then-succeed retry is not treated
    # as failed (FT-01).
    feature_error: str | None
    retries: int
    # Derived at fan-in by the worker: "ok" (everything ran), "degraded"
    # (deterministic analysis succeeded but a fan-out node fell back), or
    # "failed" (no usable analysis).
    # NOTE: this field is computed POST-graph in tasks.py (derive_status) and
    # is NOT written by any node inside the graph itself.
    status: Literal["ok", "degraded", "failed"]

    # --- Messages (for HITL, Module 4 Lesson 4) ---
    messages: Annotated[list, add_messages]
