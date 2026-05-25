import logging
import re
from collections.abc import AsyncIterator
from datetime import datetime, timezone

from atproto import AsyncClient

from criba.models.raw_post import RawPost
from criba.models.rate_limit import RateLimitConfig
from criba.models.plugin_base import SourcePlugin

logger = logging.getLogger(__name__)

HASHTAG_RE = re.compile(r"#(\w+)")
MENTION_RE = re.compile(r"@(\w+)")


class BlueskyPlugin(SourcePlugin):

    def get_name(self) -> str:
        return "bluesky"

    def get_config_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "keywords": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of search terms to monitor",
                },
                "handles": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of Bluesky handles to fetch author feeds from (e.g. user.bsky.social)",
                },
                "poll_interval": {
                    "type": "integer",
                    "default": 120,
                    "description": "Seconds between polling cycles",
                },
            },
            "required": [],
        }

    def get_rate_limits(self) -> RateLimitConfig:
        return RateLimitConfig(
            requests_per_minute=30,
            burst_size=5,
            cooldown_seconds=2.0,
        )

    def _post_to_raw_post(self, post_view) -> RawPost:
        # Search returns PostView directly; author feed returns FeedViewPost (has .post)
        if hasattr(post_view, "post"):
            post = post_view.post
        else:
            post = post_view

        author = post.author
        record = post.record

        published_at = datetime.now(timezone.utc)
        if hasattr(record, "created_at") and record.created_at:
            try:
                published_at = datetime.fromisoformat(record.created_at.replace("Z", "+00:00"))
            except (ValueError, TypeError):
                pass

        author_created_at = None
        if hasattr(author, "created_at") and author.created_at:
            try:
                author_created_at = datetime.fromisoformat(author.created_at.replace("Z", "+00:00"))
            except (ValueError, TypeError):
                pass

        source_id = getattr(post, "uri", "")
        if not source_id and hasattr(post, "cid"):
            source_id = post.cid

        handle = getattr(author, "handle", "")
        url = None
        if source_id and handle:
            post_id = source_id.split("/")[-1]
            url = f"https://bsky.app/profile/{handle}/post/{post_id}"

        content = getattr(record, "text", "") or ""

        engagement = {
            "likes": getattr(post, "like_count", 0) or 0,
            "reposts": getattr(post, "repost_count", 0) or 0,
            "replies": getattr(post, "reply_count", 0) or 0,
        }

        hashtags = []
        mentions = []
        if hasattr(record, "facets") and record.facets:
            for facet in record.facets:
                if hasattr(facet, "features"):
                    for feature in facet.features:
                        if feature.py_type == "app.bsky.richtext.facet#tag":
                            tag = getattr(feature, "tag", None)
                            if tag:
                                hashtags.append(tag)
                        elif feature.py_type == "app.bsky.richtext.facet#mention":
                            did = getattr(feature, "did", None)
                            if did:
                                mentions.append(did)
        else:
            hashtags = HASHTAG_RE.findall(content)
            mentions = MENTION_RE.findall(content)

        reply_to = None
        if hasattr(record, "reply") and record.reply:
            reply_to = getattr(record.reply, "parent", None)
            if reply_to and hasattr(reply_to, "uri"):
                reply_to = reply_to.uri

        media_urls = []
        if hasattr(post, "embed") and post.embed:
            embed = post.post.embed
            if hasattr(embed, "images"):
                for image in getattr(embed, "images", []):
                    if hasattr(image, "fullsize"):
                        media_urls.append(getattr(image.fullsize, "ref", {}).get("$link", ""))
            elif hasattr(embed, "media"):
                media = getattr(embed, "media", [])
                for m in media:
                    if hasattr(m, "external"):
                        media_urls.append(getattr(m.external, "uri", ""))

        return RawPost(
            source="bluesky",
            source_id=source_id,
            author_id=getattr(author, "did", ""),
            author_handle=handle,
            author_created_at=author_created_at,
            content=content,
            language=None,
            published_at=published_at,
            url=url,
            engagement=engagement,
            hashtags=hashtags,
            mentions=mentions,
            reply_to=reply_to,
            media_urls=media_urls,
            raw_metadata={
                "cid": getattr(post, "cid", ""),
                "uri": source_id,
            },
        )

    async def stream(self, config: dict) -> AsyncIterator[RawPost]:
        keywords = config.get("keywords", [])
        handles = config.get("handles", [])

        if not keywords and not handles:
            logger.warning("No keywords or handles configured for Bluesky")
            return

        client = AsyncClient()

        for keyword in keywords:
            try:
                logger.info("Searching Bluesky for keyword: %s", keyword)
                response = await client.app.bsky.feed.search_posts(
                    params={"q": keyword, "limit": 50}
                )

                if hasattr(response, "posts") and response.posts:
                    for post in response.posts:
                        yield self._post_to_raw_post(post)

            except Exception:
                logger.exception("Error searching Bluesky for keyword: %s", keyword)

        for handle in handles:
            try:
                logger.info("Fetching Bluesky author feed: %s", handle)
                response = await client.app.bsky.feed.get_author_feed(
                    params={"actor": handle, "limit": 50}
                )

                if hasattr(response, "feed") and response.feed:
                    for post in response.feed:
                        yield self._post_to_raw_post(post)

            except Exception:
                logger.exception("Error fetching Bluesky author feed: %s", handle)