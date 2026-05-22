"""
Chord detection using madmom's pre-trained CNN+CRF.
Vault ref: 06-Projects/05-Project-SoundBreak.md (Phase 1)

Usage:
    events = detect_chords("song.mp3")
"""
from __future__ import annotations

from pathlib import Path

from backend.schemas import ChordEvent


def detect_chords(audio_path: str | Path) -> list[ChordEvent]:
    """Return list of ChordEvent for the song.

    TODO(Module 1, Lesson 2 / Phase 1):
      1. Import madmom DeepChromaChordRecognitionProcessor
      2. Run over the audio file
      3. Convert raw output (start, end, label) -> ChordEvent
      4. Normalize labels (e.g. "C:maj" -> "C", "A:min" -> "Am")
    """
    # Sketch:
    # from madmom.features.chords import (
    #     DeepChromaChordRecognitionProcessor,
    #     DeepChromaProcessor,
    # )
    # dcp = DeepChromaProcessor()
    # chord_proc = DeepChromaChordRecognitionProcessor()
    # chroma = dcp(str(audio_path))
    # raw = chord_proc(chroma)  # [(start, end, label), ...]
    # return [ChordEvent(start=s, end=e, chord=_normalize(l)) for s, e, l in raw]
    raise NotImplementedError("Fill in during Module 1, Lesson 2")


def _normalize(madmom_label: str) -> str:
    """Convert madmom labels like 'C:maj', 'A:min7' to user-facing 'C', 'Am7'."""
    # TODO: implement mapping table
    return madmom_label
