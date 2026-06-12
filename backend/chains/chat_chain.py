"""
LangChain chatbot coordinator for the AURA music/site guide assistant.
Vault ref: 03-LangChain-Core/02-Models-Prompts-LCEL.md
"""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from backend.chains.llm_factory import build_llm
from backend.config import get_settings
from backend.prompts.chat_prompt import chat_prompt

logger = logging.getLogger(__name__)


def _format_analysis_context(analysis: dict[str, Any] | None) -> str | None:
    """Render a compact context block from a SongAnalysis-shaped dict.

    Plan 3 A4: chat answers should reference *this* song's key, tempo, and
    progression instead of being generic. We render a short summary string
    (≤ 16 chords + Roman numerals) and inject it as an extra system message
    just below the AURA persona prompt.
    """
    if not analysis:
        return None
    key = analysis.get("key") or "Unknown"
    tempo = analysis.get("tempo")
    chords = analysis.get("chords") or []
    chord_names = [
        c.get("chord") if isinstance(c, dict) else getattr(c, "chord", "?") for c in chords[:16]
    ]
    roman_obj = analysis.get("roman")
    roman_progression: list[str] = []
    if isinstance(roman_obj, dict):
        roman_progression = list(roman_obj.get("progression") or [])
    elif roman_obj is not None:
        roman_progression = list(getattr(roman_obj, "progression", []) or [])

    key_confidence = analysis.get("key_confidence")
    key_line = f"- Key: {key}"
    if key_confidence is not None:
        key_line += f" (detection confidence {float(key_confidence) * 100:.0f}%)"
    lines = [
        "CURRENT SONG CONTEXT (use this when answering — refer to "
        "*this* song, not generic theory):",
        key_line,
    ]
    if key_confidence is not None and float(
        key_confidence
    ) < get_settings().key_confidence_low_threshold:
        lines.append(
            "- NOTE: key detection is uncertain for this track — hedge "
            "key-dependent answers."
        )
    if tempo is not None:
        lines.append(f"- Tempo: {float(tempo):.0f} BPM")
    if chord_names:
        lines.append(
            f"- Progression (first {len(chord_names)}): " + " → ".join(str(c) for c in chord_names)
        )
    if roman_progression:
        lines.append("- Roman numerals: " + " → ".join(roman_progression[:16]))
    title = analysis.get("title")
    if title:
        lines.append(f"- Title: {title}")
    return "\n".join(lines)


def _build_history(
    history: list[dict],
    analysis: dict[str, Any] | None = None,
) -> list:
    """Convert dict history to LangChain message objects.

    Only the last 10 turns of user history are kept; if ``analysis`` is
    supplied we prepend a SystemMessage with the rendered song context so
    the AURA persona answers in terms of *this* song.
    """
    msgs: list[Any] = []
    ctx = _format_analysis_context(analysis)
    if ctx:
        msgs.append(SystemMessage(content=ctx))
    for item in history[-10:]:
        role = item.get("role")
        content = item.get("content", "")
        if role == "user":
            msgs.append(HumanMessage(content=content))
        elif role == "assistant":
            msgs.append(AIMessage(content=content))
    return msgs


_OFFLINE_FALLBACK = (
    "**[AURA Transmission Offline]**\n\n"
    "I was unable to connect to the configured LLM engine. Here is a local fallback guide:\n\n"
    "- **Scriabin Pitch Mapping:** C is Crimson Red (`#FF0000`), G is Orange (`#FF7F00`), "
    "E is Sky Blue (`#00BFFF`), and A is Green (`#00FF00`).\n"
    "- **How to analyze a song:** Drag and drop an audio file onto the dashboard or paste a "
    "YouTube link, then click 'Analyze'.\n"
    "- **Stem Mixer:** Go to the 'Stems' tab in the player to adjust Vocals, Drums, Bass, "
    "and Melodics."
)


def get_chat_response(
    message: str,
    history: list[dict],
    analysis: dict[str, Any] | None = None,
) -> str:
    """Invokes the AURA chat assistant. Returns a fallback message on LLM failure.

    ``analysis``: optional SongAnalysis-shaped dict. When provided, a compact
    rendering is injected as a SystemMessage so AURA references the current
    song instead of giving generic theory answers (Plan 3 A4).
    """
    from langchain_core.output_parsers import StrOutputParser

    langchain_messages = _build_history(history, analysis=analysis)
    try:
        llm = build_llm(temperature=0.7)
        chain = chat_prompt | llm | StrOutputParser()
        return chain.invoke({"message": message, "history": langchain_messages})
    except Exception as e:
        logger.warning("Chat LLM invocation failed: %s", e, exc_info=True)
        return _OFFLINE_FALLBACK


async def get_chat_response_stream(
    message: str,
    history: list[dict],
    analysis: dict[str, Any] | None = None,
) -> AsyncGenerator[str, None]:
    """Streaming version of :func:`get_chat_response` for SSE."""
    from langchain_core.output_parsers import StrOutputParser

    langchain_messages = _build_history(history, analysis=analysis)
    try:
        llm = build_llm(temperature=0.7)
        chain = chat_prompt | llm | StrOutputParser()
        async for chunk in chain.astream({"message": message, "history": langchain_messages}):
            yield chunk
    except Exception as e:
        logger.warning("Chat LLM stream failed: %s", e, exc_info=True)
        yield _OFFLINE_FALLBACK
