import logging
from collections import defaultdict
from datetime import UTC, datetime, timedelta

from criba.filters.base import BaseFilter, FilterResult
from criba.models.raw_post import RawPost

logger = logging.getLogger(__name__)

EDGE_WINDOW_HOURS = 72
TIGHT_CLUSTER_THRESHOLD = 5


class NetworkGraphFilter(BaseFilter):

    def __init__(self):
        self._adjacency: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
        self._edge_timestamps: list[tuple[str, str, datetime]] = []

    def get_name(self) -> str:
        return "network_graph"

    @property
    def weight(self) -> float:
        return 1.0

    async def apply(self, post: RawPost, context: dict) -> FilterResult:
        now = datetime.now(UTC)
        edges_to_add: list[tuple[str, str, str]] = []

        for mention in post.mentions:
            edges_to_add.append((post.author_id, mention, "mention"))

        if post.reply_to and context.get("last_post_author_id"):
            edges_to_add.append((post.author_id, context["last_post_author_id"], "reply"))

        copypasta_authors = context.get("copypasta_author_list", [])
        for other_author in copypasta_authors:
            if other_author != post.author_id:
                edges_to_add.append((post.author_id, other_author, "lexical_similarity"))

        # Edges are stored directed so the mutual-connection check below
        # only counts genuinely reciprocal interactions.
        for source, target, interaction in edges_to_add:
            self._adjacency[source][target] += 1
            self._edge_timestamps.append((source, target, now))

        self._maybe_prune(now)

        author_neighbors = self._adjacency.get(post.author_id, {})
        neighbor_count = len(author_neighbors)
        edge_weights = sum(author_neighbors.values())
        avg_weight = edge_weights / neighbor_count if neighbor_count > 0 else 0

        mutual_count = sum(1 for n in author_neighbors if post.author_id in self._adjacency.get(n, {}))

        is_tight_cluster = mutual_count >= TIGHT_CLUSTER_THRESHOLD

        if is_tight_cluster:
            score = 0.8
        elif mutual_count >= 3:
            score = 0.4
        elif neighbor_count > 10 and avg_weight > 3:
            score = 0.3
        else:
            score = 0.0

        flagged = is_tight_cluster

        return FilterResult(
            score=score,
            flagged=flagged,
            metadata={
                "network_neighbor_count": neighbor_count,
                "network_mutual_connections": mutual_count,
                "network_edge_weights": {
                    k: v for k, v in list(author_neighbors.items())[:20]
                },
                "network_edges_to_persist": [
                    {"source": s, "target": t, "interaction": i}
                    for s, t, i in edges_to_add
                ],
            },
        )

    def _maybe_prune(self, now: datetime) -> None:
        if len(self._edge_timestamps) % 500 != 0:
            return
        cutoff = now - timedelta(hours=EDGE_WINDOW_HOURS)
        for source, target, ts in self._edge_timestamps:
            if ts < cutoff and source in self._adjacency and target in self._adjacency[source]:
                self._adjacency[source][target] -= 1
                if self._adjacency[source][target] <= 0:
                    del self._adjacency[source][target]
        self._edge_timestamps = [(s, t, ts) for s, t, ts in self._edge_timestamps if ts >= cutoff]

    def export_state(self) -> dict:
        return {
            "adjacency": {source: dict(targets) for source, targets in self._adjacency.items()},
            "edge_timestamps": [(s, t, ts) for s, t, ts in self._edge_timestamps],
        }

    def load_state(self, state: dict) -> None:
        adjacency: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
        for source, targets in state.get("adjacency", {}).items():
            for target, weight in targets.items():
                adjacency[source][target] = int(weight)
        self._adjacency = adjacency
        self._edge_timestamps = [
            (s, t, ts) for s, t, ts in state.get("edge_timestamps", [])
        ]
