from types import SimpleNamespace

from criba.plugins.rss.plugin import MAX_SOURCE_ID_CHARS, RSSPlugin, _bounded_source_id


def _entry(**overrides):
    base = {
        "id": "",
        "link": "",
        "title": "Headline",
        "summary": "Body text of the entry",
        "author": "Author Name",
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def _to_raw_post(entry):
    return RSSPlugin()._entry_to_raw_post(entry, "test-feed")


def test_short_ids_pass_through_unchanged():
    assert _bounded_source_id("https://example.com/post/1") == "https://example.com/post/1"
    assert _bounded_source_id("x" * MAX_SOURCE_ID_CHARS) == "x" * MAX_SOURCE_ID_CHARS


def test_long_ids_hash_to_a_stable_short_form():
    long_id = "https://example.com/p?" + "q" * 400
    bounded = _bounded_source_id(long_id)
    assert len(bounded) <= MAX_SOURCE_ID_CHARS
    assert bounded.startswith("long:")
    assert _bounded_source_id(long_id) == bounded  # stable across polls
    assert _bounded_source_id("https://example.com/p?" + "r" * 400) != bounded


def test_entry_with_overlong_id_produces_insertable_source_id():
    post = _to_raw_post(_entry(id="tag:example.com,2026:" + "z" * 500))
    assert len(post.source_id) <= MAX_SOURCE_ID_CHARS
    assert post.source_id.startswith("long:")


def test_entry_without_id_or_link_gets_stable_derived_id():
    same_a = _to_raw_post(_entry())
    same_b = _to_raw_post(_entry())
    assert same_a.source_id == same_b.source_id  # repeats dedup
    assert same_a.source_id.startswith("derived:")

    different = _to_raw_post(_entry(summary="A completely different body"))
    assert different.source_id != same_a.source_id  # distinct entries stay distinct

    other_feed = RSSPlugin()._entry_to_raw_post(_entry(), "other-feed")
    assert other_feed.source_id != same_a.source_id
