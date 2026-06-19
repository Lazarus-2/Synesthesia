"""Reusable mock-LLM harness for AURA chat tests (spec §11).

No test should ever call a live model. ``FakeChatModel`` is a ``BaseChatModel``
that replays a scripted list of ``AIMessage`` objects (some carrying
``tool_calls``) so ``langgraph.create_react_agent`` can be driven through a full
tool-call loop offline.

Verified behaviours (langchain-core 1.4.0):
  * Pydantic v2 model → needs ``model_config = {"extra": "allow"}`` for the
    private response cursor.
  * ``create_react_agent`` calls ``ainvoke`` → base ``_agenerate`` runs
    ``_generate`` in an executor, so implementing ``_generate`` is sufficient.
  * Every real provider class overrides ``bind_tools``; the fake mirrors that
    by recording the tool names and returning a tool-aware ``self``.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult

_EXHAUSTED_SENTINEL = "(fake-llm: scripted responses exhausted)"


def tool_call(name: str, args: dict[str, Any], *, id: str = "call_0") -> dict[str, Any]:
    """Build a tool-call dict in the shape ``AIMessage.tool_calls`` expects."""
    return {"name": name, "args": dict(args), "id": id, "type": "tool_call"}


def ai(content: str = "", calls: list[dict[str, Any]] | None = None) -> AIMessage:
    """Build a scripted assistant turn, optionally requesting tool calls."""
    return AIMessage(content=content, tool_calls=list(calls or []))


class FakeChatModel(BaseChatModel):
    """Replays a fixed list of ``AIMessage`` responses; never hits the network.

    ``responses`` is consumed in order across invocations of the SAME instance.
    Construct a fresh instance per agent run (each ``create_react_agent`` loop
    consumes one entry per model turn).
    """

    responses: list[AIMessage] = []
    # Private mutable state — extra=allow lets us stash these on the model.
    model_config = {"extra": "allow"}

    def __init__(self, **data: Any) -> None:
        super().__init__(**data)
        object.__setattr__(self, "_idx", 0)
        object.__setattr__(self, "bound_tools_names", [])

    @property
    def _llm_type(self) -> str:
        return "fake-chat-model"

    def bind_tools(self, tools: Sequence[Any], **kwargs: Any) -> FakeChatModel:
        names: list[str] = []
        for t in tools:
            name = getattr(t, "name", None) or getattr(t, "__name__", None)
            if name is None and isinstance(t, dict):
                name = t.get("name") or t.get("function", {}).get("name")
            names.append(str(name))
        object.__setattr__(self, "bound_tools_names", names)
        return self

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        idx = self._idx
        if idx >= len(self.responses):
            msg: AIMessage = AIMessage(content=_EXHAUSTED_SENTINEL)
        else:
            msg = self.responses[idx]
        object.__setattr__(self, "_idx", idx + 1)
        return ChatResult(generations=[ChatGeneration(message=msg)])
