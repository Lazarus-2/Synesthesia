"""Tests for the reusable mock-LLM harness (spec §11).

The FakeChatModel must (a) replay scripted AIMessages in order, (b) survive
.bind_tools() the way every real provider class does, (c) record what tools it
was bound with, and (d) drive langgraph's create_react_agent through a
tool-call → tool-result → final-answer loop with zero network.
"""

from __future__ import annotations

from langchain_core.messages import AIMessage
from langchain_core.tools import tool

from backend.tests.fake_llm import FakeChatModel, ai, tool_call


def test_replays_scripted_responses_in_order():
    fake = FakeChatModel(responses=[ai("first"), ai("second")])
    r1 = fake.invoke([("user", "hi")])
    r2 = fake.invoke([("user", "again")])
    assert r1.content == "first"
    assert r2.content == "second"


def test_exhausted_script_returns_sentinel_not_indexerror():
    fake = FakeChatModel(responses=[ai("only")])
    fake.invoke([("user", "1")])
    # Second call past the end must not raise IndexError; returns a sentinel.
    overflow = fake.invoke([("user", "2")])
    assert isinstance(overflow.content, str)
    assert overflow.content  # non-empty sentinel


def test_bind_tools_is_recorded_and_returns_self_like():
    fake = FakeChatModel(responses=[ai("ok")])

    @tool
    def dummy(x: int) -> int:
        "Dummy."
        return x

    bound = fake.bind_tools([dummy])
    # The bound model still replays the script (provider classes all override
    # bind_tools; our fake returns a tool-aware self).
    assert bound.invoke([("user", "go")]).content == "ok"
    assert fake.bound_tools_names == ["dummy"]


def test_helpers_build_messages_and_tool_calls():
    msg = ai("", calls=[tool_call("adder", {"x": 2, "y": 3}, id="c1")])
    assert isinstance(msg, AIMessage)
    assert msg.tool_calls[0]["name"] == "adder"
    assert msg.tool_calls[0]["args"] == {"x": 2, "y": 3}
    assert msg.tool_calls[0]["id"] == "c1"


def test_drives_create_react_agent_tool_loop():
    from langgraph.prebuilt import create_react_agent

    @tool
    def adder(x: int, y: int) -> int:
        "Add x and y."
        return x + y

    fake = FakeChatModel(
        responses=[
            ai("", calls=[tool_call("adder", {"x": 2, "y": 3}, id="c1")]),
            ai("The answer is 5."),
        ]
    )
    agent = create_react_agent(model=fake, tools=[adder], prompt="sys", checkpointer=None)
    out = agent.invoke({"messages": [("user", "add 2 and 3")]}, config={"recursion_limit": 6})
    kinds = [type(m).__name__ for m in out["messages"]]
    assert "ToolMessage" in kinds
    assert out["messages"][-1].content == "The answer is 5."
