"""Unit tests for the markdown formatter. No network, no twscrape import."""

from datetime import datetime, timezone
from types import SimpleNamespace

from twscrape_twitter_mcp.formatters import joined, thread_to_md, tweet_to_md


def _user(username, displayname=None):
    return SimpleNamespace(username=username, displayname=displayname or username)


def _tweet(tid, handle, text, **kw):
    return SimpleNamespace(
        id=tid,
        user=_user(handle, kw.get("name")),
        rawContent=text,
        url=f"https://x.com/{handle}/status/{tid}",
        date=kw.get("date", datetime(2026, 6, 28, 12, 0, tzinfo=timezone.utc)),
        likeCount=kw.get("likeCount", 0),
        retweetCount=kw.get("retweetCount", 0),
        replyCount=kw.get("replyCount", 0),
        quoteCount=kw.get("quoteCount", 0),
        viewCount=kw.get("viewCount", 0),
        quotedTweet=kw.get("quotedTweet"),
        media=kw.get("media"),
        links=kw.get("links"),
    )


def test_tweet_to_md_basic():
    md = tweet_to_md(_tweet(1, "alice", "hello world", likeCount=5))
    assert "@alice" in md
    assert "hello world" in md
    assert "5 likes" in md
    assert "2026-06-28" in md


def test_tweet_to_md_handles_missing_fields():
    bare = SimpleNamespace()  # no attributes at all
    md = tweet_to_md(bare)
    assert "@unknown" in md  # degrades, does not raise


def test_quoted_tweet_is_nested_as_blockquote():
    q = _tweet(2, "bob", "quoted text")
    md = tweet_to_md(_tweet(3, "alice", "see this", quotedTweet=q))
    assert "> " in md
    assert "quoted text" in md


def test_thread_groups_author_selfthread_vs_replies():
    root = _tweet(10, "author", "1/ start")
    cont = _tweet(11, "author", "2/ more")
    reply = _tweet(12, "stranger", "nice thread")
    md = thread_to_md(root, [cont, reply])
    assert "Continued by author" in md
    assert "Replies (1)" in md
    assert "2/ more" in md
    assert "nice thread" in md


def test_thread_does_not_duplicate_root_from_conversation_results():
    root = _tweet(10, "author", "1/ start")
    reply = _tweet(12, "stranger", "nice thread")
    md = thread_to_md(root, [root, reply])
    assert md.count("1/ start") == 1
    assert "nice thread" in md


def test_joined_separates_with_rules():
    md = joined([_tweet(1, "a", "one"), _tweet(2, "b", "two")])
    assert "one" in md and "two" in md
    assert "---" in md


def test_photo_media_renders_url():
    photo = SimpleNamespace(url="https://pbs.twimg.com/media/pic.jpg")
    media = SimpleNamespace(photos=[photo], videos=[], animated=[])
    md = tweet_to_md(_tweet(1, "alice", "look", media=media))
    assert "**Media:**" in md
    assert "- Image: https://pbs.twimg.com/media/pic.jpg" in md


def test_video_picks_highest_bitrate_mp4_and_humanizes_duration():
    variants = [
        SimpleNamespace(contentType="application/x-mpegURL", bitrate=0, url="https://v/hls.m3u8"),
        SimpleNamespace(contentType="video/mp4", bitrate=256000, url="https://v/low.mp4"),
        SimpleNamespace(contentType="video/mp4", bitrate=2176000, url="https://v/high.mp4"),
    ]
    video = SimpleNamespace(
        thumbnailUrl="https://v/thumb.jpg", duration=32000, variants=variants
    )
    media = SimpleNamespace(photos=[], videos=[video], animated=[])
    md = tweet_to_md(_tweet(1, "alice", "clip", media=media))
    assert "- Video (0:32): https://v/high.mp4" in md
    assert "low.mp4" not in md


def test_video_falls_back_to_non_mp4_variant():
    variants = [
        SimpleNamespace(contentType="application/x-mpegURL", bitrate=0, url="https://v/hls.m3u8"),
    ]
    video = SimpleNamespace(thumbnailUrl="https://v/t.jpg", duration=None, variants=variants)
    media = SimpleNamespace(photos=[], videos=[video], animated=[])
    md = tweet_to_md(_tweet(1, "alice", "clip", media=media))
    assert "- Video: https://v/hls.m3u8" in md


def test_animated_gif_renders_video_url():
    gif = SimpleNamespace(thumbnailUrl="https://g/thumb.jpg", videoUrl="https://g/loop.mp4")
    media = SimpleNamespace(photos=[], videos=[], animated=[gif])
    md = tweet_to_md(_tweet(1, "alice", "haha", media=media))
    assert "- GIF: https://g/loop.mp4" in md


def test_links_render_and_filter_self_and_media_links():
    links = [
        SimpleNamespace(
            url="https://example.com/article",
            text="Great article",
            tcourl="https://t.co/abc",
        ),
        SimpleNamespace(
            url="https://x.com/alice/status/999",
            text="this tweet",
            tcourl="https://t.co/def",
        ),
        SimpleNamespace(
            url="https://pbs.twimg.com/media/pic.jpg",
            text="",
            tcourl="https://t.co/ghi",
        ),
    ]
    md = tweet_to_md(_tweet(1, "alice", "read this", links=links))
    assert "**Links:**" in md
    assert "- [Great article](https://example.com/article)" in md
    assert "/status/999" not in md
    assert "pbs.twimg.com" not in md


def test_bare_link_when_text_is_empty_or_equals_url():
    links = [SimpleNamespace(url="https://example.com", text="", tcourl="https://t.co/x")]
    md = tweet_to_md(_tweet(1, "alice", "x", links=links))
    assert "- https://example.com" in md
    assert "[" not in md.split("**Links:**", 1)[1]


def test_no_media_or_links_output_unchanged():
    md = tweet_to_md(_tweet(1, "alice", "plain tweet", likeCount=5))
    assert "**Media:**" not in md
    assert "**Links:**" not in md
