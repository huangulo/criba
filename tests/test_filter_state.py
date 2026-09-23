import pickle

import pytest

from criba.filters.account_age import AccountAgeFilter
from criba.filters.copypasta import CopypastaFilter
from criba.filters.deduplication import DeduplicationFilter
from criba.filters.hashtag import HashtagCooccurrenceFilter
from criba.filters.language import LanguageFilter
from criba.filters.network import NetworkGraphFilter
from criba.filters.temporal import TemporalAnomalyFilter


def _persist_roundtrip(snapshot: dict) -> dict:
    """Simulate what criba.filters.state does to a snapshot before storing it."""
    return pickle.loads(pickle.dumps(snapshot))


def test_stateless_filters_export_none():
    assert LanguageFilter().export_state() is None
    assert AccountAgeFilter().export_state() is None


@pytest.mark.asyncio
async def test_deduplication_state_survives_roundtrip(make_post):
    original = DeduplicationFilter()
    await original.apply(make_post(content="shared message"), {})

    restored = DeduplicationFilter()
    restored.load_state(_persist_roundtrip(original.export_state()))
    result_restored = await restored.apply(
        make_post(source_id="post_2", content="shared message"), {}
    )
    assert result_restored.flagged is True
    assert result_restored.metadata["dedup_count"] == 2

    control = DeduplicationFilter()
    result_control = await control.apply(
        make_post(source_id="post_2", content="shared message"), {}
    )
    assert result_control.flagged is False


@pytest.mark.asyncio
async def test_copypasta_state_survives_roundtrip(make_post):
    corpus = "a coordinated message about the election results today spread widely"
    original = CopypastaFilter(similar_threshold=3)
    for i in range(4):
        await original.apply(
            make_post(source_id=f"p{i}", author_id=f"author_{i}", content=corpus), {}
        )

    restored = CopypastaFilter(similar_threshold=3)
    restored.load_state(_persist_roundtrip(original.export_state()))
    probe = make_post(source_id="probe", author_id="new_author", content=corpus)
    result_restored = await restored.apply(probe, {})
    assert result_restored.metadata["copypasta_similar_count"] > 0
    assert result_restored.metadata["copypasta_unique_authors"] == 4

    control = CopypastaFilter(similar_threshold=3)
    result_control = await control.apply(probe, {})
    assert result_control.metadata["copypasta_similar_count"] == 0


@pytest.mark.asyncio
async def test_temporal_state_survives_roundtrip(make_post):
    original = TemporalAnomalyFilter()
    for i in range(100):  # pass the warmup window
        await original.apply(make_post(source_id=f"p{i}"), {})

    restored = TemporalAnomalyFilter()
    restored.load_state(_persist_roundtrip(original.export_state()))
    result_restored = await restored.apply(make_post(source_id="probe"), {})
    assert "temporal_warmup" not in result_restored.metadata

    control = TemporalAnomalyFilter()
    result_control = await control.apply(make_post(source_id="probe"), {})
    assert result_control.metadata.get("temporal_warmup") is True


@pytest.mark.asyncio
async def test_hashtag_state_survives_roundtrip(make_post):
    original = HashtagCooccurrenceFilter()
    for i in range(4):
        await original.apply(
            make_post(source_id=f"p{i}", author_id=f"author_{i}", hashtags=["alpha", "beta", "gamma"]),
            {},
        )

    restored = HashtagCooccurrenceFilter()
    restored.load_state(_persist_roundtrip(original.export_state()))
    result_restored = await restored.apply(
        make_post(source_id="probe", author_id="author_x", hashtags=["alpha", "beta", "gamma"]),
        {},
    )
    assert result_restored.metadata["hashtag_max_cooccurrence"] == 5

    control = HashtagCooccurrenceFilter()
    result_control = await control.apply(
        make_post(source_id="probe", author_id="author_x", hashtags=["alpha", "beta", "gamma"]),
        {},
    )
    assert result_control.metadata["hashtag_max_cooccurrence"] == 1


@pytest.mark.asyncio
async def test_network_state_survives_roundtrip(make_post):
    original = NetworkGraphFilter()
    await original.apply(make_post(author_id="alice", mentions=["bob"]), {})

    restored = NetworkGraphFilter()
    restored.load_state(_persist_roundtrip(original.export_state()))
    result_restored = await restored.apply(make_post(author_id="alice", mentions=[]), {})
    assert result_restored.metadata["network_neighbor_count"] == 1

    control = NetworkGraphFilter()
    result_control = await control.apply(make_post(author_id="alice", mentions=[]), {})
    assert result_control.metadata["network_neighbor_count"] == 0
