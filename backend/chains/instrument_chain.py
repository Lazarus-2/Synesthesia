"""
Instrument guide chain: SongAnalysis + instrument -> playing tips + chord diagrams.
Vault ref: 03-LangChain-Core/02-Models-Prompts-LCEL.md
"""
from __future__ import annotations

from langchain_core.runnables import Runnable, RunnableLambda, RunnableParallel
from langchain_openai import ChatOpenAI

from backend.config import get_settings
from backend.prompts.instrument_prompt import instrument_prompt
from backend.schemas import Instrument, InstrumentGuide, SongAnalysis
from backend.tools.voicings import get_chord_diagrams


def _format_inputs(payload: dict) -> dict:
    analysis: SongAnalysis = payload["analysis"]
    return {
        "key": analysis.key,
        "tempo": f"{analysis.tempo:.0f}",
        "chords": " -> ".join(c.chord for c in analysis.chords[:16]),
        "section": payload.get("section", "full song"),
        "instrument": payload["instrument"],
        "difficulty": payload["difficulty"],
    }


def build_instrument_chain() -> Runnable:
    """Runnable expecting: {"analysis": SongAnalysis, "instrument": ..., "difficulty": ...}."""
    s = get_settings()
    llm = ChatOpenAI(
        model=s.model_name,
        temperature=s.instrument_temperature,
        api_key=s.openai_api_key,
    )

    # TODO(Module 3, Lesson 2):
    # Build a parallel runnable that produces:
    #   - "tips": LLM-generated strumming pattern + practice tips
    #   - "diagrams": deterministic chord shape lookup (no LLM)
    # Then combine into an InstrumentGuide.

    llm_tips = RunnableLambda(_format_inputs) | instrument_prompt | llm
    return RunnableParallel(
        tips=llm_tips,
        diagrams=RunnableLambda(
            lambda p: get_chord_diagrams(
                chords=[c.chord for c in p["analysis"].chords],
                instrument=p["instrument"],
            )
        ),
    )
