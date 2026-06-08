"""Theory explanation chain: SongAnalysis -> harmonic analysis.

Plan 2 C2 — structured output
-----------------------------
The LLM now returns a :class:`TheoryExplanation` (Pydantic) via
``with_structured_output``. The LLM SDK handles JSON repair; we no longer
rely on hoping the model spits clean prose under a 150-word cap.

Backward compatibility: the chain's public contract is still
``invoke(SongAnalysis) -> str`` because every consumer (theory_node,
AnalyzeResponse) expects a string. A trailing flattener turns the structured
object into the same humane Markdown text the previous prompt produced.
That preserves the API while gaining repair semantics inside the chain.

Vault ref: 03-LangChain-Core/02-Models-Prompts-LCEL.md
"""

from __future__ import annotations

from langchain_core.runnables import Runnable, RunnableLambda
from pydantic import BaseModel, Field

from backend.chains.llm_factory import build_structured_llm
from backend.config import get_settings
from backend.prompts.theory_prompt import theory_prompt
from backend.schemas import SongAnalysis


class TheoryExplanation(BaseModel):
    """Structured harmonic analysis the LLM is forced into."""

    key_summary: str = Field(
        description=(
            "One sentence stating the song's key and why. "
            "Example: 'The song is in C major; the I-V-vi-IV progression "
            "centers tonally on C.'"
        )
    )
    function_explanation: str = Field(
        description=(
            "Two-to-three sentences naming the harmonic function of each "
            "chord (tonic, dominant, subdominant, etc.)."
        )
    )
    pattern_name: str | None = Field(
        default=None,
        description=(
            "Well-known progression name if applicable "
            "(e.g. 'I-V-vi-IV pop progression', 'ii-V-I jazz turnaround'). "
            "Null if none fit."
        ),
    )
    notable_techniques: list[str] = Field(
        default_factory=list,
        description=(
            "Any standout techniques: modal mixture, secondary dominants, "
            "borrowed chords, modulations. Empty list if none."
        ),
    )
    similar_song: str | None = Field(
        default=None,
        description=(
            "One famous song using a similar progression, in 'Title — Artist' "
            "form. Null if you can't recall one with confidence."
        ),
    )


def _format_inputs(analysis: SongAnalysis) -> dict:
    chord_str = " -> ".join(c.chord for c in analysis.chords[:32])
    roman_str = " -> ".join(analysis.roman.progression) if analysis.roman else "unknown"
    return {
        "key": analysis.key,
        "tempo": f"{analysis.tempo:.0f}",
        "chords": chord_str,
        "roman": roman_str,
    }


def _flatten(explanation: TheoryExplanation) -> str:
    """Render the structured analysis as the Markdown string consumers expect."""
    lines = [explanation.key_summary, "", explanation.function_explanation]
    if explanation.pattern_name:
        lines += ["", f"**Pattern:** {explanation.pattern_name}"]
    if explanation.notable_techniques:
        bullets = "\n".join(f"- {t}" for t in explanation.notable_techniques)
        lines += ["", "**Notable techniques:**", bullets]
    if explanation.similar_song:
        lines += ["", f"**Similar:** {explanation.similar_song}"]
    return "\n".join(lines).strip()


def build_theory_chain() -> Runnable:
    """Build the chain. Call .invoke(SongAnalysis) -> str."""
    s = get_settings()
    structured = build_structured_llm(TheoryExplanation, temperature=s.theory_temperature)
    return RunnableLambda(_format_inputs) | theory_prompt | structured | RunnableLambda(_flatten)
