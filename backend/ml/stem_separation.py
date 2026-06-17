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

    # Demucs is lazy-loaded via the registry — first call in this process
    # builds + downloads the model (one-time cost), subsequent calls reuse it.
    try:
        from backend.ml import registry as ml_registry

        model = ml_registry.get("demucs")
    except (ImportError, ModuleNotFoundError):
        logger.warning("demucs not installed, skipping stem separation")
        return {}
    except KeyError:
        logger.warning("demucs not registered, skipping stem separation")
        return {}

    logger.info(f"Running demucs on {audio_path}")

    try:
        import librosa
        import numpy as np
        import soundfile as sf
        import torch
        from demucs.apply import apply_model

        # IMPORTANT: load/save WITHOUT demucs.audio — its AudioFile shells out
        # to ``ffprobe``, which isn't installed here (imageio-ffmpeg ships
        # ffmpeg but not ffprobe). librosa reads the staged WAV via soundfile,
        # resamples to the model rate, and we write stems with soundfile too.
        y, _sr = librosa.load(str(audio_path), sr=model.samplerate, mono=False)
        arr = np.asarray(y, dtype="float32")
        if arr.ndim == 1:
            arr = np.stack([arr, arr])  # mono -> stereo
        wav = torch.from_numpy(arr)
        if wav.shape[0] == 1:
            wav = wav.repeat(model.audio_channels, 1)
        elif wav.shape[0] > model.audio_channels:
            wav = wav[: model.audio_channels]

        # demucs's standard per-mix normalisation (subtract mean / divide by std).
        ref = wav.mean(0)
        wav = (wav - ref.mean()) / (ref.std() + 1e-8)

        with torch.no_grad():
            est = apply_model(model, wav[None], device="cpu", progress=False)[0]
        est = est * ref.std() + ref.mean()

        # ``model.sources`` is the channel order, e.g. ['drums','bass','other','vocals'].
        for name, source in zip(model.sources, est):
            if name in stem_paths:
                # [channels, samples] -> [samples, channels] for soundfile.
                sf.write(str(stem_paths[name]), source.cpu().numpy().T, model.samplerate)

        return {k: v for k, v in stem_paths.items() if v.exists()}
    except Exception as e:
        logger.error(f"Demucs failed: {e}", exc_info=True)
        # Return whatever we generated or empty dict if nothing
        return {k: v for k, v in stem_paths.items() if v.exists()}
