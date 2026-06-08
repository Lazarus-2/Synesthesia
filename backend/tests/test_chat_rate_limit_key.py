"""Chat rate-limit key derivation (Group D.4).

The chat endpoints must rate-limit by authenticated user_id (falling back to
IP only when anonymous) so one user can't exhaust another's budget by sharing
a NAT, and a single user can't bypass the limit by rotating source IPs.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from backend.main import _chat_rate_limit_key


def _req_with_principal(user_id):
    req = MagicMock()
    req.state.principal = MagicMock(user_id=user_id) if user_id else None
    # Starlette client tuple for the IP fallback.
    req.client = MagicMock(host="203.0.113.7")
    req.headers = {}
    return req


def test_key_uses_user_id_when_present():
    assert _chat_rate_limit_key(_req_with_principal("user-42")) == "user:user-42"


def test_key_falls_back_to_ip_when_anonymous():
    key = _chat_rate_limit_key(_req_with_principal(None))
    assert key == "203.0.113.7"
