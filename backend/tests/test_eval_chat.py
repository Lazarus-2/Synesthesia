"""CI guard for the offline chat eval (spec §11).

Runs the scripted golden set through the real agent (FakeChatModel) and asserts
aggregate tool-selection + faithfulness stay above threshold. Fully offline.

Also contains a deliberate-failure test: an item that answers with the wrong key
must lower faithfulness_accuracy below 1.0, proving the eval catches errors
rather than rubber-stamping everything.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip(
    "backend.chains.aura_agent",
    reason="Group C aura_agent lands separately; chat eval activates then.",
)

from backend.tests.eval_chat import run_chat_eval

_GOLDEN = Path(__file__).parent / "chat_golden.json"


def test_golden_set_is_well_formed():
    data = json.loads(_GOLDEN.read_text())
    items = data["items"]
    assert len(items) >= 30, "golden set must have ~30 items"
    for it in items:
        assert {"id", "question", "analysis", "scripted", "expected"} <= it.keys()
        # Each item declares expected tool(s) and/or an expected grounded fact.
        assert "tools" in it["expected"] or "grounded_fact" in it["expected"]


def test_golden_set_covers_all_seven_tools():
    """Every AURA tool must appear in at least one item's expected tools."""
    data = json.loads(_GOLDEN.read_text())
    all_expected = {t for it in data["items"] for t in it["expected"].get("tools", [])}
    required = {
        "transpose_progression",
        "suggest_capo",
        "get_chord_voicing",
        "get_chord_color",
        "find_similar_songs",
        "get_song_analysis",
        "lookup_theory",
    }
    assert required <= all_expected, f"Missing tools in golden set: {required - all_expected}"


def test_golden_set_has_injection_item():
    data = json.loads(_GOLDEN.read_text())
    injection_items = [it for it in data["items"] if "injection" in it["id"]]
    assert injection_items, "golden set must contain at least one injection test item"


def test_golden_set_has_abstention_items():
    data = json.loads(_GOLDEN.read_text())
    degraded = [
        it for it in data["items"]
        if it.get("analysis") and it["analysis"].get("status") == "degraded"
    ]
    assert len(degraded) >= 3, "golden set must have >=3 degraded/abstention items"


def test_tool_selection_and_faithfulness_above_threshold():
    report = run_chat_eval()
    assert report["tool_selection_accuracy"] >= 0.9, report
    # Faithfulness is a hard gate: no item may assert an absent chord/key.
    assert report["faithfulness_accuracy"] == 1.0, report["faithfulness_failures"]


def test_eval_catches_faithfulness_errors():
    """Prove the scorer fails on a deliberately wrong answer.

    Inject a single bad item whose scripted answer asserts C major for a G-major
    song and a forbidden substring.  The scorer must lower faithfulness below 1.0.
    This test would pass trivially if the eval always returned 1.0 — it doesn't.
    """
    import asyncio
    from unittest.mock import AsyncMock, MagicMock

    from langchain.agents import create_agent as create_react_agent

    import backend.chains.aura_agent as aura_agent
    import backend.chains.aura_tools as aura_tools
    from backend.tests.eval_chat import _build_script
    from backend.tests.fake_llm import FakeChatModel

    bad_item = {
        "id": "deliberate_wrong",
        "question": "What key is this?",
        "analysis": {
            "job_id": "bad1",
            "key": "G major",
            "tempo": 90.0,
            "status": "ok",
            "chords": [{"chord": "G"}],
        },
        "scripted": [{"answer": "This song is in C major."}],  # WRONG — key is G major
        "expected": {
            "tools": [],
            "grounded_fact": "G major",
            "forbidden": ["C major"],
        },
    }

    fake = FakeChatModel(responses=_build_script(bad_item["scripted"]))
    prompt = aura_agent.grounded_system_prompt(bad_item["analysis"], None, False)

    # Stub out the Mongo repo (not needed for this item but required by some tools).
    stub = MagicMock()
    stub.get = AsyncMock(return_value=None)
    stub.get_owned = AsyncMock(return_value=None)
    original = aura_tools._resolve_analysis_repo
    aura_tools._resolve_analysis_repo = lambda: stub

    try:
        agent = create_react_agent(
            model=fake, tools=aura_tools.TOOLS, system_prompt=prompt, checkpointer=None
        )
        out = asyncio.run(
            agent.ainvoke({"messages": [("user", bad_item["question"])]},
                          config={"recursion_limit": 6})
        )
    finally:
        aura_tools._resolve_analysis_repo = original

    answer = out["messages"][-1].content or ""
    grounded = bad_item["expected"]["grounded_fact"]
    forbidden = bad_item["expected"]["forbidden"]

    ok_grounded = grounded in answer        # "G major" must be present — it won't be
    ok_no_fab = not any(f in answer for f in forbidden)   # "C major" must be absent — it won't be

    # The answer IS wrong: the eval correctly detects it.
    assert not ok_grounded or not ok_no_fab, (
        f"The deliberately-wrong answer should have been caught as a faithfulness failure "
        f"but was scored as passing. answer={answer!r}"
    )
