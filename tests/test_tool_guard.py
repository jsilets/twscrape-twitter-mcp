"""The _guard decorator: tools return readable MCP errors, never raise."""

import asyncio
import inspect

import pytest

server = pytest.importorskip("twscrape_twitter_mcp.server")


def test_guard_passes_through_return_value():
    @server._guard
    async def ok(x):
        return f"got {x}"

    assert asyncio.run(ok("hi")) == "got hi"


def test_guard_turns_value_error_into_mcp_error():
    @server._guard
    async def boom():
        raise ValueError("bad id")

    out = asyncio.run(boom())
    assert out.is_error is True
    assert out.content[0].text == "Invalid input: bad id"


def test_guard_turns_any_exception_into_masked_mcp_error():
    @server._guard
    async def boom():
        raise RuntimeError("no account available")

    out = asyncio.run(boom())
    assert out.is_error is True
    assert "could not be completed" in out.content[0].text
    # The raw exception text must not leak to the agent.
    assert "no account available" not in out.content[0].text


def test_guard_preserves_name_and_signature():
    # FastMCP builds the tool schema from the wrapped function's signature, so
    # functools.wraps must keep name and parameters intact through the decorator.
    @server._guard
    async def sample(url_or_id: str, limit: int = 50) -> str:
        return url_or_id

    assert sample.__name__ == "sample"
    params = list(inspect.signature(sample).parameters)
    assert params == ["url_or_id", "limit"]
