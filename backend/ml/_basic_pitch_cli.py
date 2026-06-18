"""Standalone basic-pitch transcription CLI.

Run with a Python interpreter that has ``basic-pitch`` installed (e.g.
``backend/.venv311`` — basic-pitch pins ``tensorflow<2.15.1`` which has no
Python 3.12 wheel, so the main 3.12 worker delegates to a 3.11 interpreter via
this script). Intentionally free of any ``backend.*`` import so it runs inside a
minimal venv that only has basic-pitch.

Usage:
    python _basic_pitch_cli.py <audio_path> <out_dir>

Writes ``<audio_stem>_basic_pitch.mid`` into ``out_dir`` (basic-pitch's default
naming); the caller renames it to the desired path.
"""

from __future__ import annotations

import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: _basic_pitch_cli.py <audio_path> <out_dir>", file=sys.stderr)
        return 2
    audio_path, out_dir = sys.argv[1], sys.argv[2]
    Path(out_dir).mkdir(parents=True, exist_ok=True)

    from basic_pitch import ICASSP_2022_MODEL_PATH
    from basic_pitch.inference import predict_and_save

    predict_and_save(
        [audio_path],
        output_directory=out_dir,
        save_midi=True,
        sonify_midi=False,
        save_model_outputs=False,
        save_notes=False,
        model_or_model_path=ICASSP_2022_MODEL_PATH,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
