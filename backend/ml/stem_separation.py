"""
Stem separation using Demucs (htdemucs_ft).
Vault ref: 06-Projects/05-Project-SoundBreak.md (Phase 2)

NOTE: Heavy model. Runs on GPU in prod (Modal/Replicate). On laptop it's slow.
"""
from __future__ import annotations

from pathlib import Path


STEM_NAMES = ("vocals", "drums", "bass", "other")


def separate_stems(audio_path: str | Path, out_dir: str | Path) -> dict[str, Path]:
    """Returns {'vocals': Path, 'drums': Path, 'bass': Path, 'other': Path}.

    TODO(Module 4, Lesson 3 / Phase 2):
      1. Call demucs.separate.main(['-n', 'htdemucs_ft', '-o', out_dir, audio_path])
      2. Or use demucs.api.Separator for programmatic use.
      3. Return paths to the 4 stem .wav files.
      4. Handle OOM by falling back to htdemucs (non-finetuned, smaller).
    """
    # from demucs.api import Separator
    # sep = Separator(model="htdemucs_ft")
    # _, sources = sep.separate_audio_file(Path(audio_path))
    # ...
    raise NotImplementedError("Fill in during Phase 2")
