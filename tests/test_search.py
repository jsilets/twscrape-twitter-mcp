"""Search must cap upstream batches at the requested result limit."""

from types import SimpleNamespace

import pytest

from twscrape_twitter_mcp import server


@pytest.mark.parametrize("product", ["Latest", "Top", "Media"])
@pytest.mark.parametrize("limit", [1, 2, 30, 100])
async def test_search_caps_upstream_batch(monkeypatch, limit, product):
    def search(query, *, limit, kv):
        assert query == "from:example"
        assert kv == {"product": product}

        async def batch():
            # twscrape can yield a whole page, including more than limit posts.
            for i in range(1, 121):
                yield SimpleNamespace(
                    user=SimpleNamespace(username="example", displayname="Example"),
                    rawContent=f"Post {i}",
                    url=f"https://x.com/example/status/{i}",
                )

        return batch()

    monkeypatch.setattr(server, "get_api", lambda: SimpleNamespace(search=search))
    tool = getattr(server.search, "fn", server.search)

    result = await tool("  from:example  ", limit=limit, product=product)

    expected = "\n\n---\n\n".join(
        f"**Example** (@example)\n\nPost {i}\n\n_https://x.com/example/status/{i}_"
        for i in range(1, limit + 1)
    )
    assert result == expected


async def test_search_empty_results(monkeypatch):
    async def search(*args, **kwargs):
        for tweet in ():
            yield tweet

    monkeypatch.setattr(server, "get_api", lambda: SimpleNamespace(search=search))
    tool = getattr(server.search, "fn", server.search)

    assert await tool("from:example", limit=1) == "No results."
