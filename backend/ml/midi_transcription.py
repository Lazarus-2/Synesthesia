"""
Audio-to-MIDI using Spotify's basic-pitch. Great for isolated bass/vocal stems.
Vault ref: 06-Projects/05-Project-SoundBreak.md (Phase 2)
"""
from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def transcribe_to_midi(audio_path: str | Path, out_midi: str | Path) -> Path | None:
    """Convert a monophonic/polyphonic stem to MIDI using basic-pitch."""
    audio_path = Path(audio_path)
    out_midi = Path(out_midi)
    
    if out_midi.exists():
        return out_midi

    try:
        from basic_pitch.inference import predict_and_save
        from basic_pitch import ICASSP_2022_MODEL_PATH
    except ImportError:
        logger.warning("basic-pitch not installed, skipping MIDI transcription")
        return None

    logger.info(f"Running basic-pitch on {audio_path}")
    
    out_dir = out_midi.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    
    try:
        predict_and_save(
            [str(audio_path)],
            output_directory=str(out_dir),
            save_midi=True,
            sonify_midi=False,
            save_model_outputs=False,
            save_notes=False,
            model_or_model_path=ICASSP_2022_MODEL_PATH,
        )
        
        # basic_pitch outputs files named like the input but with _basic_pitch.mid
        expected_out = out_dir / f"{audio_path.stem}_basic_pitch.mid"
        if expected_out.exists():
            expected_out.rename(out_midi)
            
        return out_midi if out_midi.exists() else None
    except Exception as e:
        logger.error(f"basic-pitch failed: {e}")
        return None
