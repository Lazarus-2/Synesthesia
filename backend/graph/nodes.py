"""
Individual nodes of the analysis graph.
Each node is a pure function: state -> partial state.
Vault ref: 04-LangGraph-Core/02-State-Nodes-Edges.md
"""
from __future__ import annotations

from backend.graph.state import AnalysisState
import re
from pathlib import Path
from backend.schemas import ChordEvent, BeatEvent, SongSection, RomanAnalysis, InstrumentGuide
from backend.tools.synesthesia_colors import get_chord_color, get_vibe_palette


def ingest_node(state: AnalysisState) -> dict:
    """Download YouTube audio or validate uploaded file."""
    youtube_url = state.get("youtube_url")
    audio_path = state.get("audio_path")
    errors = list(state.get("errors", []))

    if youtube_url:
        try:
            import yt_dlp
            # Create uploads directory if it doesn't exist
            out_dir = Path("./storage/uploads")
            out_dir.mkdir(parents=True, exist_ok=True)
            
            # Setup yt-dlp options
            out_path = out_dir / "%(id)s.%(ext)s"
            ydl_opts = {
                "format": "bestaudio/best",
                "outtmpl": str(out_path),
                "postprocessors": [{
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "192",
                }],
                "quiet": True,
            }
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(youtube_url, download=True)
                downloaded_file = out_dir / f"{info['id']}.mp3"
                audio_path = str(downloaded_file)
        except Exception as e:
            errors.append(f"YouTube download failed: {str(e)}")

    if not audio_path or not Path(audio_path).exists():
        errors.append(f"Audio file not found or failed to load: {audio_path}")

    return {"audio_path": audio_path, "errors": errors}


def features_node(state: AnalysisState) -> dict:
    """Extract key, tempo, beats, and chords using our Librosa fallback engines."""
    audio_path = state.get("audio_path")
    errors = list(state.get("errors", []))

    if errors:
        return {}

    from backend.ml.key_estimation import estimate_key_and_tempo
    from backend.ml.beat_tracking import track_beats
    from backend.ml.chord_detection import detect_chords

    try:
        key, tempo = estimate_key_and_tempo(audio_path)
        beats = track_beats(audio_path)
        chords = detect_chords(audio_path)
        return {
            "key": key,
            "tempo": tempo,
            "beats": beats,
            "chords": chords,
        }
    except Exception as e:
        errors.append(f"Feature extraction failed: {str(e)}")
        return {"errors": errors, "retries": state.get("retries", 0) + 1}


def roman_analysis_node(state: AnalysisState) -> dict:
    """Convert chord labels to Roman numerals based on the detected key."""
    key = state.get("key", "C major")
    chords = state.get("chords", [])
    
    if not chords:
        return {"roman": None}

    # 1. Parse Key
    match = re.match(r"^([A-G][b#]?)\s+(major|minor)$", key, re.IGNORECASE)
    key_root = match.group(1).upper() if match else "C"
    key_mode = match.group(2).lower() if match else "major"

    # Pitch naming system
    notes = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
    enharmonics = {"DB": "C#", "EB": "D#", "GB": "F#", "AB": "G#", "BB": "A#"}

    def get_pitch_class(note: str) -> int:
        n = note.upper()
        n = enharmonics.get(n, n)
        return notes.index(n) if n in notes else 0

    key_pc = get_pitch_class(key_root)

    # Roman numerals for major/minor scales (0 to 11 semitone offsets from root)
    # Maps semitone offset -> (RomanNumeralString, is_minor)
    diatonic_major = {
        0: ("I", False),   2: ("ii", True),   4: ("iii", True),
        5: ("IV", False),  7: ("V", False),   9: ("vi", True),
        11: ("vii°", True)
    }
    diatonic_minor = {
        0: ("i", True),    2: ("ii°", True),  3: ("III", False),
        5: ("iv", True),   7: ("v", True),    8: ("VI", False),
        10: ("VII", False)
    }

    diatonic_map = diatonic_minor if key_mode == "minor" else diatonic_major

    roman_chords = []
    functions = []

    # Process first 16 unique chords for progression summary
    seen = []
    for c_event in chords:
        c_name = c_event.chord
        if c_name in ("N.C.", "N", ""):
            continue
        
        # Parse root and quality
        c_match = re.match(r"^([A-G][b#]?)(.*)$", c_name)
        if not c_match:
            continue
        
        c_root, c_suffix = c_match.groups()
        c_pc = get_pitch_class(c_root)
        
        # Calculate interval offset
        offset = (c_pc - key_pc) % 12
        
        # Map to roman numeral
        if offset in diatonic_map:
            numeral, is_min = diatonic_map[offset]
            # Adjust case based on chord type
            is_minor_chord = "m" in c_suffix.lower() and "maj" not in c_suffix.lower()
            if is_minor_chord and not is_min:
                numeral = numeral.lower()
            elif not is_minor_chord and is_min:
                numeral = numeral.upper()
        else:
            # Chromatic/Borrowed Chord (simple fallback)
            accidental = "b" if offset in (1, 3, 6, 8, 10) else "#"
            # Approximate chromatic degree
            numeral = f"{accidental}degree"
        
        roman_chords.append(numeral)
        
        # Determine simple function
        if offset == 0:
            functions.append("tonic")
        elif offset == 7:
            functions.append("dominant")
        elif offset == 5:
            functions.append("subdominant")
        elif offset == 9 if key_mode == "major" else offset == 3:
            functions.append("submediant")
        else:
            functions.append("borrowed")

    # Deduplicate progressions to keep unique representations
    dedup_roman = []
    dedup_func = []
    for r, f in zip(roman_chords, functions):
        if not dedup_roman or dedup_roman[-1] != r:
            dedup_roman.append(r)
            dedup_func.append(f)

    return {
        "roman": RomanAnalysis(
            key=key,
            progression=dedup_roman[:8],
            function=dedup_func[:8]
        )
    }


def theory_node(state: AnalysisState) -> dict:
    """LLM call: generate natural-language theory explanation."""
    from backend.chains.theory_chain import build_theory_chain
    from backend.schemas import SongAnalysis

    # Build intermediate SongAnalysis object
    song_obj = SongAnalysis(
        duration=float(state["chords"][-1].end) if state.get("chords") else 0.0,
        key=state.get("key", "C major"),
        tempo=state.get("tempo", 120.0),
        chords=state.get("chords", []),
        roman=state.get("roman")
    )

    try:
        chain = build_theory_chain()
        text = chain.invoke(song_obj)
        return {"theory_explanation": text}
    except Exception as e:
        return {"theory_explanation": f"Harmonic analysis unavailable: {str(e)}"}


def instrument_node(state: AnalysisState) -> dict:
    """LLM + deterministic chord-diagram merge -> InstrumentGuide."""
    from backend.chains.instrument_chain import build_instrument_chain
    from backend.schemas import SongAnalysis

    song_obj = SongAnalysis(
        duration=float(state["chords"][-1].end) if state.get("chords") else 0.0,
        key=state.get("key", "C major"),
        tempo=state.get("tempo", 120.0),
        chords=state.get("chords", []),
        roman=state.get("roman")
    )

    payload = {
        "analysis": song_obj,
        "instrument": state.get("instrument", "guitar"),
        "difficulty": state.get("difficulty", "beginner")
    }

    try:
        chain = build_instrument_chain()
        guide: InstrumentGuide = chain.invoke(payload)
        return {"instrument_guide": guide}
    except Exception as e:
        # Fallback empty guide
        return {
            "instrument_guide": InstrumentGuide(
                instrument=payload["instrument"],
                difficulty=payload["difficulty"],
                chord_diagrams=[],
                tips=[f"Playing guide unavailable: {str(e)}"]
            )
        }


def similarity_node(state: AnalysisState) -> dict:
    """Retrieve similar songs by chord progression (RAG)."""
    from backend.chains.similarity_chain import find_similar
    chords_list = [c.chord for c in state.get("chords", [])]
    
    similar = find_similar(chords_list)
    return {"similar_songs": similar}


def should_retry(state: AnalysisState) -> str:
    """Decide whether to retry feature extraction on error."""
    if state.get("errors") and state.get("retries", 0) < 2:
        return "retry"
    if state.get("errors"):
        return "fail"
    return "ok"
