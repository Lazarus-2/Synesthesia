"""Group 6: the worker CLI invocation must discover tasks via backend.tasks,
never backend.main, so the worker process doesn't load the FastAPI app.
"""

from __future__ import annotations

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]


def test_dockerfile_worker_cmd_uses_tasks_module():
    """Dockerfile worker CMD loads backend.tasks for task discovery."""
    text = (_REPO_ROOT / "Dockerfile").read_text()
    # The worker CMD line: taskiq worker backend.worker:broker <module>
    assert 'CMD ["taskiq", "worker", "backend.worker:broker", "backend.tasks"]' in text
    assert "backend.worker:broker\", \"backend.main\"" not in text


def test_e2e_launcher_uses_tasks_module():
    """The e2e shell launcher's taskiq worker line loads backend.tasks."""
    text = (_REPO_ROOT / "backend" / "tests" / "e2e_browser" / "run_e2e.sh").read_text()
    assert "taskiq worker backend.worker:broker backend.tasks" in text
    assert "taskiq worker backend.worker:broker backend.main" not in text
