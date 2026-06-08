"""Per-user daily chat token budget (Group D.1).

A best-effort guardrail enforced BEFORE the LLM call: over-budget turns get a
friendly refusal and never reach the model (spec §10). The counter is a
day-keyed integer in the async HybridCache — Redis when up, the in-process
memory shadow when down (so a Redis outage degrades to a per-process budget
rather than 500ing the chat). Reset is implicit: a new UTC day → a new key.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from backend.config import get_settings
from backend.services.cache import cache

logger = logging.getLogger(__name__)

# Keep counters one day past the active day so a clock-skewed read can't
# resurrect a stale counter; the key itself rotates on the UTC date.
_BUDGET_TTL_S = 60 * 60 * 26


def _budget_key(user_id: str) -> str:
    day = datetime.now(UTC).strftime("%Y-%m-%d")
    return f"chat:budget:{user_id}:{day}"


async def check_and_consume(user_id: str, est_tokens: int) -> bool:
    """Atomically-ish check the per-user daily budget and consume on success.

    Returns ``True`` and increments the day counter by ``est_tokens`` when the
    user is under ``CHAT_USER_DAILY_TOKEN_BUDGET``; returns ``False`` WITHOUT
    consuming when the request would push them over. A cache error is treated
    as "allow" (fail-open) so a transient outage never blocks a paying user —
    the rate-limiter remains the hard ceiling.
    """
    budget = get_settings().chat_user_daily_token_budget
    if budget <= 0:
        return True
    key = _budget_key(user_id)
    try:
        raw = await cache.get(key)
        used = int(raw) if raw else 0
    except Exception:  # pragma: no cover - cache contract returns None on miss
        logger.warning("token_budget: cache read failed; failing open")
        return True
    if used + est_tokens > budget:
        return False
    await cache.set(key, str(used + est_tokens), ttl_seconds=_BUDGET_TTL_S)
    return True
