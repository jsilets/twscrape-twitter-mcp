"""FastMCP server: read-optimized tools shaped for "an agent reads this".

The tools return clean markdown, not raw GraphQL pages. Every read tool is wrapped
by `_guard`, which turns operational failures into a readable MCP tool error.
"""

from __future__ import annotations

import functools
import re
from typing import Annotated, Any, Awaitable, Callable, Literal
from urllib.parse import urlsplit

from fastmcp import FastMCP
from fastmcp.tools.tool import ToolResult
from pydantic import Field
from twscrape import gather

from . import __version__
from .config import settings
from .formatters import joined, thread_to_md, tweet_to_md, user_to_md
from .pool import get_api, list_accounts

mcp = FastMCP("twscrape-twitter-mcp", version=__version__, mask_error_details=True)

_ID_RE = re.compile(r"/status(?:es)?/(\d+)(?:/|$)")
_TWEET_HOSTS = {
    "m.twitter.com",
    "m.x.com",
    "mobile.twitter.com",
    "mobile.x.com",
    "twitter.com",
    "www.twitter.com",
    "www.x.com",
    "x.com",
}
_READ_ONLY_EXTERNAL = {"readOnlyHint": True, "openWorldHint": True}
_READ_ONLY_LOCAL = {"readOnlyHint": True, "openWorldHint": False}
_TweetRef = Annotated[str, Field(min_length=1, max_length=2_048)]
_Username = Annotated[str, Field(min_length=1, max_length=50)]
_Query = Annotated[str, Field(min_length=1, max_length=1_024)]
_Limit = Annotated[int, Field(ge=1, le=100)]


def _guard(
    fn: Callable[..., Awaitable[str]],
) -> Callable[..., Awaitable[str | ToolResult]]:
    """Wrap a tool so it never raises into the MCP transport.

    twscrape raises on operational failures (no account available, rate-limit,
    expired session, network), and bad input raises ValueError from `_parse_id`.
    A raised exception would reach the agent as an opaque error, so every tool
    funnels through here and returns readable markdown with `isError` set.
    """

    @functools.wraps(fn)
    async def wrapper(*args: Any, **kwargs: Any) -> str | ToolResult:
        try:
            return await fn(*args, **kwargs)
        except ValueError as e:
            return ToolResult(content=f"Invalid input: {e}", is_error=True)
        except Exception:
            return ToolResult(
                content=(
                    "The request could not be completed. The session may be rate-limited, "
                    "logged out, or no account is available. Run `twscrape-twitter-mcp accounts` "
                    "or call `auth_status` for the next step."
                ),
                is_error=True,
            )

    return wrapper


def _normalize_handle(username: str) -> str:
    """Strip surrounding whitespace and a single leading @ from a handle."""
    s = (username or "").strip()
    if s.startswith("@"):
        s = s[1:]
    if not s:
        raise ValueError("username must not be blank")
    return s


def _parse_id(url_or_id: str) -> int:
    s = (url_or_id or "").strip()
    if s.isdigit():
        tweet_id = int(s)
        if tweet_id > 0:
            return tweet_id

    parsed = urlsplit(s)
    if parsed.scheme not in {"http", "https"} or parsed.hostname not in _TWEET_HOSTS:
        raise ValueError(f"Could not parse a tweet id from: {url_or_id!r}")

    m = _ID_RE.search(parsed.path)
    if not m:
        raise ValueError(f"Could not parse a tweet id from: {url_or_id!r}")
    return int(m.group(1))


async def _conversation(api: Any, tid: int, limit: int) -> list[Any]:
    """Fetch replies/conversation for a tweet, robust across twscrape versions.

    Prefer the dedicated thread API; fall back to a conversation_id search if the
    method name shifts in a future twscrape release.
    """
    if hasattr(api, "tweet_replies"):
        try:
            res = await gather(api.tweet_replies(tid, limit=limit))
            if res:
                return _sorted_by_date(res)
        except Exception:
            pass
    res = await gather(
        api.search(f"conversation_id:{tid}", limit=limit, kv={"product": "Latest"})
    )
    return _sorted_by_date(res)


def _sorted_by_date(tweets: list[Any]) -> list[Any]:
    try:
        return sorted(tweets, key=lambda t: getattr(t, "date", None) or 0)
    except Exception:
        return tweets


def _conversation_id(tweet: Any, fallback: int) -> int:
    """Return the root conversation id when twscrape exposes it."""
    for attr in ("conversationId", "conversation_id"):
        value = getattr(tweet, attr, None)
        if value:
            try:
                return int(value)
            except (TypeError, ValueError):
                pass
    return fallback


@mcp.tool(annotations=_READ_ONLY_LOCAL)
@_guard
async def auth_status() -> str:
    """Check whether this server has an active X session, without exposing cookies."""
    rows = await list_accounts()
    # Count `active` only. twscrape's `logged_in` flag tracks its password login
    # flow; BYO-cookie sessions stay logged_in=False yet read fine, and the pool
    # dispatches reads on `active`. Gating on logged_in reported a live session as
    # "no session" (matches has_active_session, which also checks active alone).
    active = sum(1 for row in rows if row["active"])
    if active:
        return f"X session ready: {active} active account(s) in the local pool."
    return (
        "No active X session. On the server host, run "
        "`twscrape-twitter-mcp login --launch-browser chrome` or `twscrape-twitter-mcp init`."
    )


@mcp.tool(annotations=_READ_ONLY_EXTERNAL)
@_guard
async def read_tweet(url_or_id: _TweetRef) -> str:
    """Read a single X post by URL or numeric id. Returns clean markdown."""
    api = get_api()
    t = await api.tweet_details(_parse_id(url_or_id))
    if not t:
        return (
            "Tweet not found or not accessible. It may be deleted, protected, or "
            "the session is rate-limited / logged out. Try `twscrape-twitter-mcp accounts` to check."
        )
    return tweet_to_md(t)


@mcp.tool(annotations=_READ_ONLY_EXTERNAL)
@_guard
async def user_profile(username: _Username) -> str:
    """Read an X user's profile by handle. Returns clean markdown.

    Pass the handle with or without a leading @.
    """
    api = get_api()
    handle = _normalize_handle(username)
    user = await api.user_by_login(handle)
    if not user:
        return (
            "User not found or not accessible (may be suspended, protected, or the "
            "session is rate-limited / logged out)."
        )
    return user_to_md(user)


@mcp.tool(annotations=_READ_ONLY_EXTERNAL)
@_guard
async def read_thread(
    url_or_id: _TweetRef,
    max_replies: _Limit = 50,
    include_replies: bool = True,
) -> str:
    """Read a full X thread as markdown: the root post, the author's self-thread,
    and top replies. Pass any tweet in the thread."""
    api = get_api()
    tid = _parse_id(url_or_id)
    root = await api.tweet_details(tid)
    if not root:
        return "Tweet not found or not accessible."
    conversation_id = _conversation_id(root, tid)
    if conversation_id != tid:
        root = await api.tweet_details(conversation_id) or root
    replies: list[Any] = []
    if include_replies:
        replies = await _conversation(api, conversation_id, max_replies)
    return thread_to_md(root, replies)


@mcp.tool(annotations=_READ_ONLY_EXTERNAL)
@_guard
async def read_replies(url_or_id: _TweetRef, limit: _Limit = 50) -> str:
    """Read the replies to an X post as markdown."""
    api = get_api()
    replies = await _conversation(api, _parse_id(url_or_id), limit)
    if not replies:
        return "No replies found (or none accessible)."
    return joined(replies)


@mcp.tool(annotations=_READ_ONLY_EXTERNAL)
@_guard
async def read_quotes(url_or_id: _TweetRef, limit: _Limit = 30) -> str:
    """Read quote-tweets of an X post (best-effort, via search:quoted_tweet_id).
    Coverage is partial, X does not expose a complete quotes endpoint."""
    api = get_api()
    tid = _parse_id(url_or_id)
    res = await gather(
        api.search(f"quoted_tweet_id:{tid}", limit=limit, kv={"product": "Latest"})
    )
    if not res:
        return "No quote tweets found (search-based; results may be incomplete)."
    return joined(res)


@mcp.tool(annotations=_READ_ONLY_EXTERNAL)
@_guard
async def user_timeline(
    username: _Username,
    limit: _Limit = settings.default_limit,
    include_replies: bool = False,
) -> str:
    """Read a user's recent posts as markdown, newest first.

    Pass the handle with or without a leading @. Set include_replies=True to
    include the user's replies alongside their standalone posts.
    """
    api = get_api()
    handle = _normalize_handle(username)
    user = await api.user_by_login(handle)
    if not user:
        return (
            "User not found or not accessible (may be suspended, protected, or the "
            "session is rate-limited / logged out)."
        )
    gen = api.user_tweets_and_replies if include_replies else api.user_tweets
    res = await gather(gen(user.id, limit=limit))
    if not res:
        return "No posts found (or none accessible)."
    return joined(_sorted_by_date(res)[::-1])


@mcp.tool(annotations=_READ_ONLY_EXTERNAL)
@_guard
async def search(
    query: _Query,
    limit: _Limit = settings.default_limit,
    product: Literal["Latest", "Top", "Media"] = "Latest",
) -> str:
    """Search X and return matching posts as markdown.

    product: "Latest" | "Top" | "Media". Supports X operators, e.g.
    from:user, to:user, has:media, -is:retweet, min_faves:100, since:2026-01-01.
    """
    api = get_api()
    query = query.strip()
    if not query:
        raise ValueError("query must not be blank")
    res = await gather(api.search(query, limit=limit, kv={"product": product}))
    if not res:
        return "No results."
    return joined(res)
