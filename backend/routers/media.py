"""Media streaming + MIDI export (audio / stems / midi)."""

from __future__ import annotations

import asyncio
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse

from backend.api_common import _enforce_owned_read, _reject_job_id_traversal
from backend.auth import UserPrincipal, current_user
from backend.config import get_settings
from backend.database import get_mongodb
from backend.ratelimit import limiter

router = APIRouter()


@router.get("/midi/{job_id}/{stem}")
@limiter.limit(lambda: get_settings().media_rate_limit)
async def export_midi(
    request: Request,
    job_id: str,
    stem: str,
    principal: Annotated[UserPrincipal | None, Depends(current_user)] = None,
    db=Depends(get_mongodb),
):
    """Transcribe a stem (or the full mix) to MIDI (Plan 3 B10).

    ``stem`` is one of ``vocals|drums|bass|other|full``. ``full`` runs
    basic-pitch over the staged audio file (no stem separation required).
    Other values look in ``stems_dir/{job_id}/{stem}.wav`` from the stem
    separation step — if that file doesn't exist yet, returns 404.
    """
    _reject_job_id_traversal(job_id)
    await _enforce_owned_read(job_id, principal, db)
    settings = get_settings()
    if stem == "full":
        candidates = sorted(settings.audio_upload_dir.glob(f"{job_id}*"))
        if not candidates:
            raise HTTPException(status_code=404, detail="No staged audio for job")
        source = candidates[0]
        # Symlink guard (parity with /audio + /stems): glob can return a
        # symlink pointing outside the upload dir — confirm the real path
        # stays inside before transcribing it.
        try:
            source.resolve().relative_to(settings.audio_upload_dir.resolve())
        except ValueError:
            raise HTTPException(status_code=404, detail="Audio file path escapes upload dir")
    else:
        if stem not in ("vocals", "drums", "bass", "other"):
            raise HTTPException(status_code=400, detail=f"Unknown stem {stem!r}")
        source = settings.stems_dir / job_id / f"{stem}.wav"
        if not source.exists():
            raise HTTPException(
                status_code=404,
                detail=f"Stem {stem!r} not separated yet; run analysis with stems enabled",
            )
        try:
            source.resolve().relative_to(settings.stems_dir.resolve())
        except ValueError:
            raise HTTPException(status_code=404, detail="Stem path escapes stems dir")

    midi_dir = settings.stems_dir / job_id / "midi"
    midi_dir.mkdir(parents=True, exist_ok=True)
    out_midi = midi_dir / f"{stem}.mid"

    if not out_midi.exists():
        from backend.ml.midi_transcription import transcribe_to_midi

        result = await asyncio.to_thread(transcribe_to_midi, source, out_midi)
        if result is None or not out_midi.exists():
            raise HTTPException(
                status_code=503,
                detail="MIDI transcription failed. basic-pitch runs via a Python "
                "3.11 interpreter (backend/.venv311, or set $MIDI_PYTHON) because "
                "it pins tensorflow<2.15.1 (no 3.12 wheel). Check the worker logs.",
            )
    return FileResponse(
        out_midi,
        media_type="audio/midi",
        filename=f"{job_id}_{stem}.mid",
    )


@router.get("/stems/{job_id}/{stem}")
@limiter.limit(lambda: get_settings().media_rate_limit)
async def serve_stem(
    request: Request,
    job_id: str,
    stem: str,
    principal: Annotated[UserPrincipal | None, Depends(current_user)] = None,
    db=Depends(get_mongodb),
):
    """Stream a separated stem WAV (Plan 3 A2 + B7).

    ``stem`` is one of ``vocals|drums|bass|other``. Looks under
    ``settings.stems_dir/{job_id}/{stem}.wav`` (the layout written by
    ``stems_node`` via demucs).
    """
    _reject_job_id_traversal(job_id)
    await _enforce_owned_read(job_id, principal, db)
    if stem not in ("vocals", "drums", "bass", "other"):
        raise HTTPException(status_code=400, detail=f"Unknown stem {stem!r}")
    settings = get_settings()
    src = settings.stems_dir / job_id / f"{stem}.wav"
    if not src.exists():
        raise HTTPException(status_code=404, detail=f"Stem {stem!r} not available for job {job_id}")
    try:
        src.resolve().relative_to(settings.stems_dir.resolve())
    except ValueError:
        raise HTTPException(status_code=404, detail="Stem path escapes stems dir")
    return FileResponse(
        src,
        media_type="audio/wav",
        filename=f"{job_id}_{stem}.wav",
        headers={"Accept-Ranges": "bytes"},
    )


@router.get("/audio/{job_id}")
@limiter.limit(lambda: get_settings().media_rate_limit)
async def serve_audio(
    request: Request,
    job_id: str,
    principal: Annotated[UserPrincipal | None, Depends(current_user)] = None,
    db=Depends(get_mongodb),
):
    """Stream the analysed audio file by job id.

    Looks for any file in ``audio_upload_dir`` whose name starts with the
    job id (the upload pipeline stores them as ``{job_id}_{original_name}``,
    and yt-dlp downloads are renamed to ``{job_id}_{video_id}.mp3`` by
    ``ingest_node``). Falls back to a 404 envelope if nothing matches —
    better than serving an arbitrary file.

    Security (Phase 6 G2): owned audio is gated to its owner; anonymous audio
    stays public so the ``/share`` player (which embeds ``/audio/{job_id}``
    token-less) keeps working.
    """
    _reject_job_id_traversal(job_id)
    await _enforce_owned_read(job_id, principal, db)
    settings = get_settings()
    candidates = sorted(settings.audio_upload_dir.glob(f"{job_id}*"))
    if not candidates:
        raise HTTPException(status_code=404, detail=f"No audio file for job {job_id}")
    audio_file = candidates[0]
    # Guard against ``..`` shenanigans in case a malicious job_id slipped past
    # earlier validation: resolve and confirm we're still inside upload_dir.
    try:
        audio_file.resolve().relative_to(settings.audio_upload_dir.resolve())
    except ValueError:
        raise HTTPException(status_code=404, detail="Audio file path escapes upload dir")
    media_type = {
        "mp3": "audio/mpeg",
        "wav": "audio/wav",
        "flac": "audio/flac",
        "ogg": "audio/ogg",
        "m4a": "audio/mp4",
        "aac": "audio/aac",
        "opus": "audio/opus",
    }.get(audio_file.suffix.lstrip(".").lower(), "application/octet-stream")
    return FileResponse(
        audio_file,
        media_type=media_type,
        filename=audio_file.name,
        headers={"Accept-Ranges": "bytes"},
    )
