"""
Synesthesia Color Engine: Scriabin Circle of Fifths music-to-color mapping.
Vault ref: 06-Projects/05-Project-SoundBreak.md (Phase 5)
"""

from __future__ import annotations

import colorsys

from backend.tools.chords import parse_chord

# Base Scriabin Circle of Fifths mapping for note pitch classes
SCRIABIN_COLORS = {
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

# Enharmonic normalization
ENHARMONICS = {
    "DB": "C#",
    "EB": "D#",
    "GB": "F#",
    "AB": "G#",
    "BB": "A#",
}


def hex_to_hls(hex_str: str) -> tuple[float, float, float]:
    """Convert hex color string like '#FF0000' to HLS coordinates (0-1)."""
    hex_str = hex_str.lstrip("#")
    r, g, b = tuple(int(hex_str[i : i + 2], 16) / 255.0 for i in (0, 2, 4))
    return colorsys.rgb_to_hls(r, g, b)


def hls_to_hex(h: float, lt: float, s: float) -> str:
    """Convert HLS coordinates (0-1) back to hex color string."""
    r, g, b = colorsys.hls_to_rgb(h, lt, s)
    return f"#{int(r * 255):02X}{int(g * 255):02X}{int(b * 255):02X}"


def get_chord_color(chord_symbol: str) -> str:
    """Determine the synesthetic hex color for a given chord symbol.

    Quality is resolved via the canonical ``parse_chord`` so ``maj7`` is no
    longer mis-classified as minor by a naive ``"m" in suffix`` check.

    Rule details:
    - Root note determines the base hue using Scriabin's mapping.
    - Minor chords are darker and cooler (lower lightness and saturation).
    - Dominant 7th is a fluorescent boost; aug/dim get fixed accent colors.
    """
    chord_symbol = chord_symbol.strip()
    if not chord_symbol or chord_symbol.lower() == "n" or chord_symbol == "N.C.":
        return "#1A1A1A"  # Dark gray/black for No Chord

    parts = parse_chord(chord_symbol)
    if not parts.root:
        return "#8B5CF6"  # Fallback to electric violet

    root_upper = parts.root.upper()
    norm_root = ENHARMONICS.get(root_upper, root_upper)
    base_hex = SCRIABIN_COLORS.get(norm_root, "#8B5CF6")

    quality = parts.quality
    h, lt, s = hex_to_hls(base_hex)  # ``lt`` = lightness

    if quality in ("dim", "dim7", "m7b5"):
        # Diminished / half-diminished -> vibrating neon pink shift
        return "#FF00C8"
    elif quality == "aug":
        # Augmented -> radioactive lime shift
        return "#B6FF00"
    elif quality in ("min", "min7", "min9", "min11", "min13"):
        # Minor (incl. deep extensions) -> cooler, deeper, lower lightness & saturation
        if norm_root in ("C", "G", "D", "A"):
            h = (h + 0.05) % 1.0  # Shift toward green/blue
        lt = max(0.15, lt * 0.5)  # Darker
        s = max(0.2, s * 0.6)  # Less saturated
    elif quality in ("sus2", "sus4"):
        # Suspended -> unresolved, airy: washed-out pastel of the root hue
        s = max(0.25, s * 0.55)
        lt = min(0.85, lt * 1.25)
    elif quality in ("dom7", "9", "11", "13", "maj7", "maj9", "6"):
        # 7th / extended -> highly saturated neon fluorescent boost
        s = min(1.0, s * 1.3)
        lt = min(0.9, lt * 1.1)

    return hls_to_hex(h, lt, s)


def get_vibe_palette(key_name: str, chord_list: list[str]) -> list[str]:
    """Generate a cohesive color palette (vibe palette) for a song.

    Returns 3 colors: [KeyColor, HighFrequencyChordColor, ContrastingVibeColor]
    """
    # 1. Primary color from the musical key
    key_root = key_name.split()[0] if key_name else "C"
    key_root_upper = key_root.upper()
    norm_key_root = ENHARMONICS.get(key_root_upper, key_root_upper)
    primary_color = SCRIABIN_COLORS.get(norm_key_root, "#8B5CF6")

    # 2. Get colors for other common chords in the song
    unique_chords = [c for c in set(chord_list) if c not in ("N.C.", "N", "")]
    chord_colors = [get_chord_color(c) for c in unique_chords[:4]]

    # Pad or build palette
    palette = [primary_color]
    for c_col in chord_colors:
        if c_col not in palette and len(palette) < 3:
            palette.append(c_col)

    while len(palette) < 3:
        # Pad with secondary / contrast accents
        palette.append("#8B5CF6" if "#8B5CF6" not in palette else "#FF00C8")

    return palette
