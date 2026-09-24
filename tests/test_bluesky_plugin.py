import sys
from types import SimpleNamespace

import pytest

from criba.plugins.bluesky.plugin import BlueskyPlugin

# The package __init__ shadows its 'plugin' submodule with the plugin
# instance, so resolve the real module through sys.modules.
bluesky_plugin_module = sys.modules["criba.plugins.bluesky.plugin"]


class FakeClient:
    """AsyncClient stand-in recording logins and firing the session callback."""

    def __init__(self):
        self.login_calls = 0
        self.password_logins = 0
        self.session_imports = 0
        self._session_cb = None

    def on_session_change(self, callback):
        self._session_cb = callback

    async def login(self, login=None, password=None, session_string=None):
        self.login_calls += 1
        if session_string is not None:
            self.session_imports += 1
        elif login and password:
            self.password_logins += 1
        else:
            raise RuntimeError("no credentials")
        if self._session_cb:
            self._session_cb(None)  # the SDK persists the session this way

    def export_session_string(self):
        return "stored-session-string"


async def _drain(plugin, config):
    return [post async for post in plugin.stream(config)]


def _async_returning(value):
    async def getter():
        return value

    return getter


@pytest.fixture
def bluesky_env(monkeypatch, tmp_path):
    monkeypatch.setenv("BLUESKY_SESSION_PATH", str(tmp_path / "bluesky_session.string"))
    monkeypatch.setenv("BLUESKY_HANDLE", "user.bsky.social")
    monkeypatch.setenv("BLUESKY_APP_PASSWORD", "app-password")


@pytest.mark.asyncio
async def test_one_login_across_polls_in_the_same_loop(bluesky_env, monkeypatch):
    fake = FakeClient()
    monkeypatch.setattr(bluesky_plugin_module, "AsyncClient", lambda: fake)
    plugin = BlueskyPlugin()

    await _drain(plugin, {"keywords": ["election"]})
    await _drain(plugin, {"keywords": ["election"]})
    await _drain(plugin, {"handles": ["user.bsky.social"]})

    assert fake.login_calls == 1
    assert fake.password_logins == 1


@pytest.mark.asyncio
async def test_session_is_persisted_and_restored_without_a_password_login(
    bluesky_env, monkeypatch, tmp_path
):
    fake_first = FakeClient()
    monkeypatch.setattr(bluesky_plugin_module, "AsyncClient", lambda: fake_first)
    plugin = BlueskyPlugin()
    await _drain(plugin, {"keywords": ["election"]})

    session_file = tmp_path / "bluesky_session.string"
    assert session_file.read_text().strip() == "stored-session-string"

    # A "new process": fresh plugin instance and fresh client.
    fake_second = FakeClient()
    monkeypatch.setattr(bluesky_plugin_module, "AsyncClient", lambda: fake_second)
    plugin_two = BlueskyPlugin()
    await _drain(plugin_two, {"keywords": ["election"]})

    assert fake_second.login_calls == 1
    assert fake_second.session_imports == 1
    assert fake_second.password_logins == 0


@pytest.mark.asyncio
async def test_stream_skips_without_credentials_or_stored_session(monkeypatch, tmp_path):
    monkeypatch.setenv("BLUESKY_SESSION_PATH", str(tmp_path / "missing.string"))
    monkeypatch.delenv("BLUESKY_HANDLE", raising=False)
    monkeypatch.delenv("BLUESKY_APP_PASSWORD", raising=False)
    fake = FakeClient()
    monkeypatch.setattr(bluesky_plugin_module, "AsyncClient", lambda: fake)
    plugin = BlueskyPlugin()

    posts = await _drain(plugin, {"keywords": ["election"]})
    assert posts == []
    assert fake.login_calls == 0


def _paginated_client(search_pages, feed_pages):
    """AsyncClient stand-in serving cursor-bearing pages.

    Each element of search_pages/feed_pages is (items, cursor); the last page
    repeats if the plugin keeps requesting beyond it.
    """

    calls = {"search": [], "feed": []}

    async def search_posts(params=None):
        calls["search"].append(dict(params or {}))
        posts, cursor = search_pages[min(len(calls["search"]) - 1, len(search_pages) - 1)]
        return SimpleNamespace(posts=posts, cursor=cursor)

    async def get_author_feed(params=None):
        calls["feed"].append(dict(params or {}))
        posts, cursor = feed_pages[min(len(calls["feed"]) - 1, len(feed_pages) - 1)]
        return SimpleNamespace(feed=posts, cursor=cursor)

    client = SimpleNamespace(
        app=SimpleNamespace(
            bsky=SimpleNamespace(
                feed=SimpleNamespace(search_posts=search_posts, get_author_feed=get_author_feed)
            )
        )
    )
    return client, calls


@pytest.mark.asyncio
async def test_search_follows_cursor_until_exhausted(monkeypatch):
    client, calls = _paginated_client(
        search_pages=[(["p1", "p2"], "cursor-1"), (["p3"], None)],
        feed_pages=[],
    )
    plugin = BlueskyPlugin()
    monkeypatch.setattr(plugin, "_get_client", _async_returning(client))
    monkeypatch.setattr(plugin, "_post_to_raw_post", lambda post: post)

    posts = await _drain(plugin, {"keywords": ["election"]})

    assert posts == ["p1", "p2", "p3"]
    assert len(calls["search"]) == 2
    assert "cursor" not in calls["search"][0]
    assert calls["search"][1]["cursor"] == "cursor-1"


@pytest.mark.asyncio
async def test_search_stops_at_max_pages(monkeypatch):
    client, calls = _paginated_client(search_pages=[(["p"], "always-more")], feed_pages=[])
    plugin = BlueskyPlugin()
    monkeypatch.setattr(plugin, "_get_client", _async_returning(client))
    monkeypatch.setattr(plugin, "_post_to_raw_post", lambda post: post)

    posts = await _drain(plugin, {"keywords": ["election"]})

    assert posts == ["p"] * bluesky_plugin_module.MAX_PAGES
    assert len(calls["search"]) == bluesky_plugin_module.MAX_PAGES


@pytest.mark.asyncio
async def test_author_feed_follows_cursor_until_exhausted(monkeypatch):
    client, calls = _paginated_client(
        search_pages=[],
        feed_pages=[(["a1"], "cursor-1"), (["a2", "a3"], None)],
    )
    plugin = BlueskyPlugin()
    monkeypatch.setattr(plugin, "_get_client", _async_returning(client))
    monkeypatch.setattr(plugin, "_post_to_raw_post", lambda post: post)

    posts = await _drain(plugin, {"handles": ["user.bsky.social"]})

    assert posts == ["a1", "a2", "a3"]
    assert len(calls["feed"]) == 2
    assert calls["feed"][0]["actor"] == "user.bsky.social"
    assert "cursor" not in calls["feed"][0]
    assert calls["feed"][1]["cursor"] == "cursor-1"
