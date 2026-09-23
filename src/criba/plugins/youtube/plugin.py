import json
import os
import re
import logging
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from criba.models.raw_post import RawPost
from criba.models.rate_limit import RateLimitConfig
from criba.models.plugin_base import SourcePlugin

logger = logging.getLogger(__name__)

HASHTAG_RE = re.compile(r"#(\w+)")
MENTION_RE = re.compile(r"@(\w+)")

QUOTA_REASONS = {"quotaExceeded", "rateLimitExceeded", "dailyLimitExceeded"}


def _quota_reason(exc: HttpError) -> str:
    try:
        content = exc.content.decode("utf-8", "replace") if isinstance(exc.content, bytes) else exc.content
        errors = json.loads(content).get("error", {}).get("errors", [])
        return errors[0].get("reason", "") if errors else ""
    except (AttributeError, TypeError, ValueError):
        return ""


def _is_quota_error(exc: HttpError) -> bool:
    return _quota_reason(exc) in QUOTA_REASONS


class YouTubePlugin(SourcePlugin):

    def get_name(self) -> str:
        return "youtube"

    def get_config_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "channels": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of YouTube channel IDs or handles to monitor",
                },
                "poll_interval": {
                    "type": "integer",
                    "default": 300,
                    "description": "Seconds between polling cycles",
                },
            },
            "required": ["channels"],
        }

    def get_rate_limits(self) -> RateLimitConfig:
        return RateLimitConfig(
            requests_per_minute=15,
            burst_size=3,
            cooldown_seconds=4.0,
        )

    def _comment_to_raw_post(
        self,
        comment: dict,
        video_id: str,
        video_title: str,
        reply_to: str | None = None,
        is_reply_comment: bool = False,
    ) -> RawPost:
        snippet = comment.get("snippet", {})
        comment_id = comment.get("id", "")
        author_data = snippet.get("authorDisplayName", "")
        author_channel_id = snippet.get("authorChannelId", {}).get("value", "")
        text_display = snippet.get("textDisplay", "")
        published_at_str = snippet.get("publishedAt", "")
        like_count = snippet.get("likeCount", 0)
        can_reply = snippet.get("canReply", False)

        published_at = datetime.fromisoformat(published_at_str.replace("Z", "+00:00")) if published_at_str else datetime.now(timezone.utc)

        hashtags = HASHTAG_RE.findall(text_display)
        mentions = MENTION_RE.findall(text_display)

        return RawPost(
            source="youtube",
            source_id=comment_id,
            author_id=author_channel_id,
            author_handle=author_data,
            author_created_at=None,
            content=text_display,
            language=None,
            published_at=published_at,
            url=f"https://www.youtube.com/watch?v={video_id}&lc={comment_id}",
            engagement={"like_count": like_count},
            hashtags=hashtags,
            mentions=mentions,
            reply_to=reply_to,
            media_urls=[],
            raw_metadata={
                "video_id": video_id,
                "video_title": video_title,
                "can_reply": can_reply,
                "is_reply": is_reply_comment,
            },
        )

    def _resolve_handle_to_channel_id(self, youtube, handle: str) -> str | None:
        try:
            if handle.startswith("@"):
                search_response = youtube.search().list(
                    part="snippet",
                    q=handle,
                    type="channel",
                    maxResults=1,
                ).execute()
                items = search_response.get("items", [])
                if items:
                    return items[0].get("snippet", {}).get("channelId")
            return handle
        except HttpError as exc:
            logger.error("Error resolving handle %s: %s", handle, exc)
            return None

    async def stream(self, config: dict) -> AsyncIterator[RawPost]:
        api_key = os.environ.get("YOUTUBE_API_KEY")
        if not api_key:
            logger.warning("YOUTUBE_API_KEY not set, skipping YouTube plugin")
            return

        channels = config.get("channels", [])
        if not channels:
            logger.warning("No channels configured")
            return

        youtube = build("youtube", "v3", developerKey=api_key)

        for channel in channels:
            channel_id = channel
            if channel.startswith("@"):
                channel_id = self._resolve_handle_to_channel_id(youtube, channel)
                if not channel_id:
                    logger.warning("Could not resolve handle %s to channel ID", channel)
                    continue

            try:
                logger.info("Fetching YouTube videos from channel: %s", channel_id)
                videos_response = youtube.search().list(
                    part="snippet",
                    channelId=channel_id,
                    type="video",
                    order="date",
                    maxResults=10,
                ).execute()
            except HttpError as exc:
                if exc.status_code == 403 and _is_quota_error(exc):
                    logger.warning("YouTube API quota exceeded, stopping stream")
                    return
                logger.error("YouTube API error for channel %s: %s", channel_id, exc)
                continue
            except Exception:
                logger.exception("Error fetching YouTube data from channel %s", channel_id)
                continue

            videos = videos_response.get("items", [])
            for video in videos:
                video_id = video.get("id", {}).get("videoId", "")
                video_title = video.get("snippet", {}).get("title", "")
                if not video_id:
                    continue

                try:
                    logger.info("Fetching comments for video: %s", video_id)
                    comments_response = youtube.commentThreads().list(
                        part="snippet,replies",
                        videoId=video_id,
                        maxResults=50,
                        textFormat="plainText",
                    ).execute()
                except HttpError as exc:
                    if exc.status_code == 403 and _is_quota_error(exc):
                        logger.warning("YouTube API quota exceeded, stopping stream")
                        return
                    # A 403 with a non-quota reason (e.g. comments disabled on
                    # the video) must only skip this video, not the whole run.
                    logger.warning(
                        "Skipping comments for video %s: HTTP %s (%s)",
                        video_id, exc.status_code, _quota_reason(exc) or "unknown reason",
                    )
                    continue
                except Exception:
                    logger.exception("Error fetching comments for video %s", video_id)
                    continue

                comment_threads = comments_response.get("items", [])
                for thread in comment_threads:
                    top_level_comment = thread.get("snippet", {}).get("topLevelComment", {})
                    if top_level_comment:
                        yield self._comment_to_raw_post(
                            top_level_comment,
                            video_id,
                            video_title,
                            reply_to=None,
                            is_reply_comment=False,
                        )

                    top_comment_id = top_level_comment.get("id", "") if top_level_comment else None
                    replies = thread.get("replies", {}).get("comments", [])
                    for reply in replies:
                        yield self._comment_to_raw_post(
                            reply,
                            video_id,
                            video_title,
                            reply_to=top_comment_id,
                            is_reply_comment=True,
                        )
