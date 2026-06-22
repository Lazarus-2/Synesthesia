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
    """Atomically check the per-user daily budget and consume on success.

    Returns ``True`` and increments the day counter by ``est_tokens`` when the
    user is under ``CHAT_USER_DAILY_TOKEN_BUDGET``; returns ``False`` WITHOUT
    net consumption when the request would push them over. A cache error is
    treated as "allow" (fail-open) so a transient outage never blocks a paying
    user — the rate-limiter remains the hard ceiling.

    Uses an atomic INCRBY (then refunds on overflow) instead of a get/set
    read-modify-write, so N concurrent turns can't each read the same ``used``
    and collectively blow past the budget.
    """
    budget = get_settings().chat_user_daily_token_budget
    if budget <= 0:
        return True
    key = _budget_key(user_id)
    try:
        new_total = await cache.incr(key, est_tokens, ttl_seconds=_BUDGET_TTL_S)
    except Exception:  # pragma: no cover - defensive; incr already guards
        logger.warning("token_budget: cache incr failed; failing open")
        return True
    if new_total is None:
        return True  # hard cache error → fail-open
    if new_total > budget:
        # Lost the race / over budget — refund our increment so a refused turn
        # doesn't permanently count against the user.
        try:
            await cache.incr(key, -est_tokens)
        except Exception:  # pragma: no cover
            pass
        return False
    return True
