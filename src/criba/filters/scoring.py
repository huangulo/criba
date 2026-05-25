from criba.config import load_config
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
        config = load_config()
        threshold = config.general.heuristic_threshold

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
