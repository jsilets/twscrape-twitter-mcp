"""Tweet -> clean markdown.

This module is intentionally dependency-free (no twscrape import) so it is
trivially unit-testable and is the one part of the codebase that is *yours* to
shape for agent readability. All field access is defensive getattr so a model
change upstream degrades gracefully instead of crashing.
"""

from __future__ import annotations

from datetime import timezone
from typing import Any, Iterable


def _fmt_date(d: Any) -> str:
    if not d:
        return ""
    try:
        return d.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    except Exception:
        return str(d)


def _stats(t: Any) -> str:
    pairs = (
        ("likes", "likeCount"),
        ("RTs", "retweetCount"),
        ("replies", "replyCount"),
        ("quotes", "quoteCount"),
        ("views", "viewCount"),
    )
    parts = []
    for label, attr in pairs:
        v = getattr(t, attr, None)
        if v:
            parts.append(f"{v:,} {label}")
    return " · ".join(parts)


def _handle(t: Any) -> str:
    return getattr(getattr(t, "user", None), "username", None) or "unknown"


def _humanize_ms(ms: Any) -> str:
    """Milliseconds -> M:SS, or '' if not a usable number."""
    try:
        total = int(ms) // 1000
    except (TypeError, ValueError):
        return ""
    if total < 0:
        return ""
    return f"{total // 60}:{total % 60:02d}"


def _best_variant_url(video: Any) -> str:
    """Pick the highest-bitrate mp4 variant, else any variant with a url."""
    variants = getattr(video, "variants", None) or []
    best = None
    best_bitrate = -1
    fallback = ""
    for v in variants:
        url = getattr(v, "url", None)
        if not url:
            continue
        if not fallback:
            fallback = url
        if getattr(v, "contentType", None) == "video/mp4":
            bitrate = getattr(v, "bitrate", 0) or 0
            if bitrate > best_bitrate:
                best_bitrate = bitrate
                best = url
    return best or fallback


def _media_lines(t: Any) -> list[str]:
    media = getattr(t, "media", None)
    if not media:
        return []
    bullets: list[str] = []
    for photo in getattr(media, "photos", None) or []:
        url = getattr(photo, "url", None)
        if url:
            bullets.append(f"- Image: {url}")
    for video in getattr(media, "videos", None) or []:
        url = _best_variant_url(video)
        if not url:
            continue
        dur = _humanize_ms(getattr(video, "duration", None))
        label = f"Video ({dur})" if dur else "Video"
        bullets.append(f"- {label}: {url}")
    for gif in getattr(media, "animated", None) or []:
        url = getattr(gif, "videoUrl", None)
        if url:
            bullets.append(f"- GIF: {url}")
    if not bullets:
        return []
    return ["", "**Media:**", *bullets]


def _link_lines(t: Any) -> list[str]:
    links = getattr(t, "links", None)
    if not links:
        return []
    bullets: list[str] = []
    for link in links:
        url = getattr(link, "url", None)
        if not url:
            continue
        low = url.lower()
        if "/status/" in low or "pic.twitter.com" in low or "pbs.twimg.com" in low:
            continue
        text = (getattr(link, "text", None) or "").strip()
        if text and text != url:
            bullets.append(f"- [{text}]({url})")
        else:
            bullets.append(f"- {url}")
    if not bullets:
        return []
    return ["", "**Links:**", *bullets]


def tweet_to_md(t: Any, *, heading_level: int = 0) -> str:
    """Render one tweet as a markdown block."""
    user = getattr(t, "user", None)
    handle = getattr(user, "username", None) or "unknown"
    name = getattr(user, "displayname", None) or handle
    text = getattr(t, "rawContent", None) or getattr(t, "content", None) or ""
    url = getattr(t, "url", "") or ""
    date = _fmt_date(getattr(t, "date", None))

    head = "#" * heading_level + " " if heading_level else ""
    byline = f"{head}**{name}** (@{handle})"
    if date:
        byline += f" · {date}"

    lines = [byline, "", text.strip()]
    lines += _media_lines(t)
    lines += _link_lines(t)

    quoted = getattr(t, "quotedTweet", None)
    if quoted:
        q = tweet_to_md(quoted)
        lines += ["", "> " + q.replace("\n", "\n> ")]

    meta = " · ".join(x for x in (_stats(t), url) if x)
    if meta:
        lines += ["", f"_{meta}_"]

    return "\n".join(lines).strip()


def thread_to_md(root: Any, replies: Iterable[Any]) -> str:
    """Render a conversation: root post, the author's self-thread, then replies."""
    replies = list(replies or [])
    root_author = _handle(root)
    root_id = getattr(root, "id", None)
    replies = [r for r in replies if getattr(r, "id", None) != root_id]

    self_thread = [
        r
        for r in replies
        if _handle(r) == root_author
    ]
    others = [r for r in replies if r not in self_thread]

    out = ["## Thread", "", tweet_to_md(root)]

    if self_thread:
        out += ["", "### Continued by author"]
        for r in self_thread:
            out += ["", tweet_to_md(r)]

    if others:
        out += ["", f"### Replies ({len(others)})"]
        for r in others:
            out += ["", tweet_to_md(r), "", "---"]

    return "\n".join(out).strip()


def joined(tweets: Iterable[Any]) -> str:
    """Render a flat list of tweets separated by rules."""
    blocks = [tweet_to_md(t) for t in (tweets or [])]
    return "\n\n---\n\n".join(b for b in blocks if b)
