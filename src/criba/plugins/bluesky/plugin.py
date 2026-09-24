import asyncio
import logging
import os
import re
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path

from atproto import AsyncClient

from criba.models.plugin_base import SourcePlugin
from criba.models.rate_limit import RateLimitConfig
from criba.models.raw_post import RawPost

logger = logging.getLogger(__name__)

HASHTAG_RE = re.compile(r"#(\w+)")
MENTION_RE = re.compile(r"@(\w+)")

# Polls are periodic, so a single 50-post page silently misses anything
# published faster than the poll interval; follow the cursor instead, bounded
# so one busy feed cannot monopolize the run. Repeats are deduped downstream.
MAX_PAGES = 4


class BlueskyPlugin(SourcePlugin):

    def __init__(self):
        self._client: AsyncClient | None = None
        self._client_loop: asyncio.AbstractEventLoop | None = None

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

        published_at = datetime.now(UTC)
        if hasattr(record, "created_at") and record.created_at:
            try:
                published_at = datetime.fromisoformat(record.created_at)
            except (ValueError, TypeError):
                pass

        author_created_at = None
        if hasattr(author, "created_at") and author.created_at:
            try:
                author_created_at = datetime.fromisoformat(author.created_at)
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
            embed = post.embed
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

    def _session_path(self) -> Path:
        return Path(os.environ.get("BLUESKY_SESSION_PATH", "bluesky_session.string"))

    def _load_session_string(self) -> str | None:
        try:
            stored = self._session_path().read_text(encoding="utf-8").strip()
        except OSError:
            return None
        return stored or None

    def _save_session_string(self, session_string: str) -> None:
        try:
            self._session_path().write_text(session_string + "\n", encoding="utf-8")
        except OSError:
            logger.warning("Could not persist Bluesky session to %s", self._session_path(), exc_info=True)

    async def _get_client(self) -> AsyncClient | None:
        """One logged-in client per event loop, reused across polls.

        The plugin instance is a process-wide singleton but Celery runs each
        task on a fresh event loop, and the httpx-backed client cannot cross
        loops. The session string is persisted and restored instead, so a
        password login happens once ever, not once per poll.
        """
        current_loop = asyncio.get_running_loop()
        if self._client is not None and self._client_loop is not current_loop:
            # The old loop is gone; its connections cannot be reused.
            self._client = None

        if self._client is not None:
            return self._client

        client = AsyncClient()

        def persist_session(_: object) -> None:
            # Fires on login and on every session refresh; the refresh token
            # rotates, so the stored string must be kept current or restores
            # start failing.
            try:
                self._save_session_string(client.export_session_string())
            except Exception:
                logger.warning("Could not persist the refreshed Bluesky session", exc_info=True)

        client.on_session_change(persist_session)

        stored_session = self._load_session_string()
        if stored_session:
            try:
                await client.login(session_string=stored_session)
                logger.info("Bluesky session restored from %s", self._session_path())
                self._client = client
                self._client_loop = current_loop
                return self._client
            except Exception:
                logger.warning(
                    "Stored Bluesky session rejected; falling back to password login", exc_info=True
                )

        handle = os.environ.get("BLUESKY_HANDLE")
        password = os.environ.get("BLUESKY_APP_PASSWORD")
        if not handle or not password:
            logger.warning(
                "No usable Bluesky session and BLUESKY_HANDLE/BLUESKY_APP_PASSWORD not set, skipping"
            )
            return None

        await client.login(handle, password)
        self._client = client
        self._client_loop = current_loop
        return self._client

    async def _iter_search(self, client, keyword: str) -> AsyncIterator[RawPost]:
        """Paginate keyword search results up to MAX_PAGES."""
        cursor: str | None = None
        for _ in range(MAX_PAGES):
            params: dict = {"q": keyword, "limit": 50}
            if cursor:
                params["cursor"] = cursor
            response = await client.app.bsky.feed.search_posts(params=params)
            posts = getattr(response, "posts", None) or []
            for post in posts:
                yield self._post_to_raw_post(post)
            cursor = getattr(response, "cursor", None)
            if not cursor or not posts:
                return

    async def _iter_author_feed(self, client, actor: str) -> AsyncIterator[RawPost]:
        """Paginate an author's feed up to MAX_PAGES."""
        cursor: str | None = None
        for _ in range(MAX_PAGES):
            params: dict = {"actor": actor, "limit": 50}
            if cursor:
                params["cursor"] = cursor
            response = await client.app.bsky.feed.get_author_feed(params=params)
            feed = getattr(response, "feed", None) or []
            for post in feed:
                yield self._post_to_raw_post(post)
            cursor = getattr(response, "cursor", None)
            if not cursor or not feed:
                return

    async def stream(self, config: dict) -> AsyncIterator[RawPost]:
        keywords = config.get("keywords", [])
        handles = config.get("handles", [])

        if not keywords and not handles:
            logger.warning("No keywords or handles configured for Bluesky")
            return

        client = await self._get_client()
        if client is None:
            logger.warning("Bluesky client not available, skipping")
            return

        for keyword in keywords:
            try:
                logger.info("Searching Bluesky for keyword: %s", keyword)
                async for post in self._iter_search(client, keyword):
                    yield post
            except Exception:
                logger.exception("Error searching Bluesky for keyword: %s", keyword)

        for actor in handles:
            try:
                logger.info("Fetching Bluesky author feed: %s", actor)
                async for post in self._iter_author_feed(client, actor):
                    yield post
            except Exception:
                logger.exception("Error fetching Bluesky author feed: %s", actor)