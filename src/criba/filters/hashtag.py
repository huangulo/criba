import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from criba.filters.base import BaseFilter, FilterResult
from criba.models.raw_post import RawPost

logger = logging.getLogger(__name__)

COOCCURRENCE_THRESHOLD = 10
MIN_UNIQUE_AUTHORS = 3
MIN_HASHTAGS = 3
CORPUS_HOURS = 72


class _CooccurrenceRecord:
    __slots__ = ("count", "authors")

    def __init__(self):
        self.count = 0
        self.authors: set[str] = set()


class HashtagCooccurrenceFilter(BaseFilter):

    def __init__(self):
        self._pairs: dict[str, dict[str, _CooccurrenceRecord]] = defaultdict(lambda: defaultdict(_CooccurrenceRecord))
        self._entries: list[tuple[datetime, set[str]]] = []

    def get_name(self) -> str:
        return "hashtag_cooccurrence"

    @property
    def weight(self) -> float:
        return 1.0

    async def apply(self, post: RawPost, context: dict) -> FilterResult:
        hashtags = post.hashtags
        if len(hashtags) < 2:
            return FilterResult(score=0.0, metadata={"hashtag_count": len(hashtags)})

        self._maybe_prune()

        normalized = sorted(set(h.lower() for h in hashtags))
        flagged_pairs = 0
        max_cooccurrence = 0

        for i in range(len(normalized)):
            for j in range(i + 1, len(normalized)):
                h1, h2 = normalized[i], normalized[j]
                record = self._pairs[h1][h2]
                record.count += 1
                record.authors.add(post.author_id)
                max_cooccurrence = max(max_cooccurrence, record.count)

                if record.count >= COOCCURRENCE_THRESHOLD and len(record.authors) >= MIN_UNIQUE_AUTHORS:
                    flagged_pairs += 1

        self._entries.append((datetime.now(timezone.utc), set(normalized)))

        if len(normalized) < MIN_HASHTAGS:
            score = 0.0
        elif flagged_pairs == 0:
            score = 0.1
        elif flagged_pairs <= 3:
            score = 0.5
        else:
            score = 0.9

        flagged = flagged_pairs > 0 and len(normalized) >= MIN_HASHTAGS

        return FilterResult(
            score=score,
            flagged=flagged,
            metadata={
                "hashtag_count": len(normalized),
                "hashtag_flagged_pairs": flagged_pairs,
                "hashtag_max_cooccurrence": max_cooccurrence,
            },
        )

    def _maybe_prune(self) -> None:
        if len(self._entries) % 500 != 0:
            return
        cutoff = datetime.now(timezone.utc) - timedelta(hours=CORPUS_HOURS)
        self._entries = [(t, h) for t, h in self._entries if t >= cutoff]

    def export_state(self) -> dict:
        return {
            "pairs": {
                h1: {
                    h2: {"count": record.count, "authors": sorted(record.authors)}
                    for h2, record in inner.items()
                }
                for h1, inner in self._pairs.items()
            },
            "entries": [(ts, sorted(tags)) for ts, tags in self._entries],
        }

    def load_state(self, state: dict) -> None:
        pairs: dict[str, dict[str, _CooccurrenceRecord]] = defaultdict(
            lambda: defaultdict(_CooccurrenceRecord)
        )
        for h1, inner in state.get("pairs", {}).items():
            for h2, record_data in inner.items():
                record = pairs[h1][h2]
                record.count = int(record_data.get("count", 0))
                record.authors = set(record_data.get("authors", []))
        self._pairs = pairs
        self._entries = [(ts, set(tags)) for ts, tags in state.get("entries", [])]
