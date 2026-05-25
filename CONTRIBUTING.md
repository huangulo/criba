# Contributing to Criba

Thank you for your interest in contributing to Criba. This document will help you get started and guide you through contributing to the project.

## Introduction

Criba is a narrative intelligence and astroturfing detection engine built with a plugin-based architecture. At its core, Criba ingests data from various social media sources through source plugins, applies heuristic filters to detect anomalous patterns, analyzes content with local LLM inference, and clusters narratives to identify coordinated campaigns.

The plugin system is central to Criba's design. Source plugins abstract data collection from any platform, heuristic filters analyze behavior patterns, and the auto-discovery registry makes adding new integrations straightforward.

## Getting Started

### Prerequisites

Before you begin, ensure you have the following installed:

- Python 3.12 or higher
- Docker and Docker Compose
- Ollama (for local LLM inference)

### Setup

1. Clone the repository:

```bash
git clone https://github.com/user/criba.git
cd criba
```

2. Copy the example environment file and configure it:

```bash
cp .env.example .env
```

Edit `.env` with your credentials for the data sources you want to use.

3. Start the application:

```bash
docker compose up -d
```

This will start PostgreSQL, Redis, the Celery worker, and the FastAPI server.

4. Install and run Ollama with your preferred model:

```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama pull qwen2.5:14b
```

### Running Tests

Run the test suite to ensure everything is working:

```bash
pytest tests/
```

## Project Structure

```
src/criba/
├── api/           # FastAPI routes and schemas
├── db/            # SQLAlchemy models and connection
├── engine/        # Narrative clustering, campaign detection
├── filters/       # Heuristic filters (core engine)
├── llm/           # Ollama client, prompts, embeddings
├── models/        # RawPost, SourcePlugin base, RateLimitConfig
├── plugins/       # Source plugins (telegram, reddit, rss)
└── worker/        # Celery tasks, ingestion, alerts
dashboard/         # Next.js frontend
```

## Writing a New Source Plugin

### The SourcePlugin Interface

All source plugins must inherit from `SourcePlugin` and implement four required methods. The base interface is defined in `src/criba/models/plugin_base.py`:

```python
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
```

### The RawPost Schema

Plugins yield `RawPost` objects that contain all the data Criba needs for analysis. The schema is defined in `src/criba/models/raw_post.py`:

```python
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
```

### Step-by-Step Guide

#### 1. Create the Plugin Directory

Create a new directory for your plugin under `src/criba/plugins/`:

```bash
mkdir -p src/criba/plugins/your_source
```

#### 2. Create the Package Files

Create `__init__.py` to expose the plugin instance:

```python
# src/criba/plugins/your_source/__init__.py
from .plugin import plugin
```

#### 3. Implement the Plugin

Create `plugin.py` with your implementation:

```python
import logging
from collections.abc import AsyncIterator
from datetime import datetime, timezone

from criba.models.raw_post import RawPost
from criba.models.rate_limit import RateLimitConfig
from criba.models.plugin_base import SourcePlugin

logger = logging.getLogger(__name__)


class YourSourcePlugin(SourcePlugin):

    def get_name(self) -> str:
        return "your_source"

    def get_config_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "endpoints": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of webhook endpoints to receive data",
                },
                "api_key": {
                    "type": "string",
                    "description": "API key for authentication",
                },
            },
            "required": ["endpoints"],
        }

    def get_rate_limits(self) -> RateLimitConfig:
        return RateLimitConfig(
            requests_per_minute=60,
            burst_size=10,
            cooldown_seconds=1.0,
        )

    async def stream(self, config: dict) -> AsyncIterator[RawPost]:
        """Stream posts from your source."""
        endpoints = config.get("endpoints", [])
        api_key = config.get("api_key", "")

        # Fetch data from your source here
        # Convert to RawPost and yield

        for item in await self._fetch_data(endpoints, api_key):
            yield self._to_raw_post(item)

    async def _fetch_data(self, endpoints: list[str], api_key: str):
        """Fetch raw data from the source. Implement your API calls here."""
        # Your implementation
        pass

    def _to_raw_post(self, item: dict) -> RawPost:
        """Convert source-specific data to RawPost."""
        return RawPost(
            source=self.get_name(),
            source_id=str(item.get("id", "")),
            author_id=str(item.get("author_id", "")),
            author_handle=item.get("author_handle", ""),
            author_created_at=None,  # Extract if available
            content=item.get("content", ""),
            language=None,  # Will be detected by heuristics
            published_at=datetime.fromisoformat(item.get("created_at", "")),
            url=item.get("url"),
            engagement={
                "likes": item.get("likes", 0),
                "shares": item.get("shares", 0),
                "comments": item.get("comments", 0),
            },
            hashtags=item.get("hashtags", []),
            mentions=item.get("mentions", []),
            reply_to=item.get("reply_to"),
            media_urls=item.get("media_urls", []),
            raw_metadata=item,  # Store original data for reference
        )


# Create a singleton instance for registry
plugin = YourSourcePlugin()
```

#### 4. Add Configuration

Add a new section to your `criba.yml` under `sources`:

```yaml
sources:
  telegram:
    enabled: true
    channels:
      - channel_name

  reddit:
    enabled: true
    subreddits:
      - subreddit_name

  your_source:
    enabled: true
    endpoints:
      - https://api.example.com/webhook
    api_key: your_api_key_here
```

### Auto-Discovery Mechanism

The plugin registry automatically discovers all plugins in the `src/criba/plugins/` directory. The mechanism is in `src/criba/plugins/registry.py`:

```python
import importlib
import logging
import pkgutil
from pathlib import Path

from criba.models.plugin_base import SourcePlugin

logger = logging.getLogger(__name__)

_registry: dict[str, SourcePlugin] = {}
_discovered: bool = False


def register_plugin(plugin: SourcePlugin) -> None:
    """Register a source plugin."""
    name = plugin.get_name()
    if name in _registry:
        logger.warning("Plugin %s already registered, overwriting", name)
    _registry[name] = plugin
    logger.debug("Registered plugin: %s", name)


def get_plugin(name: str) -> SourcePlugin | None:
    """Get a registered plugin by name. Discovers plugins if not yet done."""
    if not _discovered:
        discover_plugins()
    return _registry.get(name)


def list_plugins() -> list[str]:
    """List all registered plugin names. Discovers plugins if not yet done."""
    if not _discovered:
        discover_plugins()
    return sorted(_registry.keys())


def discover_plugins() -> None:
    """Auto-discover plugins in the criba.plugins package."""
    global _discovered
    if _discovered:
        return

    plugins_dir = Path(__file__).parent
    logger.info("Discovering plugins in %s", plugins_dir)

    for item in plugins_dir.iterdir():
        if item.is_dir() and not item.name.startswith("_") and (item / "__init__.py").exists():
            module_name = f"criba.plugins.{item.name}"
            try:
                module = importlib.import_module(module_name)
                if hasattr(module, "plugin"):
                    plugin_instance = module.plugin
                    if isinstance(plugin_instance, SourcePlugin):
                        register_plugin(plugin_instance)
                    else:
                        logger.warning("Plugin %s 'plugin' attribute is not a SourcePlugin", item.name)
                else:
                    logger.debug("Module %s has no 'plugin' attribute, skipping", module_name)
            except Exception:
                logger.exception("Failed to load plugin module: %s", module_name)

    _discovered = True
    logger.info("Discovered %d plugins: %s", len(_registry), list(_registry.keys()))
```

Your plugin will be automatically discovered when the application starts, as long as:

1. The directory is in `src/criba/plugins/your_source/`
2. It contains an `__init__.py` file
3. The module exports a `plugin` attribute that is an instance of `SourcePlugin`

No manual registration is needed.

## Writing Heuristic Filters

Heuristic filters analyze posts for behavioral anomalies. All filters inherit from `BaseFilter` defined in `src/criba/filters/base.py`:

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from criba.models.raw_post import RawPost


@dataclass
class FilterResult:
    score: float  # 0.0 - 1.0 contribution to anomaly detection
    metadata: dict = field(default_factory=dict)
    flagged: bool = False  # whether this filter flagged the post as anomalous


class BaseFilter(ABC):

    @abstractmethod
    def get_name(self) -> str:
        """Unique identifier for this filter."""

    @abstractmethod
    async def apply(self, post: RawPost, context: dict) -> FilterResult:
        """Apply this filter to a post. context carries shared state between filters."""

    @property
    def weight(self) -> float:
        """Weight of this filter in the composite score (0.0 - 1.0). Default 1.0."""
        return 1.0
```

### Creating a New Filter

1. Create a new file in `src/criba/filters/your_filter.py`:

```python
import logging
from criba.filters.base import BaseFilter, FilterResult
from criba.models.raw_post import RawPost

logger = logging.getLogger(__name__)


class YourFilter(BaseFilter):

    def get_name(self) -> str:
        return "your_filter"

    @property
    def weight(self) -> float:
        return 0.8  # Adjust based on importance

    async def apply(self, post: RawPost, context: dict) -> FilterResult:
        """
        Analyze the post and return a FilterResult.

        Args:
            post: The raw post to analyze
            context: Shared state between filters (e.g., seen posts, counters)

        Returns:
            FilterResult with score (0.0-1.0) and optional metadata
        """
        score = 0.0
        metadata = {}
        flagged = False

        # Your analysis logic here
        # Example: Check for suspicious patterns

        if self._is_suspicious(post):
            score = 0.7
            flagged = True
            metadata["reason"] = "Suspicious pattern detected"

        return FilterResult(score=score, metadata=metadata, flagged=flagged)

    def _is_suspicious(self, post: RawPost) -> bool:
        """Helper method to detect suspicious patterns."""
        # Your logic
        return False
```

2. Add the filter to the pipeline in `src/criba/filters/pipeline.py`:

```python
from criba.filters.your_filter import YourFilter

# Add to your filter list
filters = [
    LanguageFilter(),
    DeduplicationFilter(),
    CopypastaFilter(),
    TemporalFilter(),
    AccountAgeFilter(),
    HashtagFilter(),
    NetworkFilter(),
    YourFilter(),  # Your new filter
]
```

### Filter Weights

The `weight` property controls how much each filter contributes to the composite anomaly score. Weights are multiplied by the filter's score to calculate the final score. A weight of 1.0 means full contribution, while 0.5 halves the impact.

Consider the nature of the signal when setting weights:

- Strong, specific indicators of manipulation: higher weight (0.8-1.0)
- Broad, common patterns: moderate weight (0.5-0.7)
- Supplementary signals: lower weight (0.1-0.4)

## Development Guidelines

### Code Style

- Use ruff for linting
- Line length: 120 characters
- Python version: 3.12+
- Follow PEP 8 conventions

### State Management

- All filters must be stateless or manage their own state
- Never access the database directly in filters
- Use the `context` parameter to share state between filters in a pipeline run

### Async Concurrency

- Use async/await for all I/O operations
- Prefer `async for` and `async with` where available
- Avoid blocking the event loop

### Error Handling

- Never suppress errors silently
- Let exceptions propagate to the pipeline's error handler
- Log relevant context before raising when appropriate
- Use structured logging for debugging

### Testing

- Write tests for all new filters and plugins
- Test both happy paths and error cases
- Use pytest fixtures for shared test data
- Mock external API calls in tests

## Pull Request Process

1. Fork the repository and create a feature branch
2. Make your changes with clear, focused commits
3. Add tests for new functionality
4. Ensure the build passes:

```bash
docker compose build
pytest tests/
ruff check src/
```

5. Submit a pull request with a descriptive title and summary

### PR Guidelines

- One pull request per feature or bug fix
- Include tests that cover your changes
- Update documentation if needed
- Keep PRs focused and reviewable
- Reference related issues in the description

We review PRs as quickly as possible. Feel free to add comments if you have questions during the process.