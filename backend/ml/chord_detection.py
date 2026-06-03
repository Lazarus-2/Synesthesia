"""
Chord detection using madmom's pre-trained CNN+CRF.
Vault ref: 06-Projects/05-Project-SoundBreak.md (Phase 1)

Usage:
    events = detect_chords("song.mp3")
"""
from __future__ import annotations

import logging
from pathlib import Path

from backend.config import MAX_AUDIO_DURATION_S
from backend.schemas import ChordEvent

logger = logging.getLogger(__name__)


def detect_chords(audio_path: str | Path) -> list[ChordEvent]:
    """Return list of ChordEvent for the song using a pure Python template matching algorithm."""
    import librosa
    import numpy as np

    from backend.tools.synesthesia_colors import get_chord_color

    try:
        y, sr = librosa.load(str(audio_path), sr=22050, duration=MAX_AUDIO_DURATION_S)
        y_harmonic, _ = librosa.effects.hpss(y)
        chroma = librosa.feature.chroma_cqt(y=y_harmonic, sr=sr, hop_length=512)
    except Exception as e:
        logger.warning("Chord detection failed for %s: %s", audio_path, e)
        return []

    num_frames = chroma.shape[1]
    hop_length = 512
    time_per_frame = hop_length / sr

    # 1. Define standard pitch names
    notes = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

    # 2. Define pitch templates (12 major, 12 minor)
    # Major template (root, third, fifth) -> (0, 4, 7)
    base_major = np.array([1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0])
    # Minor template (root, minor third, fifth) -> (0, 3, 7)
    base_minor = np.array([1.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0])

    templates = {}
    for i in range(12):
        templates[f"{notes[i]}"] = np.roll(base_major, i)
        templates[f"{notes[i]}m"] = np.roll(base_minor, i)

    # 3. Classify each frame (store chord + confidence score)
    frame_chords = []   # (chord_name, confidence_score)
    for t in range(num_frames):
        chroma_vec = chroma[:, t]
        chroma_norm = np.linalg.norm(chroma_vec)
        if chroma_norm == 0:
            frame_chords.append(("N.C.", 0.0))
            continue

        chroma_vec = chroma_vec / chroma_norm
        
        best_score = -1.0
        best_chord = "N.C."

        for chord_name, template in templates.items():
            temp_norm = np.linalg.norm(template)
            score = np.dot(chroma_vec, template) / (chroma_norm * temp_norm)
            if score > best_score:
                best_score = score
                best_chord = chord_name
        
        # Clamp confidence to [0, 1]
        confidence = max(0.0, min(1.0, float(best_score)))
        frame_chords.append((best_chord, confidence))

    # 4. Smooth chord transitions (majority vote filter of size 15 to prevent flickering)
    smoothed = []  # (chord_name, avg_confidence)
    window_size = 15
    half_w = window_size // 2
    for i in range(num_frames):
        start_idx = max(0, i - half_w)
        end_idx = min(num_frames, i + half_w + 1)
        neighbors = frame_chords[start_idx:end_idx]
        neighbor_chords = [n[0] for n in neighbors]
        # Most frequent chord in the window
        most_common = max(set(neighbor_chords), key=neighbor_chords.count)
        # Average confidence of frames matching the winning chord
        matching_scores = [n[1] for n in neighbors if n[0] == most_common]
        avg_conf = sum(matching_scores) / len(matching_scores) if matching_scores else 0.5
        smoothed.append((most_common, avg_conf))

    # 5. Segment frames into events
    events = []
    if not smoothed:
        return events

    curr_chord, curr_conf = smoothed[0]
    start_time = 0.0
    conf_accum = [curr_conf]  # accumulate confidence scores for averaging

    for i in range(1, num_frames):
        chord, conf = smoothed[i]
        if chord != curr_chord:
            end_time = i * time_per_frame
            avg_confidence = sum(conf_accum) / len(conf_accum)
            events.append(
                ChordEvent(
                    start=float(start_time),
                    end=float(end_time),
                    chord=curr_chord,
                    confidence=round(avg_confidence, 3),
                    color=get_chord_color(curr_chord)
                )
            )
            curr_chord = chord
            start_time = end_time
            conf_accum = [conf]
        else:
            conf_accum.append(conf)

    # Add final segment
    avg_confidence = sum(conf_accum) / len(conf_accum)
    events.append(
        ChordEvent(
            start=float(start_time),
            end=float(num_frames * time_per_frame),
            chord=curr_chord,
            confidence=round(avg_confidence, 3),
            color=get_chord_color(curr_chord)
        )
    )

    return events
