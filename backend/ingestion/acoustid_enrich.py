"""AcoustID + Chromaprint fingerprint enrichment for uploaded files.

When the user uploads an audio file we usually have no metadata about
it — the filename is whatever the browser produced and the pipeline
ends up labelling everything "Untitled". AcoustID solves this for free:
generate a 32-byte Chromaprint fingerprint, query the AcoustID public
API, and (often) get back a MusicBrainz Recording ID with the real
title + artist.

This module is the single integration point. It degrades gracefully
when the operator hasn't installed ``fpcalc`` (the Chromaprint binary)
or set ``ACOUSTID_API_KEY`` — both are optional pieces of polish,
not load-bearing for the analysis pipeline.

Cost model: AcoustID is free with attribution; no rate limit beyond
"don't be abusive". One fingerprint + lookup per upload is fine.
"""

from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _fpcalc_available() -> bool:
    """``fpcalc`` is the Chromaprint binary; pyacoustid invokes it as a
    subprocess. If it's not on PATH, fingerprinting can't run."""
    return shutil.which("fpcalc") is not None


def fingerprint_file(path: str | Path) -> tuple[int, str] | None:
    """Return ``(duration_seconds, base64_fingerprint)`` for the file,
    or ``None`` if fpcalc is missing or fingerprinting failed.

    Wraps ``acoustid.fingerprint_file`` so callers don't need to
    handle the ImportError + missing-binary cases themselves.
    """
    if not _fpcalc_available():
        logger.debug("acoustid_enrich: fpcalc binary missing on PATH; skipping fingerprint")
        return None
    try:
        import acoustid
    except ImportError:
        logger.debug("acoustid_enrich: pyacoustid not installed; skipping fingerprint")
        return None
    try:
        duration, fp = acoustid.fingerprint_file(str(path))
        return int(duration), fp.decode() if isinstance(fp, bytes) else fp
    except acoustid.FingerprintGenerationError as e:
        logger.warning("acoustid_enrich: fingerprint generation failed: %s", e)
        return None


def lookup_mbid(duration: int, fingerprint: str) -> dict[str, Any] | None:
    """Query the AcoustID API for the top match.

    Returns ``{"mbid", "title", "artist", "score"}`` on a confident
    match, ``None`` otherwise. Confidence threshold is 0.85 — the API
    returns multiple candidates with scores in [0, 1] and the top one
    is usually exact when score > 0.85.

    Requires ``ACOUSTID_API_KEY`` env var; without it returns None.
    Get a free key at https://acoustid.org/new-application.
    """
    api_key = os.environ.get("ACOUSTID_API_KEY")
    if not api_key:
        logger.debug("acoustid_enrich: ACOUSTID_API_KEY not set; skipping lookup")
        return None
    try:
        import acoustid
    except ImportError:
        return None
    try:
        results = list(
            acoustid.match(api_key, fingerprint=fingerprint, duration=duration, meta="recordings")
        )
    except acoustid.WebServiceError as e:
        logger.warning("acoustid_enrich: API call failed: %s", e)
        return None
    if not results:
        return None
    # ``acoustid.match`` yields ``(score, recording_id, title, artist)`` tuples.
    score, mbid, title, artist = results[0]
    if score < 0.85:
        logger.info(
            "acoustid_enrich: top match score %.2f below threshold; "
            "treating as no match (title=%r artist=%r)",
            score,
            title,
            artist,
        )
        return None
    return {"mbid": mbid, "title": title, "artist": artist, "score": float(score)}


def enrich_upload(path: str | Path) -> dict[str, Any]:
    """One-shot enrichment for the ingest_node upload branch.

    Returns a dict suitable for spreading into the LangGraph state
    return value (``return {**enrich_upload(path), ...}``). Empty
    dict on any failure — caller must NOT rely on any specific key
    being present.
    """
    fingerprint_result = fingerprint_file(path)
    if not fingerprint_result:
        return {}
    duration, fp = fingerprint_result
    match = lookup_mbid(duration, fp)
    if not match:
        return {}
    logger.info(
        "acoustid_enrich: matched %s as %r by %r (score=%.2f)",
        path,
        match["title"],
        match["artist"],
        match["score"],
    )
    return {
        "title": match["title"],
        "artist": match["artist"],
        "mbid": match["mbid"],
    }
