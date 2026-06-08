"""FT-01 + degradation-status: AnalysisState reducer semantics.

These tests pin the *shape* of AnalysisState — that ``errors`` is an
append-only (operator.add) channel, that ``feature_error`` is a plain
last-write-wins channel, and that ``status`` is a typed literal. They run
without ML/LLM/Mongo by inspecting the TypedDict annotations and by driving
a tiny StateGraph that exercises the reducer at fan-in.
"""

from __future__ import annotations

import operator
import typing

from langgraph.graph import END, START, StateGraph

from backend.graph.state import AnalysisState


def _reducer_of(field: str):
    """Return the reducer callable bound to an Annotated AnalysisState field.

    LangGraph stores the reducer as the second arg of ``Annotated[...]``;
    ``typing.get_type_hints(include_extras=True)`` surfaces it.
    """
    hints = typing.get_type_hints(AnalysisState, include_extras=True)
    meta = getattr(hints[field], "__metadata__", ())
    return meta[0] if meta else None


class TestErrorsReducer:
    def test_errors_uses_operator_add_reducer(self):
        assert _reducer_of("errors") is operator.add

    def test_feature_error_has_no_reducer(self):
        # Plain last-write-wins: no Annotated metadata.
        assert _reducer_of("feature_error") is None

    def test_status_field_is_declared(self):
        hints = typing.get_type_hints(AnalysisState, include_extras=True)
        assert "status" in hints

    def test_errors_concurrent_appends_merge(self):
        """Two parallel nodes each appending one error must NOT raise
        InvalidUpdateError; the operator.add reducer concatenates them."""
        g = StateGraph(AnalysisState)

        def fan_a(_state):
            return {"errors": ["a-down"]}

        def fan_b(_state):
            return {"errors": ["b-down"]}

        g.add_node("a", fan_a)
        g.add_node("b", fan_b)
        g.add_edge(START, "a")
        g.add_edge(START, "b")
        g.add_edge("a", END)
        g.add_edge("b", END)
        graph = g.compile()

        result = graph.invoke({"errors": [], "retries": 0})
        assert sorted(result["errors"]) == ["a-down", "b-down"]
