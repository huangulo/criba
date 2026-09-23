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

    def export_state(self) -> dict | None:
        """Snapshot of cross-run state for persistence, or None if stateless.

        Snapshots must be plain picklable data (dicts, lists, tuples, scalars)
        and cheap to serialize: the worker persists them after every ingested post.
        """
        return None

    def load_state(self, state: dict) -> None:
        """Restore a snapshot previously produced by export_state(). Default: no-op."""
