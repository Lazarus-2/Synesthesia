"""
Stem separation using Demucs.
Vault ref: 06-Projects/05-Project-SoundBreak.md (Phase 2)
"""
from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

STEM_NAMES = ("vocals", "drums", "bass", "other")


def separate_stems(audio_path: str | Path, out_dir: str | Path) -> dict[str, Path]:
    """Returns {'vocals': Path, 'drums': Path, 'bass': Path, 'other': Path} using Demucs."""
    audio_path = Path(audio_path)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    
    stem_paths = {stem: out_dir / f"{stem}.wav" for stem in STEM_NAMES}
    
    # Check if already processed
    if all(p.exists() for p in stem_paths.values()):
        logger.info(f"Stems already exist in {out_dir}")
        return stem_paths

    try:
        from demucs.api import Separator
    except ImportError:
        logger.warning("demucs not installed, skipping stem separation")
        return {}

    logger.info(f"Running demucs on {audio_path}")
    
    try:
        # Use htdemucs_ft which is best quality. Will use GPU if PyTorch finds it.
        sep = Separator(model="htdemucs_ft")
        
        # separate_audio_file returns (origin, dict_of_sources)
        _, sources = sep.separate_audio_file(audio_path)
        
        import torchaudio
        for stem_name, tensor in sources.items():
            if stem_name in stem_paths:
                # tensor shape is [channels, samples]
                torchaudio.save(str(stem_paths[stem_name]), tensor, sep.samplerate)
                
        return stem_paths
    except Exception as e:
        logger.error(f"Demucs failed: {e}")
        # Return whatever we generated or empty dict if nothing
        return {k: v for k, v in stem_paths.items() if v.exists()}
