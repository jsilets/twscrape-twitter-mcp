"""X Article bodies: finding them in a TweetDetail response and rendering them."""

from types import SimpleNamespace

from twscrape_twitter_mcp import server
from twscrape_twitter_mcp.articles import find_article
from twscrape_twitter_mcp.formatters import article_to_md, tweet_to_md


def _block(text, btype="unstyled", styles=(), entities=()):
    return {
        "text": text,
        "type": btype,
        "inlineStyleRanges": [{"offset": o, "length": n, "style": s} for o, n, s in styles],
        "entityRanges": [{"key": k, "offset": o, "length": n} for k, o, n in entities],
    }


ARTICLE = {
    "title": "Shipping notes",
    "cover_media": {"media_info": {"original_img_url": "https://pbs.twimg.com/media/cover.jpg"}},
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


def test_article_to_md_falls_back_to_plain_text_then_preview():
    plain = {"title": "T", "plain_text": "full body", "preview_text": "short"}
    assert article_to_md(plain) == "## T\n\nfull body"

    preview_only = {"title": "T", "preview_text": "short"}
    assert article_to_md(preview_only) == (
        "## T\n\nshort\n\n_Preview only: X did not return the article body._"
    )


def test_tweet_to_md_places_article_after_post_text():
    tweet = SimpleNamespace(
        user=SimpleNamespace(username="a", displayname="A"),
        rawContent="https://t.co/x",
        url="https://x.com/a/status/1",
    )
    md = tweet_to_md(tweet, article={"title": "T", "plain_text": "body"})
    assert md == "**A** (@a)\n\nhttps://t.co/x\n\n## T\n\nbody\n\n_https://x.com/a/status/1_"


def test_find_article_matches_the_focal_tweet_only():
    focal = {"rest_id": "1", "article": {"article_results": {"result": {"title": "mine"}}}}
    quoted = {"rest_id": "2", "article": {"article_results": {"result": {"title": "quoted"}}}}
    response = {
        "data": {
            "entries": [
                {"tweet_results": {"result": {**focal, "quoted_status_result": {"result": quoted}}}}
            ]
        }
    }
    assert find_article(response, 1) == {"title": "mine"}
    assert find_article(response, 2) == {"title": "quoted"}
    assert find_article(response, 3) is None


async def test_read_tweet_includes_article_body(monkeypatch):
    tweet = SimpleNamespace(
        user=SimpleNamespace(username="a", displayname="A"),
        rawContent="https://t.co/x",
        url="https://x.com/a/status/9",
    )

    async def tweet_details(api, twid):
        assert twid == 9
        return tweet, {"title": "T", "plain_text": "body"}

    monkeypatch.setattr(server, "get_api", lambda: object())
    monkeypatch.setattr(server.articles, "tweet_details", tweet_details)
    tool = getattr(server.read_tweet, "fn", server.read_tweet)

    result = await tool("https://x.com/a/status/9")

    assert result == "**A** (@a)\n\nhttps://t.co/x\n\n## T\n\nbody\n\n_https://x.com/a/status/9_"
