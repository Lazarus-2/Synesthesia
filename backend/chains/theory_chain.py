"""
Theory explanation chain: SongAnalysis -> natural-language harmonic analysis.
Vault ref: 03-LangChain-Core/02-Models-Prompts-LCEL.md
"""
from __future__ import annotations

from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import Runnable, RunnableLambda
from langchain_openai import ChatOpenAI

from backend.config import get_settings
from backend.prompts.theory_prompt import theory_prompt
from backend.schemas import SongAnalysis


def _format_inputs(analysis: SongAnalysis) -> dict:
    chord_str = " -> ".join(c.chord for c in analysis.chords[:32])
    roman_str = (
        " -> ".join(analysis.roman.progression) if analysis.roman else "unknown"
    )
    return {
        "key": analysis.key,
        "tempo": f"{analysis.tempo:.0f}",
        "chords": chord_str,
        "roman": roman_str,
    }


def build_theory_chain() -> Runnable:
    """Build the chain. Call .invoke(SongAnalysis) -> str."""
    s = get_settings()
    llm = ChatOpenAI(
        model=s.model_name,
        temperature=s.theory_temperature,
        api_key=s.openai_api_key,
    )
    # TODO(Module 3, Lesson 2):
    # Use LCEL pipe syntax: RunnableLambda(_format_inputs) | theory_prompt | llm | StrOutputParser()
    return RunnableLambda(_format_inputs) | theory_prompt | llm | StrOutputParser()
