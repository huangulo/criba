import asyncio
import logging
import os
import re
from collections.abc import AsyncIterator
from datetime import datetime, timezone

from telethon import TelegramClient
from telethon.errors import FloodWaitError, SessionPasswordNeededError
from telethon.tl.types import Message, Channel

from criba.models.raw_post import RawPost
from criba.models.rate_limit import RateLimitConfig
from criba.models.plugin_base import SourcePlugin

logger = logging.getLogger(__name__)

# Regex patterns for extraction
HASHTAG_RE = re.compile(r"#(\w+)")
MENTION_RE = re.compile(r"@(\w+)")


class TelegramPlugin(SourcePlugin):

    def __init__(self):
        self._client: TelegramClient | None = None
        self._client_loop: asyncio.AbstractEventLoop | None = None

    def get_name(self) -> str:
        return "telegram"

    def get_config_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "channels": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of Telegram channel/group usernames or IDs to monitor",
                },
                "poll_interval": {
                    "type": "integer",
                    "default": 60,
                    "description": "Seconds between polling cycles",
                },
            },
            "required": ["channels"],
        }

    def get_rate_limits(self) -> RateLimitConfig:
        return RateLimitConfig(
            requests_per_minute=30,
            burst_size=5,
            cooldown_seconds=2.0,
        )

    async def _get_client(self) -> TelegramClient | None:
        current_loop = asyncio.get_running_loop()

        # Telethon sockets are bound to the event loop they were created on.
        if self._client is not None and self._client_loop is not current_loop:
            try:
                await self._client.disconnect()
            except Exception:
                pass
            self._client = None

        if self._client is None or not self._client.is_connected():
            api_id = int(os.environ.get("TELEGRAM_API_ID", "0"))
            api_hash = os.environ.get("TELEGRAM_API_HASH", "")
            session_name = os.environ.get("TELEGRAM_SESSION_PATH", "telegram_session")

            if not api_id or not api_hash:
                logger.warning("Telegram API credentials not configured, skipping")
                return None

            self._client = TelegramClient(session_name, api_id, api_hash)
            await self._client.connect()

            if not await self._client.is_user_authorized():
                phone = os.environ.get("TELEGRAM_PHONE", "")
                code = os.environ.get("TELEGRAM_CODE", "")
                if phone and code:
                    try:
                        await self._client.sign_in(phone, code)
                    except Exception as exc:
                        logger.error("Telegram sign-in failed: %s", exc)
                        await self._client.disconnect()
                        self._client = None
                        return None
                else:
                    logger.warning(
                        "Telegram auth required but TELEGRAM_CODE not set. "
                        "Set TELEGRAM_CODE or run interactive auth setup. Skipping."
                    )
                    await self._client.disconnect()
                    self._client = None
                    return None

            self._client_loop = current_loop
            logger.info("Telegram client connected and authorized")

        return self._client

    def _message_to_raw_post(self, message: Message, channel_name: str) -> RawPost:
        """Convert a Telethon Message to a RawPost."""
        # Extract hashtags and mentions from text
        text = message.text or ""
        hashtags = HASHTAG_RE.findall(text)
        mentions = MENTION_RE.findall(text)

        # Extract media URLs
        media_urls = []
        if message.media:
            if hasattr(message.media, "photo") and message.media.photo:
                # Store media type indicator; actual download would be separate
                media_urls.append(f"telegram:photo:{message.id}")
            elif hasattr(message.media, "document") and message.media.document:
                media_urls.append(f"telegram:document:{message.id}")

        # Engagement metrics
        engagement = {
            "views": message.views or 0,
            "forwards": message.forwards or 0,
            "replies": message.replies.replies if message.replies else 0,
        }

        # Author info
        author_id = ""
        author_handle = ""
        author_created_at = None

        if message.sender:
            sender = message.sender
            author_id = str(sender.id)
            if hasattr(sender, "username") and sender.username:
                author_handle = sender.username
            elif hasattr(sender, "first_name"):
                author_handle = sender.first_name or ""
            if hasattr(sender, "date") and sender.date:
                author_created_at = sender.date

        # Determine URL
        url = None
        if message.chat and hasattr(message.chat, "username") and message.chat.username:
            url = f"https://t.me/{message.chat.username}/{message.id}"

        # Message IDs are only unique within a chat, so source IDs and
        # reply_to references must be scoped by the chat they belong to.
        chat_id = message.chat_id if message.chat_id is not None else channel_name

        return RawPost(
            source="telegram",
            source_id=f"{chat_id}:{message.id}",
            author_id=author_id,
            author_handle=author_handle,
            author_created_at=author_created_at,
            content=text,
            language=None,  # will be detected by heuristics
            published_at=message.date or datetime.now(timezone.utc),
            url=url,
            engagement=engagement,
            hashtags=hashtags,
            mentions=mentions,
            reply_to=f"{chat_id}:{message.reply_to.reply_to_msg_id}" if message.reply_to else None,
            media_urls=media_urls,
            raw_metadata={
                "channel": channel_name,
                "grouped_id": message.grouped_id,
                "post_author": message.post_author,
                "edit_date": message.edit_date.isoformat() if message.edit_date else None,
                "pinned": message.pinned,
            },
        )

    async def stream(self, config: dict) -> AsyncIterator[RawPost]:
        """Stream posts from configured Telegram channels."""
        channels = config.get("channels", [])
        if not channels:
            logger.warning("No Telegram channels configured")
            return

        client = await self._get_client()
        if client is None:
            logger.warning("Telegram client not available, skipping")
            return

        for channel_name in channels:
            try:
                logger.info("Fetching messages from Telegram channel: %s", channel_name)
                async for message in client.iter_messages(channel_name, limit=100):
                    if message.text:  # Only process text messages
                        yield self._message_to_raw_post(message, channel_name)
            except FloodWaitError as e:
                logger.warning("Telegram FloodWait: %d seconds for channel %s", e.seconds, channel_name)
                break
            except Exception:
                logger.exception("Error fetching from Telegram channel: %s", channel_name)
                continue
