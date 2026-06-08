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
import json
import logging
import time
import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

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
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
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

from backend.chains.chat_chain import get_chat_response, get_chat_response_stream
from backend.config import get_settings
from backend.database import get_mongodb
from backend.models import SongAnalysisModel
from backend.repositories import AnalysisRepo, ChatSessionRepo
from backend.schemas import AnalyzeResponse, SongAnalysis
from backend.services.cache import cache
from backend.services.job_store import (
    DEFAULT_HEARTBEAT_TIMEOUT_S,
    get_job_store,
)
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

_settings_for_limiter = get_settings()
limiter = Limiter(
    key_func=get_remote_address,
    storage_uri=_settings_for_limiter.redis_url,
    strategy="fixed-window",
)
app.state.limiter = limiter


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


class ChatRequest(BaseModel):
    message: str
    history: list[dict] = []
    session_id: str | None = None
    user_id: str | None = None
    # Optional job id whose persisted SongAnalysis should be injected as
    # chat context (Plan 3 A4). Looked up server-side so the client can't
    # spoof a song the user hasn't actually analyzed.
    analysis_job_id: str | None = None


class ChatResponse(BaseModel):
    reply: str


class UserRequest(BaseModel):
    id: str
    username: str
    instrument: str = "guitar"
    difficulty: str = "beginner"


class UserPreferences(BaseModel):
    """Persistent personalization defaults (Plan 3 A8)."""

    default_instrument: str | None = None
    default_difficulty: str | None = None
    default_capo: int | None = None


# ----------------------------------------------------------------------------
# Auth (Plan 3 A9) — sign-up / login over the JWT skeleton from Plan 2 D4
# ----------------------------------------------------------------------------


class SignUpRequest(BaseModel):
    username: str
    password: str


class LoginRequest(BaseModel):
    username: str
    password: str


class AuthResponse(BaseModel):
    token: str
    user_id: str
    username: str


@app.get("/health")
async def health() -> dict:
    """Liveness probe.

    Cheap and always-200 so orchestrators can use this for "is the process
    alive" without depending on downstream services. For dependency state,
    see :func:`readiness`.
    """
    return {"status": "ok"}


@app.get("/health/ready")
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


@router.post("/analyze", response_model=AnalyzeResponse)
@limiter.limit(lambda: get_settings().analyze_rate_limit)
async def analyze(
    request: Request,
    youtube_url: str | None = Form(default=None),
    instrument: str = Form(default="guitar"),
    difficulty: str = Form(default="beginner"),
    user_id: str | None = Form(default=None),
    file: UploadFile | None = File(default=None),
    db=Depends(get_mongodb),
) -> AnalyzeResponse:
    """Kicks off the audio chord and theory analysis pipeline."""
    settings = get_settings()
    job_id = str(uuid.uuid4())

    if not youtube_url and file is None:
        raise HTTPException(status_code=400, detail="Provide either youtube_url or a file upload")

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
            # Deduplication check
            existing = await db.song_analyses.find_one({"file_hash": digest})
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
async def get_analysis(
    job_id: str,
    instrument: str | None = None,
    db=Depends(get_mongodb),
) -> AnalyzeResponse:
    """Retrieves the current status or completed result of a song analysis job from MongoDB.

    Pass ``?instrument=guitar`` (etc.) to receive the matching instrument guide;
    omitting it returns no guide rather than an arbitrary one.
    """
    # 1. Cache-first (caches a per-job payload; we don't cache per-instrument so
    # the cached payload's instrument_guide may not match the request — we
    # re-pick from the persisted analysis below when an instrument is specified).
    job_store = get_job_store()
    # FT-03: the :result key is the fast path; Mongo is the durable fallback.
    cached = await job_store.get_cached_response(job_id)
    if cached and instrument is None:
        return AnalyzeResponse.model_validate_json(cached)

    # 2. Pull from persistent MongoDB database
    db_record = await db.song_analyses.find_one({"_id": job_id})
    if not db_record:
        raise HTTPException(status_code=404, detail=f"Analysis job {job_id} not found")

    song_analysis = SongAnalysisModel.model_validate(db_record)

    analysis = SongAnalysis(
        title=song_analysis.title,
        artist=song_analysis.artist,
        duration=song_analysis.duration,
        key=song_analysis.key,
        tempo=song_analysis.tempo,
        time_signature=song_analysis.time_signature,
        chords=song_analysis.chords,
        beats=song_analysis.beats,
        sections=song_analysis.sections,
        roman=song_analysis.roman,
        vibe_palette=song_analysis.vibe_palette,
        theory_explanation=song_analysis.theory_explanation,
    )

    # Pick the *requested* instrument's guide, if any. Previously this returned
    # an arbitrary first-available guide, so a piano caller could receive guitar.
    guide_obj = None
    if instrument and song_analysis.instrument_guides:
        guide_obj = song_analysis.instrument_guides.get(instrument)

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


@router.post("/auth/signup", response_model=AuthResponse)
async def signup(req: SignUpRequest, db=Depends(get_mongodb)) -> AuthResponse:
    """Create a user with a hashed password and return a JWT (Plan 3 A9).

    Idempotency: returns 409 if the username is already taken. Note that
    the server still operates in anonymous-friendly mode unless
    ``REQUIRE_AUTH=true`` — sign-up is opt-in for users who want
    persistent libraries / preferences.
    """
    from backend.auth import hash_password, issue_token

    if not req.username.strip() or len(req.password) < 8:
        raise HTTPException(
            status_code=400,
            detail="Username required and password must be at least 8 characters",
        )
    if await db.users.find_one({"username": req.username}):
        raise HTTPException(status_code=409, detail="Username already taken")
    user_id = str(uuid.uuid4())
    await db.users.insert_one(
        {
            "_id": user_id,
            "username": req.username,
            "instrument": "guitar",
            "difficulty": "beginner",
            "password_hash": hash_password(req.password),
            "created_at": datetime.now(UTC),
        }
    )
    try:
        token = issue_token(user_id=user_id, username=req.username)
    except RuntimeError as e:
        # auth_secret_key not configured — still create the user, but the
        # client gets a clear 503 instead of a cryptic 500.
        raise HTTPException(status_code=503, detail=str(e))
    return AuthResponse(token=token, user_id=user_id, username=req.username)


@router.post("/auth/login", response_model=AuthResponse)
async def login(req: LoginRequest, db=Depends(get_mongodb)) -> AuthResponse:
    """Verify password and return a JWT (Plan 3 A9)."""
    from backend.auth import issue_token, verify_password

    user = await db.users.find_one({"username": req.username})
    if not user or not user.get("password_hash"):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not verify_password(req.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    try:
        token = issue_token(user_id=user["_id"], username=user["username"])
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    return AuthResponse(token=token, user_id=user["_id"], username=user["username"])


@router.get("/auth/me")
async def whoami(request: Request) -> dict:
    """Return the authenticated principal, or ``null`` when anonymous."""
    from backend.auth import current_user

    principal = current_user(request)
    if principal is None:
        return {"user": None}
    return {"user": {"user_id": principal.user_id, "username": principal.username}}


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
    user_id: str | None = None,
    limit: int = 24,
    offset: int = 0,
    db=Depends(get_mongodb),
) -> LibraryResponse:
    """List previously-analyzed songs (Plan 3 A7).

    Sorted by ``created_at`` descending. When ``user_id`` is provided we
    will (in the auth-on world) filter to that user — for now we surface
    the whole collection since ownership isn't enforced.
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
    if user_id:
        query["user_id"] = user_id
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
        tempo=song.tempo,
        time_signature=song.time_signature,
        chords=song.chords,
        beats=song.beats,
        sections=song.sections,
        roman=song.roman,
        vibe_palette=song.vibe_palette,
        theory_explanation=song.theory_explanation,
    )
    return AnalyzeResponse(
        job_id=job_id,
        status="done",
        analysis=analysis,
        instrument_guide=None,
        audio_url=f"/api/v1/audio/{job_id}",
    )


@router.get("/midi/{job_id}/{stem}")
async def export_midi(job_id: str, stem: str):
    """Transcribe a stem (or the full mix) to MIDI (Plan 3 B10).

    ``stem`` is one of ``vocals|drums|bass|other|full``. ``full`` runs
    basic-pitch over the staged audio file (no stem separation required).
    Other values look in ``stems_dir/{job_id}/{stem}.wav`` from the stem
    separation step — if that file doesn't exist yet, returns 404.
    """
    settings = get_settings()
    if stem == "full":
        candidates = sorted(settings.audio_upload_dir.glob(f"{job_id}*"))
        if not candidates:
            raise HTTPException(status_code=404, detail="No staged audio for job")
        source = candidates[0]
    else:
        if stem not in ("vocals", "drums", "bass", "other"):
            raise HTTPException(status_code=400, detail=f"Unknown stem {stem!r}")
        source = settings.stems_dir / job_id / f"{stem}.wav"
        if not source.exists():
            raise HTTPException(
                status_code=404,
                detail=f"Stem {stem!r} not separated yet; run analysis with stems enabled",
            )

    midi_dir = settings.stems_dir / job_id / "midi"
    midi_dir.mkdir(parents=True, exist_ok=True)
    out_midi = midi_dir / f"{stem}.mid"

    if not out_midi.exists():
        from backend.ml.midi_transcription import transcribe_to_midi

        result = await asyncio.to_thread(transcribe_to_midi, source, out_midi)
        if result is None or not out_midi.exists():
            raise HTTPException(
                status_code=503,
                detail="MIDI transcription failed (basic-pitch missing or errored). "
                "Install with `pip install '.[audio-heavy]'`.",
            )
    return FileResponse(
        out_midi,
        media_type="audio/midi",
        filename=f"{job_id}_{stem}.mid",
    )


@router.get("/stems/{job_id}/{stem}")
async def serve_stem(job_id: str, stem: str):
    """Stream a separated stem WAV (Plan 3 A2 + B7).

    ``stem`` is one of ``vocals|drums|bass|other``. Looks under
    ``settings.stems_dir/{job_id}/{stem}.wav`` (the layout written by
    ``stems_node`` via demucs).
    """
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
async def serve_audio(job_id: str):
    """Stream the analysed audio file by job id.

    Looks for any file in ``audio_upload_dir`` whose name starts with the
    job id (the upload pipeline stores them as ``{job_id}_{original_name}``,
    and yt-dlp downloads are renamed to ``{job_id}_{video_id}.mp3`` by
    ``ingest_node``). Falls back to a 404 envelope if nothing matches —
    better than serving an arbitrary file.
    """
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
    """
    payload = data if isinstance(data, str) else json.dumps(data)
    return f"event: {event}\ndata: {payload}\n\n"


@router.get("/jobs/{job_id}/progress")
async def get_analysis_progress(job_id: str):
    """Server-Sent Events stream of analysis progress.

    Protocol (Plan 2 D6 — tagged events):
        event: chunk    data: {status, progress, message, ...}   (repeated)
        event: done     data: {job_id, status: "done", ...}      (terminal)
        event: error    data: {code, message}                    (terminal)

    Successful jobs end with ``done``; downstream LLM failure or worker
    crash ends with ``error``. The frontend ``openProgressStream`` consumer
    in :mod:`frontend/web/src/lib/apiClient.ts` handles both new and legacy
    formats; once it ships, the backend can stop emitting untagged frames.
    """
    job_store = get_job_store()

    async def event_generator():
        max_lifetime_s = 30 * 60  # absolute upper bound; protects against bugs
        elapsed = 0
        last_emitted: str | None = None
        while elapsed < max_lifetime_s:
            # Fix 5 (SSE efficiency): fetch :result first; only fetch
            # :progress when :result is absent; skip is_stale when :result
            # is present (a done result needs no staleness check).
            # FT-03: terminal AnalyzeResponse lands on :result; incremental
            # frames land on :progress.
            result_data = await job_store.get_cached_response(job_id)
            if result_data:
                # Job is done — emit the terminal frame immediately without
                # touching :progress or the heartbeat key.
                cached_data = result_data
                job_finished = True
            else:
                progress_data = await job_store.get_progress(job_id)
                cached_data = json.dumps(progress_data) if progress_data else None
                job_finished = False

            if cached_data and cached_data != last_emitted:
                last_emitted = cached_data
                try:
                    parsed = json.loads(cached_data)
                except json.JSONDecodeError:
                    yield _sse_frame("chunk", cached_data)
                    await asyncio.sleep(1.0)
                    elapsed += 1
                    continue

                status = parsed.get("status")
                if status == "done":
                    yield _sse_frame("done", parsed)
                    return
                if status == "error":
                    yield _sse_frame(
                        "error",
                        {
                            "code": parsed.get("code", "ANALYSIS_FAILED"),
                            "message": parsed.get("message", "Analysis failed"),
                            "job_id": job_id,
                        },
                    )
                    return
                yield _sse_frame("chunk", parsed)

            # Only run the staleness check when the job isn't finished.
            if not job_finished and await job_store.is_stale(
                job_id, timeout_s=DEFAULT_HEARTBEAT_TIMEOUT_S
            ):
                yield _sse_frame(
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

        yield _sse_frame(
            "error",
            {
                "code": "JOB_LIFETIME_EXCEEDED",
                "message": "Analysis exceeded maximum lifetime of 30 minutes.",
                "job_id": job_id,
            },
        )

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.post("/user")
async def create_or_update_user(req: UserRequest, db=Depends(get_mongodb)):
    """Registers user identity or updates musical preferences in MongoDB."""
    user_dict = {
        "_id": req.id,
        "username": req.username,
        "instrument": req.instrument,
        "difficulty": req.difficulty,
        "created_at": datetime.now(UTC),
    }
    await db.users.replace_one({"_id": req.id}, user_dict, upsert=True)
    return {
        "id": user_dict["_id"],
        "username": user_dict["username"],
        "instrument": user_dict["instrument"],
        "difficulty": user_dict["difficulty"],
        "created_at": user_dict["created_at"].isoformat(),
    }


@router.get("/user/{user_id}/preferences")
async def get_user_preferences(user_id: str, db=Depends(get_mongodb)) -> UserPreferences:
    """Read the user's persisted analyze/playback defaults (Plan 3 A8)."""
    user = await db.users.find_one({"_id": user_id})
    if not user:
        raise HTTPException(status_code=404, detail="User profile not registered")
    return UserPreferences(
        default_instrument=user.get("default_instrument") or user.get("instrument"),
        default_difficulty=user.get("default_difficulty") or user.get("difficulty"),
        default_capo=user.get("default_capo"),
    )


@router.put("/user/{user_id}/preferences", response_model=UserPreferences)
async def update_user_preferences(
    user_id: str,
    prefs: UserPreferences,
    db=Depends(get_mongodb),
) -> UserPreferences:
    """Persist analyze/playback defaults (Plan 3 A8). Upserts the user row."""
    update: dict[str, object] = {"updated_at": datetime.now(UTC)}
    if prefs.default_instrument is not None:
        update["default_instrument"] = prefs.default_instrument
    if prefs.default_difficulty is not None:
        update["default_difficulty"] = prefs.default_difficulty
    if prefs.default_capo is not None:
        update["default_capo"] = prefs.default_capo
    # Upsert the user row so a preferences-only client (no prior /user POST)
    # still gets a record.
    await db.users.update_one(
        {"_id": user_id},
        {
            "$set": update,
            "$setOnInsert": {
                "_id": user_id,
                "username": f"User-{user_id[:6]}",
                "instrument": "guitar",
                "difficulty": "beginner",
                "created_at": datetime.now(UTC),
            },
        },
        upsert=True,
    )
    return prefs


@router.get("/user/{user_id}")
async def get_user_profile(user_id: str, db=Depends(get_mongodb)):
    """Fetches registered profile metadata from MongoDB."""
    user = await db.users.find_one({"_id": user_id})
    if not user:
        raise HTTPException(status_code=404, detail="User profile not registered")
    return {
        "id": user["_id"],
        "username": user["username"],
        "instrument": user["instrument"],
        "difficulty": user["difficulty"],
        "created_at": user["created_at"].isoformat()
        if isinstance(user["created_at"], datetime)
        else user["created_at"],
    }


@router.post("/chat", response_model=ChatResponse)
@limiter.limit(lambda: get_settings().chat_rate_limit)
async def chat(
    request: Request,
    payload: ChatRequest,
    db=Depends(get_mongodb),
) -> ChatResponse:
    """Conversational AI assistant. Stores messages and coordinates session caching."""
    # ``request`` is the Starlette Request (used by slowapi's key_func);
    # ``payload`` is the parsed ChatRequest body.
    del request  # silence unused warning while preserving the slowapi dep
    # 1. Setup session and user in DB if parameters provided
    if payload.user_id and payload.session_id:
        user = await db.users.find_one({"_id": payload.user_id})
        if not user:
            await db.users.insert_one(
                {
                    "_id": payload.user_id,
                    "username": f"Hacker-{payload.user_id[:4]}",
                    "instrument": "guitar",
                    "difficulty": "beginner",
                    "created_at": datetime.now(UTC),
                }
            )

        session = await db.chat_sessions.find_one({"_id": payload.session_id})
        if not session:
            await db.chat_sessions.insert_one(
                {
                    "_id": payload.session_id,
                    "user_id": payload.user_id,
                    "messages": [],
                    "created_at": datetime.now(UTC),
                }
            )

        # Save user query
        user_msg = {"role": "user", "content": payload.message, "timestamp": datetime.now(UTC)}
        await db.chat_sessions.update_one(
            {"_id": payload.session_id}, {"$push": {"messages": user_msg}}
        )

    # 2. Look up song context (Plan 3 A4) and invoke the assistant chain.
    analysis_doc: dict | None = None
    if payload.analysis_job_id:
        analysis_doc = await db.song_analyses.find_one({"_id": payload.analysis_job_id})

    # get_chat_response is synchronous (LangChain .invoke); run in a worker
    # thread so the event loop isn't blocked while the LLM call is in flight.
    reply = await asyncio.to_thread(
        get_chat_response, payload.message, payload.history, analysis_doc
    )

    # 3. Save assistant reply to MongoDB
    if payload.user_id and payload.session_id:
        assistant_msg = {"role": "assistant", "content": reply, "timestamp": datetime.now(UTC)}
        await db.chat_sessions.update_one(
            {"_id": payload.session_id}, {"$push": {"messages": assistant_msg}}
        )

        # Re-query session messages to form correct history list
        session_doc = await db.chat_sessions.find_one({"_id": payload.session_id})
        messages = session_doc.get("messages", []) if session_doc else []
        history_payload = [{"role": msg["role"], "content": msg["content"]} for msg in messages]

        # Update cache key
        cache_key = f"chat:session:{payload.session_id}"
        await cache.set(cache_key, json.dumps(history_payload), ttl_seconds=1800)

    return ChatResponse(reply=reply)


@router.post("/chat/stream")
@limiter.limit(lambda: get_settings().chat_rate_limit)
async def chat_stream(
    request: Request,
    payload: ChatRequest,
    db=Depends(get_mongodb),
):
    """Conversational AI assistant with SSE streaming response."""
    # ``request`` is the Starlette Request (slowapi key_func reads it).
    # ``payload`` is the parsed ChatRequest body.
    del request
    # 1. Setup session and user in DB if parameters provided
    if payload.user_id and payload.session_id:
        user = await db.users.find_one({"_id": payload.user_id})
        if not user:
            await db.users.insert_one(
                {
                    "_id": payload.user_id,
                    "username": f"Hacker-{payload.user_id[:4]}",
                    "instrument": "guitar",
                    "difficulty": "beginner",
                    "created_at": datetime.now(UTC),
                }
            )

        session = await db.chat_sessions.find_one({"_id": payload.session_id})
        if not session:
            await db.chat_sessions.insert_one(
                {
                    "_id": payload.session_id,
                    "user_id": payload.user_id,
                    "messages": [],
                    "created_at": datetime.now(UTC),
                }
            )

        user_msg = {"role": "user", "content": payload.message, "timestamp": datetime.now(UTC)}
        await db.chat_sessions.update_one(
            {"_id": payload.session_id}, {"$push": {"messages": user_msg}}
        )

    # Pull song context once before opening the stream so we don't hit the
    # DB on every yielded chunk.
    analysis_doc_stream: dict | None = None
    if payload.analysis_job_id:
        analysis_doc_stream = await db.song_analyses.find_one({"_id": payload.analysis_job_id})

    async def stream_generator():
        full_reply = ""
        try:
            async for chunk in get_chat_response_stream(
                payload.message,
                payload.history,
                analysis_doc_stream,
            ):
                if chunk:
                    yield _sse_frame("chunk", {"text": chunk})
                    full_reply += chunk
        except Exception as e:
            logger.exception("chat stream failed")
            yield _sse_frame(
                "error",
                {
                    "code": "CHAT_STREAM_FAILED",
                    "message": str(e)[:200],
                },
            )
            return

        # Save assistant reply to MongoDB after stream completes
        if payload.user_id and payload.session_id:
            assistant_msg = {
                "role": "assistant",
                "content": full_reply,
                "timestamp": datetime.now(UTC),
            }
            await db.chat_sessions.update_one(
                {"_id": payload.session_id}, {"$push": {"messages": assistant_msg}}
            )

        yield _sse_frame("done", {"reply_length": len(full_reply)})

    return StreamingResponse(stream_generator(), media_type="text/event-stream")


@router.get("/chat/history/{session_id}")
async def get_chat_history(session_id: str, db=Depends(get_mongodb)):
    """Retrieves standard discussion threads from Cache or drops back to MongoDB."""
    cache_key = f"chat:session:{session_id}"
    cached = await cache.get(cache_key)
    if cached:
        return {"history": json.loads(cached)}

    # Drop back to MongoDB — window the tail server-side via $slice instead of
    # pulling the full messages array and slicing in Python.
    history_payload = await ChatSessionRepo(db).recent_turns(session_id, 200)
    # Always cache — including empty-message sessions — so a second request for
    # the same session_id doesn't re-hit Mongo. The early-return that skipped
    # caching when history_payload == [] was a bug (one Mongo query per
    # request for any session that exists but has no messages yet).
    await cache.set(cache_key, json.dumps(history_payload), ttl_seconds=1800)
    return {"history": history_payload}


# ----------------------------------------------------------------------------
# Mount the router (Plan 2 D1)
# ----------------------------------------------------------------------------
# Canonical: every endpoint lives at /api/v1/<path>. We also include the same
# router at the root so the existing frontend keeps working at unprefixed
# paths during the transition. Remove the second include once the frontend
# (or any other client) has migrated to /api/v1.
app.include_router(router, prefix="/api/v1")
app.include_router(router)  # legacy alias — remove after frontend migration
