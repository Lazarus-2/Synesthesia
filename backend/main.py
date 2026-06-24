"""
FastAPI entry point for the Synesthesia Engine.
Implements high-concurrency MongoDB persistent storage via Motor, cached session handling,
multipart audio uploads, and AI Assistant routes.

Run with:
    uvicorn backend.main:app --reload
"""

from __future__ import annotations

import asyncio
import hashlib
import inspect
import json
import logging
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi import (
    APIRouter,
    Depends,
    FastAPI,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
)
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from sse_starlette.sse import EventSourceResponse, ServerSentEvent
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)

# Allowed audio file extensions (lower-cased, without leading dot).
ALLOWED_AUDIO_EXTENSIONS = frozenset({"mp3", "wav", "m4a", "flac", "ogg", "aac", "opus"})

# Magic-byte signatures for common audio formats. Each entry is (offset, signature).
# Used to validate that the uploaded bytes actually look like audio, regardless of
# the client-supplied Content-Type (which is trivially spoofable).
_AUDIO_MAGIC_PATTERNS: tuple[tuple[int, bytes], ...] = (
    (0, b"ID3"),  # MP3 with ID3 tag
    (0, b"\xff\xfb"),  # MP3 MPEG-1 Layer 3
    (0, b"\xff\xf3"),  # MP3 MPEG-2 Layer 3
    (0, b"\xff\xf2"),  # MP3 MPEG-2.5 Layer 3
    (0, b"RIFF"),  # WAV (also AVI; downstream librosa rejects non-audio RIFFs)
    (0, b"fLaC"),  # FLAC
    (0, b"OggS"),  # OGG (Vorbis / Opus)
    (4, b"ftyp"),  # MP4 / M4A (offset 4)
)


def _safe_audio_filename(job_id: str, original: str | None) -> str:
    """Derive a path-safe filename for an upload.

    Strips any directory components from the client-supplied filename,
    rejects unrecognised extensions, and prefixes with the job ID for uniqueness.
    """
    base = Path(original or "upload").name  # strips ../, paths, NUL
    ext = base.rsplit(".", 1)[-1].lower() if "." in base else ""
    if ext not in ALLOWED_AUDIO_EXTENSIONS:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported audio extension '.{ext}'. "
            f"Allowed: {', '.join(sorted(ALLOWED_AUDIO_EXTENSIONS))}.",
        )
    return f"{job_id}_{base}"


def _is_audio_magic(head: bytes) -> bool:
    """Return True if the byte prefix matches a known audio container signature."""
    for offset, sig in _AUDIO_MAGIC_PATTERNS:
        if head[offset : offset + len(sig)] == sig:
            return True
    return False


import taskiq_fastapi

from backend.api_common import _enforce_owned_read, _reject_job_id_traversal  # noqa: F401
from backend.auth import UserPrincipal, current_user, require_user
from backend.chains.aura_agent import run_aura, stream_aura
from backend.chains.aura_tools import current_user_id
from backend.config import ANALYZER_VERSION, get_settings
from backend.database import get_mongodb
from backend.models import SongAnalysisModel
from backend.ratelimit import limiter
from backend.repositories import AnalysisRepo, ChatSessionRepo, UserRepo
from backend.routers.auth import login, signup  # noqa: F401  (re-export: test coupling)
from backend.routers.auth import router as auth_router
from backend.routers.collections import router as collections_router
from backend.routers.health import router as health_router
from backend.routers.theory import router as theory_router
from backend.routers.user import (  # noqa: F401  (re-export: test coupling)
    create_or_update_user,
    get_user_preferences,
    get_user_profile,
    update_user_preferences,
)
from backend.routers.user import router as user_router
from backend.schemas import (
    AnalyzeResponse,
    ChatRequest,
    ChatResponse,
    SongAnalysis,
)
from backend.services.cache import cache
from backend.services.job_store import (
    DEFAULT_HEARTBEAT_TIMEOUT_S,
    get_job_store,
)
from backend.services.token_budget import check_and_consume
from backend.tasks import run_analysis_pipeline  # noqa: F401
from backend.worker import broker

# The worker entrypoint imports backend.tasks (not backend.main), so the
# FastAPI app is never loaded in the worker. This init runs only when the API
# process imports main.py; it bridges the broker to the FastAPI lifespan and
# enables FastAPI-scoped TaskiqDepends resolution, so it points at the FastAPI app.
taskiq_fastapi.init(broker, "backend.main:app")


@asynccontextmanager
async def lifespan(application: FastAPI):
    """Startup/shutdown lifecycle — replaces deprecated @app.on_event."""
    # Structured JSON logs as the very first thing so subsequent startup
    # messages land in the same format.
    from backend.observability.logging_config import configure_logging
    from backend.observability.tracing import configure_tracing

    configure_logging()
    configure_tracing()
    if not broker.is_worker_process:
        await broker.startup()
    from backend.database import close_mongodb, init_mongodb

    await init_mongodb()
    try:
        yield
    finally:
        await close_mongodb()
        if not broker.is_worker_process:
            await broker.shutdown()
        # Fix 1: close the redis.asyncio connection pool on shutdown so we
        # don't leak sockets on SIGTERM / hot-reload.
        from backend.services.cache import cache as _cache

        if _cache.redis_client is not None:
            await _cache.redis_client.aclose()


app = FastAPI(title="Synesthesia API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "Accept"],
)


# ----------------------------------------------------------------------------
# Standard error envelope (Plan 2 D2)
# ----------------------------------------------------------------------------


class APIError(BaseModel):
    """Uniform error response shape for every non-2xx path.

    Clients can rely on ``status``, ``code``, and ``message`` being present;
    ``details`` carries machine-readable specifics (e.g. validation failures
    list the offending fields). Machine ``code`` is UPPER_SNAKE_CASE so it's
    easy to switch on in client code without parsing free-text messages.
    """

    status: Literal["error"] = "error"
    code: str
    message: str
    details: dict[str, Any] | None = None


_STATUS_CODE_NAMES: dict[int, str] = {
    400: "BAD_REQUEST",
    401: "UNAUTHORIZED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    409: "CONFLICT",
    413: "PAYLOAD_TOO_LARGE",
    415: "UNSUPPORTED_MEDIA_TYPE",
    422: "VALIDATION_ERROR",
    429: "RATE_LIMITED",
    500: "INTERNAL_ERROR",
    502: "BAD_GATEWAY",
    503: "SERVICE_UNAVAILABLE",
}


def _code_for_status(status_code: int) -> str:
    return _STATUS_CODE_NAMES.get(status_code, f"HTTP_{status_code}")


def _api_error_response(
    status_code: int,
    message: str,
    *,
    code: str | None = None,
    details: dict[str, Any] | None = None,
) -> JSONResponse:
    body = APIError(
        code=code or _code_for_status(status_code),
        message=message,
        details=details,
    )
    return JSONResponse(status_code=status_code, content=body.model_dump())


@app.exception_handler(StarletteHTTPException)
async def _http_exception_handler(_request: Request, exc: StarletteHTTPException):
    detail = exc.detail
    # If a caller raised HTTPException with a dict detail, treat it as
    # structured details rather than a string message.
    if isinstance(detail, dict):
        message = str(detail.get("message") or detail.get("detail") or "Error")
        return _api_error_response(exc.status_code, message, details=detail)
    return _api_error_response(exc.status_code, str(detail))


@app.exception_handler(RequestValidationError)
async def _validation_exception_handler(_request: Request, exc: RequestValidationError):
    return _api_error_response(
        422,
        "Request validation failed",
        details={"errors": exc.errors()},
    )


@app.exception_handler(Exception)
async def _generic_exception_handler(_request: Request, _exc: Exception):
    # logger.exception captures the active exception via sys.exc_info, so we
    # don't need to format _exc explicitly. The catch-all envelope hides the
    # raw exception text from clients (security: no stack-trace leakage).
    logger.exception("Unhandled exception in request handler")
    return _api_error_response(500, "An unexpected error occurred. The team has been notified.")


# ----------------------------------------------------------------------------
# Rate limiting (Plan 2 D5)
# ----------------------------------------------------------------------------
# slowapi uses ``key_func`` to identify the caller. Per-IP today via
# ``get_remote_address``; swap to per-user once D4 (auth) lands. The Redis
# storage URI shares counts across worker processes so the limit is global,
# not per-container.

app.state.limiter = limiter


def _chat_rate_limit_key(request: Request) -> str:
    """Rate-limit key for chat: authenticated user_id, else client IP.

    slowapi's ``key_func`` runs BEFORE the endpoint body executes, so we
    cannot rely on ``request.state.principal`` being populated yet.  Instead
    we decode the JWT directly from the ``Authorization`` header here — same
    call :func:`backend.auth.decode_token` does, just early.  Any decode
    failure (missing token, bad signature, expired) falls back silently to IP.
    """
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        try:
            from backend.auth import decode_token

            principal = decode_token(auth.split(" ", 1)[1])
            if principal and getattr(principal, "user_id", None):
                return f"user:{principal.user_id}"
        except Exception:
            pass
    return get_remote_address(request)


async def _resolve_session(
    repo: ChatSessionRepo, db, session_id: str | None, user_id: str
) -> tuple[str, list[dict], bool]:
    """Return ``(session_id, history, session_is_new)``.

    M5: single ``find_one({"_id": session_id})`` — avoids the two-roundtrip
    ``get_owned_session`` + ``_session_exists`` pattern while preserving the
    same 403-on-foreign vs adopt-unknown-as-new semantics.

    If ``session_id`` is None a fresh UUID is minted (always "new").
    """
    from backend.config import get_settings as _gs

    if not session_id:
        return str(uuid.uuid4()), [], True

    # Project only user_id — history is fetched separately via recent_turns
    # ($slice); without this we'd transfer the entire ever-growing messages array
    # on every turn just to read the owner.
    doc = await db.chat_sessions.find_one({"_id": session_id}, {"user_id": 1})
    if doc is None:
        # Never-seen id — adopt it as a fresh server-owned session.
        return session_id, [], True
    if doc.get("user_id") != user_id:
        # Exists but belongs to a different user.
        raise HTTPException(status_code=403, detail="Session not found")
    # Owned by caller — retrieve the windowed history.
    settings = _gs()
    history = await repo.recent_turns(session_id, settings.chat_history_turns)
    return session_id, history, False


def _estimate_tokens(message: str, history: list[dict]) -> int:
    """Cheap pre-call token estimate (~4 chars/token) for the budget gate."""
    chars = len(message) + sum(len(t.get("content", "")) for t in history)
    return max(1, chars // 4) + 512  # + headroom for the system prompt + reply


@app.exception_handler(RateLimitExceeded)
async def _rate_limit_handler(_request: Request, exc: RateLimitExceeded):
    return _api_error_response(
        429,
        f"Rate limit exceeded: {exc.detail}",
        details={"limit": str(exc.detail)},
    )


# ----------------------------------------------------------------------------
# Versioned API router (Plan 2 D1)
# ----------------------------------------------------------------------------
# All app endpoints below register on ``router``; at the bottom of this module
# we ``include_router`` it twice: once at ``/api/v1`` (the canonical mount)
# and once at root (legacy alias kept for the existing frontend until it
# migrates to the versioned base URL).
router = APIRouter()


@router.post("/analyze", response_model=AnalyzeResponse)
@limiter.limit(lambda: get_settings().analyze_rate_limit)
async def analyze(
    request: Request,
    youtube_url: str | None = Form(default=None),
    instrument: str = Form(default="guitar"),
    difficulty: str = Form(default="beginner"),
    file: UploadFile | None = File(default=None),
    principal: Annotated[UserPrincipal | None, Depends(current_user)] = None,
    db=Depends(get_mongodb),
) -> AnalyzeResponse:
    """Kicks off the audio chord and theory analysis pipeline.

    Security (Phase 6 G1): ownership is derived from the auth token, never a
    client-supplied field. Anonymous callers (default config, no token) get
    ``user_id=None`` — a public analysis, exactly as before.
    """
    user_id = principal.user_id if principal is not None else None
    settings = get_settings()
    job_id = str(uuid.uuid4())

    if not youtube_url and file is None:
        raise HTTPException(status_code=400, detail="Provide either youtube_url or a file upload")

    # Phase 6 G5: defense-in-depth disk guard (disabled when max_disk_usage_gb
    # is 0). Refuse new ingestion when storage is already over the limit so a
    # full disk degrades gracefully instead of corrupting writes mid-pipeline.
    from backend.services.disk_reaper import storage_over_limit

    if storage_over_limit(
        [settings.audio_upload_dir, settings.stems_dir], settings.max_disk_usage_gb
    ):
        raise HTTPException(
            status_code=503, detail="Server storage is full; please try again later."
        )

    # Preflight URL validation (Plan 3 live-test report 2): catch the
    # "user typed a file path into the URL field" case at the request edge
    # so the client gets a synchronous error envelope instead of seeing
    # "Analyzing…" → "pipeline crashed" via SSE 30s later. Same allowlist
    # as :func:`backend.graph.nodes._validate_youtube_url` so behaviour is
    # consistent whether rejection happens here or in the worker.
    if youtube_url and file is None:
        from backend.graph.nodes import _validate_youtube_url

        try:
            _validate_youtube_url(youtube_url)
        except ValueError as e:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid URL: {e}. Paste a YouTube link or upload an audio file.",
            )

    audio_path = None
    file_hash_val = None

    if file:
        settings.ensure_dirs()
        max_bytes = settings.max_upload_mb * 1024 * 1024

        # Reject up front based on Content-Length when the client declares one larger
        # than the cap. This is a multipart envelope so it includes form overhead;
        # allow a small slack. The per-chunk check below remains the authoritative
        # enforcer if the client lies or omits the header.
        declared = request.headers.get("content-length")
        if declared and declared.isdigit() and int(declared) > int(max_bytes * 1.1):
            raise HTTPException(
                status_code=413,
                detail=f"Declared upload size exceeds maximum of {settings.max_upload_mb}MB",
            )

        safe_filename = _safe_audio_filename(job_id, file.filename)
        dest_path = settings.audio_upload_dir / safe_filename

        try:
            total_written = 0
            hasher = hashlib.sha256()
            head_bytes = b""
            with open(dest_path, "wb") as buffer:
                while True:
                    chunk = await file.read(8192)
                    if not chunk:
                        break
                    total_written += len(chunk)
                    if total_written > max_bytes:
                        dest_path.unlink(missing_ok=True)
                        raise HTTPException(
                            status_code=413,
                            detail=f"File exceeds maximum size of {settings.max_upload_mb}MB",
                        )
                    buffer.write(chunk)
                    hasher.update(chunk)
                    if len(head_bytes) < 16:
                        head_bytes += chunk[: 16 - len(head_bytes)]

            # Validate magic bytes — the client-supplied Content-Type is unreliable.
            if not _is_audio_magic(head_bytes):
                dest_path.unlink(missing_ok=True)
                raise HTTPException(
                    status_code=415,
                    detail="Uploaded file does not look like a supported audio format.",
                )

            digest = hasher.hexdigest()
            # Deduplication check — keyed on (file_hash, analyzer_version) so a
            # re-upload after a pipeline upgrade re-analyzes instead of serving
            # the stale older-pipeline result forever (DEDUP-VER, Phase 4 G5).
            existing = await db.song_analyses.find_one(
                {"file_hash": digest, "analyzer_version": ANALYZER_VERSION}
            )
            if existing:
                dest_path.unlink(missing_ok=True)
                return AnalyzeResponse(
                    job_id=existing["_id"],
                    status="done",
                    analysis=SongAnalysis.model_validate(existing),
                    instrument_guide=None,
                    audio_url=f"/api/v1/audio/{existing['_id']}",
                )

            audio_path = str(dest_path)
            file_hash_val = digest
        except HTTPException:
            raise
        except Exception as e:
            dest_path.unlink(missing_ok=True)
            logger.exception("Failed to save uploaded file for job %s", job_id)
            raise HTTPException(status_code=500, detail=f"Failed to save uploaded file: {str(e)}")

    response = AnalyzeResponse(
        job_id=job_id,
        status="queued",
        audio_url=f"/api/v1/audio/{job_id}" if audio_path else None,
    )
    await get_job_store().cache_response(job_id, response.model_dump_json())

    await run_analysis_pipeline.kiq(
        job_id,
        youtube_url,
        audio_path,
        instrument,
        difficulty,
        user_id,
        file_hash_val if file else None,
    )

    return response


@router.get("/analyze/{job_id}", response_model=AnalyzeResponse)
@limiter.limit(lambda: get_settings().read_rate_limit)
async def get_analysis(
    request: Request,
    job_id: str,
    instrument: str | None = None,
    principal: Annotated[UserPrincipal | None, Depends(current_user)] = None,
    db=Depends(get_mongodb),
) -> AnalyzeResponse:
    """Retrieves the current status or completed result of a song analysis job from MongoDB.

    Pass ``?instrument=guitar`` (etc.) to receive the matching instrument guide;
    omitting it returns no guide rather than an arbitrary one.

    Security (Phase 6 G2): an authenticated caller may only read an OWNED
    analysis they own; anonymous analyses (``user_id is None``) stay public —
    so the cache fast-path is preserved unchanged for anonymous deployments,
    and ownership is enforced *before* the cache can leak an owned payload.
    """
    job_store = get_job_store()
    repo = AnalysisRepo(db)

    if principal is not None:
        # Authenticated: the resolver returns the readable doc (owner or
        # anonymous) or None (missing / someone else's) -> 404, no oracle.
        db_record = await repo.resolve_readable(job_id, principal.user_id)
        if db_record is None:
            raise HTTPException(status_code=404, detail=f"Analysis job {job_id} not found")
        # FT-03 cache fast-path, now gated behind the ownership check above.
        cached = await job_store.get_cached_response(job_id)
        if cached and instrument is None:
            return AnalyzeResponse.model_validate_json(cached)
    else:
        # Anonymous deployment: every analysis is public; cache-first as before.
        cached = await job_store.get_cached_response(job_id)
        if cached and instrument is None:
            return AnalyzeResponse.model_validate_json(cached)
        db_record = await db.song_analyses.find_one({"_id": job_id})
        if not db_record:
            raise HTTPException(status_code=404, detail=f"Analysis job {job_id} not found")

    song_analysis = SongAnalysisModel.model_validate(db_record)

    analysis = SongAnalysis(
        title=song_analysis.title,
        artist=song_analysis.artist,
        duration=song_analysis.duration,
        key=song_analysis.key,
        key_confidence=song_analysis.key_confidence,            # P4/P5 confidences
        tempo=song_analysis.tempo,
        tempo_confidence=song_analysis.tempo_confidence,
        time_signature=song_analysis.time_signature,
        time_signature_confidence=song_analysis.time_signature_confidence,
        chords=song_analysis.chords,
        beats=song_analysis.beats,
        sections=song_analysis.sections,
        roman=song_analysis.roman,
        vibe_palette=song_analysis.vibe_palette,
        theory=song_analysis.theory,                        # structured object (G2)
        theory_explanation=song_analysis.theory_explanation,
        similar_songs=song_analysis.similar_songs,          # online recommendations (G4)
    )

    # Pick the *requested* instrument's guide, if any. Previously this returned
    # an arbitrary first-available guide, so a piano caller could receive guitar.
    guide_obj = None
    if instrument and song_analysis.instrument_guides:
        guide_obj = song_analysis.instrument_guides.get(instrument)

    # On-demand fallback: the analysis only pre-computes the guide for the
    # instrument chosen at submit time, so switching instruments in the player
    # would otherwise get an empty guide. The chord *diagrams* are fully
    # deterministic (tools/voicings), so build them on the fly for the requested
    # instrument — fast, no LLM. (Per-instrument LLM practice tips are only
    # generated in the pipeline; the switcher just needs the voicings.)
    if guide_obj is None and instrument and song_analysis.chords:
        from backend.schemas import InstrumentGuide
        from backend.tools.voicings import get_chord_diagrams

        chord_symbols = [c.chord for c in song_analysis.chords]
        guide_obj = InstrumentGuide(
            instrument=instrument,  # type: ignore[arg-type]
            difficulty="beginner",
            chord_diagrams=get_chord_diagrams(chord_symbols, instrument),  # type: ignore[arg-type]
        )

    response = AnalyzeResponse(
        job_id=job_id,
        status="done",
        analysis=analysis,
        instrument_guide=guide_obj,
        audio_url=f"/api/v1/audio/{job_id}",
    )

    # Only cache the un-instrumented response so the per-instrument variants
    # don't pollute the shared key.
    if instrument is None:
        await job_store.cache_response(job_id, response.model_dump_json())
    return response


class LibraryEntry(BaseModel):
    """Summary row for the library page (Plan 3 A7)."""

    job_id: str
    title: str | None = None
    artist: str | None = None
    key: str
    tempo: float
    duration: float
    created_at: datetime | None = None
    vibe_palette: list[str] = []


class LibraryResponse(BaseModel):
    items: list[LibraryEntry]
    total: int
    limit: int
    offset: int


@router.get("/library", response_model=LibraryResponse)
async def list_library(
    limit: int = 24,
    offset: int = 0,
    principal: UserPrincipal | None = Depends(current_user),
    db=Depends(get_mongodb),
) -> LibraryResponse:
    """List previously-analyzed songs (Plan 3 A7), newest first.

    Identity comes from the JWT, never the query string (a client-supplied
    ``user_id`` could otherwise enumerate another user's library — BOLA). When
    a user is authenticated we filter to analyses they own; in anonymous mode
    (no principal, ``require_auth=False``) we surface the shared collection,
    matching single-tenant local use.
    """
    limit = max(1, min(limit, 100))
    offset = max(0, offset)
    projection = {
        "_id": 1,
        "title": 1,
        "artist": 1,
        "key": 1,
        "tempo": 1,
        "duration": 1,
        "created_at": 1,
        "vibe_palette": 1,
    }
    query: dict = {}
    if principal is not None:
        # Authenticated: only this user's analyses. (Anonymous mode leaves the
        # query open so a local single-tenant deployment still lists everything.)
        query["user_id"] = principal.user_id
    total = await db.song_analyses.count_documents(query)
    cursor = (
        db.song_analyses.find(query, projection).sort("created_at", -1).skip(offset).limit(limit)
    )
    items: list[LibraryEntry] = []
    async for doc in cursor:
        items.append(
            LibraryEntry(
                job_id=doc["_id"],
                title=doc.get("title"),
                artist=doc.get("artist"),
                key=doc.get("key", "Unknown"),
                tempo=float(doc.get("tempo", 0.0)),
                duration=float(doc.get("duration", 0.0)),
                created_at=doc.get("created_at"),
                vibe_palette=doc.get("vibe_palette") or [],
            )
        )
    return LibraryResponse(items=items, total=total, limit=limit, offset=offset)


# ----------------------------------------------------------------------
# Cross-platform search (Plan v2 C5) and synced lyrics (Plan v2 C6)
# ----------------------------------------------------------------------


@router.get("/search")
@limiter.limit("30/minute")
async def search_tracks(request: Request, q: str, limit: int = 10) -> dict:
    """Search the merged Deezer + MusicBrainz catalog.

    Returns ``{results: [...]}`` where each entry has at minimum
    ``title``, ``artist``, plus whichever of ``deezer_id``, ``mbid``,
    ``preview_url``, ``image_url``, ``album``, ``year`` were resolved.

    Deezer (no auth, rich metadata) + MusicBrainz (rate-limited 1/sec,
    authoritative MBIDs) run in parallel. Merged and deduped by
    ``(title.lower, artist.lower)``.

    Cached for 1h via HybridCache — search queries are stable, and
    the upstream APIs (especially MusicBrainz) have aggressive rate
    limits we should respect.
    """
    if not q or len(q) > 200:
        raise HTTPException(status_code=400, detail="Query must be 1-200 characters")
    limit = max(1, min(limit, 25))

    import json as _json

    from backend.search import merged_search

    cache_key = f"search:q={q.lower().strip()}:limit={limit}"
    cached = await cache.get(cache_key)
    if cached:
        return {"results": _json.loads(cached), "cached": True}
    results = await merged_search(q, limit=limit)
    await cache.set(cache_key, _json.dumps(results), ttl_seconds=3600)
    return {"results": results, "cached": False}


@router.get("/lyrics")
@limiter.limit("60/minute")
async def get_lyrics(
    request: Request,
    track_name: str,
    artist_name: str,
    duration: int | None = None,
) -> dict:
    """Fetch synced + plain lyrics from LRCLIB.

    Returns ``{synced_lyrics, plain_lyrics, source}``. Both lyric
    fields are empty strings on a no-match — the frontend interprets
    that as "no lyrics available for this track".

    ``duration`` (seconds) is optional but helps LRCLIB disambiguate
    covers and live versions.
    """
    if not track_name or not artist_name:
        raise HTTPException(status_code=400, detail="track_name and artist_name are required")

    import json as _json

    from backend.lyrics import fetch_lyrics

    cache_key = (
        f"lyrics:t={track_name.lower().strip()}"
        f":a={artist_name.lower().strip()}:d={duration or 'any'}"
    )
    cached = await cache.get(cache_key)
    if cached:
        return _json.loads(cached) | {"cached": True}
    payload = await fetch_lyrics(track_name, artist_name, duration)
    # Cache hits AND misses (both are valuable). 6h TTL.
    await cache.set(cache_key, _json.dumps(payload), ttl_seconds=6 * 3600)
    return payload | {"cached": False}


@router.get("/share/{job_id}", response_model=AnalyzeResponse)
async def share_analysis(job_id: str, db=Depends(get_mongodb)) -> AnalyzeResponse:
    """Read-only public view of a completed analysis (Plan 3 B8).

    Same shape as ``GET /analyze/{job_id}`` but explicitly read-only,
    requires no instrument selector, and is the documented stable URL for
    "show this analysis to someone." Frontend builds the share link as
    ``/s/{job_id}`` which proxies here.
    """
    db_record = await AnalysisRepo(db).get(job_id)
    if not db_record:
        raise HTTPException(status_code=404, detail=f"Analysis {job_id} not found")
    song = SongAnalysisModel.model_validate(db_record)
    analysis = SongAnalysis(
        title=song.title,
        artist=song.artist,
        duration=song.duration,
        key=song.key,
        key_confidence=song.key_confidence,             # P4/P5 confidences
        tempo=song.tempo,
        tempo_confidence=song.tempo_confidence,
        time_signature=song.time_signature,
        time_signature_confidence=song.time_signature_confidence,
        chords=song.chords,
        beats=song.beats,
        sections=song.sections,
        roman=song.roman,
        vibe_palette=song.vibe_palette,
        theory=song.theory,                              # structured object (G2)
        theory_explanation=song.theory_explanation,
        similar_songs=song.similar_songs,               # online recommendations (G4)
    )
    return AnalyzeResponse(
        job_id=job_id,
        status="done",
        analysis=analysis,
        instrument_guide=None,
        audio_url=f"/api/v1/audio/{job_id}",
    )


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


def _sse_frame(event: str, data: dict | str) -> str:
    """Format a tagged SSE frame (Plan 2 D6).

    Always emits an ``event:`` line so clients can switch on the event
    name rather than parsing payload shape. Multi-line ``data`` would
    need to be re-line-prefixed; we always pass JSON or a short token, so
    a single ``data:`` line suffices.

    NOTE: used by the chat/stream endpoint which uses StreamingResponse
    with raw strings.  For the progress SSE endpoint (EventSourceResponse)
    use :func:`_sse_event` (module-level, returns ServerSentEvent) instead —
    passing a pre-formatted string into EventSourceResponse would double-prefix
    every line with ``data:``.
    """
    payload = data if isinstance(data, str) else json.dumps(data)
    return f"event: {event}\ndata: {payload}\n\n"


async def _await_if_needed(value):
    """Await *value* only if it is a coroutine / awaitable; return it otherwise.

    Module-level so it can be reused across request handlers without
    redefining a closure per request.
    """
    if inspect.isawaitable(value):
        return await value
    return value


@router.get("/jobs/{job_id}/progress")
async def get_analysis_progress(
    job_id: str,
    request: Request,
    principal: Annotated[UserPrincipal | None, Depends(current_user)] = None,
    db=Depends(get_mongodb),
):
    """Server-Sent Events stream of analysis progress.

    Protocol (Plan 2 D6 — tagged events):
        event: chunk    data: {status, progress, message, ...}   (repeated)
        event: done     data: {job_id, status: "done", ...}      (terminal)
        event: error    data: {code, message}                    (terminal)

    Successful jobs end with ``done``; downstream LLM failure or worker
    crash ends with ``error``. The generator also exits promptly once the
    HTTP client disconnects (``await request.is_disconnected()``) so a
    closed browser tab doesn't keep us polling Redis for the full lifetime.

    Security (Phase 6 G2): an authenticated caller can't stream another user's
    OWNED job's progress. ``allow_missing=True`` keeps in-flight jobs (whose
    final analysis doc isn't written yet) streamable to their owner.
    """
    await _enforce_owned_read(job_id, principal, db, allow_missing=True)
    job_store = get_job_store()

    def _sse_event(event: str, data: dict | str) -> ServerSentEvent:
        """Build a ``ServerSentEvent`` carrying the same tagged-event wire
        format the frontend ``consumeSse`` parser expects.

        ``EventSourceResponse`` does the ``event:``/``data:`` line framing
        itself, so we must hand it a structured ``ServerSentEvent`` (event
        name + JSON-string payload) rather than a pre-formatted ``_sse_frame``
        string — passing the raw string would make sse-starlette re-prefix
        every line with ``data:`` and corrupt the frame. The emitted bytes
        are ``event: <event>\r\ndata: <json>\r\n\r\n``; ``consumeSse``
        ``.trim()``s each line, so the ``\r`` is harmless.

        NOTE: for the chat/stream endpoint (StreamingResponse with raw strings)
        use the module-level :func:`_sse_frame` helper instead.
        """
        payload = data if isinstance(data, str) else json.dumps(data)
        return ServerSentEvent(event=event, data=payload)

    # _await_if_needed is module-level (see above _sse_frame); reuse it here.

    async def event_generator():
        max_lifetime_s = 30 * 60  # absolute upper bound; protects against bugs
        elapsed = 0
        last_emitted: str | None = None
        while elapsed < max_lifetime_s:
            # Disconnect-detection: exit as soon as the client closes the tab.
            if await request.is_disconnected():
                return

            # FT-03: :result key holds the final AnalyzeResponse; :progress
            # key holds incremental worker frames.  We must NOT treat a
            # :result with status "queued" as terminal — that's the stub
            # written by POST /analyze so GET /analyze/{job_id} responds
            # immediately.  Only status=="done" on :result ends the stream.
            result_data = await _await_if_needed(job_store.get_cached_response(job_id))
            result_status: str | None = None
            if result_data:
                try:
                    result_status = json.loads(result_data).get("status")
                except (json.JSONDecodeError, AttributeError):
                    result_status = None

            if result_data and result_status == "done":
                # Job is done — emit the terminal frame immediately without
                # touching :progress or the heartbeat key.
                cached_data = result_data
                job_finished = True
            else:
                # :result is absent or not yet "done" (e.g. status="queued").
                # Read the incremental progress frame the worker writes via
                # _progress() → job_store.set_progress() → :progress key.
                # ``get_progress`` may be absent on minimal test stubs; treat
                # that as "no incremental frame yet" rather than crashing.
                get_progress = getattr(job_store, "get_progress", None)
                progress_data = (
                    await _await_if_needed(get_progress(job_id))
                    if get_progress is not None
                    else None
                )
                cached_data = json.dumps(progress_data) if progress_data else None
                # Only error frames on :progress terminate the stream —
                # the worker crash path writes status="error" via _progress().
                job_finished = bool(progress_data and progress_data.get("status") == "error")

            if cached_data and cached_data != last_emitted:
                last_emitted = cached_data
                try:
                    parsed = json.loads(cached_data)
                except json.JSONDecodeError:
                    yield _sse_event("chunk", cached_data)
                    await asyncio.sleep(1.0)
                    elapsed += 1
                    continue

                status = parsed.get("status")
                if status == "done":
                    yield _sse_event("done", parsed)
                    return
                if status == "error":
                    yield _sse_event(
                        "error",
                        {
                            "code": parsed.get("code", "ANALYSIS_FAILED"),
                            "message": parsed.get("message", "Analysis failed"),
                            "job_id": job_id,
                        },
                    )
                    return
                yield _sse_event("chunk", parsed)

            # Only create+await the is_stale coroutine when the job is NOT
            # finished — avoids an unawaited-coroutine RuntimeWarning and
            # the 30-min spin that would otherwise continue after "done".
            if not job_finished:
                stale = job_store.is_stale(job_id, timeout_s=DEFAULT_HEARTBEAT_TIMEOUT_S)
                if await _await_if_needed(stale):
                    yield _sse_event(
                        "error",
                        {
                            "code": "WORKER_STALE",
                            "message": (
                                f"Analysis worker has not reported in "
                                f"{DEFAULT_HEARTBEAT_TIMEOUT_S}s — likely crashed."
                            ),
                            "job_id": job_id,
                        },
                    )
                    return

            await asyncio.sleep(1.0)
            elapsed += 1

        yield _sse_event(
            "error",
            {
                "code": "JOB_LIFETIME_EXCEEDED",
                "message": "Analysis exceeded maximum lifetime of 30 minutes.",
                "job_id": job_id,
            },
        )

    return EventSourceResponse(
        event_generator(),
        ping=15,  # keepalive comment frame every 15s to defeat idle proxies
        headers={"X-Accel-Buffering": "no"},  # disable nginx response buffering
    )


@router.post("/chat", response_model=ChatResponse)
@limiter.limit(lambda: get_settings().chat_rate_limit, key_func=_chat_rate_limit_key)
async def chat(
    request: Request,
    payload: ChatRequest,
    principal: UserPrincipal | None = Depends(current_user),
    db=Depends(get_mongodb),
) -> ChatResponse:
    """Grounded AURA chat (non-stream). Identity from the JWT when present;
    in anonymous mode (require_auth=False) chat works without login under a
    shared "anonymous" identity. session + history are server-owned;
    over-budget turns refuse before the model."""
    user_id = principal.user_id if principal is not None else "anonymous"
    settings = get_settings()

    # 1. Resolve a server-owned session id (generate if absent; ownership-check
    #    if supplied). Degrade to no-history on Mongo errors rather than 500.
    # M5: single-query path via _resolve_session.
    history: list[dict] = []
    analysis: dict | None = None
    mongo_ok = True
    session_id = payload.session_id
    repo = ChatSessionRepo(db)
    try:
        session_id, history, _ = await _resolve_session(
            repo, db, session_id, user_id
        )
        if payload.analysis_job_id:
            # I1: drop the public get() fallback — never expose another user's
            # analysis.  If the caller doesn't own the job, analysis stays None
            # and the agent uses its no-song-loaded path.
            analysis = await AnalysisRepo(db).get_owned(
                payload.analysis_job_id, user_id
            )
    except HTTPException:
        raise
    except Exception:
        logger.warning("chat: Mongo unavailable; degrading to no-history", exc_info=True)
        mongo_ok = False
        if not session_id:
            session_id = str(uuid.uuid4())

    # 2. Per-user token budget — friendly refusal, no model call.
    if not await check_and_consume(user_id, _estimate_tokens(payload.message, history)):
        return ChatResponse(
            reply=(
                "You've reached today's chat limit. Your budget resets at "
                "midnight UTC — thanks for using AURA so much!"
            ),
            session_id=session_id,
        )

    # 3. Personalization profile (best-effort).
    profile: dict | None = None
    if mongo_ok:
        try:
            profile = await UserRepo(db).get(user_id)
        except Exception:
            profile = None

    # 4. Run the grounded agent (degrades internally to the LCEL chat path on
    #    tool-capability / agent errors). Set the ownership contextvar so the
    #    analysis-reading tools enforce per-user ownership (Group B IDOR fix).
    token = current_user_id.set(user_id)
    try:
        reply = await run_aura(
            message=payload.message,
            history=history,
            analysis=analysis,
            profile=profile,
            tutor_mode=payload.tutor_mode or settings.chat_tutor_default,
        )
    finally:
        current_user_id.reset(token)

    # 5. Persist both turns (best-effort; never fail the response on a write).
    if mongo_ok:
        try:
            await repo.append_turn(session_id, "user", payload.message, user_id=user_id)
            await repo.append_turn(session_id, "assistant", reply, user_id=user_id)
        except Exception:
            logger.warning("chat: failed to persist turns", exc_info=True)

    return ChatResponse(reply=reply, session_id=session_id)


@router.post("/chat/stream")
@limiter.limit(lambda: get_settings().chat_rate_limit, key_func=_chat_rate_limit_key)
async def chat_stream(
    request: Request,
    payload: ChatRequest,
    principal: UserPrincipal | None = Depends(current_user),
    db=Depends(get_mongodb),
):
    """Grounded AURA chat (SSE). Same resolution as /chat (anonymous-allowed
    when require_auth=False); streams context/tool/chunk/done/error frames
    from stream_aura via EventSourceResponse (client-disconnect + keepalive)."""
    user_id = principal.user_id if principal is not None else "anonymous"
    settings = get_settings()

    history: list[dict] = []
    analysis: dict | None = None
    mongo_ok = True
    session_id = payload.session_id
    repo = ChatSessionRepo(db)
    try:
        # M5: single-query path via _resolve_session.
        session_id, history, _ = await _resolve_session(
            repo, db, session_id, user_id
        )
        if payload.analysis_job_id:
            # I1: drop the public get() fallback — never expose another user's
            # analysis.  If the caller doesn't own the job, analysis stays None.
            analysis = await AnalysisRepo(db).get_owned(
                payload.analysis_job_id, user_id
            )
    except HTTPException:
        raise
    except Exception:
        logger.warning("chat/stream: Mongo unavailable; degrading", exc_info=True)
        mongo_ok = False
        if not session_id:
            session_id = str(uuid.uuid4())

    # Budget: emit a single error frame instead of a 200 stream of content.
    if not await check_and_consume(user_id, _estimate_tokens(payload.message, history)):
        async def _refused():
            yield ServerSentEvent(
                event="error",
                data=json.dumps(
                    {"code": "CHAT_BUDGET_EXCEEDED",
                     "message": "Daily chat limit reached; resets at midnight UTC."}
                ),
            )
        return EventSourceResponse(
            _refused(),
            headers={"X-Accel-Buffering": "no", "X-Session-Id": session_id},
        )

    profile: dict | None = None
    if mongo_ok:
        try:
            profile = await UserRepo(db).get(user_id)
        except Exception:
            profile = None

    tutor_mode = payload.tutor_mode or settings.chat_tutor_default

    # I2: persist the user turn BEFORE streaming starts — it's known now and
    # must survive even a mid-stream error.
    if mongo_ok:
        try:
            await repo.append_turn(session_id, "user", payload.message, user_id=user_id)
        except Exception:
            logger.warning("chat/stream: failed to persist user turn", exc_info=True)

    async def event_generator():
        assistant_text_parts: list[str] = []
        # Set the ownership contextvar inside the generator task (Group B IDOR fix).
        _token = current_user_id.set(user_id)
        try:
            async for frame in stream_aura(
                message=payload.message,
                history=history,
                analysis=analysis,
                profile=profile,
                tutor_mode=tutor_mode,
            ):
                # Accumulate assistant text from chunk frames for persistence.
                if frame.event == "chunk":
                    try:
                        assistant_text_parts.append(json.loads(frame.data).get("text", ""))
                    except (json.JSONDecodeError, AttributeError):
                        pass
                # Inject the resolved session_id into the terminal done frame so
                # the frontend can persist it for multi-turn continuity.
                if frame.event == "done":
                    try:
                        done_data = json.loads(frame.data) if frame.data else {}
                    except (json.JSONDecodeError, AttributeError):
                        done_data = {}
                    done_data["session_id"] = session_id
                    yield ServerSentEvent(event="done", data=json.dumps(done_data))
                    continue
                yield frame
        except Exception:
            # I2: persist whatever partial assistant text accumulated before
            # re-raising the error frame, so mid-stream failures don't lose turns.
            logger.exception("chat/stream: aura stream failed")
            if mongo_ok:
                partial = "".join(assistant_text_parts)
                try:
                    await repo.append_turn(
                        session_id, "assistant", partial, user_id=user_id
                    )
                except Exception:
                    logger.warning("chat/stream: failed to persist partial assistant turn", exc_info=True)
            yield ServerSentEvent(
                event="error",
                data=json.dumps(
                    {"code": "CHAT_STREAM_FAILED",
                     "message": "AURA hit an error mid-stream."}
                ),
            )
            return
        finally:
            current_user_id.reset(_token)
        # Persist the assistant turn once the stream drains cleanly.
        if mongo_ok:
            reply = "".join(assistant_text_parts)
            try:
                await repo.append_turn(session_id, "assistant", reply, user_id=user_id)
            except Exception:
                logger.warning("chat/stream: failed to persist assistant turn", exc_info=True)

    return EventSourceResponse(
        event_generator(),
        ping=15,
        headers={"X-Accel-Buffering": "no", "X-Session-Id": session_id},
    )


@router.get("/chat/history/{session_id}")
async def get_chat_history(
    session_id: str,
    principal: UserPrincipal = Depends(require_user),
    db=Depends(get_mongodb),
):
    """Owner-only chat history. Returns 404 (not 403) for a session the caller
    doesn't own so we don't confirm the existence of someone else's session."""
    repo = ChatSessionRepo(db)
    # I3: verify ownership first (cheap _id+user_id query), then use the
    # windowed repo read — never pulls the full messages array.
    owned = await repo.get_owned_session(session_id, principal.user_id)
    if owned is None:
        raise HTTPException(status_code=404, detail="Session not found")
    history = await repo.recent_turns(session_id, get_settings().chat_history_turns)
    return {"history": history}


# ----------------------------------------------------------------------------
# Mount the router (Plan 2 D1)
# ----------------------------------------------------------------------------
# Canonical: every endpoint lives at /api/v1/<path>. We also include the same
# router at the root so the existing frontend keeps working at unprefixed
# paths during the transition. Remove the second include once the frontend
# (or any other client) has migrated to /api/v1.
app.include_router(router, prefix="/api/v1")
app.include_router(router)  # legacy alias — remove after frontend migration

# Domain routers — each dual-mounted (canonical /api/v1 + legacy root) to
# match the historical behaviour of the single combined router.
for _domain_router in (theory_router, collections_router, auth_router, user_router):
    app.include_router(_domain_router, prefix="/api/v1")
    app.include_router(_domain_router)

# Health probes are intentionally root-only (no /api/v1 variant) so
# orchestrators hit a stable, unversioned path.
app.include_router(health_router)

