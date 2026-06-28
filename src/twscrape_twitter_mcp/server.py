"""FastMCP server: read-optimized tools shaped for "an agent reads this".

The tools return clean markdown, not raw GraphQL pages. Each tool degrades to a
plain explanatory string on miss/rate-limit rather than raising, so the agent
gets a usable signal instead of a stack trace.
"""

from __future__ import annotations

import re
from typing import Any

from fastmcp import FastMCP
from twscrape import gather

from .config import settings
from .formatters import joined, thread_to_md, tweet_to_md
from .pool import get_api

mcp = FastMCP("twscrape-twitter-mcp")

_ID_RE = re.compile(r"(?:status(?:es)?/)(\d+)")


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
async def login() -> str:
    """Capture an existing signed-in browser session via CDP.

    Use this if reads start failing with 'not accessible' and you have a browser
    running with --remote-debugging-port=9222.
    """
    from .auth import ensure_session

    ok = await ensure_session(open_browser=True, force=True)
    return "Session captured." if ok else "Session capture did not complete."


@mcp.tool
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
async def read_replies(url_or_id: str, limit: int = 50) -> str:
    """Read the replies to an X post as markdown."""
    api = get_api()
    replies = await _conversation(api, _parse_id(url_or_id), limit)
    if not replies:
        return "No replies found (or none accessible)."
    return joined(replies)


@mcp.tool
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
