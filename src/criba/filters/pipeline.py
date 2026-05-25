import logging
from dataclasses import dataclass, field

from criba.models.raw_post import RawPost
from .base import BaseFilter, FilterResult

logger = logging.getLogger(__name__)


@dataclass
class PipelineResult:
    composite_score: float  # 0.0 - 1.0
    should_send_to_llm: bool
    filter_results: dict[str, FilterResult] = field(default_factory=dict)


class FilterPipeline:
    """Orchestrates the sequential execution of heuristic filters."""

    def __init__(self, filters: list[BaseFilter], threshold: float = 0.6):
        self.filters = filters
        self.threshold = threshold

    async def run(self, post: RawPost) -> PipelineResult:
        """Run all filters and compute composite anomaly score."""
        context: dict = {}
        filter_results: dict[str, FilterResult] = {}
        weighted_sum = 0.0
        total_weight = 0.0

        for f in self.filters:
            try:
                result = await f.apply(post, context)
                filter_results[f.get_name()] = result
                weighted_sum += result.score * f.weight
                total_weight += f.weight
                context[f"last_{f.get_name()}_score"] = result.score
                context.update(result.metadata)
            except Exception:
                logger.exception("Filter %s failed for post %s", f.get_name(), post.source_id)
                filter_results[f.get_name()] = FilterResult(score=0.0, flagged=False)

        composite = weighted_sum / total_weight if total_weight > 0 else 0.0
        composite = min(1.0, max(0.0, composite))

        return PipelineResult(
            composite_score=composite,
            should_send_to_llm=composite >= self.threshold,
            filter_results=filter_results,
        )
