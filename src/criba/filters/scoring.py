from criba.filters.pipeline import FilterPipeline
from criba.filters.language import LanguageFilter
from criba.filters.deduplication import DeduplicationFilter
from criba.filters.copypasta import CopypastaFilter
from criba.filters.temporal import TemporalAnomalyFilter
from criba.filters.account_age import AccountAgeFilter
from criba.filters.hashtag import HashtagCooccurrenceFilter
from criba.filters.network import NetworkGraphFilter


def create_pipeline(threshold: float | None = None) -> FilterPipeline:
    """Create a FilterPipeline with all heuristic filters configured."""
    if threshold is None:
        threshold = 0.6  # fallback default; caller should fetch from DB when possible

    filters = [
        LanguageFilter(),
        DeduplicationFilter(),
        CopypastaFilter(),
        TemporalAnomalyFilter(),
        AccountAgeFilter(),
        HashtagCooccurrenceFilter(),
        NetworkGraphFilter(),
    ]

    return FilterPipeline(filters=filters, threshold=threshold)


async def get_heuristic_threshold() -> float:
    """Fetch the heuristic threshold from system_settings."""
    from sqlalchemy import select
    from criba.db.connection import get_async_session_factory
    from criba.db.models import SystemSetting

    session_factory = get_async_session_factory()
    async with session_factory() as session:
        result = await session.execute(
            select(SystemSetting.value).where(SystemSetting.key == "heuristic_threshold")
        )
        row = result.scalar_one_or_none()
        return float(row) if row else 0.6
