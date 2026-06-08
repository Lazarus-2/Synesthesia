"""Background analysis task — extracted from main.py to break the
API<->worker circular import.

``main.py`` used to define ``run_analysis_pipeline`` AND import ``broker``
from ``worker.py``; the worker CLI then imported the whole FastAPI app
(``taskiq worker backend.worker:broker backend.main``) just to register the
task. That made ``main`` <-> ``worker`` a cycle and forced the worker
process to load every route/chain/middleware.

This module owns the task. It imports ``broker`` from ``backend.worker``
(one direction only) and is what both the worker CLI and ``main.py`` import
to find / enqueue the task. It must NOT import ``backend.main``.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path

from taskiq import Context, TaskiqDepends

from backend.models import SongAnalysisModel
from backend.schemas import AnalyzeResponse, SongAnalysis
from backend.services.job_store import get_job_store
from backend.tools.synesthesia_colors import get_vibe_palette
from backend.worker import broker

logger = logging.getLogger(__name__)


def _clean_audio_title(audio_path: str | None, youtube_url: str | None) -> str:
    """Render a human-friendly song title from the staged path or source URL.

    Stripped:
      - The ``{job_id}_`` prefix added by ``_safe_audio_filename`` for upload safety.
      - The file extension.
      - Underscores → spaces, title-cased so ``my_song`` → ``My Song``.
    Falls back to "YouTube Analysis" / "Audio Breakdown" if no audio_path.
    """
    if not audio_path:
        return "YouTube Analysis" if youtube_url else "Audio Breakdown"
    stem = Path(audio_path).stem
    # ``_safe_audio_filename`` prefixes ``{uuid}_`` to avoid collisions —
    # strip the leading uuid + underscore if it looks uuid-shaped.
    if (
        len(stem) > 37
        and stem[8] == "-"
        and stem[13] == "-"
        and stem[18] == "-"
        and stem[23] == "-"
        and stem[36] == "_"
    ):
        stem = stem[37:]
    return stem.replace("_", " ").replace("-", " ").strip().title() or "Audio Breakdown"


async def _write_dlq(
    db,
    *,
    job_id: str,
    payload: dict,
    error: BaseException,
    attempt: int,
    max_attempts: int,
) -> None:
    """Persist a permanently-failed job to the dead-letter collection.

    Called when a task has exhausted its retry budget. Operators can inspect
    ``failed_jobs`` to triage and (eventually) re-enqueue. The collection has
    a TTL index declared in :func:`backend.database.init_mongodb`.
    """
    try:
        await db.failed_jobs.insert_one(
            {
                "job_id": job_id,
                "payload": payload,
                "error": repr(error),
                "error_type": type(error).__name__,
                "attempts": attempt,
                "max_attempts": max_attempts,
                "created_at": datetime.now(UTC),
            }
        )
    except Exception:
        # Last-ditch logging — if even the DLQ write fails, surface it but
        # don't let it mask the original exception that's about to re-raise.
        logger.exception("DLQ insert failed for job %s", job_id)


@broker.task(retry_on_error=True, max_retries=2)
async def run_analysis_pipeline(
    job_id: str,
    youtube_url: str | None,
    audio_path: str | None,
    instrument: str,
    difficulty: str,
    user_id: str | None,
    file_hash: str | None = None,
    *,
    context: Context = TaskiqDepends(),
):
    """Executes the LangGraph analysis pipeline in the background and saves results to MongoDB.

    Retry / DLQ semantics
    ---------------------
    The ``@broker.task`` labels opt this task into Taskiq's
    :class:`SimpleRetryMiddleware`. ``max_retries=2`` is Taskiq's "max
    attempts" — the original + one retry — so a transient failure gets
    exactly one second chance. When the final attempt fails, this function
    writes the original payload + error to ``failed_jobs`` (DLQ) before
    re-raising.

    Idempotency
    -----------
    If MongoDB already has a completed analysis for ``job_id`` (i.e. a
    previous attempt finished and wrote it), the task returns immediately
    without re-running the pipeline.
    """
    # Imported lazily so the worker process doesn't compile the LangGraph at
    # module-import time (matches the prior main.py behaviour).
    from backend.graph.graph import get_graph

    # --- Retry bookkeeping --------------------------------------------------
    labels = context.message.labels
    attempt = int(labels.get("_retries", 0)) + 1
    max_attempts = int(labels.get("max_retries", 2))
    is_final_attempt = attempt >= max_attempts

    initial_payload = {
        "job_id": job_id,
        "youtube_url": youtube_url,
        "audio_path": audio_path,
        "instrument": instrument,
        "difficulty": difficulty,
        "user_id": user_id,
        "file_hash": file_hash,
    }
    logger.info(
        "run_analysis_pipeline: job_id=%s attempt=%d/%d",
        job_id,
        attempt,
        max_attempts,
    )

    job_store = get_job_store()

    def _progress(pct: int, msg: str, status: str = "processing"):
        """Push incremental progress + heartbeat to the unified JobStore."""
        job_store.set_progress(
            job_id,
            {"job_id": job_id, "status": status, "progress": pct, "message": msg},
        )

    # --- Idempotency check --------------------------------------------------
    # Re-running a completed job is wasted ML/LLM cost. If Mongo already has
    # the analysis document, replay the cached response and return.
    from backend.database import get_mongodb

    db = get_mongodb()
    try:
        existing = await db.song_analyses.find_one({"_id": job_id})
    except Exception:
        # Don't let a DB hiccup short-circuit the pipeline — fall through
        # to the normal flow and let the actual work surface any real
        # connection problem.
        existing = None
    if existing:
        logger.info("Job %s already complete in DB; idempotent return", job_id)
        cached = job_store.get_cached_response(job_id)
        if not cached:
            try:
                replay = AnalyzeResponse(
                    job_id=job_id,
                    status="done",
                    analysis=SongAnalysis.model_validate(existing),
                    instrument_guide=None,
                )
                job_store.cache_response(job_id, replay.model_dump_json())
            except Exception:
                logger.exception("Failed to rebuild cached response for %s", job_id)
        return

    graph = get_graph()
    initial_state = {
        "youtube_url": youtube_url,
        "audio_path": audio_path,
        "instrument": instrument,
        "difficulty": difficulty,
        "user_id": user_id,
        "errors": [],
        "retries": 0,
    }

    _progress(0, "Queued for analysis", "queued")

    try:
        _progress(5, "Loading audio file...")
        result = await graph.ainvoke(
            initial_state,
            config={"configurable": {"thread_id": job_id}},
        )
        _progress(80, "Building analysis results...")

        errors = result.get("errors", [])
        if errors:
            _progress(0, "; ".join(errors), "error")
            return

        chords = result.get("chords", [])
        chord_names = [c.chord for c in chords]
        vibe_pal = get_vibe_palette(result.get("key", "C major"), chord_names)

        analysis = SongAnalysis(
            title=_clean_audio_title(audio_path, youtube_url),
            artist="Local Engine" if audio_path else "YouTube Stream",
            duration=float(chords[-1].end) if chords else 180.0,
            key=result.get("key", "C major"),
            tempo=result.get("tempo", 120.0),
            time_signature="4/4",
            chords=chords,
            beats=result.get("beats", []),
            sections=result.get("sections", []),
            roman=result.get("roman"),
            vibe_palette=vibe_pal,
            theory_explanation=result.get("theory_explanation"),
            instrument_guides={},
            stems=result.get("stems", {}),
        )

        _progress(90, "Saving to database...")

        # Fetch existing record to preserve other instrument guides
        existing_for_merge = await db.song_analyses.find_one({"_id": job_id})
        guides = {}
        if existing_for_merge and "instrument_guides" in existing_for_merge:
            guides = existing_for_merge["instrument_guides"]

        if result.get("instrument_guide"):
            guides[instrument] = result.get("instrument_guide").model_dump()

        analysis_record = SongAnalysisModel(
            id=job_id,
            file_hash=file_hash,
            title=analysis.title,
            artist=analysis.artist,
            duration=analysis.duration,
            key=analysis.key,
            tempo=analysis.tempo,
            time_signature=analysis.time_signature,
            chords=analysis.chords,
            beats=analysis.beats,
            sections=analysis.sections,
            roman=analysis.roman,
            vibe_palette=analysis.vibe_palette,
            theory_explanation=analysis.theory_explanation,
            instrument_guides=guides,
            stems=analysis.stems,
        )

        write_result = await db.song_analyses.replace_one(
            {"_id": job_id},
            analysis_record.model_dump(by_alias=True),
            upsert=True,
        )
        if not (write_result.matched_count or write_result.upserted_id):
            logger.error("Mongo replace_one for job %s reported neither match nor upsert", job_id)

        # Cache completed analysis response with full analysis data
        done_response = AnalyzeResponse(
            job_id=job_id,
            status="done",
            analysis=analysis,
            instrument_guide=result.get("instrument_guide"),
            audio_url=f"/api/v1/audio/{job_id}",
        )
        job_store.cache_response(job_id, done_response.model_dump_json())

    except Exception as e:
        # Push a user-visible error frame to the SSE cache so the client
        # knows something went wrong on THIS attempt. The retry middleware
        # will re-enqueue and subsequent attempts will overwrite this.
        _progress(0, f"Analysis pipeline crashed: {e}", "error")
        if is_final_attempt:
            logger.error(
                "run_analysis_pipeline: job_id=%s exhausted retries (attempt %d/%d)",
                job_id,
                attempt,
                max_attempts,
            )
            await _write_dlq(
                db,
                job_id=job_id,
                payload=initial_payload,
                error=e,
                attempt=attempt,
                max_attempts=max_attempts,
            )
        # Re-raise so SimpleRetryMiddleware sees the failure and decides
        # whether to enqueue another attempt.
        raise
