import hashlib
import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from criba.filters.base import BaseFilter, FilterResult
from criba.models.raw_post import RawPost

logger = logging.getLogger(__name__)

DEDUP_WINDOW_HOURS = 72


class DeduplicationFilter(BaseFilter):
    
    def __init__(self):
        self._seen: dict[str, list[datetime]] = defaultdict(list)
    
    def get_name(self) -> str:
        return "deduplication"
    
    @property
    def weight(self) -> float:
        return 0.8
    
    def _hash(self, content: str) -> str:
        normalized = " ".join(content.lower().split())
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    
    async def apply(self, post: RawPost, context: dict) -> FilterResult:
        now = datetime.now(timezone.utc)
        content_hash = self._hash(post.content)
        
        self._maybe_prune(now)
        
        is_duplicate = len(self._seen[content_hash]) > 0
        
        self._seen[content_hash].append(now)
        
        if is_duplicate:
            duplicate_count = len(self._seen[content_hash])
            return FilterResult(
                score=0.8,
                flagged=True,
                metadata={
                    "dedup_is_duplicate": True,
                    "dedup_count": duplicate_count,
                },
            )
        
        return FilterResult(
            score=0.0,
            flagged=False,
            metadata={"dedup_is_duplicate": False},
        )
    
    def _maybe_prune(self, now: datetime) -> None:
        cutoff = now - timedelta(hours=DEDUP_WINDOW_HOURS)
        expired_keys = []
        for key, timestamps in self._seen.items():
            self._seen[key] = [t for t in timestamps if t >= cutoff]
            if not self._seen[key]:
                expired_keys.append(key)
        for key in expired_keys:
            del self._seen[key]
