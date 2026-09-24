"""Pagination behavior of the YouTube plugin's comment fetching."""

import sys

import pytest

from criba.plugins.youtube.plugin import YouTubePlugin

# The package __init__ shadows its 'plugin' submodule with the plugin
# instance, so resolve the real module through sys.modules.
youtube_plugin_module = sys.modules["criba.plugins.youtube.plugin"]


def _thread(comment_id):
    return {
        "snippet": {
            "topLevelComment": {
                "id": comment_id,
                "snippet": {
                    "textDisplay": f"Comment {comment_id}",
                    "publishedAt": "2026-01-01T00:00:00Z",
                    "authorDisplayName": "alice",
                    "authorChannelId": {"value": "UC-alice"},
                    "likeCount": 1,
                    "canReply": True,
                },
            }
        },
        "replies": {"comments": []},
    }


def _fake_youtube(comment_pages):
    """googleapiclient build() stand-in serving canned comment pages.

    Each page is a commentThreads response dict; the last page repeats if
    the plugin keeps requesting beyond it.
    """
    state = {"pages": list(comment_pages), "search_calls": [], "comment_calls": []}

    class SearchList:
        def __init__(self, kwargs):
            self.kwargs = kwargs

        def execute(self):
            state["search_calls"].append(dict(self.kwargs))
            return {
                "items": [
                    {"id": {"videoId": "vid1"}, "snippet": {"title": "Video One"}},
                ]
            }

    class Search:
        def list(self, **kwargs):
            return SearchList(kwargs)

    class CommentThreadsList:
        def __init__(self, kwargs):
            self.kwargs = kwargs

        def execute(self):
            state["comment_calls"].append(dict(self.kwargs))
            if len(state["pages"]) > 1:
                return state["pages"].pop(0)
            return state["pages"][0]

    class CommentThreads:
        def list(self, **kwargs):
            return CommentThreadsList(kwargs)

    class Youtube:
        def search(self):
            return Search()

        def commentThreads(self):
            return CommentThreads()

    return Youtube(), state


async def _drain(plugin, config):
    return [post async for post in plugin.stream(config)]


@pytest.mark.asyncio
async def test_comments_follow_next_page_token_until_exhausted(monkeypatch):
    pages = [
        {"items": [_thread("c1"), _thread("c2")], "nextPageToken": "pt2"},
        {"items": [_thread("c3")]},
    ]
    fake, state = _fake_youtube(pages)
    monkeypatch.setenv("YOUTUBE_API_KEY", "fake-key")
    monkeypatch.setattr(youtube_plugin_module, "build", lambda *a, **k: fake)
    plugin = YouTubePlugin()

    posts = await _drain(plugin, {"channels": ["UCabc"]})

    assert [p.source_id for p in posts] == ["c1", "c2", "c3"]
    assert len(state["comment_calls"]) == 2
    assert "pageToken" not in state["comment_calls"][0]
    assert state["comment_calls"][1]["pageToken"] == "pt2"


@pytest.mark.asyncio
async def test_comments_stop_at_max_comment_pages(monkeypatch):
    # A viral video always offering another page must not monopolize the run.
    pages = [{"items": [_thread("c1")], "nextPageToken": "always-more"}]
    fake, state = _fake_youtube(pages)
    monkeypatch.setenv("YOUTUBE_API_KEY", "fake-key")
    monkeypatch.setattr(youtube_plugin_module, "build", lambda *a, **k: fake)
    plugin = YouTubePlugin()

    posts = await _drain(plugin, {"channels": ["UCabc"]})

    assert len(posts) == youtube_plugin_module.MAX_COMMENT_PAGES
    assert len(state["comment_calls"]) == youtube_plugin_module.MAX_COMMENT_PAGES


@pytest.mark.asyncio
async def test_search_requests_the_largest_page_available(monkeypatch):
    # search.list costs the same quota units regardless of maxResults.
    fake, state = _fake_youtube([{"items": [_thread("c1")]}])
    monkeypatch.setenv("YOUTUBE_API_KEY", "fake-key")
    monkeypatch.setattr(youtube_plugin_module, "build", lambda *a, **k: fake)
    plugin = YouTubePlugin()

    await _drain(plugin, {"channels": ["UCabc"]})

    assert state["search_calls"][0]["maxResults"] == 50
