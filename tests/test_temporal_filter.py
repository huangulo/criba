from datetime import UTC, datetime

import pytest

from criba.filters.temporal import TemporalAnomalyFilter


@pytest.mark.asyncio
async def test_warmup_period(make_post):
    filter = TemporalAnomalyFilter()
    context = {}
    for i in range(99):
        post = make_post(source_id=f"post_{i}", published_at=datetime(2025, 1, 15, i % 24, 0, 0, tzinfo=UTC))
        result = await filter.apply(post, context)
        assert result.score == 0.0
        assert result.flagged is False
        assert result.metadata["temporal_warmup"] is True


@pytest.mark.asyncio
async def test_after_warmup_normal_hour(make_post):
    filter = TemporalAnomalyFilter()
    context = {}
    for i in range(100):
        post = make_post(source_id=f"post_{i}", published_at=datetime(2025, 1, 15, i % 24, 0, 0, tzinfo=UTC))
        await filter.apply(post, context)
    post_after = make_post(source_id="post_101", published_at=datetime(2025, 1, 15, 12, 0, 0, tzinfo=UTC))
    result = await filter.apply(post_after, context)
    assert "temporal_percentile_rank" in result.metadata


@pytest.mark.asyncio
async def test_different_sources_separate_warmup(make_post):
    filter = TemporalAnomalyFilter()
    context = {}
    post1 = make_post(source="telegram", source_id="post_1", published_at=datetime(2025, 1, 15, 14, 0, 0, tzinfo=UTC))
    result1 = await filter.apply(post1, context)
    assert result1.metadata["temporal_warmup"] is True
    assert result1.metadata["temporal_warmup_progress"] == 1
    post2 = make_post(source="reddit", source_id="post_1", published_at=datetime(2025, 1, 15, 14, 0, 0, tzinfo=UTC))
    result2 = await filter.apply(post2, context)
    assert result2.metadata["temporal_warmup"] is True
    assert result2.metadata["temporal_warmup_progress"] == 1


@pytest.mark.asyncio
async def test_hour_tracking(make_post):
    filter = TemporalAnomalyFilter()
    context = {}
    for hour in range(10):
        for minute in range(10):
            post = make_post(source_id=f"post_{hour}_{minute}", published_at=datetime(2025, 1, 15, hour, minute, 0, tzinfo=UTC))
            await filter.apply(post, context)
    post_test = make_post(source_id="post_test", published_at=datetime(2025, 1, 15, 5, 0, 0, tzinfo=UTC))
    result = await filter.apply(post_test, context)
    assert "temporal_percentile_rank" in result.metadata