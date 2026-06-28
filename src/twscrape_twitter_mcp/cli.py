"""Command-line entry: init | login | serve | accounts | smoke."""

from __future__ import annotations

import argparse
import asyncio
import getpass
import sys

from .config import settings


def _cmd_init(args: argparse.Namespace) -> int:
    """Capture cookies and add a session to the pool."""
    from .pool import add_account_from_cookies

    username = args.username
    auth_token = args.auth_token
    ct0 = args.ct0

    if not username:
        username = input("X username (handle, no @): ").strip().lstrip("@")
    if not auth_token:
        auth_token = getpass.getpass("auth_token cookie: ").strip()
    if not ct0:
        ct0 = getpass.getpass("ct0 cookie: ").strip()

    if not (username and auth_token and ct0):
        print("Need username + auth_token + ct0. Aborting.", file=sys.stderr)
        return 2

    asyncio.run(
        add_account_from_cookies(username=username, auth_token=auth_token, ct0=ct0)
    )
    print(f"Added @{username} to the pool at {settings.db_path}")
    print("Verify with:  twscrape-twitter-mcp smoke")
    return 0


def _cmd_accounts(args: argparse.Namespace) -> int:
    from .pool import list_accounts

    rows = asyncio.run(list_accounts())
    if not rows:
        print("No accounts in the pool. Sign in with:  twscrape-twitter-mcp login")
        return 0
    for r in rows:
        print(
            f"@{r['username']:<20} active={r['active']} "
            f"logged_in={r['logged_in']} last_used={r['last_used']}"
        )
    return 0


def _cmd_smoke(args: argparse.Namespace) -> int:
    """Live end-to-end check: read one known public tweet.

    Exercises the same path the MCP tool uses (pool -> twscrape -> formatter)
    without depending on FastMCP internals, so it is stable for CI.
    """
    from .formatters import tweet_to_md
    from .pool import get_api
    from .server import _parse_id

    target = args.url or "https://x.com/Twitter/status/20"  # the first-ever tweet

    async def _run() -> str:
        api = get_api()
        t = await api.tweet_details(_parse_id(target))
        return tweet_to_md(t) if t else ""

    out = asyncio.run(_run())
    if not out:
        print("SMOKE FAILED: no readable tweet returned.", file=sys.stderr)
        return 1
    print(out)
    print("\nSMOKE OK")
    return 0


def _cmd_login(args: argparse.Namespace) -> int:
    """Capture a signed-in X session without cookie paste."""
    from .auth import (
        add_cookies_to_pool,
        attach_session,
        has_active_session,
        interactive_login,
        launch_managed_browser,
        wait_for_attached_session,
        wait_for_cdp,
    )

    if args.fresh_browser:
        print(
            "Opening an automated login browser. This is a fallback and may be "
            "blocked by X; prefer `twscrape-twitter-mcp login --attach`.",
            file=sys.stderr,
        )
        try:
            cmap = asyncio.run(interactive_login())
        except Exception as e:
            print(str(e), file=sys.stderr)
            return 1
    else:
        if args.launch_browser:
            try:
                launch_managed_browser(args.launch_browser, args.cdp_url)
                wait_for_cdp(args.cdp_url)
            except Exception as e:
                print(str(e), file=sys.stderr)
                return 1
            print(
                "Opened a dedicated browser profile for twscrape-twitter-mcp. Sign in to X there; "
                "waiting for the session...",
                file=sys.stderr,
            )
            attach = wait_for_attached_session(args.cdp_url)
        else:
            attach = attach_session(args.cdp_url)
        try:
            cmap = asyncio.run(attach)
        except Exception as e:
            print(str(e), file=sys.stderr)
            return 1

    asyncio.run(add_cookies_to_pool(cmap))
    ok = asyncio.run(has_active_session())
    if ok:
        print("Session captured. Verify with:  twscrape-twitter-mcp smoke")
        return 0
    print("Session capture did not complete.", file=sys.stderr)
    return 1


def _cmd_serve(args: argparse.Namespace) -> int:
    from .auth import ensure_session
    from .server import mcp

    if args.transport == "stdio":
        # On startup, silently reuse a session or try a configured CDP endpoint.
        if not args.no_auto_login:
            asyncio.run(ensure_session(open_browser=True))
        mcp.run()  # default stdio transport
        return 0

    # HTTP transport for Fly/Railway. Headless: can't pop a window, so just warn
    # if no session is seeded. Reload a persisted storage_state silently if present.
    asyncio.run(ensure_session(open_browser=False))

    # Gate it with a bearer token if configured.
    host = args.host
    port = args.port or settings.port
    app = mcp.http_app(path="/mcp")

    token = settings.http_auth_token
    if token:
        from starlette.middleware.base import BaseHTTPMiddleware
        from starlette.responses import JSONResponse

        class _TokenAuth(BaseHTTPMiddleware):
            async def dispatch(self, request, call_next):
                if request.headers.get("authorization", "") != f"Bearer {token}":
                    return JSONResponse({"error": "unauthorized"}, status_code=401)
                return await call_next(request)

        app.add_middleware(_TokenAuth)
    else:
        print(
            "WARNING: serving HTTP without TWSCRAPE_TWITTER_MCP_AUTH_TOKEN. Anyone who can reach "
            f"http://{host}:{port}/mcp can use your X session. Set a token.",
            file=sys.stderr,
        )

    import uvicorn

    uvicorn.run(app, host=host, port=port)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="twscrape-twitter-mcp", description="Read-optimized X (Twitter) MCP server.")
    sub = p.add_subparsers(dest="cmd", required=True)

    pl = sub.add_parser("login", help="Capture an existing signed-in X browser session.")
    login_mode = pl.add_mutually_exclusive_group()
    login_mode.add_argument(
        "--attach",
        action="store_true",
        help="Attach to a browser DevTools endpoint. This is the default.",
    )
    pl.add_argument(
        "--launch-browser",
        choices=["chrome", "brave"],
        help="Launch a dedicated browser profile with CDP enabled, then attach.",
    )
    pl.add_argument(
        "--cdp-url",
        default=settings.cdp_url,
        help=f"Browser DevTools endpoint (default: {settings.cdp_url}).",
    )
    login_mode.add_argument(
        "--fresh-browser",
        action="store_true",
        help="Fallback: open an automated browser login. X may block this.",
    )
    pl.set_defaults(func=_cmd_login)

    pi = sub.add_parser(
        "init",
        help="Manual/CI fallback: add a session from raw cookies (auth_token + ct0). "
        "Prefer `login` for interactive use.",
    )
    pi.add_argument("--username", help="Handle without @.")
    pi.add_argument("--auth-token", help="auth_token cookie value.")
    pi.add_argument("--ct0", help="ct0 cookie value.")
    pi.set_defaults(func=_cmd_init)

    pa = sub.add_parser("accounts", help="List sessions in the pool.")
    pa.set_defaults(func=_cmd_accounts)

    ps = sub.add_parser("smoke", help="Live check: read one public tweet end-to-end.")
    ps.add_argument("--url", help="Tweet URL/id to read (default: the first-ever tweet).")
    ps.set_defaults(func=_cmd_smoke)

    pv = sub.add_parser("serve", help="Run the MCP server.")
    pv.add_argument("--transport", choices=["stdio", "http"], default="stdio")
    pv.add_argument("--host", default="127.0.0.1")
    pv.add_argument("--port", type=int, default=0, help="Default: $PORT or 8080.")
    pv.add_argument(
        "--no-auto-login",
        action="store_true",
        help="Do not try CDP session capture on startup even if no session exists.",
    )
    pv.set_defaults(func=_cmd_serve)

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
