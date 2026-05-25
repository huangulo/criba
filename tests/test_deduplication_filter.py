import pytest
import pytest_asyncio

from criba.filters.deduplication import DeduplicationFilter


@pytest.mark.asyncio
async def test_first_occurrence(make_post):
    filter = DeduplicationFilter()
    post = make_post(content="This is a unique post content")
    context = {}
    result = await filter.apply(post, context)
    assert result.score == 0.0
    assert result.flagged is False
    assert result.metadata["dedup_is_duplicate"] is False


@pytest.mark.asyncio
async def test_exact_duplicate(make_post):
    filter = DeduplicationFilter()
    post1 = make_post(source_id="post_1", content="This is duplicate content")
    post2 = make_post(source_id="post_2", content="This is duplicate content")
    context = {}
    result1 = await filter.apply(post1, context)
    result2 = await filter.apply(post2, context)
    assert result1.score == 0.0
    assert result1.flagged is False
    assert result2.score == 0.8
    assert result2.flagged is True
    assert result2.metadata["dedup_is_duplicate"] is True
    assert result2.metadata["dedup_count"] == 2


@pytest.mark.asyncio
async def test_normalized_duplicate(make_post):
    filter = DeduplicationFilter()
    post1 = make_post(source_id="post_1", content="This is duplicate content")
    post2 = make_post(source_id="post_2", content="This    is   duplicate  content")
    post3 = make_post(source_id="post_3", content="This is duplicate content ")
    context = {}
    result1 = await filter.apply(post1, context)
    result2 = await filter.apply(post2, context)
    result3 = await filter.apply(post3, context)
    assert result1.score == 0.0
    assert result2.score == 0.8
    assert result3.score == 0.8
    assert result3.metadata["dedup_count"] == 3


@pytest.mark.asyncio
async def test_different_content(make_post):
    filter = DeduplicationFilter()
    post1 = make_post(source_id="post_1", content="First unique post")
    post2 = make_post(source_id="post_2", content="Second unique post")
    context = {}
    result1 = await filter.apply(post1, context)
    result2 = await filter.apply(post2, context)
    assert result1.score == 0.0
    assert result2.score == 0.0
    assert result1.flagged is False
    assert result2.flagged is False


@pytest.mark.asyncio
async def test_multiple_dedups_increment_counter(make_post):
    filter = DeduplicationFilter()
    content = "Repeated content"
    post1 = make_post(source_id="post_1", content=content)
    post2 = make_post(source_id="post_2", content=content)
    post3 = make_post(source_id="post_3", content=content)
    post4 = make_post(source_id="post_4", content=content)
    context = {}
    await filter.apply(post1, context)
    await filter.apply(post2, context)
    await filter.apply(post3, context)
    result4 = await filter.apply(post4, context)
    assert result4.score == 0.8
    assert result4.metadata["dedup_count"] == 4