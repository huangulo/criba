import httpx
import pytest

from criba.worker import alerts

CAMPAIGN = {"id": "c1", "label": "Test campaign", "confidence": 0.9}

SETTINGS = {
    "slack_webhook_url": "https://hooks.slack.example/services/x",
    "discord_webhook_url": "https://discord.example/api/webhooks/x",
    "telegram_bot_token": "token",
    "telegram_chat_id": "123",
    "confidence_threshold": "0.85",
}


@pytest.fixture
def fake_settings(monkeypatch):
    async def _settings():
        return dict(SETTINGS)

    monkeypatch.setattr(alerts, "_get_notification_settings", _settings)


@pytest.fixture
def allow_any_url(monkeypatch):
    async def _guard(url):
        return None

    # The send path imports the guard inside the function, so patch the source
    # module attribute instead of the alerts namespace.
    monkeypatch.setattr("criba.utils.net.assert_public_http_url", _guard)


@pytest.mark.asyncio
async def test_one_raising_channel_does_not_block_the_rest(fake_settings, allow_any_url, monkeypatch):
    async def broken_slack(url, msg):
        raise httpx.ConnectError("slack is down")

    async def ok_discord(url, msg):
        return True

    async def ok_telegram(token, chat, msg):
        return True

    monkeypatch.setattr(alerts, "_send_slack", broken_slack)
    monkeypatch.setattr(alerts, "_send_discord", ok_discord)
    monkeypatch.setattr(alerts, "_send_telegram", ok_telegram)

    results = await alerts._send_campaign_alert_async(CAMPAIGN)
    assert results == {"slack": False, "discord": True, "telegram": True}


@pytest.mark.asyncio
async def test_all_channels_raising_triggers_a_retry(fake_settings, allow_any_url, monkeypatch):
    async def broken(url, msg):
        raise httpx.ReadTimeout("network down")

    async def broken_telegram(token, chat, msg):
        raise httpx.ReadTimeout("network down")

    monkeypatch.setattr(alerts, "_send_slack", broken)
    monkeypatch.setattr(alerts, "_send_discord", broken)
    monkeypatch.setattr(alerts, "_send_telegram", broken_telegram)

    with pytest.raises(httpx.ReadTimeout):
        await alerts._send_campaign_alert_async(CAMPAIGN)


@pytest.mark.asyncio
async def test_permanent_failures_do_not_trigger_a_retry(fake_settings, allow_any_url, monkeypatch):
    async def rejected(url, msg):
        return False

    async def rejected_telegram(token, chat, msg):
        return False

    monkeypatch.setattr(alerts, "_send_slack", rejected)
    monkeypatch.setattr(alerts, "_send_discord", rejected)
    monkeypatch.setattr(alerts, "_send_telegram", rejected_telegram)

    results = await alerts._send_campaign_alert_async(CAMPAIGN)
    assert results == {"slack": False, "discord": False, "telegram": False}


@pytest.mark.asyncio
async def test_test_alert_reports_failure_instead_of_raising(fake_settings, monkeypatch):
    async def broken(url, msg):
        raise httpx.ConnectError("slack is down")

    monkeypatch.setattr(alerts, "_send_slack", broken)

    result = await alerts.send_test_alert("slack")
    assert result["channel"] == "slack"
    assert result["success"] is False
    assert result["error"]


def test_escape_markdown_neutralizes_all_specials():
    raw = "weird_label [with] *specials* _and_ `ticks`"
    escaped = alerts._escape_markdown(raw)
    assert escaped == "weird\\_label \\[with\\] \\*specials\\* \\_and\\_ \\`ticks\\`"
    # No unescaped special survives.
    import re as re_mod

    assert not re_mod.search(r"(?<!\\)[*_`\[\]]", escaped)


@pytest.mark.asyncio
async def test_telegram_send_escapes_user_content(monkeypatch):
    captured = {}

    class FakeResponse:
        status_code = 200
        text = "ok"

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def post(self, url, json=None):
            captured["url"] = url
            captured["payload"] = json
            return FakeResponse()

    monkeypatch.setattr(alerts.httpx, "AsyncClient", FakeAsyncClient)

    msg = {
        "label": "Shadow_op [coordinated] *push*",
        "confidence_pct": 90,
        "platforms_str": "TELEGRAM, RSS",
        "account_count": 12,
        "post_count": 340,
        "inspector_url": "http://localhost:3030?campaign=abc",
        "campaign_id": "abc",
        "timestamp": "",
    }
    ok = await alerts._send_telegram("token", "chat", msg)

    assert ok is True
    assert captured["url"] == "https://api.telegram.org/bottoken/sendMessage"
    text = captured["payload"]["text"]
    assert "*Shadow\\_op \\[coordinated\\] \\*push\\**" in text
    assert "Platforms: TELEGRAM, RSS" in text
    assert captured["payload"]["parse_mode"] == "Markdown"
