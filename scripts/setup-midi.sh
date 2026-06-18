#!/usr/bin/env bash
#
# Set up the Python 3.11 "MIDI sidecar" venv that the /midi endpoint uses for
# Spotify's basic-pitch. basic-pitch pins tensorflow<2.15.1, which has no
# Python 3.12 wheel, so it CANNOT live in the main 3.12 backend venv — the
# transcription step shells out to this 3.11 interpreter instead
# (see backend/ml/midi_transcription.py).
#
# Idempotent. Uses `uv` if available (fast, can fetch a standalone 3.11),
# otherwise a system `python3.11`.
#
# After running, MIDI works automatically because midi_transcription.py looks
# for backend/.venv311 by default; override with $MIDI_PYTHON if you put it
# elsewhere.
#
# Usage:  ./scripts/setup-midi.sh
set -euo pipefail

cd "$(dirname "$0")/.."
VENV="backend/.venv311"

echo "==> Creating MIDI sidecar venv at $VENV (Python 3.11 + basic-pitch)"
if command -v uv >/dev/null 2>&1; then
  uv venv --python 3.11 "$VENV"
  # setuptools<81 still ships pkg_resources, which resampy (a basic-pitch dep)
  # imports — newer setuptools removed it.
  uv pip install --python "$VENV/bin/python" "basic-pitch>=0.4.0" "setuptools<81"
elif command -v python3.11 >/dev/null 2>&1; then
  python3.11 -m venv "$VENV"
  "$VENV/bin/pip" install --upgrade pip "setuptools<81" wheel
  "$VENV/bin/pip" install "basic-pitch>=0.4.0" "setuptools<81"
else
  echo "ERROR: need either 'uv' (recommended) or a system 'python3.11'." >&2
  echo "  Install uv:  curl -LsSf https://astral.sh/uv/install.sh | sh" >&2
  exit 1
fi

echo "==> Verifying basic-pitch imports"
"$VENV/bin/python" - <<'PY'
import basic_pitch
from basic_pitch import ICASSP_2022_MODEL_PATH
print("basic-pitch OK:", ICASSP_2022_MODEL_PATH)
PY

# ffprobe sanity (yt-dlp metadata + librosa). Docker installs ffmpeg (which
# bundles ffprobe); local devs may not have it.
if ! command -v ffprobe >/dev/null 2>&1; then
  echo "WARN: ffprobe not on PATH — yt-dlp metadata extraction will warn (non-fatal)."
  echo "      Install ffmpeg (apt install ffmpeg / brew install ffmpeg) to silence it."
fi

echo "==> Done. MIDI sidecar ready at $VENV"
