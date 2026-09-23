from criba.filters.pipeline import FilterPipeline
from criba.filters.language import LanguageFilter
from criba.filters.deduplication import DeduplicationFilter
from criba.filters.copypasta import CopypastaFilter
from criba.filters.temporal import TemporalAnomalyFilter
from criba.filters.account_age import AccountAgeFilter
from criba.filters.hashtag import HashtagCooccurrenceFilter
from criba.filters.network import NetworkGraphFilter

DEFAULT_SCORING_SETTINGS = {
    "heuristic_threshold": 0.6,
    "copypasta_threshold": 10,
    "temporal_cluster_min": 5,
    "new_account_days": 7,
}


def create_pipeline(
    threshold: float | None = None,
    copypasta_threshold: int | None = None,
    temporal_cluster_min: int | None = None,
    new_account_days: int | None = None,
) -> FilterPipeline:
    """Create a FilterPipeline with all heuristic filters configured.

    Each setting maps to the matching system_settings key; None falls back
    to the built-in defaults in DEFAULT_SCORING_SETTINGS.
    """
    if threshold is None:
        threshold = DEFAULT_SCORING_SETTINGS["heuristic_threshold"]

    filters = [
        LanguageFilter(),
        DeduplicationFilter(),
        CopypastaFilter(similar_threshold=copypasta_threshold),
        TemporalAnomalyFilter(cluster_min=temporal_cluster_min),
        AccountAgeFilter(new_account_days=new_account_days),
        HashtagCooccurrenceFilter(),
        NetworkGraphFilter(),
    ]

    return FilterPipeline(filters=filters, threshold=threshold)


async def get_scoring_settings() -> dict[str, float | int]:
    """Fetch all heuristic scoring settings from system_settings."""
    from sqlalchemy import select
    from criba.db.connection import get_async_session_factory
    from criba.db.models import SystemSetting

    session_factory = get_async_session_factory()
    async with session_factory() as session:
        result = await session.execute(
            select(SystemSetting.key, SystemSetting.value).where(
                SystemSetting.key.in_(DEFAULT_SCORING_SETTINGS)
            )
        )
        stored = {key: value for key, value in result.all()}

    settings: dict[str, float | int] = {}
    for key, default in DEFAULT_SCORING_SETTINGS.items():
        try:
            settings[key] = type(default)(stored.get(key, default))
        except (TypeError, ValueError):
            settings[key] = default
    return settings
