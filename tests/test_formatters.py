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
