"""
Synesthesia Color Engine: Scriabin Circle of Fifths music-to-color mapping.
Vault ref: 06-Projects/05-Project-SoundBreak.md (Phase 5)
"""
from __future__ import annotations

import colorsys
import re

# Base Scriabin Circle of Fifths mapping for note pitch classes
SCRIABIN_COLORS = {
    "C": "#FF0000",      # Red
    "G": "#FF7F00",      # Orange
    "D": "#FFFF00",      # Yellow
    "A": "#00FF00",      # Green
    "E": "#00BFFF",      # Sky Blue (Moonshine)
    "B": "#0000FF",      # Blue
    "F#": "#4B0082",     # Violet-Blue / Indigo
    "C#": "#8B00FF",     # Violet / Purple
    "G#": "#D8BFD8",     # Purple / Lilac / Thistle
    "D#": "#FFC0CB",     # Pink / Flesh
    "A#": "#708090",     # Steel Gray
    "F": "#8B0000",      # Deep Red
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
    r, g, b = tuple(int(hex_str[i:i+2], 16) / 255.0 for i in (0, 2, 4))
    return colorsys.rgb_to_hls(r, g, b)


def hls_to_hex(h: float, l: float, s: float) -> str:
    """Convert HLS coordinates (0-1) back to hex color string."""
    r, g, b = colorsys.hls_to_rgb(h, l, s)
    return f"#{int(r * 255):02X}{int(g * 255):02X}{int(b * 255):02X}"


def get_chord_color(chord_symbol: str) -> str:
    """Determine the synesthetic hex color for a given chord symbol.

    Rule details:
    - Root note determines the base hue using Scriabin's mapping.
    - Minor chords are darker and cooler (lower lightness and saturation).
    - Dominant 7th or Augmented/Diminished are vibrant/fluorescent.
    """
    chord_symbol = chord_symbol.strip()
    if not chord_symbol or chord_symbol.lower() == "n" or chord_symbol == "N.C.":
        return "#1A1A1A"  # Dark gray/black for No Chord

    # Split root from quality suffix (e.g., Cmaj7 -> C, maj7)
    match = re.match(r"^([A-G][b#]?)(.*)$", chord_symbol)
    if not match:
        return "#8B5CF6"  # Fallback to electric violet

    root, suffix = match.groups()
    root_upper = root.upper()

    # Normalize enharmonics (e.g. Db -> C#)
    norm_root = ENHARMONICS.get(root_upper, root_upper)
    base_hex = SCRIABIN_COLORS.get(norm_root, "#8B5CF6")

    # Detect chord quality from suffix
    suffix_lower = suffix.lower()
    h, l, s = hex_to_hls(base_hex)

    if "dim" in suffix_lower or "o" in suffix_lower or "ø" in suffix_lower:
        # Diminished -> vibrating neon pink shift
        return "#FF00C8"
    elif "aug" in suffix_lower or "+" in suffix_lower:
        # Augmented -> radioactive lime shift
        return "#B6FF00"
    elif "min" in suffix_lower or "m" in suffix_lower:
        # Minor -> Cooler, deeper, lower lightness & saturation
        # Make it cooler by shifting hue slightly toward blue
        if norm_root in ("C", "G", "D", "A"):
            h = (h + 0.05) % 1.0  # Shift toward green/blue
        l = max(0.15, l * 0.5)  # Darker
        s = max(0.2, s * 0.6)   # Less saturated
    elif "7" in suffix_lower:
        # Dominant 7th -> highly saturated neon fluorescent boost
        s = min(1.0, s * 1.3)
        l = min(0.9, l * 1.1)

    return hls_to_hex(h, l, s)


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
