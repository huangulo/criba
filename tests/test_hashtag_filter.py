import pytest
import pytest_asyncio

from criba.filters.hashtag import HashtagCooccurrenceFilter


@pytest.mark.asyncio
async def test_no_hashtags(make_post):
    filter = HashtagCooccurrenceFilter()
    post = make_post(hashtags=[])
    context = {}
    result = await filter.apply(post, context)
    assert result.score == 0.0
    assert result.flagged is False
    assert result.metadata["hashtag_count"] == 0


@pytest.mark.asyncio
async def test_one_hashtag(make_post):
    filter = HashtagCooccurrenceFilter()
    post = make_post(hashtags=["politics"])
    context = {}
    result = await filter.apply(post, context)
    assert result.score == 0.0
    assert result.flagged is False
    assert result.metadata["hashtag_count"] == 1


@pytest.mark.asyncio
async def test_two_hashtags_no_flag(make_post):
    filter = HashtagCooccurrenceFilter()
    post = make_post(hashtags=["politics", "elections"])
    context = {}
    result = await filter.apply(post, context)
    assert result.score == 0.0
    assert result.flagged is False
    assert result.metadata["hashtag_count"] == 2
    assert result.metadata["hashtag_flagged_pairs"] == 0


@pytest.mark.asyncio
async def test_many_hashtags_same_author(make_post):
    filter = HashtagCooccurrenceFilter()
    hashtags = ["politics", "elections", "corruption", "government"]
    post = make_post(hashtags=hashtags)
    context = {}
    result = await filter.apply(post, context)
    assert result.metadata["hashtag_count"] == 4
    assert result.metadata["hashtag_flagged_pairs"] == 0


@pytest.mark.asyncio
async def test_hashtag_pair_accumulation(make_post):
    filter = HashtagCooccurrenceFilter()
    hashtags = ["politics", "elections", "corruption"]
    context = {}
    for i in range(15):
        post = make_post(author_id=f"author_{i}", source_id=f"post_{i}", hashtags=hashtags)
        await filter.apply(post, context)
    final_post = make_post(author_id="author_15", source_id="post_15", hashtags=hashtags)
    result = await filter.apply(final_post, context)
    assert result.metadata["hashtag_flagged_pairs"] == 3


@pytest.mark.asyncio
async def test_normalized_hashtags(make_post):
    filter = HashtagCooccurrenceFilter()
    post1 = make_post(author_id="author_1", source_id="post_1", hashtags=["Politics", "Elections"])
    post2 = make_post(author_id="author_2", source_id="post_2", hashtags=["politics", "elections"])
    context = {}
    await filter.apply(post1, context)
    result2 = await filter.apply(post2, context)
    assert result2.metadata["hashtag_count"] == 2
    assert result2.metadata["hashtag_max_cooccurrence"] == 2