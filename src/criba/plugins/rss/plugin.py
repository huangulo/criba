import logging
import re
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import feedparser
import httpx

from criba.models.raw_post import RawPost
from criba.models.rate_limit import RateLimitConfig
from criba.models.plugin_base import SourcePlugin

logger = logging.getLogger(__name__)

HASHTAG_RE = re.compile(r"#(\w+)")
MENTION_RE = re.compile(r"@(\w+)")
HTML_TAG_RE = re.compile(r"<[^>]+>")


def _strip_html(text: str) -> str:
    """Remove HTML tags and decode basic entities."""
    text = HTML_TAG_RE.sub("", text)
    text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    text = text.replace("&nbsp;", " ").replace("&#39;", "'").replace("&quot;", '"')
    return text.strip()


def _parse_date(entry) -> datetime | None:
    """Parse publication date from RSS entry."""
    for field in ("published", "updated", "created"):
        value = getattr(entry, field, None)
        if value:
            try:
                if isinstance(value, str):
                    return parsedate_to_datetime(value)
                elif hasattr(value, "timetuple"):
                    return datetime(*value.timetuple()[:6], tzinfo=timezone.utc)
            except (ValueError, TypeError):
                continue
    return None


class RSSPlugin(SourcePlugin):

    def get_name(self) -> str:
        return "rss"

    def get_config_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "feeds": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "url": {"type": "string", "format": "uri"},
                        },
                        "required": ["name", "url"],
                    },
                    "description": "List of RSS/Atom feeds to monitor",
                },
                "poll_interval": {
                    "type": "integer",
                    "default": 300,
                    "description": "Seconds between polling cycles",
                },
            },
            "required": ["feeds"],
        }

    def get_rate_limits(self) -> RateLimitConfig:
        return RateLimitConfig(
            requests_per_minute=30,
            burst_size=5,
            cooldown_seconds=2.0,
        )

    def _entry_to_raw_post(self, entry, feed_name: str) -> RawPost:
        """Convert a feedparser entry to a RawPost."""
        # Get content (prefer full content, fall back to summary)
        content = ""
        if hasattr(entry, "content") and entry.content:
            content = entry.content[0].get("value", "")
        elif hasattr(entry, "summary"):
            content = entry.summary
        elif hasattr(entry, "description"):
            content = entry.description

        content = _strip_html(content)

        # Extract title and prepend to content
        title = getattr(entry, "title", "")
        if title and title not in content:
            content = f"{title}\n\n{content}"

        # Parse author
        author = getattr(entry, "author", "") or feed_name

        # Parse date
        published_at = _parse_date(entry) or datetime.now(timezone.utc)

        # Extract link
        url = getattr(entry, "link", None)

        # Build engagement from feed metadata (if available)
        engagement = {}

        # Extract hashtags and mentions from content
        hashtags = HASHTAG_RE.findall(content)
        mentions = MENTION_RE.findall(content)

        # Generate stable source_id from entry id or link
        source_id = getattr(entry, "id", "") or url or ""

        return RawPost(
            source="rss",
            source_id=source_id,
            author_id=feed_name,
            author_handle=author,
            author_created_at=None,
            content=content,
            language=None,  # detected by heuristics
            published_at=published_at,
            url=url,
            engagement=engagement,
            hashtags=hashtags,
            mentions=mentions,
            reply_to=None,
            media_urls=[],
            raw_metadata={
                "feed_name": feed_name,
                "title": title,
                "summary": getattr(entry, "summary", ""),
                "tags": [tag.get("term", "") for tag in getattr(entry, "tags", [])],
            },
        )

    async def stream(self, config: dict) -> AsyncIterator[RawPost]:
        """Stream posts from configured RSS feeds."""
        feeds = config.get("feeds", [])
        if not feeds:
            logger.warning("No RSS feeds configured")
            return

        async with httpx.AsyncClient(
            timeout=30.0,
            follow_redirects=True,
            headers={"User-Agent": "Criba/0.1.0 (OSINT Bot)"},
        ) as client:
            for feed_config in feeds:
                feed_name = feed_config.get("name", "unknown")
                feed_url = feed_config.get("url", "")

                if not feed_url:
                    logger.warning("RSS feed %s has no URL, skipping", feed_name)
                    continue

                try:
                    logger.info("Fetching RSS feed: %s (%s)", feed_name, feed_url)
                    response = await client.get(feed_url)
                    response.raise_for_status()

                    parsed = feedparser.parse(response.text)

                    if parsed.bozo and not parsed.entries:
                        logger.warning("RSS feed %s parse error: %s", feed_name, parsed.bozo_exception)
                        continue

                    for entry in parsed.entries:
                        yield self._entry_to_raw_post(entry, feed_name)

                except httpx.HTTPError:
                    logger.exception("HTTP error fetching RSS feed: %s", feed_name)
                except Exception:
                    logger.exception("Error processing RSS feed: %s", feed_name)
