import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from criba.filters.base import BaseFilter, FilterResult
from criba.models.raw_post import RawPost

logger = logging.getLogger(__name__)

DEAD_HOUR_PERCENTILE = 0.02
LOW_ACTIVITY_PERCENTILE = 0.10
CLUSTER_MIN_POSTS = 5
CLUSTER_WINDOW_MINUTES = 60
WARMUP_POSTS = 100


class TemporalAnomalyFilter(BaseFilter):

    def __init__(self, cluster_min: int | None = None):
        self._hourly_counts: dict[str, list[int]] = defaultdict(lambda: [0] * 24)
        self._total_counts: dict[str, int] = defaultdict(int)
        self._recent_posts: dict[str, list[datetime]] = defaultdict(list)
        self._cluster_min = cluster_min if cluster_min is not None else CLUSTER_MIN_POSTS

    def get_name(self) -> str:
        return "temporal_anomaly"

    @property
    def weight(self) -> float:
        return 1.2

    async def apply(self, post: RawPost, context: dict) -> FilterResult:
        source = post.source
        now = datetime.now(timezone.utc)

        post_hour = post.published_at.hour

        self._hourly_counts[source][post_hour] += 1
        self._total_counts[source] += 1

        self._recent_posts[source].append(now)
        cutoff = now - timedelta(minutes=CLUSTER_WINDOW_MINUTES)
        self._recent_posts[source] = [t for t in self._recent_posts[source] if t >= cutoff]

        recent_count = len(self._recent_posts[source])

        if self._total_counts[source] < WARMUP_POSTS:
            return FilterResult(
                score=0.0,
                flagged=False,
                metadata={"temporal_warmup": True, "temporal_warmup_progress": self._total_counts[source]},
            )

        counts = self._hourly_counts[source]
        total = sum(counts)

        percentile_rank = sum(1 for c in counts if c < counts[post_hour]) / 24.0
        hour_fraction = counts[post_hour] / total if total > 0 else 0

        if percentile_rank <= DEAD_HOUR_PERCENTILE:
            base_score = 0.6
            is_dead_hour = True
        elif percentile_rank <= LOW_ACTIVITY_PERCENTILE:
            base_score = 0.4
            is_dead_hour = False
        else:
            base_score = max(0.0, 0.2 - hour_fraction * 2)
            is_dead_hour = False

        cluster_bonus = 0.0
        if is_dead_hour and recent_count >= self._cluster_min:
            cluster_bonus = 0.4
        elif recent_count >= self._cluster_min * 2:
            cluster_bonus = 0.2

        score = min(1.0, base_score + cluster_bonus)
        flagged = score >= 0.6

        return FilterResult(
            score=score,
            flagged=flagged,
            metadata={
                "temporal_percentile_rank": round(percentile_rank, 4),
                "temporal_hour_fraction": round(hour_fraction, 4),
                "temporal_dead_hour": is_dead_hour,
                "temporal_recent_cluster_size": recent_count,
            },
        )

    def export_state(self) -> dict:
        return {
            "hourly_counts": {source: list(counts) for source, counts in self._hourly_counts.items()},
            "total_counts": dict(self._total_counts),
            "recent_posts": {source: list(ts) for source, ts in self._recent_posts.items()},
        }

    def load_state(self, state: dict) -> None:
        self._hourly_counts = defaultdict(
            lambda: [0] * 24,
            {source: list(counts) for source, counts in state.get("hourly_counts", {}).items()},
        )
        self._total_counts = defaultdict(int, state.get("total_counts", {}))
        self._recent_posts = defaultdict(
            list, {source: list(ts) for source, ts in state.get("recent_posts", {}).items()}
        )
