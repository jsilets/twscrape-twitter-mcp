"""Normalizing a handle. Imports server, which needs deps installed."""

import pytest

server = pytest.importorskip("twscrape_twitter_mcp.server")


@pytest.mark.parametrize(
    "value,expected",
    [
        ("handle", "handle"),
        ("@handle", "handle"),
        ("  @handle ", "handle"),
    ],
)
def test_normalize_handle(value, expected):
    assert server._normalize_handle(value) == expected
