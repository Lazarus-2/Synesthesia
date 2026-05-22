"""
Individual nodes of the analysis graph.
Each node is a pure function: state -> partial state.
Vault ref: 04-LangGraph-Core/02-State-Nodes-Edges.md
"""
from __future__ import annotations

from backend.graph.state import AnalysisState


def ingest_node(state: AnalysisState) -> dict:
    """Download YouTube audio or validate uploaded file.
    TODO(Module 4, Lesson 2): use yt-dlp if state['youtube_url'] is set.
    """
    # import yt_dlp; ...
    return {"errors": state.get("errors", [])}


def features_node(state: AnalysisState) -> dict:
    """Run key/tempo/beats/chords in parallel or sequentially.
    TODO(Module 4, Lesson 2 / Lesson 5 for parallelism):
      - call backend.ml.key_estimation.estimate_key_and_tempo
      - call backend.ml.beat_tracking.track_beats
      - call backend.ml.chord_detection.detect_chords
    """
    # from backend.ml.chord_detection import detect_chords
    # from backend.ml.beat_tracking import track_beats
    # from backend.ml.key_estimation import estimate_key_and_tempo
    # key, tempo = estimate_key_and_tempo(state["audio_path"])
    # beats = track_beats(state["audio_path"])
    # chords = detect_chords(state["audio_path"])
    # return {"key": key, "tempo": tempo, "beats": beats, "chords": chords}
    return {}


def roman_analysis_node(state: AnalysisState) -> dict:
    """Convert chord labels -> roman numerals given the key.
    TODO(Module 4, Lesson 2): implement with music21 or a small lookup.
    """
    return {}


def theory_node(state: AnalysisState) -> dict:
    """LLM call: generate natural-language theory explanation."""
    # from backend.chains.theory_chain import build_theory_chain
    # chain = build_theory_chain()
    # text = chain.invoke(_build_song_analysis(state))
    # return {"theory_explanation": text}
    return {}


def instrument_node(state: AnalysisState) -> dict:
    """LLM + deterministic chord-diagram merge -> InstrumentGuide."""
    # from backend.chains.instrument_chain import build_instrument_chain
    # chain = build_instrument_chain()
    # result = chain.invoke({...})
    # return {"instrument_guide": InstrumentGuide(...)}
    return {}


def similarity_node(state: AnalysisState) -> dict:
    """Retrieve similar songs by chord progression (RAG)."""
    # from backend.chains.similarity_chain import find_similar
    # return {"similar_songs": find_similar([c.chord for c in state["chords"]])}
    return {}


# TODO(Module 4, Lesson 3): add conditional-routing helpers
def should_retry(state: AnalysisState) -> str:
    """Decide whether to retry feature extraction on error."""
    if state.get("errors") and state.get("retries", 0) < 2:
        return "retry"
    if state.get("errors"):
        return "fail"
    return "ok"
