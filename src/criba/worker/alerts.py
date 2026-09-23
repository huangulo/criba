import asyncio
import logging

import httpx

from criba.celery_app import app

logger = logging.getLogger(__name__)

DASHBOARD_BASE_URL = "http://localhost:3030"


def _build_message(campaign: dict) -> dict:
    label = campaign.get("label", "Unnamed Campaign")
    confidence = campaign.get("confidence", 0)
    platforms = campaign.get("platforms", [])
    account_count = campaign.get("account_count", 0)
    post_count = campaign.get("post_count", 0)
    campaign_id = campaign.get("id", "")

    confidence_pct = round(confidence * 100) if confidence else 0
    platforms_str = ", ".join(p.upper() for p in (platforms or []))
    inspector_url = f"{DASHBOARD_BASE_URL}?campaign={campaign_id}"

    return {
        "label": label,
        "confidence_pct": confidence_pct,
        "platforms_str": platforms_str,
        "account_count": account_count,
        "post_count": post_count,
        "inspector_url": inspector_url,
        "campaign_id": str(campaign_id),
    }


async def _send_slack(webhook_url: str, msg: dict) -> bool:
    text = (
        f"🚨 *Astroturfing Campaign Detected*\n"
        f"*{msg['label']}*\n"
        f"Confidence: *{msg['confidence_pct']}%* | "
        f"Platforms: {msg['platforms_str']} | "
        f"Authors: {msg['account_count']} | Posts: {msg['post_count']}\n"
        f"<{msg['inspector_url']}|View Campaign Inspector>"
    )
    payload = {"text": text}
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(webhook_url, json=payload)
        if resp.status_code == 200:
            logger.info("Slack alert sent successfully")
            return True
        logger.error("Slack alert failed: %d %s", resp.status_code, resp.text)
        return False


async def _send_discord(webhook_url: str, msg: dict) -> bool:
    embed = {
        "title": "🚨 Astroturfing Campaign Detected",
        "description": (
            f"**{msg['label']}**\n\n"
            f"**Confidence:** {msg['confidence_pct']}%\n"
            f"**Platforms:** {msg['platforms_str']}\n"
            f"**Authors:** {msg['account_count']} | **Posts:** {msg['post_count']}\n\n"
            f"[View Campaign Inspector]({msg['inspector_url']})"
        ),
        "color": 16711680,
        "timestamp": msg.get("timestamp", ""),
    }
    payload = {"embeds": [embed]}
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(webhook_url, json=payload)
        if resp.status_code in (200, 204):
            logger.info("Discord alert sent successfully")
            return True
        logger.error("Discord alert failed: %d %s", resp.status_code, resp.text)
        return False


async def _send_telegram(bot_token: str, chat_id: str, msg: dict) -> bool:
    text = (
        f"🚨 *Astroturfing Campaign Detected*\n\n"
        f"*{msg['label']}*\n\n"
        f"Confidence: *{msg['confidence_pct']}%*\n"
        f"Platforms: {msg['platforms_str']}\n"
        f"Authors: {msg['account_count']} | Posts: {msg['post_count']}\n\n"
        f"[View Campaign Inspector]({msg['inspector_url']})"
    )
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True,
    }
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(url, json=payload)
        if resp.status_code == 200:
            logger.info("Telegram alert sent successfully")
            return True
        logger.error("Telegram alert failed: %d %s", resp.status_code, resp.text)
        return False


async def _get_notification_settings() -> dict[str, str]:
    """Fetch notification settings from system_settings table."""
    from sqlalchemy import select
    from criba.db.connection import get_async_session_factory
    from criba.db.models import SystemSetting

    keys = [
        "slack_webhook_url", "discord_webhook_url",
        "telegram_bot_token", "telegram_chat_id", "confidence_threshold",
    ]
    settings = {}
    session_factory = get_async_session_factory()
    async with session_factory() as session:
        for key in keys:
            result = await session.execute(
                select(SystemSetting.value).where(SystemSetting.key == key)
            )
            row = result.scalar_one_or_none()
            settings[key] = row or ""
    return settings


async def _send_campaign_alert_async(campaign_data: dict) -> dict:
    from criba.utils.net import assert_public_http_url

    notif = await _get_notification_settings()
    msg = _build_message(campaign_data)
    msg["timestamp"] = campaign_data.get("detected_at", "")

    results: dict[str, bool] = {}
    raised: list[Exception] = []

    async def attempt(name: str, send) -> None:
        """Send to one channel; its failure must never block the others."""
        try:
            results[name] = await send()
        except Exception as exc:
            logger.exception("%s alert raised; continuing with the other channels", name.capitalize())
            results[name] = False
            raised.append(exc)

    if notif.get("slack_webhook_url"):
        slack_webhook = notif["slack_webhook_url"]
        try:
            await assert_public_http_url(slack_webhook)
        except ValueError as exc:
            logger.error("Slack webhook rejected: %s", exc)
            results["slack"] = False
        else:
            await attempt("slack", lambda: _send_slack(slack_webhook, msg))
    if notif.get("discord_webhook_url"):
        discord_webhook = notif["discord_webhook_url"]
        try:
            await assert_public_http_url(discord_webhook)
        except ValueError as exc:
            logger.error("Discord webhook rejected: %s", exc)
            results["discord"] = False
        else:
            await attempt("discord", lambda: _send_discord(discord_webhook, msg))
    if notif.get("telegram_bot_token") and notif.get("telegram_chat_id"):
        bot_token = notif["telegram_bot_token"]
        telegram_chat_id = notif["telegram_chat_id"]
        await attempt("telegram", lambda: _send_telegram(bot_token, telegram_chat_id, msg))

    if not results:
        logger.info("No notification channels configured, skipping alerts")
        return results

    if not any(results.values()) and raised:
        # Every configured channel failed and at least one failed with a
        # transient error: re-raise so the Celery task retries instead of
        # silently losing the alert. Channels that only returned False
        # (rejected webhook URL, bad HTTP status) are permanently broken;
        # retrying cannot fix them, so those results are returned as-is.
        raise raised[-1]

    return results


@app.task(bind=True, max_retries=2, default_retry_delay=30)
def send_campaign_alert(self, campaign_data: dict) -> dict:
    try:
        return asyncio.run(_send_campaign_alert_async(campaign_data))
    except Exception as exc:
        logger.exception("Campaign alert task failed")
        raise self.retry(exc=exc)


async def _attempt_test(channel: str, send) -> dict:
    """Run one test send; report the failure instead of raising it to the API."""
    try:
        return {"channel": channel, "success": await send()}
    except Exception as exc:
        logger.exception("Test alert to %s failed", channel)
        return {"channel": channel, "success": False, "error": str(exc)}


async def send_test_alert(channel: str) -> dict:
    from criba.utils.net import assert_public_http_url

    notif = await _get_notification_settings()

    test_msg = {
        "label": "Criba Test Alert",
        "confidence_pct": 100,
        "platforms_str": "TEST",
        "account_count": 0,
        "post_count": 0,
        "inspector_url": DASHBOARD_BASE_URL,
        "campaign_id": "test",
        "timestamp": "",
    }

    if channel == "slack" and notif.get("slack_webhook_url"):
        webhook = notif["slack_webhook_url"]
        try:
            await assert_public_http_url(webhook)
        except ValueError as exc:
            return {"channel": channel, "success": False, "error": f"Webhook rejected: {exc}"}
        return await _attempt_test(channel, lambda: _send_slack(webhook, test_msg))
    elif channel == "discord" and notif.get("discord_webhook_url"):
        webhook = notif["discord_webhook_url"]
        try:
            await assert_public_http_url(webhook)
        except ValueError as exc:
            return {"channel": channel, "success": False, "error": f"Webhook rejected: {exc}"}
        return await _attempt_test(channel, lambda: _send_discord(webhook, test_msg))
    elif channel == "telegram" and notif.get("telegram_bot_token") and notif.get("telegram_chat_id"):
        bot_token = notif["telegram_bot_token"]
        chat_id = notif["telegram_chat_id"]
        return await _attempt_test(channel, lambda: _send_telegram(bot_token, chat_id, test_msg))
    else:
        return {"channel": channel, "success": False, "error": "Channel not configured"}