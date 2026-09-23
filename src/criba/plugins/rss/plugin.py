import hashlib
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

MAX_SOURCE_ID_CHARS = 255


def _bounded_source_id(raw: str) -> str:
    """Bound an entry identifier to the posts.source_id column (String(255)).

    Feed entry IDs and links are unbounded; one longer than the column would
    fail the insert on every poll and turn a single bad entry into a
    permanent ingestion retry loop. Over-long values hash to a stable short
    form so dedup keeps working across polls.
    """
    raw = raw.strip()
    if len(raw) <= MAX_SOURCE_ID_CHARS:
        return raw
    return "long:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _strip_html(text: str) -> str:
    """Remove HTML tags and decode basic entities."""
    text = HTML_TAG_RE.sub("", text)
    text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    text = text.replace("&nbsp;", " ").replace("&#39;", "'").replace("&quot;", '"')
    return text.strip()


def _parse_date(entry) -> datetime | None:
    """Parse publication date from an RSS/Atom entry.

    Prefers feedparser's normalized *_parsed time tuples, which it fills
    for both RFC 2822 (RSS) and ISO 8601 (Atom) dates; falls back to parsing
    the raw string fields with either date format.
    """
    for field in ("published_parsed", "updated_parsed", "created_parsed"):
        value = getattr(entry, field, None)
        if value:
            try:
                return datetime(*value[:6], tzinfo=timezone.utc)
            except (ValueError, TypeError):
                continue
    for field in ("published", "updated", "created"):
        value = getattr(entry, field, None)
        if not isinstance(value, str) or not value:
            continue
        for parser in (parsedate_to_datetime, datetime.fromisoformat):
            try:
                parsed = parser(value)
            except (ValueError, TypeError):
                continue
            if parsed is not None:
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=timezone.utc)
                return parsed
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

        # Generate stable source_id from entry id or link. Over-long values
        # are hashed to fit posts.source_id (String(255)); entries without
        # any identifier get a content-derived one so distinct entries stay
        # distinct and repeats still dedup.
        raw_source_id = getattr(entry, "id", "") or url or ""
        if not raw_source_id:
            material = f"{feed_name}|{title}|{content[:500]}"
            raw_source_id = "derived:" + hashlib.sha256(material.encode("utf-8")).hexdigest()
        source_id = _bounded_source_id(raw_source_id)

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
        from criba.utils.net import assert_public_http_url

        feeds = config.get("feeds", [])
        if not feeds:
            logger.warning("No RSS feeds configured")
            return

        async def guard_request(request: httpx.Request) -> None:
            """httpx event hook: refuse requests to non-public destinations."""
            await assert_public_http_url(str(request.url))

        async with httpx.AsyncClient(
            timeout=30.0,
            follow_redirects=True,
            headers={"User-Agent": "Criba/0.1.0 (OSINT Bot)"},
            event_hooks={"request": [guard_request]},
        ) as client:
            for feed_config in feeds:
                feed_name = feed_config.get("name", "unknown")
                feed_url = feed_config.get("url", "")

                if not feed_url:
                    logger.warning("RSS feed %s has no URL, skipping", feed_name)
                    continue

                try:
                    await assert_public_http_url(feed_url)
                except ValueError as exc:
                    logger.warning("Refusing to fetch RSS feed %s: %s", feed_name, exc)
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
