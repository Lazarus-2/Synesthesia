"""
Integration tests for the full LangGraph pipeline.
Vault refs:
  - 03-LangChain-Core/05-Testing-Debugging-LangChain.md
  - 04-LangGraph-Core/02-State-Nodes-Edges.md

These tests use a short test_song.mp3 you place in tests/audio/.
"""
from pathlib import Path

import pytest

from backend.graph.graph import get_graph

AUDIO = Path(__file__).parent / "audio" / "test_song.mp3"

pytestmark = pytest.mark.skipif(
    not AUDIO.exists(), reason="Put a short mp3 at tests/audio/test_song.mp3"
)


@pytest.mark.asyncio
async def test_pipeline_produces_chords():
    graph = get_graph()
    result = await graph.ainvoke(
        {"audio_path": str(AUDIO), "instrument": "guitar", "difficulty": "beginner"},
        config={"configurable": {"thread_id": "test-1"}},
    )
    assert "chords" in result
    assert len(result["chords"]) > 0


# TODO(Module 4, Lesson 3): test conditional retry
# TODO(Module 4, Lesson 4): test checkpointing resume
