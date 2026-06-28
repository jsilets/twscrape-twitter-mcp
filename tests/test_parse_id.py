"""Parsing tweet ids from URLs/ids. Imports server, which needs deps installed."""

import pytest

server = pytest.importorskip("twscrape_twitter_mcp.server")


@pytest.mark.parametrize(
    "value,expected",
    [
        ("https://x.com/markletree/status/2070969409230057947", 2070969409230057947),
        ("https://twitter.com/foo/status/20?s=20", 20),
        ("20", 20),
        ("https://x.com/i/web/status/12345", 12345),
    ],
)
def test_parse_id(value, expected):
    assert server._parse_id(value) == expected


def test_parse_id_rejects_garbage():
    with pytest.raises(ValueError):
        server._parse_id("https://x.com/markletree")


def test_conversation_id_prefers_root_id():
    class Tweet:
        conversationId = "99"

    assert server._conversation_id(Tweet(), 20) == 99


def test_conversation_id_falls_back_on_missing_or_bad_value():
    class Tweet:
        conversationId = "not-an-id"

    assert server._conversation_id(Tweet(), 20) == 20
