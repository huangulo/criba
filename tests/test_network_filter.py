import pytest

from criba.filters.network import NetworkGraphFilter


@pytest.mark.asyncio
async def test_no_interactions(make_post):
    filter = NetworkGraphFilter()
    post = make_post()
    context = {}
    result = await filter.apply(post, context)
    assert result.score == 0.0
    assert result.flagged is False
    assert result.metadata["network_neighbor_count"] == 0
    assert result.metadata["network_mutual_connections"] == 0


@pytest.mark.asyncio
async def test_mention_creates_edge(make_post):
    filter = NetworkGraphFilter()
    post = make_post(mentions=["user2"])
    context = {}
    result = await filter.apply(post, context)
    assert result.metadata["network_neighbor_count"] == 1
    assert len(result.metadata["network_edges_to_persist"]) == 1


@pytest.mark.asyncio
async def test_reply_creates_edge(make_post):
    filter = NetworkGraphFilter()
    context = {"last_post_author_id": "user2"}
    post = make_post(reply_to="post_1")
    result = await filter.apply(post, context)
    assert result.metadata["network_neighbor_count"] == 1
    assert len(result.metadata["network_edges_to_persist"]) == 1


@pytest.mark.asyncio
async def test_one_way_mentions_are_not_reciprocal(make_post):
    """One-way mentions must not count as mutual connections."""
    filter = NetworkGraphFilter()
    context = {}
    post = make_post(
        author_id="author1",
        source_id="post_1",
        mentions=["user2", "user3", "user4", "user5", "user6"],
    )
    result = await filter.apply(post, context)
    assert result.metadata["network_neighbor_count"] == 5
    assert result.metadata["network_mutual_connections"] == 0
    assert result.score == 0.0
    assert result.flagged is False


@pytest.mark.asyncio
async def test_tight_cluster_detection(make_post):
    filter = NetworkGraphFilter()
    context = {}
    # users 2..7 each mention user1 (user_i -> user1 edges)
    for i in range(2, 8):
        post = make_post(author_id=f"user{i}", source_id=f"post_{i}", mentions=["user1"])
        await filter.apply(post, context)
    # user1 mentions five of them back: genuinely reciprocal links
    final_post = make_post(
        author_id="user1",
        source_id="post_final",
        mentions=["user2", "user3", "user4", "user5", "user6"],
    )
    result = await filter.apply(final_post, context)
    assert result.score >= 0.8
    assert result.flagged is True
    assert result.metadata["network_mutual_connections"] >= 5


@pytest.mark.asyncio
async def test_bidirectional_edges(make_post):
    filter = NetworkGraphFilter()
    context = {}
    post1 = make_post(author_id="user1", source_id="post_1", mentions=["user2"])
    await filter.apply(post1, context)
    post2 = make_post(author_id="user2", source_id="post_2", mentions=["user1"])
    result2 = await filter.apply(post2, context)
    assert result2.metadata["network_mutual_connections"] >= 1


@pytest.mark.asyncio
async def test_multiple_mentions_increases_neighbor_count(make_post):
    filter = NetworkGraphFilter()
    post = make_post(mentions=["user2", "user3", "user4"])
    context = {}
    result = await filter.apply(post, context)
    assert result.metadata["network_neighbor_count"] == 3


@pytest.mark.asyncio
async def test_moderate_mutual_connections_score(make_post):
    filter = NetworkGraphFilter()
    context = {}
    for i in range(2, 5):
        post = make_post(author_id=f"user{i}", source_id=f"post_{i}", mentions=["user1"])
        await filter.apply(post, context)
    final_post = make_post(
        author_id="user1",
        source_id="post_final",
        mentions=["user2", "user3", "user4"],
    )
    result = await filter.apply(final_post, context)
    assert result.score == 0.4
    assert result.flagged is False
