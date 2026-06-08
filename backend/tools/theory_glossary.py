"""Keyword theory glossary + the lookup_theory @tool.

No embeddings (spec §4): a curated ~50-entry YAML is loaded once and matched by
exact term, alias, then substring. Each hit cites its stable ``snippet_id`` so
the agent's answer can render a ``[theory:<id>]`` source chip (spec §7).
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

_GLOSSARY_PATH = Path(__file__).resolve().parents[1] / "knowledge" / "theory_glossary.yaml"


@lru_cache(maxsize=1)
def load_glossary() -> list[dict]:
    """Load and cache the theory glossary (list of entry dicts).

    Cached because the YAML is immutable at runtime and the lookup tool reads it
    on every invocation. Tests that want a fresh read can call
    ``load_glossary.cache_clear()``.
    """
    raw = yaml.safe_load(_GLOSSARY_PATH.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError(f"theory glossary must be a YAML list, got {type(raw)!r}")
    return raw
