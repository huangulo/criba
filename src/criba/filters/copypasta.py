import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from datasketch import MinHash, MinHashLSH

from criba.filters.base import BaseFilter, FilterResult
from criba.models.raw_post import RawPost

logger = logging.getLogger(__name__)

NUM_PERM = 128
SHINGLE_SIZE = 5
JACCARD_THRESHOLD = 0.7
CORPUS_HOURS = 72
MIN_UNIQUE_AUTHORS = 3
DEFAULT_SIMILAR_THRESHOLD = 10


def _shingle(text: str, k: int = SHINGLE_SIZE) -> set[str]:
    words = text.lower().split()
    if len(words) < k:
        return {"".join(words)} if words else set()
    return {" ".join(words[i:i + k]) for i in range(len(words) - k + 1)}


def _create_minhash(shingles: set[str]) -> MinHash:
    mh = MinHash(num_perm=NUM_PERM)
    for s in shingles:
        mh.update(s.encode("utf-8"))
    return mh


class _CorpusEntry:
    __slots__ = ("post_id", "author_id", "minhash", "timestamp")

    def __init__(self, post_id: str, author_id: str, minhash: MinHash, timestamp: datetime):
        self.post_id = post_id
        self.author_id = author_id
        self.minhash = minhash
        self.timestamp = timestamp


class CopypastaFilter(BaseFilter):

    def __init__(self, similar_threshold: int | None = None):
        self._lsh = MinHashLSH(threshold=JACCARD_THRESHOLD, num_perm=NUM_PERM)
        self._entries: dict[str, _CorpusEntry] = {}
        self._last_prune: datetime = datetime.now(timezone.utc)
        self._similar_threshold = (
            similar_threshold if similar_threshold is not None else DEFAULT_SIMILAR_THRESHOLD
        )

    def get_name(self) -> str:
        return "copypasta"

    @property
    def weight(self) -> float:
        return 1.5

    async def apply(self, post: RawPost, context: dict) -> FilterResult:
        self._maybe_prune()

        shingles = _shingle(post.content)
        if not shingles:
            return FilterResult(score=0.0, flagged=False)

        mh = _create_minhash(shingles)
        matches = self._lsh.query(mh)

        unique_authors: set[str] = set()
        max_jaccard = 0.0
        similar_count = 0

        for match_key in matches:
            entry = self._entries.get(match_key)
            if entry is None or entry.author_id == post.author_id:
                continue
            unique_authors.add(entry.author_id)
            jaccard = mh.jaccard(entry.minhash)
            max_jaccard = max(max_jaccard, jaccard)
            similar_count += 1

        unique_count = len(unique_authors)
        flagged = similar_count >= self._similar_threshold or unique_count >= MIN_UNIQUE_AUTHORS

        if unique_count >= 6:
            score = 1.0
        elif unique_count >= 3:
            score = 0.7
        elif unique_count >= 1:
            score = 0.3
        else:
            score = 0.0

        key = f"{post.source}:{post.source_id}"
        self._entries[key] = _CorpusEntry(
            post_id=post.source_id,
            author_id=post.author_id,
            minhash=mh,
            timestamp=datetime.now(timezone.utc),
        )
        self._lsh.insert(key, mh)

        return FilterResult(
            score=score,
            flagged=flagged,
            metadata={
                "copypasta_similar_count": similar_count,
                "copypasta_unique_authors": unique_count,
                "copypasta_max_jaccard": round(max_jaccard, 4),
                "copypasta_author_list": list(unique_authors),
            },
        )

    def _maybe_prune(self) -> None:
        now = datetime.now(timezone.utc)
        if now - self._last_prune < timedelta(hours=1):
            return

        cutoff = now - timedelta(hours=CORPUS_HOURS)
        expired = [k for k, v in self._entries.items() if v.timestamp < cutoff]

        for key in expired:
            self._lsh.remove(key)
            del self._entries[key]

        if expired:
            logger.info("Pruned %d expired copypasta entries", len(expired))
        self._last_prune = now

    def export_state(self) -> dict:
        # Export the corpus, not the LSH object: the entries are enough to
        # rebuild it deterministically and stay picklable across versions.
        return {
            "entries": [
                (key, entry.author_id, entry.minhash, entry.timestamp)
                for key, entry in self._entries.items()
            ],
            "last_prune": self._last_prune,
        }

    def load_state(self, state: dict) -> None:
        for key, author_id, minhash, timestamp in state.get("entries", []):
            self._entries[key] = _CorpusEntry(
                post_id=key, author_id=author_id, minhash=minhash, timestamp=timestamp
            )
            try:
                self._lsh.insert(key, minhash)
            except ValueError:
                # Duplicate key in the snapshot; the entry dict already won.
                logger.warning("Skipped duplicate copypasta corpus key %s", key)
        last_prune = state.get("last_prune")
        if isinstance(last_prune, datetime):
            self._last_prune = last_prune
