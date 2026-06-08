"""Group 6: backend.tasks must hold the Taskiq task and be importable
without dragging the whole FastAPI app in (no API<->worker cycle).

These tests deliberately manipulate ``sys.modules`` so the "did importing
backend.tasks import backend.main?" assertion is meaningful in a clean
interpreter, not polluted by an earlier conftest import of main.
"""

from __future__ import annotations

import importlib
import sys


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
    """The moved helpers are absent from main.py and the API uses the tasks module object."""
    import backend.main as main_mod
    import backend.tasks as tasks_mod

    # (a) The API's run_analysis_pipeline must be exactly the object defined in
    # backend.tasks — not a second @broker.task definition in main.py.
    assert main_mod.run_analysis_pipeline.__wrapped__ is tasks_mod.run_analysis_pipeline.__wrapped__

    # (b) main.py source must not (re-)define these private helpers.
    import pathlib
    main_src = pathlib.Path(main_mod.__file__).read_text()
    assert "def _write_dlq" not in main_src, "main.py must not define _write_dlq"
    assert "def _clean_audio_title" not in main_src, "main.py must not define _clean_audio_title"
    assert "def run_analysis_pipeline" not in main_src, "main.py must not define run_analysis_pipeline"


# ---------------------------------------------------------------------------
# Bug B regression: user_id must be persisted on the SongAnalysisModel doc
# ---------------------------------------------------------------------------

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.asyncio
async def test_run_analysis_pipeline_persists_user_id():
    """Bug B regression: user_id passed to the task must be saved on SongAnalysisModel.

    Before the fix, user_id was threaded into initial_state and the task
    signature but was never forwarded to the SongAnalysisModel(...) constructor,
    so every analysis was stored with user_id=None, defeating the ownership model
    (AnalysisRepo.get_owned, /library?user_id= filter).

    This test mocks the graph, DB, and JobStore so only the tasks.py code path
    runs, then asserts the captured SongAnalysisModel carries the user_id.
    """
    import json

    from backend.models import SongAnalysisModel

    captured_records: list[SongAnalysisModel] = []

    # --- Mock DB ----------------------------------------------------------------
    mock_db = MagicMock()
    mock_db.song_analyses.find_one = AsyncMock(return_value=None)  # no existing record

    async def _replace_one(filter_, doc, *, upsert=False):
        # Reconstruct the model from what tasks.py passes so we can assert on it.
        record = SongAnalysisModel.model_validate(doc)
        captured_records.append(record)
        result = MagicMock()
        result.matched_count = 0
        result.upserted_id = "fake-upsert-id"
        return result

    mock_db.song_analyses.replace_one = AsyncMock(side_effect=_replace_one)
    mock_db.failed_jobs.insert_one = AsyncMock()

    # --- Mock graph result -------------------------------------------------------
    # A minimal graph result that satisfies all the tasks.py assertions.
    from backend.schemas import ChordEvent, BeatEvent

    fake_chord = ChordEvent(chord="C", start=0.0, end=2.0, confidence=0.9)
    graph_result = {
        "key": "C major",
        "tempo": 120.0,
        "chords": [fake_chord],
        "beats": [],
        "sections": [],
        "roman": None,
        "stems": {},
        "errors": [],
        "theory_explanation": "Test theory",
        "instrument_guide": None,
        "user_id": "user-abc",
    }

    mock_graph = MagicMock()
    mock_graph.ainvoke = AsyncMock(return_value=graph_result)

    # --- Mock JobStore -----------------------------------------------------------
    class _MockStore:
        async def set_progress(self, job_id, payload):
            pass

        async def get_cached_response(self, job_id):
            return None

        async def cache_response(self, job_id, response_json):
            pass

        async def get_progress(self, job_id):
            return None

    # --- Patch everything --------------------------------------------------------
    # get_job_store is module-level in backend.tasks; get_mongodb and get_graph
    # are imported lazily inside the task body so we patch their source modules.
    with (
        patch("backend.tasks.get_job_store", return_value=_MockStore()),
        patch("backend.graph.graph.get_graph", return_value=mock_graph),
        patch("backend.graph.status.derive_status", return_value="ok"),
        patch("backend.database.get_mongodb", return_value=mock_db),
    ):
        # Reconstruct the task function directly (bypassing Taskiq broker).
        from backend.tasks import run_analysis_pipeline

        context = MagicMock()
        context.message.labels = {"_retries": "0", "max_retries": "2"}

        await run_analysis_pipeline.__wrapped__(
            "job-user-test",
            None,          # youtube_url
            "/tmp/test.mp3",  # audio_path
            "guitar",      # instrument
            "beginner",    # difficulty
            "user-abc",    # user_id  ← the field under test
            None,          # file_hash
            context=context,
        )

    # Assert that exactly one record was written and it carries the user_id.
    assert len(captured_records) == 1, (
        f"Expected replace_one to be called once; called {len(captured_records)} times"
    )
    record = captured_records[0]
    assert record.user_id == "user-abc", (
        f"SongAnalysisModel.user_id should be 'user-abc' but got {record.user_id!r}. "
        "The user_id is not being persisted — Bug B is present."
    )
