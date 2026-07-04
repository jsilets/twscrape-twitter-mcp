"""The _guard decorator: tools return a string, never raise. Imports server."""

import asyncio
import inspect

import pytest

server = pytest.importorskip("twscrape_twitter_mcp.server")


def test_guard_passes_through_return_value():
    @server._guard
    async def ok(x):
        return f"got {x}"

    assert asyncio.run(ok("hi")) == "got hi"


def test_guard_turns_value_error_into_string():
    @server._guard
    async def boom():
        raise ValueError("bad id")

    out = asyncio.run(boom())
    assert isinstance(out, str)
    assert "Invalid input" in out
    assert "bad id" in out


def test_guard_turns_any_exception_into_string():
    @server._guard
    async def boom():
        raise RuntimeError("no account available")

    out = asyncio.run(boom())
    assert isinstance(out, str)
    assert "could not be completed" in out
    # The raw exception text must not leak to the agent.
    assert "no account available" not in out


def test_guard_preserves_name_and_signature():
    # FastMCP builds the tool schema from the wrapped function's signature, so
    # functools.wraps must keep name and parameters intact through the decorator.
    @server._guard
    async def sample(url_or_id: str, limit: int = 50) -> str:
        return url_or_id

    assert sample.__name__ == "sample"
    params = list(inspect.signature(sample).parameters)
    assert params == ["url_or_id", "limit"]
