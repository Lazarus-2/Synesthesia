"""Shared slowapi limiter.

Single source of the ``Limiter`` instance so routers across the app key
their rate limits against the same Redis-backed fixed-window store. The
storage URI shares counts across worker processes so limits are global,
not per-container.
"""

from __future__ import annotations

from slowapi import Limiter
from slowapi.util import get_remote_address

from backend.config import get_settings

_s = get_settings()
limiter = Limiter(
    key_func=get_remote_address,
    storage_uri=_s.redis_url,
    strategy="fixed-window",
)
