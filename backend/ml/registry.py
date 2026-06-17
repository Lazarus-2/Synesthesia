"""ML model registry (Plan 2 C1).

Stem separation and MIDI transcription each load a multi-hundred-MB model
on import. Before this registry, every call to ``separate_stems`` /
``transcribe_to_midi`` re-instantiated those models — wasted seconds per
job, with risk of double-allocating in concurrent workers.

The registry is a lazy-loading process-singleton. First access pays the
load cost; subsequent calls reuse the cached object.

Currently registered builders
-----------------------------
- ``"demucs"``      -> ``demucs.api.Separator(model="htdemucs_ft")``
- ``"basic_pitch"`` -> ``basic_pitch.ICASSP_2022_MODEL_PATH`` (the model
  itself is loaded lazily inside ``predict_and_save``, so we cache the
  *path* here for symmetry).

Add a new model by registering a builder via :func:`register`. Builders
must be thread-safe to call concurrently — the registry serializes only
the *first* build per key, so subsequent concurrent callers see the cached
object without contention.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)

_builders: dict[str, Callable[[], Any]] = {}
_instances: dict[str, Any] = {}
_lock = threading.Lock()


def register(name: str, builder: Callable[[], Any]) -> None:
    """Register a lazy builder. Overwrites silently if called twice."""
    _builders[name] = builder


def get(name: str) -> Any:
    """Return the cached instance, building on first access. Raises on unknown name."""
    inst = _instances.get(name)
    if inst is not None:
        return inst
    with _lock:
        inst = _instances.get(name)
        if inst is not None:
            return inst
        builder = _builders.get(name)
        if builder is None:
            raise KeyError(f"ML model {name!r} not registered. Known: {sorted(_builders)}")
        logger.info("ml.registry: building %s", name)
        inst = builder()
        _instances[name] = inst
        return inst


def reset_for_tests() -> None:
    """Drop all cached instances. Builders are kept."""
    _instances.clear()


# ---- Default builders -------------------------------------------------------
def _build_demucs():
    # demucs 4.x: the high-level ``demucs.api.Separator`` is absent from some
    # published wheels (e.g. the 4.0.1 wheel installed here ships no api.py),
    # so we use the stable lower-level path — ``pretrained.get_model`` +
    # ``apply.apply_model`` (see stem_separation.separate_stems).
    #
    # "htdemucs" (single transformer model, ~80MB) instead of "htdemucs_ft"
    # (a 4-model bag, ~1GB and ~4x slower): on CPU the _ft variant is far too
    # slow for an interactive request. Quality of the single model is still
    # excellent for the vocals/drums/bass/other split we surface.
    from demucs.pretrained import get_model

    model = get_model("htdemucs")
    model.eval()
    return model


def _build_basic_pitch_path():
    from basic_pitch import ICASSP_2022_MODEL_PATH

    return ICASSP_2022_MODEL_PATH


register("demucs", _build_demucs)
register("basic_pitch", _build_basic_pitch_path)
