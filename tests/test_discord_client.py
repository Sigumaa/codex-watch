from __future__ import annotations

from pathlib import Path
import sys

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from codexwatch.config import Settings
from codexwatch.discord_client import DiscordClient


def test_send_message_posts_webhook_payload() -> None:
    observed: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        observed["method"] = request.method
        observed["url"] = str(request.url)
        observed["body"] = request.content.decode("utf-8")
        return httpx.Response(204)

    webhook = "https://discord.test/api/webhooks/1/token"
    client = DiscordClient(
        settings=Settings(discord_webhook_url=webhook),
        transport=httpx.MockTransport(handler),
    )

    client.send_message("  hello world  ")

    assert observed["method"] == "POST"
    assert observed["url"] == webhook
    assert observed["body"] == '{"content":"hello world"}'


def test_send_message_raises_for_empty_payload() -> None:
    client = DiscordClient(settings=Settings(discord_webhook_url="https://discord.test/webhook"))

    with pytest.raises(ValueError, match="must not be empty"):
        client.send_message("   ")


def test_send_message_raises_when_webhook_missing() -> None:
    client = DiscordClient(settings=Settings(discord_webhook_url=None))

    with pytest.raises(ValueError, match="DISCORD_WEBHOOK_URL"):
        client.send_message("hello")


def test_send_message_raises_on_http_error() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"message": "error"})

    client = DiscordClient(
        settings=Settings(discord_webhook_url="https://discord.test/webhook"),
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(httpx.HTTPStatusError):
        client.send_message("hello")
