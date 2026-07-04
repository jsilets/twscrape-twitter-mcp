"""Unit tests for the user profile formatter. No network, no twscrape import."""

from datetime import datetime, timezone
from types import SimpleNamespace

from twscrape_twitter_mcp.formatters import user_to_md


def _full_user(**kw):
    return SimpleNamespace(
        username=kw.get("username", "alice"),
        displayname=kw.get("displayname", "Alice Example"),
        rawDescription=kw.get("rawDescription", "Builder of things. Coffee first."),
        location=kw.get("location", "San Francisco, CA"),
        created=kw.get("created", datetime(2009, 3, 21, 20, 50, tzinfo=timezone.utc)),
        followersCount=kw.get("followersCount", 12345),
        friendsCount=kw.get("friendsCount", 678),
        statusesCount=kw.get("statusesCount", 9001),
        verified=kw.get("verified", False),
        blue=kw.get("blue", False),
        url=kw.get("url", "https://x.com/alice"),
    )


def test_user_to_md_full_profile():
    md = user_to_md(_full_user())
    assert "**Alice Example**" in md
    assert "@alice" in md
    assert "Builder of things. Coffee first." in md
    assert "San Francisco, CA" in md
    assert "12,345 followers" in md
    assert "678 following" in md
    assert "9,001 tweets" in md
    assert "2009-03-21" in md
    assert "https://x.com/alice" in md


def test_user_to_md_verified_marker():
    assert "✓" in user_to_md(_full_user(verified=True))
    assert "✓" in user_to_md(_full_user(blue=True))
    assert "✓" not in user_to_md(_full_user())


def test_user_to_md_handles_missing_fields():
    bare = SimpleNamespace()  # no attributes at all
    md = user_to_md(bare)
    assert "@unknown" in md  # degrades, does not raise
