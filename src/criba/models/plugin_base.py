from abc import ABC, abstractmethod
from collections.abc import AsyncIterator

from .raw_post import RawPost
from .rate_limit import RateLimitConfig


class SourcePlugin(ABC):
    """Base class for all data source plugins."""

    @abstractmethod
    def get_name(self) -> str:
        """Unique identifier for this source (e.g., 'telegram', 'reddit')."""

    @abstractmethod
    def get_config_schema(self) -> dict:
        """JSON schema for required configuration (API keys, channels, etc.)."""

    @abstractmethod
    async def stream(self, config: dict) -> AsyncIterator[RawPost]:
        """Yield raw posts from the source. Runs as a Celery task."""

    @abstractmethod
    def get_rate_limits(self) -> RateLimitConfig:
        """Return rate limit parameters for this source."""
