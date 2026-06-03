"""Build the StateGraph: nodes + edges + persistent checkpointer.

Checkpointer durability
-----------------------
Previously this module used :class:`InMemorySaver`, which means a worker
restart mid-analysis would lose all intermediate graph state. We now use the
``langgraph-checkpoint-mongodb`` saver against the same Mongo instance the
rest of the app already talks to, so a crashed worker can resume from the
last completed node.

The MongoDB checkpointer ships only a sync class (:class:`MongoDBSaver`) in
``langgraph-checkpoint-mongodb`` 0.4.x, but the saver implements both ``put``
and ``aput`` — LangGraph's async runtime uses the async variants, which the
saver dispatches via ``run_in_executor``. This is acceptable: checkpoint
writes are tiny next to the ML/LLM work in each node.

Vault refs:
  - 04-LangGraph-Core/02-State-Nodes-Edges.md
  - 04-LangGraph-Core/03-Routing-Retries-Recovery.md
  - 04-LangGraph-Core/04-Checkpoints-Human-In-The-Loop.md
"""
from __future__ import annotations

import logging
import threading

from langgraph.graph import END, START, StateGraph

from backend.graph.nodes import (
    features_node,
    has_errors_route,
    ingest_node,
    instrument_node,
    roman_analysis_node,
    should_retry,
    similarity_node,
    stems_node,
    theory_node,
    validate_audio_node,
)
from backend.graph.state import AnalysisState

logger = logging.getLogger(__name__)


def build_graph(checkpointer):
    """Build + compile the StateGraph with the given checkpointer.

    Pipeline:
        ingest -> features -> roman -> [theory, instrument, similarity] (parallel) -> END
    """
    g = StateGraph(AnalysisState)

    g.add_node("ingest", ingest_node)
    g.add_node("validate_audio", validate_audio_node)
    g.add_node("features", features_node)
    g.add_node("roman", roman_analysis_node)
    g.add_node("theory", theory_node)
    g.add_node("instrument", instrument_node)
    g.add_node("similarity", similarity_node)
    g.add_node("stems", stems_node)

    g.add_edge(START, "ingest")

    # Plan 3 live-test bug fix: a bad input (rejected YouTube URL, etc.)
    # would set ``state["errors"]`` in ``ingest_node``; the downstream nodes
    # short-circuit on pre-existing errors but ``should_retry`` then looped
    # back to features without ever incrementing the retry counter,
    # producing LangGraph's 10007-iteration recursion error. We now route
    # error states straight to END after each pre-features stage.
    g.add_conditional_edges(
        "ingest",
        has_errors_route,
        {"fail": END, "ok": "validate_audio"},
    )
    g.add_conditional_edges(
        "validate_audio",
        has_errors_route,
        {"fail": END, "ok": "features"},
    )

    g.add_conditional_edges(
        "features",
        should_retry,
        {
            "retry": "features",
            "fail": END,
            "ok": "roman",
        },
    )

    # Fan-out from roman; fan-in to END. Stems run in parallel with the
    # LLM nodes; if demucs is unavailable the node returns {} and the join
    # simply lacks the ``stems`` key.
    g.add_edge("roman", "theory")
    g.add_edge("roman", "instrument")
    g.add_edge("roman", "similarity")
    g.add_edge("roman", "stems")
    g.add_edge("theory", END)
    g.add_edge("instrument", END)
    g.add_edge("similarity", END)
    g.add_edge("stems", END)

    return g.compile(checkpointer=checkpointer)


# Module-level singleton built on first access. Locked because LangGraph
# may be invoked from concurrent contexts (FastAPI request handlers in the
# API process, multiple Taskiq workers in the worker process).
_compiled_graph = None
_checkpointer = None
_graph_lock = threading.Lock()


def _build_mongo_checkpointer():
    """Construct a MongoDBSaver from app settings.

    Uses a sync pymongo client (the only kind the checkpointer accepts in
    0.4.x). This is a separate connection from the async motor client the
    rest of the app uses; that's fine — pymongo manages its own pool.
    """
    from langgraph.checkpoint.mongodb import MongoDBSaver
    from pymongo import MongoClient

    from backend.config import get_settings

    s = get_settings()
    client = MongoClient(s.mongo_uri)
    saver = MongoDBSaver(client, db_name=s.mongo_db_name)
    logger.info(
        "LangGraph checkpointer: MongoDBSaver(db=%s)", s.mongo_db_name
    )
    return saver


def get_graph():
    """Return the compiled graph, building it (and the checkpointer) lazily.

    Safe to call from both API and worker processes. The first caller pays
    the build cost (~ms); the lock serializes concurrent first-callers.
    """
    global _compiled_graph, _checkpointer
    if _compiled_graph is None:
        with _graph_lock:
            if _compiled_graph is None:
                _checkpointer = _build_mongo_checkpointer()
                _compiled_graph = build_graph(_checkpointer)
    return _compiled_graph


def reset_graph_for_tests() -> None:
    """Drop the cached graph + checkpointer. For tests only."""
    global _compiled_graph, _checkpointer
    if _checkpointer is not None:
        try:
            _checkpointer.close()
        except Exception:  # noqa: BLE001 — cleanup path
            pass
    _compiled_graph = None
    _checkpointer = None
