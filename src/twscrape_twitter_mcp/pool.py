"""twscrape account-pool management.

This is the only place we touch twscrape's account/session machinery. The pool
is sqlite-backed (TWSCRAPE_TWITTER_MCP_DB) and natively rotates across accounts to smooth rate
limits, which is exactly the "multi-account" substrate we want even for a single
operator running a couple of burner sessions.
"""

from __future__ import annotations

from typing import Any

from twscrape import API

from .config import settings

_api: "API | None" = None


def get_api() -> "API":
    """Lazily build a singleton twscrape API bound to our sqlite pool."""
    global _api
    if _api is None:
        settings.ensure_dirs()
        _api = API(str(settings.db_path))
    return _api


async def add_account_from_cookies(
    *,
    username: str,
    auth_token: str,
    ct0: str,
    proxy: str | None = None,
) -> str:
    """Add (or refresh) an account in the pool from browser cookies.

    Only auth_token + ct0 are required to read. Password/email are placeholders
    because cookie auth never exercises the login flow.
    """
    api = get_api()
    cookies = f"auth_token={auth_token}; ct0={ct0}"

    await api.pool.add_account(
        username=username,
        password="cookie-auth",
        email=f"{username}@cookie.local",
        email_password="cookie-auth",
        cookies=cookies,
        proxy=proxy or settings.proxy,
    )
    # With cookies present twscrape activates the session without a password
    # login. login_all() is the documented way to mark added accounts usable.
    try:
        await api.pool.login_all()
    except Exception:
        # Non-fatal: the account row exists; a bad cookie surfaces on first read.
        pass
    return username


async def list_accounts() -> list[dict[str, Any]]:
    api = get_api()
    infos = await api.pool.accounts_info()
    out: list[dict[str, Any]] = []
    for info in infos:
        # accounts_info() returns plain dicts.
        get = info.get if isinstance(info, dict) else (lambda k, d=None: getattr(info, k, d))
        out.append(
            {
                "username": get("username") or "?",
                "active": bool(get("active")),
                "logged_in": bool(get("logged_in")),
                "last_used": str(get("last_used") or ""),
            }
        )
    return out
