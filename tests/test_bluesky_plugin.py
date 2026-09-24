import sys

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
