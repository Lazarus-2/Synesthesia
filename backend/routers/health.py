"""Liveness + readiness probes."""

from __future__ import annotations

import time

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from backend.database import get_mongodb

router = APIRouter()


@router.get("/health")
async def health() -> dict:
    """Liveness probe.

    Cheap and always-200 so orchestrators can use this for "is the process
    alive" without depending on downstream services. For dependency state,
    see :func:`readiness`.
    """
    return {"status": "ok"}


@router.get("/health/ready")
async def readiness(db=Depends(get_mongodb)) -> JSONResponse:
    """Readiness probe — pings Mongo and Redis, surfaces per-dependency state.

    Returns 200 only when every required dependency is reachable, 503
    otherwise with the per-dep breakdown. Use this for Kubernetes
    ``readinessProbe`` so traffic doesn't hit a node whose Mongo connection
    is wedged.
    """
    checks: dict[str, dict] = {}
    overall_ok = True

    # Mongo ping
    t0 = time.perf_counter()
    try:
        await db.command("ping")
        checks["mongodb"] = {
            "ok": True,
            "latency_ms": round((time.perf_counter() - t0) * 1000, 1),
        }
    except Exception as e:
        overall_ok = False
        checks["mongodb"] = {"ok": False, "error": type(e).__name__, "msg": str(e)[:120]}

    # Redis ping
    t0 = time.perf_counter()
    try:
        from backend.services.cache import cache

        if await cache.ping():
            checks["redis"] = {
                "ok": True,
                "latency_ms": round((time.perf_counter() - t0) * 1000, 1),
            }
        else:
            checks["redis"] = {
                "ok": False,
                "error": "unreachable",
                "msg": "Redis unreachable or breaker open; fell back to in-memory",
            }
            overall_ok = False
    except Exception as e:
        overall_ok = False
        checks["redis"] = {"ok": False, "error": type(e).__name__, "msg": str(e)[:120]}

    body = {"status": "ok" if overall_ok else "degraded", "checks": checks}
    return JSONResponse(status_code=200 if overall_ok else 503, content=body)
