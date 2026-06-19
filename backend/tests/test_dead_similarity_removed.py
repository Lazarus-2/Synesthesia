"""Assert the dead local similarity code has been removed and the graph
still builds without it."""
from __future__ import annotations

import sys


def test_similarity_chain_module_deleted():
    """backend.chains.similarity_chain must not exist after removal."""
    # Remove from sys.modules if previously imported in this session.
    sys.modules.pop("backend.chains.similarity_chain", None)
    try:
        import backend.chains.similarity_chain  # noqa: F401
        raise AssertionError(
            "backend.chains.similarity_chain still importable — it was NOT deleted"
        )
    except ModuleNotFoundError:
        pass  # expected


def test_similarity_node_not_in_nodes_module():
    """similarity_node must no longer be defined in backend.graph.nodes."""
    import backend.graph.nodes as nodes_mod
    assert not hasattr(nodes_mod, "similarity_node"), (
        "similarity_node still present in backend.graph.nodes"
    )


def test_graph_builds_without_similarity_node(monkeypatch):
    """build_graph must compile a working StateGraph after the similarity
    node is removed — validates wiring is consistent."""
    # Use InMemorySaver so the test never touches MongoDB.
    from langgraph.checkpoint.memory import MemorySaver

    from backend.graph.graph import build_graph

    checkpointer = MemorySaver()
    compiled = build_graph(checkpointer)
    # Compiled graph exposes .nodes — check similarity is absent.
    assert "similarity" not in compiled.nodes, (
        "'similarity' node still registered in compiled graph"
    )
    # Verify the canonical fan-out nodes are still present.
    for expected in ("ingest", "roman", "theory", "instrument", "stems"):
        assert expected in compiled.nodes, f"Expected node '{expected}' missing from graph"
