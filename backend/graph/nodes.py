"""
Individual nodes of the analysis graph.
Each node is a pure function: state -> partial state.
Vault ref: 04-LangGraph-Core/02-State-Nodes-Edges.md
"""

from __future__ import annotations

import ipaddress
import logging
import re
import socket
from pathlib import Path
from urllib.parse import urlparse

from backend.graph.state import AnalysisState
from backend.schemas import InstrumentGuide, RomanAnalysis, SongAnalysis


def _song_analysis_from_state(state: AnalysisState) -> SongAnalysis:
    """Pack the analysis-state slice every LLM chain needs.

    Both theory_node and instrument_node feed their LLM chains the same
    SongAnalysis object built from state, so the construction lives here.
    """
    chords = state.get("chords") or []
    return SongAnalysis(
        duration=float(chords[-1].end) if chords else 0.0,
        key=state.get("key", "C major"),
        tempo=state.get("tempo", 120.0),
        chords=chords,
        roman=state.get("roman"),
    )

logger = logging.getLogger(__name__)

# Domains explicitly allowed for yt-dlp ingestion. yt-dlp supports thousands of
# sites; restricting to YouTube prevents the endpoint from being abused as an
# arbitrary URL fetcher.
_YTDLP_ALLOWED_HOSTS = frozenset(
    {
        "youtube.com",
        "www.youtube.com",
        "m.youtube.com",
        "music.youtube.com",
        "youtu.be",
    }
)


def _validate_youtube_url(url: str) -> None:
    """Reject non-HTTPS schemes, non-YouTube hosts, and private/loopback IPs (SSRF).

    Raises ValueError with a user-safe message on rejection.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"Unsupported URL scheme: {parsed.scheme!r}")
    host = (parsed.hostname or "").lower()
    if not host:
        raise ValueError("URL has no host")
    if host not in _YTDLP_ALLOWED_HOSTS:
        raise ValueError(f"Host not allowed: {host!r}. Only YouTube URLs are accepted.")
    # Block hosts that resolve to private / loopback / link-local addresses.
    try:
        resolved = socket.getaddrinfo(host, None)
    except socket.gaierror as e:
        raise ValueError(f"Could not resolve host {host!r}: {e}") from e
    for family, _socktype, _proto, _canon, sockaddr in resolved:
        ip_str = sockaddr[0]
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:
            continue
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            raise ValueError(f"Host {host!r} resolves to disallowed address range ({ip_str})")


def ingest_node(state: AnalysisState) -> dict:
    """Download YouTube audio or validate uploaded file."""
    youtube_url = state.get("youtube_url")
    audio_path = state.get("audio_path")
    errors = list(state.get("errors", []))

    if youtube_url:
        try:
            _validate_youtube_url(youtube_url)
        except ValueError as e:
            errors.append(f"Rejected URL: {e}")
            return {"audio_path": audio_path, "errors": errors}

        try:
            import yt_dlp

            out_dir = Path("./storage/uploads")
            out_dir.mkdir(parents=True, exist_ok=True)

            out_path = out_dir / "%(id)s.%(ext)s"
            ydl_opts = {
                "format": "bestaudio/best",
                "outtmpl": str(out_path),
                "postprocessors": [
                    {
                        "key": "FFmpegExtractAudio",
                        "preferredcodec": "mp3",
                        "preferredquality": "192",
                    }
                ],
                "quiet": True,
                # Hardening: never expand playlists, cap file size, fail fast on
                # unexpected redirects to non-YouTube hosts.
                "noplaylist": True,
                "max_filesize": 100 * 1024 * 1024,  # 100 MB
                "extractor_args": {"youtube": {"player_client": ["web"]}},
            }

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(youtube_url, download=True)
                downloaded_file = out_dir / f"{info['id']}.mp3"
                audio_path = str(downloaded_file)
        except Exception as e:
            logger.warning("YouTube download failed for %r: %s", youtube_url, e)
            errors.append(f"YouTube download failed: {e}")

    if not audio_path or not Path(audio_path).exists():
        errors.append(f"Audio file not found or failed to load: {audio_path}")

    return {"audio_path": audio_path, "errors": errors}


def validate_audio_node(state: AnalysisState) -> dict:
    """Validate the staged audio file before ML processing (Plan 2 C3).

    Catches obvious failure modes (missing file, zero bytes, unreadable
    container, oversized duration) and surfaces them as structured errors
    instead of letting the features node crash deep in librosa.
    """
    audio_path = state.get("audio_path")
    errors = list(state.get("errors", []))

    # If a previous node already errored, don't compound the noise.
    if errors:
        return {}

    if not audio_path:
        errors.append("validate_audio: no audio path")
        return {"errors": errors}

    p = Path(audio_path)
    if not p.exists():
        errors.append(f"validate_audio: file does not exist: {audio_path}")
        return {"errors": errors}

    try:
        size = p.stat().st_size
    except OSError as e:
        errors.append(f"validate_audio: cannot stat {audio_path}: {e}")
        return {"errors": errors}

    if size == 0:
        errors.append(f"validate_audio: empty file: {audio_path}")
        return {"errors": errors}

    # Soft duration check — librosa can probe without fully decoding.
    try:
        import soundfile as sf

        with sf.SoundFile(str(p)) as f:
            duration_s = float(f.frames) / max(f.samplerate, 1)
            sr = f.samplerate
    except Exception as e:
        logger.warning("validate_audio: soundfile probe failed for %s: %s", p, e)
        # Don't hard-fail here — librosa may still load it via the audioread
        # backend. Let features_node be the authoritative loader.
        return {}

    # Hard cap mirrors the ML modules (chord_detection / beat_tracking) which
    # truncate at MAX_AUDIO_DURATION_S already; surfacing it as a clear error
    # is friendlier than silently chopping a 10-minute song to 3 minutes.
    from backend.config import MAX_AUDIO_DURATION_S

    if duration_s > MAX_AUDIO_DURATION_S * 1.05:
        errors.append(
            f"validate_audio: duration {duration_s:.1f}s exceeds limit {MAX_AUDIO_DURATION_S}s"
        )
        return {"errors": errors}

    if sr < 8000:
        errors.append(f"validate_audio: sample rate {sr}Hz is too low for chord analysis")
        return {"errors": errors}

    logger.info(
        "validate_audio: %s — duration=%.1fs sr=%d size=%d bytes",
        p.name,
        duration_s,
        sr,
        size,
    )
    return {}


def features_node(state: AnalysisState) -> dict:
    """Extract key, tempo, beats, chords, and song structure (Plan 3 B2).

    Defense-in-depth (live-test report 2): ``retries`` is **always**
    incremented on entry, including on the successful path. This guarantees
    that even if a future bug routes a clean-state run back here (or if the
    conditional edges from ingest/validate get accidentally removed), the
    counter advances and ``should_retry`` will eventually fail rather than
    looping until the 10007-iteration recursion limit fires.
    """
    audio_path = state.get("audio_path")
    errors = list(state.get("errors", []))
    next_retries = state.get("retries", 0) + 1

    from backend.ml.beat_tracking import track_beats
    from backend.ml.chord_detection import detect_chords
    from backend.ml.key_estimation import estimate_key_and_tempo
    from backend.ml.structure_detection import detect_sections

    try:
        key, tempo = estimate_key_and_tempo(audio_path)
        beats = track_beats(audio_path)
        chords = detect_chords(audio_path)
        sections = detect_sections(audio_path)  # Plan 3 B2; may return []
        return {
            "key": key,
            "tempo": tempo,
            "beats": beats,
            "chords": chords,
            "sections": sections,
            "retries": next_retries,
        }
    except Exception as e:
        errors.append(f"Feature extraction failed: {str(e)}")
        return {"errors": errors, "retries": next_retries}


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
        0: ("I", False),
        2: ("ii", True),
        4: ("iii", True),
        5: ("IV", False),
        7: ("V", False),
        9: ("vi", True),
        11: ("vii°", True),
    }
    diatonic_minor = {
        0: ("i", True),
        2: ("ii°", True),
        3: ("III", False),
        5: ("iv", True),
        7: ("v", True),
        8: ("VI", False),
        10: ("VII", False),
    }

    diatonic_map = diatonic_minor if key_mode == "minor" else diatonic_major

    roman_chords = []
    functions = []

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

    return {"roman": RomanAnalysis(key=key, progression=dedup_roman[:8], function=dedup_func[:8])}


def theory_node(state: AnalysisState) -> dict:
    """LLM call: generate natural-language theory explanation."""
    from backend.chains.theory_chain import build_theory_chain

    song_obj = _song_analysis_from_state(state)

    try:
        chain = build_theory_chain()
        text = chain.invoke(song_obj)
        return {"theory_explanation": text}
    except Exception as e:
        # Human-friendly degraded message — don't expose raw exception text.
        # The deterministic chord/Roman analysis is still useful on its own;
        # we make that explicit so users don't think analysis is "broken".
        logger.warning("theory_node: LLM unavailable: %s", e)
        key = song_obj.key
        roman = song_obj.roman.progression if song_obj.roman else []
        roman_str = " → ".join(roman[:8]) if roman else "(no progression detected)"
        return {
            "theory_explanation": (
                f"The deterministic part of the analysis ran cleanly: this song "
                f"is in **{key}** with the progression **{roman_str}**.\n\n"
                f"_The AI commentary engine is offline right now, so the prose "
                f"explanation is unavailable for this run. Restart Ollama (or "
                f"flip ``LLM_PROVIDER`` to a reachable backend) and re-analyze "
                f"to get the full narrative._"
            )
        }


def instrument_node(state: AnalysisState) -> dict:
    """LLM + deterministic chord-diagram merge -> InstrumentGuide."""
    from backend.chains.instrument_chain import build_instrument_chain

    song_obj = _song_analysis_from_state(state)

    payload = {
        "analysis": song_obj,
        "instrument": state.get("instrument", "guitar"),
        "difficulty": state.get("difficulty", "beginner"),
    }

    try:
        chain = build_instrument_chain()
        guide: InstrumentGuide = chain.invoke(payload)
        return {"instrument_guide": guide}
    except Exception as e:
        # Fall back to a guide containing just the deterministic chord
        # diagrams — better than an empty guide that hides the chord data
        # users came for.
        logger.warning("instrument_node: LLM unavailable: %s", e)
        from backend.tools.voicings import get_chord_diagrams

        chords_list = [c.chord for c in payload["analysis"].chords]
        diagrams = get_chord_diagrams(chords_list, payload["instrument"])
        return {
            "instrument_guide": InstrumentGuide(
                instrument=payload["instrument"],
                difficulty=payload["difficulty"],
                chord_diagrams=diagrams,
                tips=[
                    "The AI tutor is offline — chord shapes shown but "
                    "personalized strumming/fingering tips were skipped."
                ],
            )
        }


def stems_node(state: AnalysisState) -> dict:
    """Stem separation via demucs (Plan 3 A2).

    Gated by ``settings.enable_stems`` so dev boxes without a GPU can
    opt out. The actual demucs call lives in
    :mod:`backend.ml.stem_separation` and uses the ML registry singleton
    so the model loads once per worker process, not per request.

    The returned ``stems`` mapping uses *relative* paths under
    ``settings.stems_dir`` so the persistence layer can store them
    without leaking absolute filesystem paths.
    """
    from backend.config import get_settings
    from backend.ml.stem_separation import separate_stems

    audio_path = state.get("audio_path")
    settings = get_settings()
    if not audio_path or not settings.enable_stems:
        return {}

    job_id = Path(audio_path).stem.split("_")[0]
    out_dir = settings.stems_dir / job_id
    try:
        result = separate_stems(audio_path, out_dir)
    except Exception as e:
        logger.warning("stems_node: separation failed for %s: %s", job_id, e)
        return {}

    # Convert absolute Paths to relative-under-stems_dir strings.
    rel: dict[str, str] = {}
    for stem_name, p in result.items():
        try:
            rel[stem_name] = str(p.relative_to(settings.stems_dir))
        except (ValueError, AttributeError):
            rel[stem_name] = str(p)
    if rel:
        logger.info("stems_node: %d stems for job %s", len(rel), job_id)
    return {"stems": rel}


def similarity_node(state: AnalysisState) -> dict:
    """Retrieve similar songs by chord progression (RAG).

    Passes the detected key so the v2 sequence-aware embedding can rotate
    progressions into a common tonal frame (Plan 3 A6).
    """
    from backend.chains.similarity_chain import find_similar

    chords_list = [c.chord for c in state.get("chords", [])]
    similar = find_similar(chords_list, key=state.get("key"))
    return {"similar_songs": similar}


def has_errors_route(state: AnalysisState) -> str:
    """Conditional-edge helper: route to END as soon as a stage produces errors.

    Used right after :func:`ingest_node` and :func:`validate_audio_node` so a
    bad input (e.g. rejected YouTube URL) terminates the pipeline immediately
    instead of trickling through to ``features_node`` where ``should_retry``
    could loop indefinitely (Plan 3 live-test bug: "Recursion limit of 10007").
    """
    return "fail" if state.get("errors") else "ok"


def should_retry(state: AnalysisState) -> str:
    """Decide whether to retry feature extraction on error.

    Only invoked after ``features_node`` — by this point any pre-features
    errors have already been routed to END via :func:`has_errors_route`, so
    a non-empty ``errors`` list here is genuinely from features itself and
    we can retry once before giving up.

    Safety bound: ``features_node`` always increments ``retries`` (success
    or failure), so even pathological inputs can't loop more than a handful
    of times before ``retries >= MAX_FEATURE_RETRIES`` flips us to "fail".
    """
    MAX_FEATURE_RETRIES = 2
    if state.get("errors") and state.get("retries", 0) < MAX_FEATURE_RETRIES:
        return "retry"
    if state.get("errors"):
        return "fail"
    return "ok"
