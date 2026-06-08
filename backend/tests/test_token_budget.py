"""Per-user daily token budget (Group D.1).

check_and_consume increments a day-keyed counter in the async cache and
returns False once the per-user daily budget is exhausted. A fake async
cache lets us assert the keying + arithmetic without Redis.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from backend.services import token_budget


class FakeCache:
    """Minimal async stand-in for HybridCache: get/set over a dict."""

    def __init__(self) -> None:
        self.store: dict[str, str] = {}
        self.set_calls: list[tuple[str, str, int | None]] = []

    async def get(self, key: str):
        return self.store.get(key)

    async def set(self, key: str, value: str, ttl_seconds: int | None = 1800):
        self.store[key] = value
        self.set_calls.append((key, value, ttl_seconds))
        return True


@pytest.fixture
def fake_cache(monkeypatch) -> FakeCache:
    fc = FakeCache()
    monkeypatch.setattr(token_budget, "cache", fc)
    return fc


def _expected_key(user_id: str) -> str:
    day = datetime.now(UTC).strftime("%Y-%m-%d")
    return f"chat:budget:{user_id}:{day}"


@pytest.mark.asyncio
async def test_first_call_under_budget_returns_true(fake_cache, monkeypatch):
    monkeypatch.setenv("CHAT_USER_DAILY_TOKEN_BUDGET", "1000")
    from backend.config import get_settings

    get_settings.cache_clear()
    ok = await token_budget.check_and_consume("user-1", est_tokens=100)
    assert ok is True
    # Counter is now 100, stored under the day-keyed budget key.
    assert fake_cache.store[_expected_key("user-1")] == "100"


@pytest.mark.asyncio
async def test_accumulates_across_calls(fake_cache, monkeypatch):
    monkeypatch.setenv("CHAT_USER_DAILY_TOKEN_BUDGET", "1000")
    from backend.config import get_settings

    get_settings.cache_clear()
    assert await token_budget.check_and_consume("user-1", est_tokens=400) is True
    assert await token_budget.check_and_consume("user-1", est_tokens=400) is True
    assert fake_cache.store[_expected_key("user-1")] == "800"


@pytest.mark.asyncio
async def test_over_budget_returns_false_and_does_not_consume(fake_cache, monkeypatch):
    monkeypatch.setenv("CHAT_USER_DAILY_TOKEN_BUDGET", "1000")
    from backend.config import get_settings

    get_settings.cache_clear()
    # Pre-seed the counter near the cap.
    fake_cache.store[_expected_key("user-1")] = "950"
    ok = await token_budget.check_and_consume("user-1", est_tokens=100)
    assert ok is False
    # Rejected request must NOT increment the counter.
    assert fake_cache.store[_expected_key("user-1")] == "950"


@pytest.mark.asyncio
async def test_per_user_isolation(fake_cache, monkeypatch):
    monkeypatch.setenv("CHAT_USER_DAILY_TOKEN_BUDGET", "1000")
    from backend.config import get_settings

    get_settings.cache_clear()
    await token_budget.check_and_consume("user-a", est_tokens=900)
    # A different user has their own counter, still empty.
    assert await token_budget.check_and_consume("user-b", est_tokens=900) is True
    assert fake_cache.store[_expected_key("user-a")] == "900"
    assert fake_cache.store[_expected_key("user-b")] == "900"
