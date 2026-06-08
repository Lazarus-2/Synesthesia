"""Group 6: backend.tasks must hold the Taskiq task and be importable
without dragging the whole FastAPI app in (no API<->worker cycle).

These tests deliberately manipulate ``sys.modules`` so the "did importing
backend.tasks import backend.main?" assertion is meaningful in a clean
interpreter, not polluted by an earlier conftest import of main.
"""

from __future__ import annotations

import importlib
import sys

import pytest


def _purge(*prefixes: str) -> None:
    """Drop the named top-level modules (and submodules) from sys.modules."""
    for name in list(sys.modules):
        if name in prefixes or any(name.startswith(p + ".") for p in prefixes):
            del sys.modules[name]


def test_run_analysis_pipeline_lives_in_tasks_module():
    """The canonical task object is defined in backend.tasks."""
    tasks = importlib.import_module("backend.tasks")
    assert hasattr(tasks, "run_analysis_pipeline")
    # AsyncTaskiqDecoratedTask exposes .kiq for enqueue.
    assert hasattr(tasks.run_analysis_pipeline, "kiq")
    assert callable(tasks.run_analysis_pipeline.kiq)


def test_write_dlq_lives_in_tasks_module():
    """The DLQ helper moved alongside the task (not left in main)."""
    tasks = importlib.import_module("backend.tasks")
    assert hasattr(tasks, "_write_dlq")
    assert callable(tasks._write_dlq)


def test_task_registered_on_worker_broker():
    """The task is registered on the same broker the worker CLI loads."""
    from backend.worker import broker

    tasks = importlib.import_module("backend.tasks")
    task_name = tasks.run_analysis_pipeline.task_name
    assert task_name in broker.get_all_tasks()


def test_importing_tasks_does_not_import_main():
    """Importing backend.tasks must NOT import backend.main.

    This is the load-bearing assertion: the worker entrypoint imports
    backend.tasks, and it must not pull the FastAPI app (routes, CORS,
    limiter, chains) into the worker process. Proves the cycle is broken.
    """
    _purge("backend.tasks", "backend.main", "backend.worker")
    assert "backend.main" not in sys.modules
    importlib.import_module("backend.tasks")
    assert "backend.tasks" in sys.modules
    assert "backend.main" not in sys.modules, (
        "importing backend.tasks pulled in backend.main — circular import "
        "not broken; the worker would import the whole FastAPI app"
    )


def test_clean_audio_title_helper_moved_to_tasks():
    """The private title helper the task needs moved with it."""
    tasks = importlib.import_module("backend.tasks")
    assert tasks._clean_audio_title(None, "https://youtu.be/x") == "YouTube Analysis"
    assert tasks._clean_audio_title(None, None) == "Audio Breakdown"
    assert tasks._clean_audio_title("/tmp/my_song.wav", None) == "My Song"


def test_main_imports_task_from_tasks_not_its_own_def():
    """main.py uses the canonical task object from backend.tasks.

    main.py still has a /analyze route that calls run_analysis_pipeline.kiq();
    after the move it must reference the *same* task object that the worker
    registered, i.e. the one defined in backend.tasks — not a second @broker.task
    definition that would double-register under the same name.
    """
    import backend.main as main_mod
    import backend.tasks as tasks_mod

    assert main_mod.run_analysis_pipeline is tasks_mod.run_analysis_pipeline


def test_main_no_longer_defines_write_dlq_or_clean_title():
    """The moved helpers are gone from main.py's own globals (not redefined)."""
    import inspect

    import backend.main as main_mod
    import backend.tasks as tasks_mod

    # _write_dlq, _clean_audio_title and run_analysis_pipeline must resolve to
    # objects defined in backend.tasks, never re-defined in backend.main.
    for name in ("_write_dlq", "_clean_audio_title", "run_analysis_pipeline"):
        obj = getattr(main_mod, name, None)
        if obj is None:
            continue
        src_mod = getattr(obj, "__module__", None)
        # .kiq-wrapped task has no __module__; unwrap via the original func.
        if name == "run_analysis_pipeline":
            assert obj is tasks_mod.run_analysis_pipeline
        else:
            assert src_mod == "backend.tasks", (
                f"{name} in main.py resolves to {src_mod}, expected backend.tasks "
                "(it should be moved, not duplicated)"
            )
