from datetime import UTC, datetime

import pytest_asyncio

from criba.models.raw_post import RawPost


@pytest_asyncio.fixture
def make_post():
    """Helper function to create a RawPost with sensible defaults."""
    def _make_post(**overrides):
        defaults = {
            "source": "test",
            "source_id": "post_1",
            "author_id": "author_1",
            "author_handle": "user1",
            "author_created_at": None,
            "content": "This is a test post with some content for testing purposes",
            "language": None,
            "published_at": datetime(2025, 1, 15, 14, 0, 0, tzinfo=UTC),
            "url": None,
            "engagement": {},
            "hashtags": [],
            "mentions": [],
            "reply_to": None,
            "media_urls": [],
            "raw_metadata": {},
        }
        defaults.update(overrides)
        return RawPost(**defaults)
    return _make_post