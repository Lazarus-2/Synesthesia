"""
Audio-to-MIDI using Spotify's basic-pitch. Great for isolated bass/vocal stems.
Vault ref: 06-Projects/05-Project-SoundBreak.md (Phase 2)
"""
from __future__ import annotations

from pathlib import Path


def transcribe_to_midi(audio_path: str | Path, out_midi: str | Path) -> Path:
    """Convert a monophonic/polyphonic stem to MIDI."""
    # TODO(Phase 2):
    # from basic_pitch.inference import predict_and_save
    # from basic_pitch import ICASSP_2022_MODEL_PATH
    # predict_and_save(
    #     [str(audio_path)],
    #     output_directory=str(Path(out_midi).parent),
    #     save_midi=True,
    #     sonify_midi=False,
    #     save_model_outputs=False,
    #     save_notes=False,
    #     model_or_model_path=ICASSP_2022_MODEL_PATH,
    # )
    # return Path(out_midi)
    raise NotImplementedError("Fill in during Phase 2")
