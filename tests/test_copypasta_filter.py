import pytest

from criba.filters.copypasta import CopypastaFilter


@pytest.mark.asyncio
async def test_single_post_no_match(make_post):
    filter = CopypastaFilter()
    long_content = "This is a very long post with many words to ensure that shingles can be extracted properly for testing the copypasta filter with multiple authors and similar content that should trigger the detection mechanism when the same text is posted by different users in a short period of time"
    post = make_post(author_id="author_1", source_id="post_1", content=long_content)
    context = {}
    result = await filter.apply(post, context)
    assert result.score == 0.0
    assert result.flagged is False
    assert result.metadata["copypasta_similar_count"] == 0
    assert result.metadata["copypasta_unique_authors"] == 0


@pytest.mark.asyncio
async def test_three_authors_same_content(make_post):
    filter = CopypastaFilter()
    long_content = "This is a very long post with many words to ensure that shingles can be extracted properly for testing the copypasta filter with multiple authors and similar content that should trigger the detection mechanism when the same text is posted by different users in a short period of time"
    post1 = make_post(author_id="author_1", source_id="post_1", content=long_content)
    post2 = make_post(author_id="author_2", source_id="post_2", content=long_content)
    post3 = make_post(author_id="author_3", source_id="post_3", content=long_content)
    context = {}
    await filter.apply(post1, context)
    await filter.apply(post2, context)
    result3 = await filter.apply(post3, context)
    assert result3.score >= 0.3
    assert result3.metadata["copypasta_unique_authors"] >= 2


@pytest.mark.asyncio
async def test_same_author_no_flag(make_post):
    filter = CopypastaFilter()
    long_content = "This is a very long post with many words to ensure that shingles can be extracted properly for testing the copypasta filter with multiple authors and similar content that should trigger the detection mechanism when the same text is posted by different users in a short period of time"
    post1 = make_post(author_id="author_1", source_id="post_1", content=long_content)
    post2 = make_post(author_id="author_1", source_id="post_2", content=long_content)
    post3 = make_post(author_id="author_1", source_id="post_3", content=long_content)
    context = {}
    await filter.apply(post1, context)
    await filter.apply(post2, context)
    result3 = await filter.apply(post3, context)
    assert result3.score == 0.0
    assert result3.flagged is False
    assert result3.metadata["copypasta_unique_authors"] == 0


@pytest.mark.asyncio
async def test_slightly_different_content_still_detected(make_post):
    filter = CopypastaFilter()
    long_content1 = "This is a very long post with many words to ensure that shingles can be extracted properly for testing the copypasta filter with multiple authors and similar content that should trigger the detection mechanism"
    long_content2 = "This is a very long post with many words to ensure that shingles can be extracted properly for testing the copypasta filter with multiple authors and similar content that should trigger the detection system"
    post1 = make_post(author_id="author_1", source_id="post_1", content=long_content1)
    post2 = make_post(author_id="author_2", source_id="post_2", content=long_content1)
    post3 = make_post(author_id="author_3", source_id="post_3", content=long_content2)
    context = {}
    await filter.apply(post1, context)
    await filter.apply(post2, context)
    result3 = await filter.apply(post3, context)
    assert result3.metadata["copypasta_unique_authors"] >= 1


@pytest.mark.asyncio
async def test_six_authors_high_score(make_post):
    filter = CopypastaFilter()
    long_content = "This is a very long post with many words to ensure that shingles can be extracted properly for testing the copypasta filter with multiple authors and similar content that should trigger the detection mechanism when the same text is posted by different users in a short period of time"
    context = {}
    for i in range(1, 7):
        post = make_post(author_id=f"author_{i}", source_id=f"post_{i}", content=long_content)
        await filter.apply(post, context)
    post7 = make_post(author_id="author_7", source_id="post_7", content=long_content)
    result7 = await filter.apply(post7, context)
    assert result7.score == 1.0
    assert result7.flagged is True