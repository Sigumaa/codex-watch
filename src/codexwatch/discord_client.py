from __future__ import annotations

import httpx

from codexwatch.config import Settings


class DiscordClient:
    def __init__(
        self,
        settings: Settings,
        *,
        timeout: float = 10.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._settings = settings
        self._timeout = timeout
        self._transport = transport

    def send_message(self, content: str) -> None:
        normalized = content.strip()
        if not normalized:
            raise ValueError("Discord message content must not be empty")

        webhook_url = self._settings.discord_webhook_url
        if not webhook_url:
            raise ValueError("DISCORD_WEBHOOK_URL is not configured")

        with httpx.Client(timeout=self._timeout, transport=self._transport) as client:
            response = client.post(webhook_url, json={"content": normalized})
            response.raise_for_status()
