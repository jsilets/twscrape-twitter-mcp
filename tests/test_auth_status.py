"""auth_status reports readiness from the `active` flag, not twscrape's
`logged_in` flag. BYO-cookie sessions stay logged_in=False yet read fine, so
gating on logged_in used to report a live session as "no session"."""

import asyncio

import pytest

server = pytest.importorskip("twscrape_twitter_mcp.server")

# auth_status is wrapped by @mcp.tool/@_guard; reach the underlying coroutine.
_auth_status = getattr(server.auth_status, "fn", server.auth_status)


def _run(rows, monkeypatch):
    async def fake_list_accounts():
        return rows

    monkeypatch.setattr(server, "list_accounts", fake_list_accounts)
    return asyncio.run(_auth_status())


def test_cookie_session_reports_ready(monkeypatch):
    # The regression: active cookie session, logged_in False -> must be "ready".
    rows = [{"username": "u", "active": True, "logged_in": False, "last_used": ""}]
    out = _run(rows, monkeypatch)
    assert "X session ready: 1 active account(s)" in out


def test_no_active_account_reports_no_session(monkeypatch):
    rows = [{"username": "u", "active": False, "logged_in": False, "last_used": ""}]
    out = _run(rows, monkeypatch)
    assert "No active X session" in out


def test_empty_pool_reports_no_session(monkeypatch):
    out = _run([], monkeypatch)
    assert "No active X session" in out
