"""Async MongoDB client lifecycle.

Connections are established in :func:`init_mongodb` (called from the FastAPI
``lifespan`` hook) and torn down in :func:`close_mongodb`. Request handlers
get the live database via the :func:`get_mongodb` dependency.

Previously this module had a lazy-init path with module-level globals mutated
on first request, which raced under concurrent first-request load and could
create multiple Motor clients.
"""

from __future__ import annotations

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from backend.config import get_settings

_client: AsyncIOMotorClient | None = None
_db: AsyncIOMotorDatabase | None = None


# 90 days in seconds — applied as Mongo TTL on the created_at field of
# transient collections (analyses, failed jobs). Tweak via env if you need
# longer retention for compliance / debugging.
_TTL_SECONDS_90_DAYS = 60 * 60 * 24 * 90


async def _create_indexes(db) -> None:
    """Create all Mongo indexes used by the app. Idempotent — Mongo
    silently no-ops re-creating an identical index."""
    # User lookup by username (login flow, future auth).
    await db.users.create_index("username")

    # Chat sessions: list/lookup by user; sorted-by-recency.
    await db.chat_sessions.create_index([("user_id", 1), ("created_at", -1)])

    # Song analyses:
    # - file_hash for upload deduplication.
    # - created_at TTL so abandoned analyses age out after 90 days.
    await db.song_analyses.create_index("file_hash", sparse=True)
    await db.song_analyses.create_index(
        "created_at",
        expireAfterSeconds=_TTL_SECONDS_90_DAYS,
    )

    # Dead-letter queue (failed_jobs): lookup by job_id for triage; TTL on
    # created_at so the collection self-bounds.
    await db.failed_jobs.create_index("job_id")
    await db.failed_jobs.create_index(
        "created_at",
        expireAfterSeconds=_TTL_SECONDS_90_DAYS,
    )


async def init_mongodb() -> None:
    """Connect to MongoDB and create indexes. Idempotent."""
    global _client, _db
    if _db is not None:
        return
    settings = get_settings()
    _client = AsyncIOMotorClient(settings.mongo_uri)
    _db = _client[settings.mongo_db_name]
    await _create_indexes(_db)


async def close_mongodb() -> None:
    """Close the MongoDB client. Idempotent."""
    global _client, _db
    if _client is not None:
        _client.close()
    _client = None
    _db = None


def get_mongodb() -> AsyncIOMotorDatabase:
    """FastAPI dependency that returns the initialized database.

    Raises RuntimeError if called before :func:`init_mongodb` has been awaited
    (i.e. outside the FastAPI lifespan).
    """
    if _db is None:
        raise RuntimeError("MongoDB not initialized. Did the FastAPI lifespan hook run?")
    return _db


# --- Legacy Compatibility Stubs (kept; other modules may still import these) ---
def create_db_and_tables() -> None:
    """Stub to support legacy startup sequences."""


def get_session():
    """Stub to prevent SQL dependency generation issues."""
    yield None


class DummyEngine:
    pass


engine = DummyEngine()
