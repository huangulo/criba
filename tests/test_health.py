"""Health endpoint: dependency checks and status mapping."""

import json

import pytest

from criba.api import health as health_module
from criba.api.health import _check_ollama, _check_postgres, _check_redis, health


class _FakePgSession:
    def __init__(self, fail=False, hang=False):
        self._fail = fail
        self._hang = hang

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def execute(self, stmt):
        if self._hang:
            import asyncio

            await asyncio.sleep(10)
        if self._fail:
            raise RuntimeError("connection refused")


@pytest.mark.asyncio
async def test_check_postgres_ok(monkeypatch):
    monkeypatch.setattr("criba.db.connection.get_async_session_factory", lambda: lambda: _FakePgSession())
    assert await _check_postgres() == "ok"


@pytest.mark.asyncio
async def test_check_postgres_down_on_connection_error(monkeypatch):
    monkeypatch.setattr(
        "criba.db.connection.get_async_session_factory", lambda: lambda: _FakePgSession(fail=True)
    )
    assert await _check_postgres() == "down"


@pytest.mark.asyncio
async def test_check_postgres_down_on_timeout(monkeypatch):
    # A hung connect must not stall the probe past its bound.
    monkeypatch.setattr(health_module, "CHECK_TIMEOUT_SECONDS", 0.1)
    monkeypatch.setattr(
        "criba.db.connection.get_async_session_factory", lambda: lambda: _FakePgSession(hang=True)
    )
    assert await _check_postgres() == "down"


class _FakeRedis:
    def __init__(self, fail=False):
        self._fail = fail
        self.closed = False

    async def ping(self):
        if self._fail:
            raise ConnectionError("no redis")

    async def aclose(self):
        self.closed = True


@pytest.mark.asyncio
async def test_check_redis_ok_and_closes_client(monkeypatch):
    client = _FakeRedis()
    monkeypatch.setattr("redis.asyncio.from_url", lambda url, socket_timeout=None: client)
    assert await _check_redis() == "ok"
    assert client.closed


@pytest.mark.asyncio
async def test_check_redis_down_on_connection_error(monkeypatch):
    client = _FakeRedis(fail=True)
    monkeypatch.setattr("redis.asyncio.from_url", lambda url, socket_timeout=None: client)
    assert await _check_redis() == "down"
    assert client.closed  # the client is still released on failure


class _FakeOllama:
    def __init__(self, available=True, raises=False):
        self._available = available
        self._raises = raises

    async def is_available(self):
        if self._raises:
            raise RuntimeError("constructor state broken")
        return self._available


@pytest.mark.asyncio
async def test_check_ollama_reports_availability(monkeypatch):
    monkeypatch.setattr("criba.llm.client.OllamaClient", lambda: _FakeOllama(available=True))
    assert await _check_ollama() == "ok"

    monkeypatch.setattr("criba.llm.client.OllamaClient", lambda: _FakeOllama(available=False))
    assert await _check_ollama() == "down"


@pytest.mark.asyncio
async def test_check_ollama_down_on_probe_failure(monkeypatch):
    monkeypatch.setattr("criba.llm.client.OllamaClient", lambda: _FakeOllama(raises=True))
    assert await _check_ollama() == "down"


def _stub_checks(monkeypatch, postgres="ok", redis="ok", ollama="ok"):
    async def _pg():
        return postgres

    async def _redis():
        return redis

    async def _ollama():
        return ollama

    monkeypatch.setattr(health_module, "_check_postgres", _pg)
    monkeypatch.setattr(health_module, "_check_redis", _redis)
    monkeypatch.setattr(health_module, "_check_ollama", _ollama)


async def _body(response) -> dict:
    return json.loads(response.body)


@pytest.mark.asyncio
async def test_health_all_up(monkeypatch):
    _stub_checks(monkeypatch)
    response = await health()
    body = await _body(response)
    assert response.status_code == 200
    assert body["status"] == "ok"
    assert body["dependencies"] == {"postgres": "ok", "redis": "ok", "ollama": "ok"}
    assert body["checked_at"]


@pytest.mark.asyncio
async def test_health_degraded_when_only_ollama_is_down(monkeypatch):
    # The API serves fine without Ollama; the container must stay healthy.
    _stub_checks(monkeypatch, ollama="down")
    response = await health()
    body = await _body(response)
    assert response.status_code == 200
    assert body["status"] == "degraded"


@pytest.mark.asyncio
async def test_health_down_when_core_dependency_fails(monkeypatch):
    _stub_checks(monkeypatch, postgres="down")
    response = await health()
    assert response.status_code == 503
    assert (await _body(response))["status"] == "down"

    _stub_checks(monkeypatch, redis="down")
    response = await health()
    assert response.status_code == 503
    assert (await _body(response))["status"] == "down"


def test_health_route_serves_without_the_api_key(monkeypatch):
    # Infra probes carry no credentials: /health must answer (200 or a
    # dependency-driven 503) even with auth enforced, while /api routes
    # reject the same keyless request with 401.
    from fastapi.testclient import TestClient

    from criba.api.main import app

    monkeypatch.setenv("CRIBA_API_KEY", "test-secret")
    client = TestClient(app)  # no context manager: lifespan (redis subscriber) stays off

    response = client.get("/health")
    assert response.status_code in (200, 503)
    assert response.json()["status"] in ("ok", "degraded", "down")

    protected = client.get("/api/narratives")
    assert protected.status_code == 401
