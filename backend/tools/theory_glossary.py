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


from langchain_core.tools import tool


def _normalize(text: str) -> str:
    return " ".join(text.lower().split())


def _cite(entry: dict) -> str:
    return f"[theory:{entry['snippet_id']}] {entry['explanation'].strip()}"


def _find(term: str) -> dict | None:
    """Resolve a query to a glossary entry by exact term/alias, then substring.

    Precedence (most specific first):
      1. exact match on a term or alias,
      2. a term/alias that appears as a substring of the query,
      3. a term/alias that contains the query as a substring (longest term wins,
         so 'dominant' does not get shadowed by 'secondary dominant').
    """
    q = _normalize(term)
    if not q:
        return None

    entries = load_glossary()

    # 1. exact term/alias
    for e in entries:
        names = [e["term"]] + list(e.get("aliases", []))
        if any(_normalize(n) == q for n in names):
            return e

    # 2. a glossary name is a whole-substring of the query (e.g. "what is a tritone")
    # Require the matching name to be at least 4 characters to avoid single-char
    # aliases (e.g. "m", "o", "I") spuriously matching inside unrelated words.
    best: dict | None = None
    best_len = -1
    for e in entries:
        names = [e["term"]] + list(e.get("aliases", []))
        for n in names:
            nn = _normalize(n)
            if nn and len(nn) >= 4 and nn in q and len(nn) > best_len:
                best, best_len = e, len(nn)
    if best is not None:
        return best

    # 3. the query is a substring of a glossary name (loose, last resort).
    # Only attempt this if the query is long enough to avoid spurious single-char
    # alias matches (e.g. alias "m" matching inside the word "quantum").
    if len(q) >= 4:
        for e in entries:
            names = [e["term"]] + list(e.get("aliases", []))
            if any(q in _normalize(n) for n in names):
                return e

    return None


@tool
def lookup_theory(term: str) -> str:
    """Look up a general music-theory concept (interval, chord quality, mode,
    cadence, progression, modulation, voice-leading, etc.) and return a short,
    cited explanation. Use this for theory questions that are NOT about the
    specific analyzed song. Returns a string beginning with [theory:<id>]."""
    entry = _find(term)
    if entry is None:
        return (
            f"No glossary entry found for {term!r}. I couldn't find a curated "
            "definition; answer from general knowledge and say it isn't a cited fact."
        )
    return _cite(entry)
