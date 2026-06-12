"""Theory explanation chain: SongAnalysis -> TheoryExplanation.

Phase 3 G2
----------
The chain now returns the structured :class:`~backend.schemas.TheoryExplanation`
object directly.  The ``_flatten`` helper is kept as a module-level utility
(``to_text``) for back-compat and for the offline-degradation path in
``theory_node``, but it is NOT wired into the chain's return value anymore.

``theory_node`` (nodes.py) is responsible for writing the structured object
onto ``SongAnalysis.theory``; ``SongAnalysis._sync_theory_explanation``
then back-fills ``.theory_explanation`` automatically.

Vault ref: 03-LangChain-Core/02-Models-Prompts-LCEL.md
"""

from __future__ import annotations

from langchain_core.runnables import Runnable, RunnableLambda

from backend.chains.llm_factory import build_structured_llm
from backend.config import get_settings
from backend.prompts.theory_prompt import theory_prompt
from backend.schemas import SongAnalysis, TheoryExplanation


def _confidence_note(analysis: SongAnalysis) -> str:
    """Render the key-confidence note the v3 prompt hedges on (Phase 4 G5)."""
    conf = analysis.key_confidence
    if conf is None:
        return "unknown (analyzed before confidence tracking existed)"
    threshold = get_settings().key_confidence_low_threshold
    pct = f"{conf * 100:.0f}%"
    if conf < threshold:
        return (
            f"LOW ({pct}) — the detected key is uncertain; hedge key-dependent "
            f"claims (say the song is 'likely in {analysis.key}') and avoid "
            "asserting borrowed-chord or modulation interpretations that hinge "
            "on the exact key."
        )
    return f"{pct} — the detected key is reliable; state it plainly."


def _format_inputs(analysis: SongAnalysis) -> dict:
    chord_str = " -> ".join(c.chord for c in analysis.chords[:32])
    roman = analysis.roman

    # THEORY-CAP: cap Roman numerals like chords (long songs blew up the prompt).
    roman_str = " -> ".join(roman.progression[:32]) if roman else "unknown"

    # G2.3: inject deterministic cadence facts if G1 has populated them.
    cadence_facts = ""
    if roman and getattr(roman, "cadences", None):
        cadences = roman.cadences
        # cadences is list[dict] from RomanAnalysis — format each entry
        parts = []
        for c in cadences:
            if isinstance(c, dict):
                parts.append(f"{c.get('type', '?')} at index {c.get('index', '?')}")
            else:
                parts.append(str(c))
        cadence_facts = "; ".join(parts)

    # THEORY-CAP: modulations were computed but never reached the prompt.
    if roman and getattr(roman, "modulations", None):
        mod_parts = [
            f"modulation to {m.get('to_key', '?')} at index {m.get('at_index', '?')}"
            for m in roman.modulations
            if isinstance(m, dict)
        ]
        if mod_parts:
            cadence_facts = "; ".join(filter(None, [cadence_facts, *mod_parts]))

    return {
        "key": analysis.key,
        "key_confidence_note": _confidence_note(analysis),
        "tempo": f"{analysis.tempo:.0f}",
        "chords": chord_str,
        "roman": roman_str,
        "cadence_facts": cadence_facts or "None detected",
    }


def _flatten(explanation: TheoryExplanation) -> str:
    """Render the structured analysis as Markdown.

    Kept as a utility for the offline-degradation path and for legacy callers.
    No longer wired into build_theory_chain()'s return type.
    """
    lines = [explanation.key_summary, "", explanation.function_explanation]
    if explanation.pattern_name:
        lines += ["", f"**Pattern:** {explanation.pattern_name}"]
    if explanation.notable_techniques:
        bullets = "\n".join(f"- {t}" for t in explanation.notable_techniques)
        lines += ["", "**Notable techniques:**", bullets]
    if explanation.similar_song:
        lines += ["", f"**Similar:** {explanation.similar_song}"]
    return "\n".join(lines).strip()


# Public alias for _flatten — preferred name going forward.
to_text = _flatten


def build_theory_chain() -> Runnable:
    """Build the chain.

    Call ``.invoke(SongAnalysis) -> TheoryExplanation``.

    The caller (theory_node) is responsible for attaching the result to
    ``SongAnalysis.theory`` and persisting it.
    """
    s = get_settings()
    structured = build_structured_llm(TheoryExplanation, temperature=s.theory_temperature)
    # No _flatten at the end — returns TheoryExplanation directly.
    return RunnableLambda(_format_inputs) | theory_prompt | structured
