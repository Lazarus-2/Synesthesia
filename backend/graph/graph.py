"""
Build the StateGraph: wires nodes + edges + checkpointer.
Vault refs:
  - 04-LangGraph-Core/02-State-Nodes-Edges.md
  - 04-LangGraph-Core/03-Routing-Retries-Recovery.md
  - 04-LangGraph-Core/04-Checkpoints-Human-In-The-Loop.md
"""
from __future__ import annotations

from functools import lru_cache

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from backend.graph.nodes import (
    features_node,
    ingest_node,
    instrument_node,
    roman_analysis_node,
    similarity_node,
    theory_node,
)
from backend.graph.state import AnalysisState


def build_graph():
    """Build + compile the StateGraph.

    Pipeline:
        ingest -> features -> roman -> [theory, instrument, similarity] (parallel) -> END
    """
    g = StateGraph(AnalysisState)

    g.add_node("ingest", ingest_node)
    g.add_node("features", features_node)
    g.add_node("roman", roman_analysis_node)
    g.add_node("theory", theory_node)
    g.add_node("instrument", instrument_node)
    g.add_node("similarity", similarity_node)

    g.add_edge(START, "ingest")
    g.add_edge("ingest", "features")
    
    # Conditional routing for retries
    from backend.graph.nodes import should_retry
    g.add_conditional_edges(
        "features",
        should_retry,
        {
            "retry": "features",
            "fail": END,
            "ok": "roman"
        }
    )

    # Fan-out parallel nodes from roman
    g.add_edge("roman", "theory")
    g.add_edge("roman", "instrument")
    g.add_edge("roman", "similarity")

    # Fan-in back to END
    g.add_edge("theory", END)
    g.add_edge("instrument", END)
    g.add_edge("similarity", END)

    checkpointer = InMemorySaver()
    return g.compile(checkpointer=checkpointer)


@lru_cache
def get_graph():
    return build_graph()
