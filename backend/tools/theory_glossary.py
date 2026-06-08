"""Keyword theory glossary + the lookup_theory @tool.

No embeddings (spec §4): a curated ~50-entry YAML is loaded once and matched by
exact term, alias, then substring. Each hit cites its stable ``snippet_id`` so
the agent's answer can render a ``[theory:<id>]`` source chip (spec §7).
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

import yaml
from langchain_core.tools import tool

_GLOSSARY_PATH = Path(__file__).resolve().parents[1] / "knowledge" / "theory_glossary.yaml"


@lru_cache(maxsize=1)
def load_glossary() -> list[dict]:
    """Load and cache the theory glossary (list of entry dicts).

    Cached because the YAML is immutable at runtime and the lookup tool reads it
    on every invocation. Tests that want a fresh read can call
    ``load_glossary.cache_clear()``.

    Raises:
        ValueError: if the YAML structure is wrong or any entry is missing
            required fields (term, explanation, snippet_id, aliases).
    """
    raw = yaml.safe_load(_GLOSSARY_PATH.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError(f"theory glossary must be a YAML list, got {type(raw)!r}")

    for entry in raw:
        term = entry.get("term", "")
        if not (isinstance(term, str) and term.strip()):
            raise ValueError(
                f"glossary entry missing non-empty 'term': {entry!r}"
            )
        explanation = entry.get("explanation", "")
        if not (isinstance(explanation, str) and explanation.strip()):
            raise ValueError(
                f"glossary entry {term!r} missing non-empty 'explanation'"
            )
        snippet_id = entry.get("snippet_id", "")
        if not (isinstance(snippet_id, str) and snippet_id.strip()):
            raise ValueError(
                f"glossary entry {term!r} missing non-empty 'snippet_id'"
            )
        aliases = entry.get("aliases")
        if not isinstance(aliases, list):
            raise ValueError(
                f"glossary entry {term!r} 'aliases' must be a list, got {type(aliases)!r}"
            )

    return raw


def _normalize(text: str) -> str:
    return " ".join(text.lower().split())


def _cite(entry: dict) -> str:
    return f"[theory:{entry['snippet_id']}] {entry['explanation'].strip()}"


def _word_in(needle: str, haystack: str) -> bool:
    """Return True when *needle* appears in *haystack* on whole-word boundaries."""
    return bool(re.search(r"(?<!\w)" + re.escape(needle) + r"(?!\w)", haystack))


def _find(term: str) -> dict | None:
    """Resolve a query to a glossary entry by exact term/alias, then substring.

    Precedence (most specific first):
      1. exact match on a term or alias,
      2. a term/alias that appears as a whole-word in the query (longest wins),
      3. the query is a whole-word substring of a term/alias (loose, last resort).
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

    # 2. a glossary name is a whole-word substring of the query
    # (e.g. "what is a tritone" contains "tritone" as a whole word)
    # Require the matching name to be at least 4 characters to avoid single-char
    # aliases (e.g. "m", "o", "I") spuriously matching inside unrelated words.
    best: dict | None = None
    best_len = -1
    for e in entries:
        names = [e["term"]] + list(e.get("aliases", []))
        for n in names:
            nn = _normalize(n)
            if nn and len(nn) >= 4 and _word_in(nn, q) and len(nn) > best_len:
                best, best_len = e, len(nn)
    if best is not None:
        return best

    # 3. the query is a whole-word substring of a glossary name (loose, last resort).
    # Only attempt this if the query is long enough to avoid spurious single-char
    # alias matches (e.g. alias "m" matching inside the word "quantum").
    if len(q) >= 4:
        for e in entries:
            names = [e["term"]] + list(e.get("aliases", []))
            if any(_word_in(q, _normalize(n)) for n in names):
                return e

    return None


@tool
def lookup_theory(term: str) -> str:
    """Look up a general music-theory concept (interval, chord quality, scale, mode,
    cadence, progression, modulation, or voice-leading). Pass a short canonical label
    (e.g. 'tritone', 'secondary dominant', 'dorian mode') — NOT a full question. Use
    only for general theory, not facts about the specific analyzed song. Returns
    '[theory:<id>] <explanation>' on success, or a plain 'No glossary entry found…'
    message when the concept isn't curated — in that case answer from general knowledge
    and say it isn't a cited fact."""
    entry = _find(term)
    if entry is None:
        return (
            f"No glossary entry found for {term!r}. I couldn't find a curated "
            "definition; answer from general knowledge and say it isn't a cited fact."
        )
    return _cite(entry)
