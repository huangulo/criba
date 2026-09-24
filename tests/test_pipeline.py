from datetime import UTC, datetime, timedelta

import pytest

from criba.filters.account_age import AccountAgeFilter
from criba.filters.deduplication import DeduplicationFilter
from criba.filters.hashtag import HashtagCooccurrenceFilter
from criba.filters.language import LanguageFilter
from criba.filters.network import NetworkGraphFilter
from criba.filters.pipeline import FilterPipeline


class BrokenFilter(LanguageFilter):
    def get_name(self) -> str:
        return "broken"

    async def apply(self, post, context):
        raise RuntimeError("This filter always fails")


@pytest.mark.asyncio
async def test_pipeline_runs_all_filters(make_post):
    filters = [
        LanguageFilter(),
        DeduplicationFilter(),
        AccountAgeFilter(),
        HashtagCooccurrenceFilter(),
        NetworkGraphFilter(),
    ]
    pipeline = FilterPipeline(filters, threshold=0.6)
    post = make_post()
    result = await pipeline.run(post)
    assert result.composite_score >= 0.0
    assert result.composite_score <= 1.0
    assert len(result.filter_results) == 5
    assert "language" in result.filter_results
    assert "deduplication" in result.filter_results
    assert "account_age" in result.filter_results
    assert "hashtag_cooccurrence" in result.filter_results
    assert "network_graph" in result.filter_results


@pytest.mark.asyncio
async def test_pipeline_threshold(make_post):
    filters = [LanguageFilter()]
    pipeline = FilterPipeline(filters, threshold=0.2)
    post = make_post(content="This is English text")
    result = await pipeline.run(post)
    assert result.composite_score > 0
    assert result.should_send_to_llm is True


@pytest.mark.asyncio
async def test_filter_failure_handled(make_post):
    filters = [BrokenFilter(), LanguageFilter()]
    pipeline = FilterPipeline(filters, threshold=0.6)
    post = make_post()
    result = await pipeline.run(post)
    assert len(result.filter_results) == 2
    assert result.filter_results["broken"].score == 0.0
    assert result.filter_results["language"].score >= 0.0


@pytest.mark.asyncio
async def test_composite_score_calculation(make_post):
    filters = [LanguageFilter(), DeduplicationFilter()]
    pipeline = FilterPipeline(filters, threshold=0.5)
    post = make_post(content="This is a test post")
    result1 = await pipeline.run(post)
    result2 = await pipeline.run(make_post(source_id="post_2", content="This is a test post"))
    assert result2.composite_score > result1.composite_score


@pytest.mark.asyncio
async def test_pipeline_with_account_age_filter(make_post):
    filters = [AccountAgeFilter()]
    pipeline = FilterPipeline(filters, threshold=0.5)
    now = datetime.now(UTC)
    post = make_post(author_created_at=now - timedelta(days=5))
    result = await pipeline.run(post)
    assert result.composite_score == 0.8
    assert result.should_send_to_llm is True
    assert result.filter_results["account_age"].flagged is True


@pytest.mark.asyncio
async def test_pipeline_with_network_filter(make_post):
    filters = [NetworkGraphFilter()]
    pipeline = FilterPipeline(filters, threshold=0.6)
    post = make_post(mentions=["user2", "user3"])
    result = await pipeline.run(post)
    assert "network_graph" in result.filter_results
    assert result.filter_results["network_graph"].metadata["network_neighbor_count"] == 2


@pytest.mark.asyncio
async def test_pipeline_clamped_score(make_post):
    filters = [LanguageFilter()]
    pipeline = FilterPipeline(filters, threshold=0.6)
    post = make_post(content="This is English content that should not match")
    result = await pipeline.run(post)
    assert result.composite_score >= 0.0
    assert result.composite_score <= 1.0