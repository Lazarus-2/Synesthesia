"""Offline AURA chat-eval scorer (spec §11).

Drives the REAL grounded_system_prompt + create_react_agent with a scripted
FakeChatModel so each golden item runs deterministically with no network and
no live model. Scores:

  * tool_selection_accuracy — fraction of items where the tools the agent
    actually called == the expected tool set.
  * faithfulness_accuracy   — fraction of items whose final answer contains the
    expected grounded fact AND none of the forbidden (fabricated) facts. A hard
    gate: an answer asserting a chord/key/tempo the analysis lacks fails.

The two tools that normally query MongoDB (get_song_analysis, find_similar_songs)
are served from the analysis data embedded in each golden item via a lightweight
repo stub, keeping the eval fully offline.

Run standalone:
    backend/.venv/bin/python -m backend.tests.eval_chat
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

from langgraph.prebuilt import create_react_agent

from backend.tests.fake_llm import FakeChatModel, ai
from backend.tests.fake_llm import tool_call as _tool_call

_GOLDEN = Path(__file__).parent / "chat_golden.json"


def _build_script(scripted: list[dict[str, Any]]) -> list:
    """Turn a golden 'scripted' list into FakeChatModel responses."""
    out = []
    for i, turn in enumerate(scripted):
        if "tool" in turn:
            out.append(
                ai("", calls=[_tool_call(turn["tool"], turn.get("args", {}), id=f"call_{i}")])
            )
        else:
            out.append(ai(turn["answer"]))
    return out


def _tools_called(messages: list[Any]) -> list[str]:
    """Extract, in order, the tool names the agent actually invoked."""
    names: list[str] = []
    for m in messages:
        for call in getattr(m, "tool_calls", None) or []:
            names.append(call["name"])
    return names


def _make_repo_stub(analysis: dict[str, Any] | None):
    """Build a lightweight AnalysisRepo stub that serves ``analysis`` by job_id.

    The real get_song_analysis / find_similar_songs call _resolve_analysis_repo()
    then await repo.get(job_id) or repo.get_owned(job_id, uid).  We replace the
    repo object so both paths return the embedded analysis document without Mongo.
    """
    stub = MagicMock()

    async def _get(job_id: str) -> dict | None:
        if analysis and analysis.get("job_id") == job_id:
            return analysis
        return None

    async def _get_owned(job_id: str, uid: Any = None) -> dict | None:  # noqa: ARG001
        return await _get(job_id)

    stub.get = AsyncMock(side_effect=_get)
    stub.get_owned = AsyncMock(side_effect=_get_owned)
    return stub


async def _run_item(
    it: dict[str, Any],
    aura_agent: Any,
    aura_tools: Any,
) -> dict[str, Any]:
    """Run a single golden item through the agent and return metrics."""
    analysis = it["analysis"]

    # Build the FakeChatModel scripted for this item.
    fake = FakeChatModel(responses=_build_script(it["scripted"]))

    # Build the grounded system prompt from the golden item's analysis.
    prompt = aura_agent.grounded_system_prompt(analysis, None, False)

    # Patch the Mongo-dependent repo resolver so get_song_analysis /
    # find_similar_songs are served from the embedded analysis without DB.
    repo_stub = _make_repo_stub(analysis)
    original_resolver = aura_tools._resolve_analysis_repo
    aura_tools._resolve_analysis_repo = lambda: repo_stub

    try:
        # Build an offline agent using the real TOOLS list + fake model.
        # We use create_react_agent directly so we can inject the fake model
        # without going through build_chat_llm.
        agent = create_react_agent(
            model=fake,
            tools=aura_tools.TOOLS,
            prompt=prompt,
            checkpointer=None,
        )

        out = await agent.ainvoke(
            {"messages": [("user", it["question"])]},
            config={"recursion_limit": 6},
        )
    finally:
        aura_tools._resolve_analysis_repo = original_resolver

    called = _tools_called(out["messages"])
    answer = out["messages"][-1].content or ""

    expected_tools = it["expected"].get("tools", [])
    tool_ok = set(called) == set(expected_tools)

    grounded = it["expected"].get("grounded_fact")
    forbidden = it["expected"].get("forbidden", [])
    ok_grounded = (grounded is None) or (grounded in answer)
    ok_no_fab = not any(f in answer for f in forbidden)
    faith_ok = ok_grounded and ok_no_fab

    result: dict[str, Any] = {
        "id": it["id"],
        "called": called,
        "expected_tools": expected_tools,
        "tool_ok": tool_ok,
        "answer": answer,
        "grounded": grounded,
        "forbidden": forbidden,
        "faith_ok": faith_ok,
        "ok_grounded": ok_grounded,
        "ok_no_fab": ok_no_fab,
    }
    return result


async def _run_eval_async() -> dict[str, Any]:
    """Async implementation of the eval loop."""
    import backend.chains.aura_agent as aura_agent
    import backend.chains.aura_tools as aura_tools

    data = json.loads(_GOLDEN.read_text())
    items = data["items"]

    results = [await _run_item(it, aura_agent, aura_tools) for it in items]

    tool_hits = sum(1 for r in results if r["tool_ok"])
    faith_hits = sum(1 for r in results if r["faith_ok"])
    faithfulness_failures = [
        {
            "id": r["id"],
            "answer": r["answer"],
            "grounded": r["grounded"],
            "forbidden": r["forbidden"],
        }
        for r in results
        if not r["faith_ok"]
    ]
    per_item = [
        {"id": r["id"], "called": r["called"], "expected_tools": r["expected_tools"]}
        for r in results
    ]

    n = len(items) or 1
    return {
        "n": len(items),
        "tool_selection_accuracy": tool_hits / n,
        "faithfulness_accuracy": faith_hits / n,
        "faithfulness_failures": faithfulness_failures,
        "per_item": per_item,
    }


def run_chat_eval() -> dict[str, Any]:
    """Run the full golden set and return a metrics report (sync entry point)."""
    return asyncio.run(_run_eval_async())


if __name__ == "__main__":
    report = run_chat_eval()
    print(
        f"[chat-eval] n={report['n']} "
        f"tool_selection={report['tool_selection_accuracy']:.2f} "
        f"faithfulness={report['faithfulness_accuracy']:.2f}"
    )
    for f in report["faithfulness_failures"]:
        print(f"  [FAITHFULNESS FAIL] {f['id']}: {f['answer']!r}")
    for item in report["per_item"]:
        if set(item["called"]) != set(item["expected_tools"]):
            print(
                f"  [TOOL MISMATCH] {item['id']}: "
                f"called={item['called']} expected={item['expected_tools']}"
            )
