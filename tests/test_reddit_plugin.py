"""Pagination behavior of the Reddit plugin's /new.json polling."""

import sys

import pytest

from criba.plugins.reddit.plugin import RedditPlugin

# The package __init__ shadows its 'plugin' submodule with the plugin
# instance, so resolve the real module through sys.modules.
reddit_plugin_module = sys.modules["criba.plugins.reddit.plugin"]


def _t3(name):
    return {
        "kind": "t3",
        "data": {
            "name": name,
            "id": name,
            "title": f"Post {name}",
            "selftext": "",
            "author": "alice",
            "subreddit": "colombia",
            "permalink": f"/r/colombia/comments/{name}/post_{name}/",
            "created_utc": 1760000000,
            "score": 1,
            "upvote_ratio": 0.9,
            "num_comments": 0,
        },
    }


class FakeRedditResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


class FakeRedditClient:
    """httpx.AsyncClient stand-in serving canned /new.json pages forever.

    Each page is (children, after); the last page repeats if the plugin
    keeps requesting beyond it.
    """

    def __init__(self, pages):
        self._pages = pages
        self.calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get(self, url, params=None):
        self.calls.append((url, dict(params or {})))
        children, after = self._pages[min(len(self.calls) - 1, len(self._pages) - 1)]
        return FakeRedditResponse({"data": {"children": children, "after": after}})


async def _drain(plugin, config):
    return [post async for post in plugin.stream(config)]


@pytest.mark.asyncio
async def test_new_listing_follows_after_token_until_exhausted(monkeypatch):
    pages = [
        ([_t3("a"), _t3("b")], "t3_a"),
        ([_t3("c")], None),
    ]
    fake = FakeRedditClient(pages)
    monkeypatch.setattr(reddit_plugin_module.httpx, "AsyncClient", lambda *a, **k: fake)
    plugin = RedditPlugin()

    posts = await _drain(plugin, {"subreddits": ["colombia"]})

    assert [p.source_id for p in posts] == ["a", "b", "c"]
    assert len(fake.calls) == 2
    assert fake.calls[0][0].endswith("/r/colombia/new.json")
    assert "after" not in fake.calls[0][1]
    assert fake.calls[1][1]["after"] == "t3_a"


@pytest.mark.asyncio
async def test_new_listing_stops_at_max_pages(monkeypatch):
    # A busy subreddit always offering another page must not monopolize the run.
    fake = FakeRedditClient([([_t3("x")], "t3_x")])
    monkeypatch.setattr(reddit_plugin_module.httpx, "AsyncClient", lambda *a, **k: fake)
    plugin = RedditPlugin()

    posts = await _drain(plugin, {"subreddits": ["colombia"]})

    assert len(posts) == reddit_plugin_module.MAX_PAGES
    assert len(fake.calls) == reddit_plugin_module.MAX_PAGES


@pytest.mark.asyncio
async def test_new_listing_requests_full_pages(monkeypatch):
    # The old implementation fetched 25 posts per poll; the poll gap on
    # active subreddits silently dropped everything in between.
    fake = FakeRedditClient([([_t3("x")], None)])
    monkeypatch.setattr(reddit_plugin_module.httpx, "AsyncClient", lambda *a, **k: fake)
    plugin = RedditPlugin()

    await _drain(plugin, {"subreddits": ["colombia"]})

    assert fake.calls[0][1]["limit"] == reddit_plugin_module.PAGE_LIMIT
