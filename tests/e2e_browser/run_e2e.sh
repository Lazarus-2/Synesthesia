#!/usr/bin/env bash
# Drive the live browser E2E suite end-to-end.
#
# Assumes:
#   - .venv/ has playwright + pytest-playwright installed
#   - chromium has been pulled (playwright install chromium)
#   - Mongo + Redis are reachable on localhost
#
# Brings up uvicorn + Taskiq worker if they're not already serving on :8000.
# Starts the Next.js dev server if :3000 isn't responding. Re-seeds the
# Mongo samples, then runs the suite and prints the artifact path.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

started_uvicorn=0
started_worker=0
started_frontend=0

ensure_uvicorn() {
    if curl -fsS -m 3 http://localhost:8000/health >/dev/null 2>&1; then
        echo "[ok] uvicorn already serving"
        return
    fi
    echo "[start] uvicorn"
    mkdir -p logs
    nohup .venv/bin/uvicorn backend.main:app --host 127.0.0.1 --port 8000 --log-level warning >logs/uvicorn.log 2>&1 &
    disown
    started_uvicorn=1
    for _ in 1 2 3 4 5 6 7 8 9 10; do
        sleep 1
        if curl -fsS -m 2 http://localhost:8000/health >/dev/null 2>&1; then
            echo "[ok] uvicorn ready"; return
        fi
    done
    echo "[err] uvicorn never became ready" >&2; exit 1
}

ensure_worker() {
    if pgrep -f "taskiq worker backend.worker" >/dev/null; then
        echo "[ok] taskiq worker already running"; return
    fi
    echo "[start] taskiq worker"
    nohup .venv/bin/taskiq worker backend.worker:broker backend.main --workers 1 >logs/worker.log 2>&1 &
    disown
    started_worker=1
    sleep 3
}

ensure_frontend() {
    if curl -fsS -m 3 -o /dev/null -w "%{http_code}" http://localhost:3000/ | grep -q "^200$"; then
        echo "[ok] frontend already serving"; return
    fi
    echo "[start] next dev"
    (cd frontend/web && nohup npm run dev >../../logs/frontend.log 2>&1 &)
    disown
    started_frontend=1
    for _ in 1 2 3 4 5 6 7 8 9 10; do
        sleep 2
        code=$(curl -fsS -m 2 -o /dev/null -w "%{http_code}" http://localhost:3000/ || echo 000)
        if [ "$code" = "200" ]; then echo "[ok] frontend ready"; return; fi
    done
    echo "[err] frontend never became ready" >&2; exit 1
}

seed_samples() {
    echo "[seed] sample-* analyses"
    .venv/bin/python scripts/seed_samples.py | tail -3
}

ensure_uvicorn
ensure_worker
ensure_frontend
seed_samples

echo "==> running tests/e2e_browser/"
.venv/bin/pytest tests/e2e_browser/ -v --tb=short --capture=no
status=$?

echo
echo "report: tests/e2e_browser/artifacts/run_report.md"
echo "screens: tests/e2e_browser/artifacts/screenshots/"
echo "videos:  tests/e2e_browser/artifacts/video/"
exit "$status"
