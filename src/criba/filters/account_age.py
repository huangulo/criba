import logging
from datetime import datetime, timezone

from criba.filters.base import BaseFilter, FilterResult
from criba.models.raw_post import RawPost

logger = logging.getLogger(__name__)

NEW_ACCOUNT_DAYS = 7
SUSPICIOUS_ACCOUNT_DAYS = 30
MODERATE_ACCOUNT_DAYS = 90


class AccountAgeFilter(BaseFilter):
    
    def __init__(self, new_account_days: int | None = None):
        self._new_account_days = new_account_days if new_account_days is not None else NEW_ACCOUNT_DAYS
    
    def get_name(self) -> str:
        return "account_age"
    
    @property
    def weight(self) -> float:
        return 1.0
    
    async def apply(self, post: RawPost, context: dict) -> FilterResult:
        if post.author_created_at is None:
            return FilterResult(
                score=0.0,
                flagged=False,
                metadata={"account_age_days": None},
            )
        
        now = datetime.now(timezone.utc)
        age_days = (now - post.author_created_at).days
        
        if age_days <= self._new_account_days:
            score = 0.8
        elif age_days <= SUSPICIOUS_ACCOUNT_DAYS:
            score = 0.5
        elif age_days <= MODERATE_ACCOUNT_DAYS:
            score = 0.2
        else:
            score = 0.0
        
        flagged = age_days <= self._new_account_days
        
        return FilterResult(
            score=score,
            flagged=flagged,
            metadata={
                "account_age_days": age_days,
                "account_is_new": age_days <= self._new_account_days,
            },
        )
