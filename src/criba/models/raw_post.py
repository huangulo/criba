from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class RawPost:
    """Raw post data structure for ingesting content from various sources."""

    source: str
    source_id: str
    author_id: str
    author_handle: str
    author_created_at: datetime | None
    content: str
    language: str | None
    published_at: datetime
    url: str | None
    engagement: dict = field(default_factory=dict)
    hashtags: list[str] = field(default_factory=list)
    mentions: list[str] = field(default_factory=list)
    reply_to: str | None = None
    media_urls: list[str] = field(default_factory=list)
    raw_metadata: dict = field(default_factory=dict)
