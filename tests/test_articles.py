"""X Article bodies: twscrape parses `tweet.article`, the formatter renders it."""

from types import SimpleNamespace

from twscrape.models import Article

from twscrape_twitter_mcp import server
from twscrape_twitter_mcp.formatters import article_to_md, tweet_to_md


def _block(text, btype="unstyled", styles=(), entities=()):
    return {
        "text": text,
        "type": btype,
        "inlineStyleRanges": [{"offset": o, "length": n, "style": s} for o, n, s in styles],
        "entityRanges": [{"key": k, "offset": o, "length": n} for k, o, n in entities],
    }


def _article(result):
    """Parse a raw `article_results.result` dict the way twscrape does for a tweet."""
    return Article.parse({"article": {"article_results": {"result": {"rest_id": "5", **result}}}})


ARTICLE = _article(
    {
        "title": "Shipping notes",
        "cover_media": {
            "media_info": {"original_img_url": "https://pbs.twimg.com/media/cover.jpg"}
        },
        "preview_text": "short preview",
        "content_state": {
            "blocks": [
                _block("Intro paragraph."),
                _block("Section", "header-two"),
                # "🚀 " is 3 UTF-16 code units, so "bold" starts at offset 3.
                _block("🚀 bold then link here", styles=[(3, 4, "Bold")], entities=[(1, 13, 4)]),
                _block("first", "unordered-list-item"),
                _block("second", "unordered-list-item"),
                _block(" ", "atomic", entities=[(0, 0, 1)]),
                _block(" ", "atomic", entities=[(2, 0, 1)]),
            ],
            "entityMap": [
                {
                    "key": "0",
                    "value": {"type": "MEDIA", "data": {"mediaItems": [{"mediaId": "77"}]}},
                },
                {"key": "1", "value": {"type": "LINK", "data": {"url": "https://example.com"}}},
                {"key": "2", "value": {"type": "TWEET", "data": {"tweetId": "123"}}},
            ],
        },
        "media_entities": [
            {
                "media_id": "77",
                "media_info": {
                    "duration_millis": 46966,
                    "variants": [
                        {"content_type": "video/mp4", "bit_rate": 100, "url": "https://v/low.mp4"},
                        {"content_type": "video/mp4", "bit_rate": 900, "url": "https://v/high.mp4"},
                        {"content_type": "application/x-mpegURL", "url": "https://v/pl.m3u8"},
                    ],
                },
            }
        ],
    }
)


def test_article_to_md_renders_rich_body():
    assert article_to_md(ARTICLE) == (
        "## Shipping notes\n"
        "\n"
        "Cover image: https://pbs.twimg.com/media/cover.jpg\n"
        "\n"
        "Intro paragraph.\n"
        "\n"
        "#### Section\n"
        "\n"
        "🚀 **bold** then [link](https://example.com) here\n"
        "\n"
        "- first\n"
        "- second\n"
        "\n"
        "- Video (0:46): https://v/high.mp4\n"
        "\n"
        "- Embedded post: https://x.com/i/status/123"
    )


def test_article_to_md_falls_back_to_preview():
    assert article_to_md(_article({"title": "T", "preview_text": "short"})) == (
        "## T\n\nshort\n\n_Preview only: X did not return the article body._"
    )


def _tweet(article, tid=1):
    return SimpleNamespace(
        user=SimpleNamespace(username="a", displayname="A"),
        rawContent="https://t.co/x",
        url=f"https://x.com/a/status/{tid}",
        article=article,
    )


def test_tweet_to_md_places_article_after_post_text():
    md = tweet_to_md(_tweet(_article({"title": "T", "preview_text": "body"})))
    assert md == (
        "**A** (@a)\n\nhttps://t.co/x\n\n## T\n\nbody\n\n"
        "_Preview only: X did not return the article body._\n\n_https://x.com/a/status/1_"
    )


async def test_read_tweet_includes_article_body(monkeypatch):
    tweet = _tweet(_article({"title": "T", "preview_text": "body"}), tid=9)

    class Api:
        async def tweet_details(self, twid):
            assert twid == 9
            return tweet

    monkeypatch.setattr(server, "get_api", lambda: Api())
    tool = getattr(server.read_tweet, "fn", server.read_tweet)

    result = await tool("https://x.com/a/status/9")

    assert result == (
        "**A** (@a)\n\nhttps://t.co/x\n\n## T\n\nbody\n\n"
        "_Preview only: X did not return the article body._\n\n_https://x.com/a/status/9_"
    )
