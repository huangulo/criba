from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass
class GeneralConfig:
    language: str
    timezone: str
    heuristic_threshold: float


@dataclass
class OllamaConfig:
    host: str
    model: str
    timeout: int


@dataclass
class SourceConfig:
    enabled: bool
    channels: list[str]
    poll_interval: int


@dataclass
class RssFeedConfig:
    name: str
    url: str


@dataclass
class RssSourceConfig:
    enabled: bool
    feeds: list[RssFeedConfig]
    poll_interval: int


@dataclass
class BlueskySourceConfig:
    enabled: bool
    keywords: list[str]
    handles: list[str]
    poll_interval: int


@dataclass
class YoutubeSourceConfig:
    enabled: bool
    channels: list[str]
    poll_interval: int


@dataclass
class SourcesConfig:
    telegram: SourceConfig
    reddit: SourceConfig
    rss: RssSourceConfig
    bluesky: BlueskySourceConfig
    youtube: YoutubeSourceConfig


@dataclass
class AlertsConfig:
    copypasta_threshold: int
    temporal_cluster_min: int
    new_account_days: int


@dataclass
class NotificationConfig:
    slack_webhook_url: str = ""
    discord_webhook_url: str = ""
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    confidence_threshold: float = 0.85


@dataclass
class CribaConfig:
    general: GeneralConfig
    ollama: OllamaConfig
    sources: SourcesConfig
    alerts: AlertsConfig
    notifications: NotificationConfig


def load_config(path: str = "criba.yml") -> CribaConfig:
    config_path = Path(path)

    if not config_path.is_absolute():
        config_path = Path(__file__).parent.parent.parent / path

    with open(config_path) as f:
        data: dict[str, Any] = yaml.safe_load(f)

    general_data = data.get("general", {})
    general_config = GeneralConfig(
        language=general_data.get("language", "es"),
        timezone=general_data.get("timezone", "America/Bogota"),
        heuristic_threshold=general_data.get("heuristic_threshold", 0.6),
    )

    ollama_data = data.get("ollama", {})
    ollama_config = OllamaConfig(
        host=ollama_data.get("host", "http://localhost:11434"),
        model=ollama_data.get("model", "qwen2.5:14b"),
        timeout=ollama_data.get("timeout", 30),
    )

    sources_data = data.get("sources", {})

    telegram_data = sources_data.get("telegram", {})
    telegram_config = SourceConfig(
        enabled=telegram_data.get("enabled", True),
        channels=telegram_data.get("channels", []),
        poll_interval=telegram_data.get("poll_interval", 60),
    )

    reddit_data = sources_data.get("reddit", {})
    reddit_config = SourceConfig(
        enabled=reddit_data.get("enabled", True),
        channels=reddit_data.get("subreddits", []),
        poll_interval=reddit_data.get("poll_interval", 120),
    )

    rss_data = sources_data.get("rss", {})
    feeds_data = rss_data.get("feeds", [])
    rss_feeds = [RssFeedConfig(name=feed["name"], url=feed["url"]) for feed in feeds_data]
    rss_config = RssSourceConfig(
        enabled=rss_data.get("enabled", True),
        feeds=rss_feeds,
        poll_interval=rss_data.get("poll_interval", 300),
    )

    bluesky_data = sources_data.get("bluesky", {})
    bluesky_config = BlueskySourceConfig(
        enabled=bluesky_data.get("enabled", False),
        keywords=bluesky_data.get("keywords", []),
        handles=bluesky_data.get("handles", []),
        poll_interval=bluesky_data.get("poll_interval", 120),
    )

    youtube_data = sources_data.get("youtube", {})
    youtube_config = YoutubeSourceConfig(
        enabled=youtube_data.get("enabled", False),
        channels=youtube_data.get("channels", []),
        poll_interval=youtube_data.get("poll_interval", 300),
    )

    sources_config = SourcesConfig(
        telegram=telegram_config,
        reddit=reddit_config,
        rss=rss_config,
        bluesky=bluesky_config,
        youtube=youtube_config,
    )

    alerts_data = data.get("alerts", {})
    alerts_config = AlertsConfig(
        copypasta_threshold=alerts_data.get("copypasta_threshold", 10),
        temporal_cluster_min=alerts_data.get("temporal_cluster_min", 5),
        new_account_days=alerts_data.get("new_account_days", 7),
    )

    notif_data = data.get("notifications", {})
    notifications_config = NotificationConfig(
        slack_webhook_url=notif_data.get("slack_webhook_url", ""),
        discord_webhook_url=notif_data.get("discord_webhook_url", ""),
        telegram_bot_token=notif_data.get("telegram_bot_token", ""),
        telegram_chat_id=notif_data.get("telegram_chat_id", ""),
        confidence_threshold=notif_data.get("confidence_threshold", 0.85),
    )

    return CribaConfig(
        general=general_config,
        ollama=ollama_config,
        sources=sources_config,
        alerts=alerts_config,
        notifications=notifications_config,
    )


def save_config(config: CribaConfig, path: str = "criba.yml") -> None:
    config_path = Path(path)
    if not config_path.is_absolute():
        config_path = Path(__file__).parent.parent.parent / path

    data = {
        "general": {
            "language": config.general.language,
            "timezone": config.general.timezone,
            "heuristic_threshold": config.general.heuristic_threshold,
        },
        "ollama": {
            "host": config.ollama.host,
            "model": config.ollama.model,
            "timeout": config.ollama.timeout,
        },
        "sources": {
            "telegram": {
                "enabled": config.sources.telegram.enabled,
                "channels": config.sources.telegram.channels,
                "poll_interval": config.sources.telegram.poll_interval,
            },
            "reddit": {
                "enabled": config.sources.reddit.enabled,
                "subreddits": config.sources.reddit.channels,
                "poll_interval": config.sources.reddit.poll_interval,
            },
            "rss": {
                "enabled": config.sources.rss.enabled,
                "feeds": [{"name": f.name, "url": f.url} for f in config.sources.rss.feeds],
                "poll_interval": config.sources.rss.poll_interval,
            },
            "bluesky": {
                "enabled": config.sources.bluesky.enabled,
                "keywords": config.sources.bluesky.keywords,
                "handles": config.sources.bluesky.handles,
                "poll_interval": config.sources.bluesky.poll_interval,
            },
            "youtube": {
                "enabled": config.sources.youtube.enabled,
                "channels": config.sources.youtube.channels,
                "poll_interval": config.sources.youtube.poll_interval,
            },
        },
        "alerts": {
            "copypasta_threshold": config.alerts.copypasta_threshold,
            "temporal_cluster_min": config.alerts.temporal_cluster_min,
            "new_account_days": config.alerts.new_account_days,
        },
        "notifications": {
            "slack_webhook_url": config.notifications.slack_webhook_url,
            "discord_webhook_url": config.notifications.discord_webhook_url,
            "telegram_bot_token": config.notifications.telegram_bot_token,
            "telegram_chat_id": config.notifications.telegram_chat_id,
            "confidence_threshold": config.notifications.confidence_threshold,
        },
    }

    with open(config_path, "w") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)
