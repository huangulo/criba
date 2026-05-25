from dataclasses import dataclass


@dataclass
class RateLimitConfig:
    """Rate limit configuration for source plugins."""

    requests_per_minute: int = 60
    burst_size: int = 10
    cooldown_seconds: float = 1.0
