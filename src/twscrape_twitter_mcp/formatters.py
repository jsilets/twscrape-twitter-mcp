"""Tweet -> clean markdown.

This module is intentionally dependency-free (no twscrape import) so it is
trivially unit-testable and is the one part of the codebase that is *yours* to
shape for agent readability. All field access is defensive getattr so a model
change upstream degrades gracefully instead of crashing.
"""

from __future__ import annotations

from datetime import timezone
from typing import Any, Iterable
from urllib.parse import urlparse


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
        host = (urlparse(url).hostname or "").lower()
        is_twitter = (
            host in ("x.com", "twitter.com")
            or host.endswith(".x.com")
            or host.endswith(".twitter.com")
        )
        is_media_host = "pic.twitter.com" in host or "pbs.twimg.com" in host
        if (is_twitter and "/status/" in url.lower()) or is_media_host:
            continue
        text = (getattr(link, "text", None) or "").strip()
        if text and text != url:
            bullets.append(f"- [{text}]({url})")
        else:
            bullets.append(f"- {url}")
    if not bullets:
        return []
    return ["", "**Links:**", *bullets]


def _entity_map(content_state: dict) -> dict[str, dict]:
    """X sends entityMap as a list of {key, value}; Draft.js uses {key: value}."""
    raw = content_state.get("entityMap") or {}
    if isinstance(raw, dict):
        return {str(k): v for k, v in raw.items() if isinstance(v, dict)}
    out: dict[str, dict] = {}
    for item in raw:
        if isinstance(item, dict) and isinstance(item.get("value"), dict):
            out[str(item.get("key"))] = item["value"]
    return out


def _utf16_slice(text: str, start: int, end: int) -> str:
    """Slice by UTF-16 code units, which is what Draft.js offsets count."""
    data = text.encode("utf-16-le")
    return data[start * 2 : end * 2].decode("utf-16-le", errors="ignore")


def _wrap(seg: str, bold: bool, italic: bool, url: str | None) -> str:
    """Apply markdown marks to a run, keeping edge whitespace outside the marks."""
    core = seg.strip()
    if not core:
        return seg
    lead = seg[: len(seg) - len(seg.lstrip())]
    trail = seg[len(seg.rstrip()) :]
    if url:
        core = f"[{core}]({url})"
    if italic:
        core = f"_{core}_"
    if bold:
        core = f"**{core}**"
    return f"{lead}{core}{trail}"


def _inline_md(block: dict, entities: dict[str, dict]) -> str:
    """Render one block's text with Bold/Italic style ranges and LINK entities."""
    text = block.get("text") or ""
    length = len(text.encode("utf-16-le")) // 2
    marks: list[tuple[int, int, str, str | None]] = []
    for r in block.get("inlineStyleRanges") or []:
        style = r.get("style")
        if style in ("Bold", "BOLD", "Italic", "ITALIC"):
            kind = "bold" if style.lower() == "bold" else "italic"
            marks.append((r.get("offset", 0), r.get("offset", 0) + r.get("length", 0), kind, None))
    for r in block.get("entityRanges") or []:
        ent = entities.get(str(r.get("key"))) or {}
        url = (ent.get("data") or {}).get("url")
        if ent.get("type") == "LINK" and url:
            marks.append((r.get("offset", 0), r.get("offset", 0) + r.get("length", 0), "link", url))
    if not marks:
        return text

    cuts = sorted({0, length, *(m[0] for m in marks), *(m[1] for m in marks)})
    runs: list[tuple[str, tuple[bool, bool, str | None]]] = []
    for a, b in zip(cuts, cuts[1:]):
        if not 0 <= a < b <= length:
            continue
        active = [m for m in marks if m[0] <= a and b <= m[1]]
        attrs = (
            any(m[2] == "bold" for m in active),
            any(m[2] == "italic" for m in active),
            next((m[3] for m in active if m[2] == "link"), None),
        )
        seg = _utf16_slice(text, a, b)
        if runs and runs[-1][1] == attrs:
            runs[-1] = (runs[-1][0] + seg, attrs)
        else:
            runs.append((seg, attrs))
    return "".join(_wrap(seg, *attrs) for seg, attrs in runs)


def _article_media(article: dict) -> dict[str, str]:
    """Map media_id -> markdown bullet for the Article's inline media."""
    out: dict[str, str] = {}
    for m in article.get("media_entities") or []:
        info = m.get("media_info") or {}
        mid = str(m.get("media_id") or "")
        if not mid:
            continue
        variants = [
            v for v in info.get("variants") or [] if v.get("content_type") == "video/mp4"
        ]
        if variants:
            best = max(variants, key=lambda v: v.get("bit_rate") or 0)
            dur = _humanize_ms(info.get("duration_millis"))
            label = f"Video ({dur})" if dur else "Video"
            out[mid] = f"- {label}: {best.get('url')}"
        elif info.get("original_img_url"):
            out[mid] = f"- Image: {info['original_img_url']}"
    return out


def _atomic_md(block: dict, entities: dict[str, dict], media: dict[str, str]) -> str:
    """Render an atomic block (inline media, embedded post, code, divider)."""
    lines: list[str] = []
    for r in block.get("entityRanges") or []:
        ent = entities.get(str(r.get("key"))) or {}
        kind = ent.get("type")
        data = ent.get("data") or {}
        if kind == "MEDIA":
            for item in data.get("mediaItems") or []:
                line = media.get(str(item.get("mediaId") or ""))
                if line:
                    lines.append(line)
        elif kind == "TWEET" and data.get("tweetId"):
            lines.append(f"- Embedded post: https://x.com/i/status/{data['tweetId']}")
        elif kind == "MARKDOWN" and data.get("markdown"):
            lines.append(str(data["markdown"]).strip())
        elif kind == "DIVIDER":
            lines.append("---")
        elif kind == "LINK" and data.get("url"):
            lines.append(f"- {data['url']}")
    return "\n".join(lines)


_BLOCK_PREFIX = {
    "header-one": "### ",
    "header-two": "#### ",
    "header-three": "##### ",
    "blockquote": "> ",
    "unordered-list-item": "- ",
    "ordered-list-item": "1. ",
}
_LIST_TYPES = ("unordered-list-item", "ordered-list-item")


def article_to_md(article: Any) -> str:
    """Render an X Article (raw `article_results.result` dict) as markdown.

    Uses the rich `content_state` blocks when present, then `plain_text`, then
    the short `preview_text` X sends when the field toggles are missing.
    """
    if not isinstance(article, dict):
        return ""
    title = (article.get("title") or "").strip()
    out: list[str] = [f"## {title}" if title else "## Article"]

    cover = ((article.get("cover_media") or {}).get("media_info") or {}).get("original_img_url")
    if cover:
        out += ["", f"Cover image: {cover}"]

    content_state = article.get("content_state") or {}
    blocks = content_state.get("blocks") or []
    if blocks:
        entities = _entity_map(content_state)
        media = _article_media(article)
        body = ""
        prev_type = None
        for block in blocks:
            btype = block.get("type") or "unstyled"
            if btype == "atomic":
                chunk = _atomic_md(block, entities, media)
            elif btype == "code-block":
                chunk = f"```\n{block.get('text') or ''}\n```"
            else:
                text = _inline_md(block, entities)
                chunk = _BLOCK_PREFIX.get(btype, "") + text if text.strip() else ""
            if not chunk:
                continue
            sep = "\n" if btype in _LIST_TYPES and prev_type == btype else "\n\n"
            body += (sep if body else "") + chunk
            prev_type = btype
        out += ["", body]
    else:
        text = (article.get("plain_text") or "").strip()
        if text:
            out += ["", text]
        else:
            preview = (article.get("preview_text") or "").strip()
            if preview:
                out += ["", preview, "", "_Preview only: X did not return the article body._"]

    return "\n".join(out).strip()


def tweet_to_md(t: Any, *, heading_level: int = 0, article: Any = None) -> str:
    """Render one tweet as a markdown block, with its X Article body when given."""
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
    if article:
        lines += ["", article_to_md(article)]
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


def _profile_stats(u: Any) -> str:
    pairs = (
        ("followers", "followersCount"),
        ("following", "friendsCount"),
        ("tweets", "statusesCount"),
    )
    parts = []
    for label, attr in pairs:
        v = getattr(u, attr, None)
        if v is not None:
            parts.append(f"{v:,} {label}")
    return " · ".join(parts)


def user_to_md(u: Any) -> str:
    """Render an X user's profile as a markdown block."""
    handle = getattr(u, "username", None) or "unknown"
    name = getattr(u, "displayname", None) or handle

    byline = f"**{name}** (@{handle})"
    if getattr(u, "verified", None) or getattr(u, "blue", None):
        byline += " · ✓"

    lines = [byline]

    bio = getattr(u, "rawDescription", None)
    if bio:
        lines += ["", bio.strip()]

    meta = []
    location = getattr(u, "location", None)
    if location:
        meta.append(f"📍 {location}")
    joined_date = _fmt_date(getattr(u, "created", None))
    if joined_date:
        meta.append(f"joined {joined_date}")
    if meta:
        lines += ["", " · ".join(meta)]

    stats = _profile_stats(u)
    if stats:
        lines += ["", f"_{stats}_"]

    url = getattr(u, "url", None)
    if url:
        lines += ["", url]

    return "\n".join(lines).strip()


def thread_to_md(root: Any, replies: Iterable[Any], *, root_article: Any = None) -> str:
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

    out = ["## Thread", "", tweet_to_md(root, article=root_article)]

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
