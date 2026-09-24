import logging
import re
from collections.abc import AsyncIterator
from datetime import datetime, timezone

import httpx

from criba.models.raw_post import RawPost
from criba.models.rate_limit import RateLimitConfig
from criba.models.plugin_base import SourcePlugin

logger = logging.getLogger(__name__)

HASHTAG_RE = re.compile(r"#(\w+)")
MENTION_RE = re.compile(r"@(\w+)")
USER_AGENT = "linux:criba-reddit-plugin:v0.1.0"

# A single 25-post page of /new silently misses everything published faster
# than the 120s poll interval on active subreddits; follow the "after" token
# instead, bounded so one busy subreddit cannot monopolize the run. Repeats
# are deduped downstream.
MAX_PAGES = 4
PAGE_LIMIT = 100


class RedditPlugin(SourcePlugin):

    def get_name(self) -> str:
        return "reddit"

    def get_config_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "subreddits": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of subreddit names to monitor",
                },
                "poll_interval": {
                    "type": "integer",
                    "default": 120,
                    "description": "Seconds between polling cycles",
                },
            },
            "required": ["subreddits"],
        }

    def get_rate_limits(self) -> RateLimitConfig:
        return RateLimitConfig(
            requests_per_minute=30,
            burst_size=2,
            cooldown_seconds=2.0,
        )

    def _submission_to_raw_post(self, sub: dict) -> RawPost:
        title = sub.get("title", "")
        body = sub.get("selftext", "")
        content = f"{title}\n\n{body}" if body else title

        author = sub.get("author") or "[deleted]"
        subreddit = sub.get("subreddit", "")
        permalink = sub.get("permalink", "")
        url = f"https://www.reddit.com{permalink}" if permalink else None
        source_id = sub.get("name") or sub.get("id", "")

        created_utc = sub.get("created_utc", 0)
        published_at = datetime.fromtimestamp(created_utc, tz=timezone.utc) if created_utc else datetime.now(timezone.utc)

        hashtags = HASHTAG_RE.findall(content)
        mentions = MENTION_RE.findall(content)

        return RawPost(
            source="reddit",
            source_id=source_id,
            author_id=author,
            author_handle=author,
            author_created_at=None,
            content=content,
            language=None,
            published_at=published_at,
            url=url,
            engagement={
                "score": sub.get("score", 0),
                "upvote_ratio": sub.get("upvote_ratio", 0),
                "num_comments": sub.get("num_comments", 0),
            },
            hashtags=hashtags,
            mentions=mentions,
            reply_to=None,
            raw_metadata={
                "subreddit": subreddit,
                "link_flair": sub.get("link_flair_text"),
                "is_self": sub.get("is_self", False),
                "over_18": sub.get("over_18", False),
            },
        )

    async def stream(self, config: dict) -> AsyncIterator[RawPost]:
        subreddits = config.get("channels", config.get("subreddits", []))
        if not subreddits:
            logger.warning("No subreddits configured")
            return

        async with httpx.AsyncClient(
            timeout=30.0,
            headers={"User-Agent": USER_AGENT},
        ) as client:
            for subreddit in subreddits:
                after: str | None = None
                for _ in range(MAX_PAGES):
                    url = f"https://www.reddit.com/r/{subreddit}/new.json"
                    params: dict = {"limit": PAGE_LIMIT, "raw_json": 1}
                    if after:
                        params["after"] = after
                    try:
                        logger.info("Fetching Reddit posts: r/%s", subreddit)
                        response = await client.get(url, params=params)
                        response.raise_for_status()

                        data = response.json()
                        listing = data.get("data", {})
                        children = listing.get("children", [])

                        for child in children:
                            if child.get("kind") == "t3":
                                yield self._submission_to_raw_post(child["data"])

                        after = listing.get("after")
                        if not after or not children:
                            break
                    except httpx.HTTPStatusError as exc:
                        if exc.response.status_code == 429:
                            logger.warning("Reddit rate limited for r/%s, backing off", subreddit)
                        else:
                            logger.error("Reddit HTTP error for r/%s: %s", subreddit, exc)
                        break
                    except Exception:
                        logger.exception("Error fetching Reddit posts from r/%s", subreddit)
                        break
