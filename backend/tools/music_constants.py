"""Canonical music constants. Single source of truth — import these instead of
redefining the chromatic scale / enharmonic maps / Scriabin colors locally."""

from __future__ import annotations

# Chromatic scale, sharps only.
NOTES: list[str] = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

# Common flat->sharp enharmonics, title-case (chord roots).
FLAT_TO_SHARP: dict[str, str] = {"Db": "C#", "Eb": "D#", "Gb": "F#", "Ab": "G#", "Bb": "A#"}

# Upper-case enharmonic map incl. theoretical Cb/Fb — for key-name normalization.
FLAT_TO_SHARP_KEYS: dict[str, str] = {
    "DB": "C#", "EB": "D#", "GB": "F#", "AB": "G#", "BB": "A#", "CB": "B", "FB": "E",
}

# Scriabin circle-of-fifths color palette (pitch-class -> hex).
SCRIABIN_COLORS: dict[str, str] = {
    "C": "#FF0000",  # Red
    "G": "#FF7F00",  # Orange
    "D": "#FFFF00",  # Yellow
    "A": "#00FF00",  # Green
    "E": "#00BFFF",  # Sky Blue (Moonshine)
    "B": "#0000FF",  # Blue
    "F#": "#4B0082",  # Violet-Blue / Indigo
    "C#": "#8B00FF",  # Violet / Purple
    "G#": "#D8BFD8",  # Purple / Lilac / Thistle
    "D#": "#FFC0CB",  # Pink / Flesh
    "A#": "#708090",  # Steel Gray
    "F": "#8B0000",  # Deep Red
}

# Upper-case enharmonics used by the color helpers.
ENHARMONICS: dict[str, str] = {
    "DB": "C#",
    "EB": "D#",
    "GB": "F#",
    "AB": "G#",
    "BB": "A#",
}
