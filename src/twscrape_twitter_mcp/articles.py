"""TweetDetail fetch that also returns the body of an X Article.

X sends an Article's body (`content_state`) only when the TweetDetail request
sets the `withArticleRichContentState` field toggle. twscrape 0.20.1 sends no
field toggles on TweetDetail and has no Article model, so a plain
`api.tweet_details` call returns only the post's t.co link. This module sends
the same request as `api.tweet_details_raw` plus the toggles, then parses the
tweet with twscrape and returns the raw Article dict next to it.

Remove this module when the twscrape pin includes vladkens/twscrape#323 (merged
on main after v0.20.1): that release sends the toggles and parses `tweet.article`.
"""

from __future__ import annotations

from typing import Any

from twscrape.api import GQL_FEATURES, GQL_URL, OP_TweetDetail
from twscrape.models import parse_tweet
from twscrape.queue_client import QueueClient
from twscrape.utils import encode_params

ARTICLE_FIELD_TOGGLES = {
    "withArticleRichContentState": True,
    "withArticlePlainText": True,
}


async def tweet_details(api: Any, twid: int) -> tuple[Any | None, dict | None]:
    """Return (Tweet, Article dict) for one post. Either value can be None."""
    kv = {
        "focalTweetId": str(twid),
        "with_rux_injections": True,
        "includePromotedContent": True,
        "withCommunity": True,
        "withQuickPromoteEligibilityTweetFields": True,
        "withBirdwatchNotes": True,
        "withVoice": True,
        "withV2Timeline": True,
    }
    params = {
        "variables": kv,
        "features": GQL_FEATURES,
        "fieldToggles": ARTICLE_FIELD_TOGGLES,
    }
    queue = OP_TweetDetail.split("/")[-1]
    async with QueueClient(api.pool, queue, api.debug, proxy=api.proxy) as client:
        rep = await client.get(f"{GQL_URL}/{OP_TweetDetail}", params=encode_params(params))
    if rep is None:
        return None, None
    tweet = parse_tweet(rep, twid)
    try:
        article = find_article(rep.json(), twid)
    except Exception:
        article = None
    return tweet, article


def find_article(obj: Any, twid: int) -> dict | None:
    """Find the Article result attached to tweet `twid` in a TweetDetail response.

    Matches on rest_id so an Article on a quoted or replied-to post is not used.
    """
    stack = [obj]
    target = str(twid)
    while stack:
        cur = stack.pop()
        if isinstance(cur, dict):
            if cur.get("rest_id") == target and isinstance(cur.get("article"), dict):
                result = cur["article"].get("article_results", {}).get("result")
                if isinstance(result, dict):
                    return result
            stack.extend(cur.values())
        elif isinstance(cur, list):
            stack.extend(cur)
    return None
