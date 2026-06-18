"""
Audio-to-MIDI using Spotify's basic-pitch. Great for isolated bass/vocal stems.
Vault ref: 06-Projects/05-Project-SoundBreak.md (Phase 2)

basic-pitch pins ``tensorflow<2.15.1`` which has no Python 3.12 wheel, so it
cannot be imported in the main 3.12 worker. When that's the case we delegate to
a dedicated 3.11 interpreter (``$MIDI_PYTHON`` or ``backend/.venv311``) running
``_basic_pitch_cli.py`` as a subprocess. When the current interpreter DOES have
basic-pitch (e.g. a 3.11 worker), we run it in-process.
"""

from __future__ import annotations

import logging
import os
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

# basic-pitch's default output filename suffix.
_BP_SUFFIX = "_basic_pitch.mid"


def _resolve_midi_python() -> str | None:
    """Path to a Python that has basic-pitch, or None. Prefers ``$MIDI_PYTHON``,
    else the conventional ``backend/.venv311`` next to this package."""
    cand = os.environ.get("MIDI_PYTHON")
    if cand and Path(cand).exists():
        return cand
    default = Path(__file__).resolve().parents[1] / ".venv311" / "bin" / "python"
    return str(default) if default.exists() else None


def transcribe_to_midi(audio_path: str | Path, out_midi: str | Path) -> Path | None:
    """Convert a monophonic/polyphonic stem to MIDI using basic-pitch."""
    audio_path = Path(audio_path)
    out_midi = Path(out_midi)

    if out_midi.exists():
        return out_midi

    out_dir = out_midi.parent
    out_dir.mkdir(parents=True, exist_ok=True)

    # Path A — basic-pitch importable in THIS interpreter: run in-process.
    in_process = False
    predict_and_save = None
    model_path = None
    try:
        from basic_pitch.inference import predict_and_save  # type: ignore

        from backend.ml import registry as ml_registry

        model_path = ml_registry.get("basic_pitch")
        in_process = True
    except (ImportError, ModuleNotFoundError, KeyError):
        in_process = False

    if in_process and predict_and_save is not None:
        logger.info(f"Running basic-pitch in-process on {audio_path}")
        try:
            predict_and_save(
                [str(audio_path)],
                output_directory=str(out_dir),
                save_midi=True,
                sonify_midi=False,
                save_model_outputs=False,
                save_notes=False,
                model_or_model_path=model_path,
            )
        except Exception as e:
            logger.error(f"basic-pitch failed: {e}")
            return None
    else:
        # Path B — delegate to a 3.11 interpreter that has basic-pitch.
        midi_python = _resolve_midi_python()
        if not midi_python:
            logger.warning(
                "basic-pitch not importable and no MIDI_PYTHON / backend/.venv311 "
                "interpreter found; skipping MIDI transcription"
            )
            return None
        cli = Path(__file__).with_name("_basic_pitch_cli.py")
        logger.info(f"Running basic-pitch via {midi_python} on {audio_path}")
        try:
            subprocess.run(
                [midi_python, str(cli), str(audio_path), str(out_dir)],
                check=True,
                capture_output=True,
                timeout=600,
            )
        except subprocess.CalledProcessError as e:
            logger.error(f"basic-pitch subprocess failed (rc={e.returncode}): {e.stderr.decode('utf-8', 'replace')[-500:]}")
            return None
        except subprocess.TimeoutExpired:
            logger.error("basic-pitch subprocess timed out after 600s")
            return None

    # basic-pitch writes ``<stem>_basic_pitch.mid`` into out_dir; rename to target.
    expected_out = out_dir / f"{audio_path.stem}{_BP_SUFFIX}"
    if expected_out.exists():
        expected_out.rename(out_midi)

    return out_midi if out_midi.exists() else None
