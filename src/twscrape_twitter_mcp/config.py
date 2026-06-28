"""Environment-driven configuration.

Everything is overridable by env var so the same image runs locally (stdio) or
on Fly/Railway (HTTP) without code changes.
"""

from __future__ import annotations

import os
from pathlib import Path

APP_NAME = "twscrape-twitter-mcp"


def _default_config_dir() -> Path:
    xdg = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg) if xdg else Path.home() / ".config"
    return base / APP_NAME


def _env(name: str) -> str | None:
    return os.environ.get(name)


class Settings:
    def __init__(self) -> None:
        # TWSCRAPE_TWITTER_MCP_HOME holds the twscrape sqlite account pool. On Fly/Railway
        # point this at a mounted volume so sessions survive restarts.
        self.config_dir = Path(_env("TWSCRAPE_TWITTER_MCP_HOME") or str(_default_config_dir()))
        self.db_path = Path(
            _env("TWSCRAPE_TWITTER_MCP_DB") or str(self.config_dir / "accounts.db")
        )
        self.default_limit = int(_env("TWSCRAPE_TWITTER_MCP_DEFAULT_LIMIT") or "40")

        # When serving over HTTP, require this bearer token. Leave unset only for
        # stdio / trusted-private-network use.
        self.http_auth_token = _env("TWSCRAPE_TWITTER_MCP_AUTH_TOKEN") or None

        # Optional global proxy applied to every account in the pool.
        self.proxy = _env("TWSCRAPE_TWITTER_MCP_PROXY") or None

        # Browser DevTools endpoint used by `twscrape-twitter-mcp login --attach`.
        self.cdp_url = _env("TWSCRAPE_TWITTER_MCP_CDP_URL") or "http://127.0.0.1:9222"

        # Railway injects PORT; Fly uses internal_port. Default 8080.
        self.port = int(os.environ.get("PORT", "8080"))

    def ensure_dirs(self) -> None:
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)


settings = Settings()
