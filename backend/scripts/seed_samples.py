"""Seed canned sample analyses into MongoDB (Plan 3 live-test Bug 2 fix).

Without this, the "Try a Sample Analysis" cards on the landing page are
dead — clicking them does nothing because there's no analysis to link to.
This script upserts three stable-id documents so the cards can navigate
to ``/s/sample-blackbird`` (etc.) and render the share page exactly the
same way as a real analysis.

Usage
-----
::

    python scripts/seed_samples.py
    # or against an explicit Mongo URI:
    MONGO_URI=mongodb://localhost:27017 python scripts/seed_samples.py

Re-running is safe — every record is upserted by its stable ``_id``.

Audio
-----
We deliberately do NOT bundle real audio with these samples (we'd need
licensed clips of three commercial songs). The UploadModal's WaveformPlayer
gracefully renders "No audio loaded" when ``audioFileUrl`` is unset, so the
analysis UI (chord timeline, theory, instrument guides) works as a demo
without an actual playback file.
"""
from __future__ import annotations

import asyncio
import sys
from datetime import datetime, timezone

# ``backend`` is importable via the editable install (pip install -e .).


# Sample analysis catalog — keep IDs stable so the URLs don't drift.
# Each entry is a fully-formed song_analyses document compatible with
# SongAnalysisModel (see backend/models.py).

def _chords(seq):
    """Build chord events from (chord_symbol, start_s, end_s, color) tuples."""
    return [
        {"chord": c, "start": float(s), "end": float(e),
         "confidence": 0.95, "color": col}
        for c, s, e, col in seq
    ]


_SAMPLES: list[dict] = [
    {
        "_id": "sample-blackbird",
        "file_hash": None,
        "title": "Blackbird",
        "artist": "The Beatles",
        "duration": 138.0,
        "key": "G major",
        "tempo": 96.0,
        "time_signature": "3/4",
        "chords": _chords([
            ("G",   0.0,  4.0, "#FF7F00"),
            ("Am7", 4.0,  8.0, "#00FF00"),
            ("G/B", 8.0, 12.0, "#FF7F00"),
            ("C",  12.0, 16.0, "#FF0000"),
            ("D7", 16.0, 20.0, "#FFFF00"),
            ("G",  20.0, 24.0, "#FF7F00"),
        ]),
        "beats": [],
        "sections": [
            {"name": "Intro",  "start": 0.0,   "end": 20.0},
            {"name": "Verse",  "start": 20.0,  "end": 80.0},
            {"name": "Chorus", "start": 80.0, "end": 120.0},
            {"name": "Outro",  "start": 120.0, "end": 138.0},
        ],
        "roman": {
            "key": "G major",
            "progression": ["I", "ii7", "I/3", "IV", "V7", "I"],
            "function": ["tonic", "supertonic", "tonic",
                          "subdominant", "dominant", "tonic"],
        },
        "vibe_palette": ["#FF7F00", "#00FF00", "#FF0000", "#FFFF00"],
        "theory_explanation": (
            "Blackbird sits firmly in G major, with a fingerpicked descending "
            "line that walks the bass through G, A, B, C, D, and back. The "
            "ii7 → I/3 → IV motion gives the verse its lullaby quality."
        ),
        "instrument_guides": {},
        "stems": {},
        "created_at": datetime.now(timezone.utc),  # fresh, otherwise Mongo TTL drops it
    },
    {
        "_id": "sample-wonderwall",
        "file_hash": None,
        "title": "Wonderwall",
        "artist": "Oasis",
        "duration": 258.0,
        "key": "F# minor",
        "tempo": 87.0,
        "time_signature": "4/4",
        "chords": _chords([
            ("Em7",     0.0,   4.0, "#FF0000"),
            ("G",       4.0,   8.0, "#FF7F00"),
            ("Dsus4",   8.0,  12.0, "#FFFF00"),
            ("A7sus4", 12.0,  16.0, "#00FF00"),
            ("Em7",    16.0,  20.0, "#FF0000"),
            ("G",      20.0,  24.0, "#FF7F00"),
        ]),
        "beats": [],
        "sections": [
            {"name": "Intro",  "start": 0.0,    "end": 24.0},
            {"name": "Verse",  "start": 24.0,   "end": 90.0},
            {"name": "Chorus", "start": 90.0,   "end": 180.0},
            {"name": "Outro",  "start": 180.0,  "end": 258.0},
        ],
        "roman": {
            "key": "F# minor",
            "progression": ["vii", "II", "VI", "III"],
            "function": ["subtonic", "supertonic",
                          "submediant", "mediant"],
        },
        "vibe_palette": ["#FF0000", "#FF7F00", "#FFFF00", "#00FF00"],
        "theory_explanation": (
            "A capo-2 staple — the shapes are F#m / A / E / B in concert, "
            "but voiced as Em7 / G / Dsus4 / A7sus4. The sus voicings give "
            "the song its open, ringing character."
        ),
        "instrument_guides": {},
        "stems": {},
        "created_at": datetime.now(timezone.utc),  # fresh, otherwise Mongo TTL drops it
    },
    {
        "_id": "sample-creep",
        "file_hash": None,
        "title": "Creep",
        "artist": "Radiohead",
        "duration": 238.0,
        "key": "G major",
        "tempo": 92.0,
        "time_signature": "4/4",
        "chords": _chords([
            ("G", 0.0,  4.0, "#FF7F00"),
            ("B", 4.0,  8.0, "#0000FF"),
            ("C", 8.0, 12.0, "#FF0000"),
            ("Cm",12.0, 16.0, "#8B0000"),
            ("G", 16.0, 20.0, "#FF7F00"),
            ("B", 20.0, 24.0, "#0000FF"),
        ]),
        "beats": [],
        "sections": [
            {"name": "Intro",  "start": 0.0,   "end": 24.0},
            {"name": "Verse",  "start": 24.0,  "end": 80.0},
            {"name": "Chorus", "start": 80.0,  "end": 160.0},
            {"name": "Bridge", "start": 160.0, "end": 200.0},
            {"name": "Outro",  "start": 200.0, "end": 238.0},
        ],
        "roman": {
            "key": "G major",
            "progression": ["I", "III", "IV", "iv"],
            "function": ["tonic", "mediant",
                          "subdominant", "borrowed subdominant"],
        },
        "vibe_palette": ["#FF7F00", "#0000FF", "#FF0000", "#8B0000"],
        "theory_explanation": (
            "I-III-IV-iv is the secret sauce. The III is a chromatic mediant "
            "(non-diatonic in G major) and the iv borrows from G minor, "
            "creating the heart-tug just before the chorus payoff."
        ),
        "instrument_guides": {},
        "stems": {},
        "created_at": datetime.now(timezone.utc),  # fresh, otherwise Mongo TTL drops it
    },
]


async def main() -> int:
    from motor.motor_asyncio import AsyncIOMotorClient

    from backend.config import get_settings

    settings = get_settings()
    client = AsyncIOMotorClient(settings.mongo_uri)
    db = client[settings.mongo_db_name]

    upserts = 0
    for doc in _SAMPLES:
        await db.song_analyses.replace_one(
            {"_id": doc["_id"]}, doc, upsert=True,
        )
        upserts += 1
        print(f"  upserted: {doc['_id']!r:24} {doc['artist']} — {doc['title']}")

    print(f"Seeded {upserts} sample analyses into {settings.mongo_db_name}.song_analyses")
    client.close()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
