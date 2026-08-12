"""Unit tests for the two research-oriented MCP tools."""

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

server = pytest.importorskip("twscrape_twitter_mcp.server")


async def _items(values):
    for value in values:
        yield value


def _user(username="alice"):
    return SimpleNamespace(
        id=42,
        username=username,
        displayname="Alice Analyst",
        verified=False,
        blue=False,
        rawDescription="Public-markets notes and charts.",
        location="Toronto",
        created=datetime(2020, 1, 1, tzinfo=timezone.utc),
        followersCount=1_500,
        friendsCount=200,
        statusesCount=900,
        url=f"https://x.com/{username}",
    )


def _tweet(tid, text, *, date, with_photo=False):
    media = None
    if with_photo:
        photo = SimpleNamespace(url="https://pbs.twimg.com/media/chart.jpg")
        media = SimpleNamespace(photos=[photo], videos=[], animated=[])
    return SimpleNamespace(
        id=tid,
        user=_user(),
        rawContent=text,
        url=f"https://x.com/alice/status/{tid}",
        date=date,
        likeCount=0,
        retweetCount=0,
        replyCount=0,
        quoteCount=0,
        viewCount=0,
        quotedTweet=None,
        media=media,
        links=None,
    )


@pytest.mark.parametrize(
    "value,expected",
    [
        ("aapl", "AAPL"),
        ("$msft", "MSFT"),
        ("  brk.b ", "BRK.B"),
        ("btc-usd", "BTC-USD"),
    ],
)
def test_normalize_ticker(value, expected):
    assert server._normalize_ticker(value) == expected


@pytest.mark.parametrize("value", ["", "$", "AAPL OR MSFT", "AAPL -is:retweet", "A" * 16])
def test_normalize_ticker_rejects_search_injection(value):
    with pytest.raises(ValueError, match="ticker must contain"):
        server._normalize_ticker(value)


@pytest.mark.asyncio
async def test_research_x_account_combines_profile_posts_and_media(monkeypatch):
    older = _tweet(
        1,
        "older thesis",
        date=datetime(2026, 7, 1, tzinfo=timezone.utc),
    )
    newer = _tweet(
        2,
        "new chart",
        date=datetime(2026, 8, 1, tzinfo=timezone.utc),
        with_photo=True,
    )

    class FakeAPI:
        async def user_by_login(self, handle):
            assert handle == "alice"
            return _user(handle)

        def user_tweets(self, user_id, *, limit):
            assert (user_id, limit) == (42, 2)
            return _items([older, newer])

    monkeypatch.setattr(server, "get_api", FakeAPI)

    result = await server.research_x_account("@alice", limit=2)

    assert result.startswith("# X account research: @alice")
    assert "## Profile" in result
    assert "Public-markets notes and charts." in result
    assert "## Recent posts (2)" in result
    assert result.index("new chart") < result.index("older thesis")
    assert "https://pbs.twimg.com/media/chart.jpg" in result


@pytest.mark.asyncio
async def test_research_x_account_can_include_replies(monkeypatch):
    post = _tweet(1, "reply included", date=datetime(2026, 8, 1, tzinfo=timezone.utc))

    class FakeAPI:
        async def user_by_login(self, handle):
            return _user(handle)

        def user_tweets_and_replies(self, user_id, *, limit):
            assert (user_id, limit) == (42, 3)
            return _items([post])

    monkeypatch.setattr(server, "get_api", FakeAPI)

    result = await server.research_x_account("alice", limit=3, include_replies=True)

    assert "reply included" in result


@pytest.mark.asyncio
async def test_research_ticker_posts_builds_bounded_cashtag_search(monkeypatch):
    post = _tweet(
        3,
        "$AAPL margin chart",
        date=datetime(2026, 8, 1, tzinfo=timezone.utc),
        with_photo=True,
    )
    calls = []

    class FakeAPI:
        def search(self, query, *, limit, kv):
            calls.append((query, limit, kv))
            return _items([post])

    monkeypatch.setattr(server, "get_api", FakeAPI)

    result = await server.research_ticker_posts("$aapl", limit=12, product="Media")

    assert calls == [("$AAPL -is:retweet", 12, {"product": "Media"})]
    assert result.startswith("# X ticker research: $AAPL")
    assert "results: 1" in result
    assert "$AAPL margin chart" in result
    assert "https://pbs.twimg.com/media/chart.jpg" in result


@pytest.mark.asyncio
async def test_research_ticker_posts_can_include_retweets(monkeypatch):
    post = _tweet(4, "$TSLA", date=datetime(2026, 8, 1, tzinfo=timezone.utc))
    calls = []

    class FakeAPI:
        def search(self, query, *, limit, kv):
            calls.append(query)
            return _items([post])

    monkeypatch.setattr(server, "get_api", FakeAPI)

    await server.research_ticker_posts("tsla", include_retweets=True)

    assert calls == ["$TSLA"]


@pytest.mark.asyncio
async def test_research_ticker_posts_rejects_query_operators_before_api_access(monkeypatch):
    def fail_if_called():
        raise AssertionError("get_api should not run for invalid ticker input")

    monkeypatch.setattr(server, "get_api", fail_if_called)

    result = await server.research_ticker_posts("AAPL OR MSFT")

    assert result.is_error is True
    assert "ticker must contain" in result.content[0].text


@pytest.mark.asyncio
async def test_only_two_research_tools_are_registered():
    names = {tool.name for tool in await server.mcp.list_tools()}

    assert {name for name in names if name.startswith("research_")} == {
        "research_x_account",
        "research_ticker_posts",
    }
