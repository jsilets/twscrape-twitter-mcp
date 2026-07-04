"""FastMCP server: read-optimized tools shaped for "an agent reads this".

The tools return clean markdown, not raw GraphQL pages. Every tool is wrapped by
`_guard`, which turns any failure (bad input, rate-limit, expired session, no
account available, network error) into a plain explanatory string. That keeps the
MCP contract: the agent gets a usable signal instead of an opaque protocol error.
"""

from __future__ import annotations

import functools
import re
from typing import Any, Awaitable, Callable

from fastmcp import FastMCP
from twscrape import gather

from .config import settings
from .formatters import joined, thread_to_md, tweet_to_md, user_to_md
from .pool import get_api

mcp = FastMCP("twscrape-twitter-mcp")

_ID_RE = re.compile(r"(?:status(?:es)?/)(\d+)")


def _guard(fn: Callable[..., Awaitable[str]]) -> Callable[..., Awaitable[str]]:
    """Wrap a tool so it always returns a string and never raises.

    twscrape raises on operational failures (no account available, rate-limit,
    expired session, network), and bad input raises ValueError from `_parse_id`.
    A raised exception would reach the agent as an opaque error, so every tool
    funnels through here and degrades to readable markdown instead.
    """

    @functools.wraps(fn)
    async def wrapper(*args: Any, **kwargs: Any) -> str:
        try:
            return await fn(*args, **kwargs)
        except ValueError as e:
            return f"Invalid input: {e}"
        except Exception:
            return (
                "The request could not be completed. The session may be rate-limited, "
                "logged out, or no account is available. Try `twscrape-twitter-mcp accounts`."
            )

    return wrapper


def _normalize_handle(username: str) -> str:
    """Strip surrounding whitespace and a single leading @ from a handle."""
    s = (username or "").strip()
    if s.startswith("@"):
        s = s[1:]
    return s


def _parse_id(url_or_id: str) -> int:
    s = (url_or_id or "").strip()
    if s.isdigit():
        return int(s)
    m = _ID_RE.search(s)
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


@mcp.tool
@_guard
async def login() -> str:
    """Capture an existing signed-in browser session via CDP.

    Use this if reads start failing with 'not accessible' and you have a browser
    running with --remote-debugging-port=9222.
    """
    from .auth import ensure_session

    ok = await ensure_session(open_browser=True, force=True)
    return "Session captured." if ok else "Session capture did not complete."


@mcp.tool
@_guard
async def read_tweet(url_or_id: str) -> str:
    """Read a single X post by URL or numeric id. Returns clean markdown."""
    api = get_api()
    t = await api.tweet_details(_parse_id(url_or_id))
    if not t:
        return (
            "Tweet not found or not accessible. It may be deleted, protected, or "
            "the session is rate-limited / logged out. Try `twscrape-twitter-mcp accounts` to check."
        )
    return tweet_to_md(t)


@mcp.tool
@_guard
async def user_profile(username: str) -> str:
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


@mcp.tool
@_guard
async def read_thread(
    url_or_id: str, max_replies: int = 50, include_replies: bool = True
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


@mcp.tool
@_guard
async def read_replies(url_or_id: str, limit: int = 50) -> str:
    """Read the replies to an X post as markdown."""
    api = get_api()
    replies = await _conversation(api, _parse_id(url_or_id), limit)
    if not replies:
        return "No replies found (or none accessible)."
    return joined(replies)


@mcp.tool
@_guard
async def read_quotes(url_or_id: str, limit: int = 30) -> str:
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


@mcp.tool
@_guard
async def user_timeline(
    username: str, limit: int = 40, include_replies: bool = False
) -> str:
    """Read a user's recent posts as markdown, newest first.

    Pass the handle with or without a leading @. Set include_replies=True to
    include the user's replies alongside their standalone posts.
    """
    api = get_api()
    limit = limit or settings.default_limit
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


@mcp.tool
@_guard
async def search(query: str, limit: int = 20, product: str = "Latest") -> str:
    """Search X and return matching posts as markdown.

    product: "Latest" | "Top" | "Media". Supports X operators, e.g.
    from:user, to:user, has:media, -is:retweet, min_faves:100, since:2026-01-01.
    """
    api = get_api()
    limit = limit or settings.default_limit
    res = await gather(api.search(query, limit=limit, kv={"product": product}))
    if not res:
        return "No results."
    return joined(res)
