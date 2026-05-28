"""
LangChain chatbot coordinator for the AURA music/site guide assistant.
Vault ref: 03-LangChain-Core/02-Models-Prompts-LCEL.md
"""
from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.output_parsers import StrOutputParser
from backend.chains.llm_factory import build_llm
from backend.prompts.chat_prompt import chat_prompt


def get_chat_response(message: str, history: list[dict]) -> str:
    """Invokes AURA AI assistant with the provided history and user message.

    'history' is a list of dictionaries with structure:
      {"role": "user" | "assistant", "content": "..."}
    """
    langchain_messages = []
    # Limit history to the last 10 messages to save context/token budget
    for item in history[-10:]:
        role = item.get("role")
        content = item.get("content", "")
        if role == "user":
            langchain_messages.append(HumanMessage(content=content))
        elif role == "assistant":
            langchain_messages.append(AIMessage(content=content))

    try:
        # Use a slightly higher creative temperature for natural conversational flow
        llm = build_llm(temperature=0.7)
        chain = chat_prompt | llm | StrOutputParser()
        
        return chain.invoke({"message": message, "history": langchain_messages})
    except Exception as e:
        # Graceful local fallback if local Ollama or cloud providers are offline
        return (
            f"**[AURA Transmission Offline]**\n\n"
            f"Greetings! I was unable to connect to the configured LLM engine. Here is a local fallback guide:\n\n"
            f"- **Scriabin Pitch Mapping:** C is Crimson Red (`#FF0000`), G is Orange (`#FF7F00`), E is Sky Blue (`#00BFFF`), and A is Green (`#00FF00`).\n"
            f"- **How to analyze a song:** Drag and drop an audio file onto the dashboard or paste a YouTube link, then click 'Analyze'.\n"
            f"- **Stem Mixer:** Go to the 'Stems' tab in the player to adjust Vocals, Drums, Bass, and Melodics.\n\n"
            f"*(Debug detail: {str(e)})*"
        )

from typing import AsyncGenerator

async def get_chat_response_stream(message: str, history: list[dict]) -> AsyncGenerator[str, None]:
    """Invokes AURA AI assistant via streaming (SSE)."""
    langchain_messages = []
    for item in history[-10:]:
        role = item.get("role")
        content = item.get("content", "")
        if role == "user":
            langchain_messages.append(HumanMessage(content=content))
        elif role == "assistant":
            langchain_messages.append(AIMessage(content=content))

    try:
        llm = build_llm(temperature=0.7)
        chain = chat_prompt | llm | StrOutputParser()
        
        async for chunk in chain.astream({"message": message, "history": langchain_messages}):
            yield chunk
    except Exception as e:
        yield (
            f"**[AURA Transmission Offline]**\n\n"
            f"Greetings! I was unable to connect to the configured LLM engine.\n\n"
            f"*(Debug detail: {str(e)})*"
        )
