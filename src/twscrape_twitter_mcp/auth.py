"""Browser session capture for X auth.

The primary path is CDP attach: connect to a browser the user already launched
with a DevTools port, read its live X session, and add those cookies to
twscrape's account pool. That avoids automated fresh login, which X commonly
detects and may rate-limit.

The older launched-browser login is kept as an explicit fallback only.
Playwright imports are lazy so importing this module never requires the browser
to be present.
"""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from .config import settings
from .pool import add_account_from_cookies, get_api

LOGIN_URL = "https://x.com/i/flow/login"
DEFAULT_CDP_URL = "http://127.0.0.1:9222"
MAC_BROWSER_PATHS = {
    "chrome": "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "brave": "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
}


def storage_state_path() -> Path:
    settings.ensure_dirs()
    return settings.config_dir / "storage_state.json"


def managed_profile_dir() -> Path:
    settings.ensure_dirs()
    return settings.config_dir / "browser-profile"


def _cdp_port(cdp_url: str) -> int:
    parsed = urllib.parse.urlparse(cdp_url)
    return parsed.port or 9222


def _async_playwright():
    """Prefer patchright (stealth); fall back to vanilla playwright."""
    try:
        from patchright.async_api import async_playwright  # type: ignore

        return async_playwright
    except ImportError:
        from playwright.async_api import async_playwright

        return async_playwright


def _uid_key(cmap: dict[str, str]) -> str:
    """Stable pool key from the twid cookie (u=<userid>), so re-login dedupes."""
    twid = urllib.parse.unquote(cmap.get("twid", ""))
    if twid.startswith("u="):
        return f"uid_{twid[2:]}"
    return "session"


def _creds_from_storage_state() -> dict[str, str] | None:
    path = storage_state_path()
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
    except Exception:
        return None
    cmap = {c.get("name"): c.get("value") for c in data.get("cookies", [])}
    if cmap.get("auth_token") and cmap.get("ct0"):
        return cmap  # type: ignore[return-value]
    return None


def _account_field(info: Any, key: str, default: Any = None) -> Any:
    if isinstance(info, dict):
        return info.get(key, default)
    return getattr(info, key, default)


def _extract_creds(cookies: list[dict[str, Any]]) -> dict[str, str] | None:
    cmap = {
        c.get("name"): c.get("value")
        for c in cookies
        if c.get("name") and c.get("value")
    }
    if cmap.get("auth_token") and cmap.get("ct0"):
        return cmap  # type: ignore[return-value]
    return None


def _storage_state(cookies: list[dict[str, Any]]) -> dict[str, Any]:
    """Return the small subset of Playwright storage-state shape we need."""
    return {"cookies": cookies, "origins": []}


def _cdp_json(cdp_url: str, path: str) -> dict[str, Any]:
    url = cdp_url.rstrip("/") + path
    with urllib.request.urlopen(url, timeout=2) as response:
        return json.loads(response.read().decode("utf-8"))


async def _cdp_command(
    websocket_url: str, method: str, params: dict[str, Any] | None = None
) -> dict[str, Any]:
    import websockets

    async with websockets.connect(websocket_url, max_size=10 * 1024 * 1024) as ws:
        await ws.send(json.dumps({"id": 1, "method": method, "params": params or {}}))
        while True:
            message = json.loads(await ws.recv())
            if message.get("id") != 1:
                continue
            if "error" in message:
                raise RuntimeError(message["error"].get("message", str(message["error"])))
            return message.get("result", {})


async def _cookies_from_cdp(cdp_url: str) -> list[dict[str, Any]]:
    version = _cdp_json(cdp_url, "/json/version")
    browser_ws = version.get("webSocketDebuggerUrl")
    if not browser_ws:
        raise RuntimeError(f"No browser websocket URL exposed by {cdp_url}.")

    try:
        result = await _cdp_command(browser_ws, "Storage.getCookies")
    except Exception:
        result = await _cdp_command(browser_ws, "Network.getAllCookies")
    cookies = result.get("cookies") or []
    if not isinstance(cookies, list):
        return []
    return cookies


def _ensure_browser_installed() -> None:
    """First-run convenience: download Chromium if it isn't there yet."""
    try:
        subprocess.run(
            [sys.executable, "-m", "playwright", "install", "chromium"],
            check=True,
        )
    except Exception as e:  # pragma: no cover - best effort
        raise RuntimeError(
            "Could not auto-install the browser. Run manually:\n"
            "    python -m playwright install chromium"
        ) from e


def _browser_executable(name: str) -> str:
    if name in MAC_BROWSER_PATHS and Path(MAC_BROWSER_PATHS[name]).exists():
        return MAC_BROWSER_PATHS[name]
    for candidate in {
        "chrome": ("google-chrome", "chrome", "chromium"),
        "brave": ("brave-browser", "brave"),
    }.get(name, (name,)):
        try:
            path = subprocess.run(
                ["which", candidate],
                check=False,
                capture_output=True,
                text=True,
            ).stdout.strip()
        except Exception:
            path = ""
        if path:
            return path
    raise RuntimeError(
        f"Could not find {name!r}. Install it or use `twscrape-twitter-mcp login --attach` "
        "with a browser you launched yourself."
    )


def launch_managed_browser(browser_name: str, cdp_url: str | None = None) -> None:
    """Launch a dedicated browser profile with CDP enabled.

    This is a normal user-controlled browser, not a Playwright automation
    context. The profile lives under TWSCRAPE_TWITTER_MCP_HOME so the X login survives restarts
    without touching the user's daily browser profile.
    """
    endpoint = cdp_url or settings.cdp_url or DEFAULT_CDP_URL
    exe = _browser_executable(browser_name)
    profile = managed_profile_dir()
    profile.mkdir(parents=True, exist_ok=True)
    port = _cdp_port(endpoint)
    subprocess.Popen(
        [
            exe,
            f"--remote-debugging-port={port}",
            f"--user-data-dir={profile}",
            "--no-first-run",
            "--no-default-browser-check",
            "https://x.com/home",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


def wait_for_cdp(cdp_url: str, timeout_s: int = 20) -> None:
    end = time.monotonic() + timeout_s
    version_url = cdp_url.rstrip("/") + "/json/version"
    while time.monotonic() < end:
        try:
            with urllib.request.urlopen(version_url, timeout=1):
                return
        except Exception:
            time.sleep(0.25)
    raise RuntimeError(
        f"Timed out waiting for browser DevTools at {cdp_url}. "
        "Make sure no other browser is already using that port."
    )


async def attach_session(cdp_url: str | None = None) -> dict[str, str]:
    """Capture auth cookies from an already-running Chromium browser via CDP.

    The browser must have been started with a remote debugging port and already
    be signed in to X in one of its contexts.
    """
    endpoint = cdp_url or settings.cdp_url or DEFAULT_CDP_URL
    storage = storage_state_path()

    try:
        cookies = await _cookies_from_cdp(endpoint)
    except Exception as e:
        raise RuntimeError(
            f"Could not read cookies from browser DevTools at {endpoint}.\n"
            "Start a Chromium-family browser with --remote-debugging-port=9222, "
            "make sure it is signed in to x.com, then retry `twscrape-twitter-mcp login --attach`."
        ) from e

    creds = _extract_creds(cookies)
    if creds:
        storage.write_text(json.dumps(_storage_state(cookies), indent=2))
        return creds

    raise RuntimeError(
        "No X session cookies found in the attached browser. Open x.com in that "
        "browser, confirm you are signed in, then retry."
    )


async def wait_for_attached_session(
    cdp_url: str | None = None, timeout_s: int = 300
) -> dict[str, str]:
    endpoint = cdp_url or settings.cdp_url or DEFAULT_CDP_URL
    end = time.monotonic() + timeout_s
    last_error: Exception | None = None
    while time.monotonic() < end:
        try:
            return await attach_session(endpoint)
        except Exception as e:
            last_error = e
            await asyncio.sleep(1)
    raise TimeoutError(
        f"No X session appeared in the attached browser within {timeout_s}s. "
        "Confirm you completed sign-in at x.com."
    ) from last_error


async def interactive_login(timeout_s: int = 300, headed: bool = True) -> dict[str, str]:
    """Open a browser at X's login page and wait until a session exists.

    Returns the captured cookie map and persists storage state for silent reuse.
    """
    async_playwright = _async_playwright()
    storage = storage_state_path()

    async def _run() -> dict[str, str]:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=not headed)
            ctx_kwargs: dict[str, Any] = {}
            if storage.exists():
                ctx_kwargs["storage_state"] = str(storage)
            context = await browser.new_context(**ctx_kwargs)
            page = await context.new_page()
            await page.goto(LOGIN_URL)

            print(
                "A browser window opened. Sign in to X there; this will capture "
                "your session automatically.",
                file=sys.stderr,
            )

            creds: dict[str, str] | None = None
            end = time.monotonic() + timeout_s
            while time.monotonic() < end:
                cookies = await context.cookies("https://x.com")
                cmap = {c["name"]: c["value"] for c in cookies}
                if cmap.get("auth_token") and cmap.get("ct0"):
                    creds = cmap
                    break
                await page.wait_for_timeout(1000)

            if creds:
                await context.storage_state(path=str(storage))
            await browser.close()

            if not creds:
                raise TimeoutError(
                    f"Login not completed within {timeout_s}s. Re-run `twscrape-twitter-mcp login`."
                )
            return creds

    try:
        return await _run()
    except Exception as e:
        # The most common first-run failure is a missing browser binary.
        if "Executable doesn't exist" in str(e) or "playwright install" in str(e):
            _ensure_browser_installed()
            return await _run()
        if "TargetClosedError" in type(e).__name__ or "Target page, context or browser has been closed" in str(e):
            raise RuntimeError(
                "X closed the automated login browser. Use `twscrape-twitter-mcp login --attach` "
                "with an already signed-in browser instead."
            ) from e
        raise


async def has_active_session() -> bool:
    api = get_api()
    try:
        infos = await api.pool.accounts_info()
    except Exception:
        return False
    return any(bool(_account_field(i, "active")) for i in infos)


async def add_cookies_to_pool(cmap: dict[str, str]) -> str:
    return await add_account_from_cookies(
        username=_uid_key(cmap),
        auth_token=cmap["auth_token"],
        ct0=cmap["ct0"],
    )


async def ensure_session(open_browser: bool = True, force: bool = False) -> bool:
    """Make sure the pool has a usable session.

    Order of preference, all paste-free:
      1. An already-active account in the pool -> done silently.
      2. A persisted storage_state from a previous login -> reload silently.
      3. open_browser -> try CDP attach against the configured browser endpoint.

    Set open_browser=False on headless servers. This does not launch an automated
    login browser; use interactive_login only as an explicit fallback.
    """
    if not force and await has_active_session():
        return True

    if not force:
        cmap = _creds_from_storage_state()
        if cmap:
            await add_cookies_to_pool(cmap)
            if await has_active_session():
                return True

    if not open_browser:
        print(
            "No X session available.\n"
            "Authenticate locally with `twscrape-twitter-mcp login --attach`, then ship the resulting\n"
            f"{storage_state_path()} (or its cookies) to this host.",
            file=sys.stderr,
        )
        return False

    try:
        cmap = await attach_session()
    except Exception as e:
        print(
            "No X session available from the browser debug endpoint.\n"
            f"Tried: {settings.cdp_url}\n"
            "Start a signed-in Chromium browser with --remote-debugging-port=9222, "
            "then run `twscrape-twitter-mcp login --attach`.\n"
            f"Details: {e}",
            file=sys.stderr,
        )
        return False

    await add_cookies_to_pool(cmap)
    return await has_active_session()
