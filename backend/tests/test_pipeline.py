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


from backend.graph.nodes import should_retry

def test_should_retry_logic():
    """Test conditional edge routing based on errors and retries."""
    assert should_retry({"errors": ["Audio error"], "retries": 1}) == "retry"
    assert should_retry({"errors": ["Audio error"], "retries": 3}) == "fail"
    assert should_retry({"errors": [], "retries": 0}) == "ok"

@pytest.mark.asyncio
async def test_checkpointing_resume():
    """Test memory saver checkpointing."""
    graph = get_graph()
    config = {"configurable": {"thread_id": "checkpoint-test"}}
    
    # Push an initial state into the graph's memory saver manually
    graph.update_state(config, {"retries": 2, "errors": []})
    
    # Retrieve the state to ensure checkpointing works
    state = graph.get_state(config)
    assert state.values["retries"] == 2
    assert state.values["errors"] == []
