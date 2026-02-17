from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import os

from dotenv import load_dotenv

_TRUE_VALUES = {"1", "true", "yes", "on"}
_FALSE_VALUES = {"0", "false", "no", "off"}


@dataclass(frozen=True)
class Settings:
    github_repo: str = "openai/codex"
    github_base_branch: str = "main"
    github_api_url: str = "https://api.github.com"
    poll_interval_minutes: int = 10
    dry_run: bool = True
    github_token: str | None = None
    openai_api_key: str | None = None
    discord_webhook_url: str | None = None


def _read_bool(name: str, raw: str | None, *, default: bool) -> bool:
    if raw is None:
        return default

    lowered = raw.strip().lower()
    if lowered in _TRUE_VALUES:
        return True
    if lowered in _FALSE_VALUES:
        return False
    raise ValueError(f"Invalid boolean value for {name}: {raw!r}")


def _read_positive_int(name: str, raw: str | None, *, default: int) -> int:
    if raw is None:
        return default

    try:
        parsed = int(raw)
    except ValueError as exc:
        raise ValueError(f"Invalid integer value for {name}: {raw!r}") from exc

    if parsed <= 0:
        raise ValueError(f"{name} must be greater than 0: {raw!r}")
    return parsed


def load_settings(env: Mapping[str, str] | None = None) -> Settings:
    source: Mapping[str, str]
    if env is None:
        load_dotenv()
        source = os.environ
    else:
        source = env

    return Settings(
        github_repo=source.get("CODEXWATCH_GITHUB_REPO", "openai/codex"),
        github_base_branch=source.get("CODEXWATCH_GITHUB_BASE_BRANCH", "main"),
        github_api_url=source.get("CODEXWATCH_GITHUB_API_URL", "https://api.github.com"),
        poll_interval_minutes=_read_positive_int(
            "CODEXWATCH_POLL_INTERVAL_MINUTES",
            source.get("CODEXWATCH_POLL_INTERVAL_MINUTES"),
            default=10,
        ),
        dry_run=_read_bool(
            "CODEXWATCH_DRY_RUN",
            source.get("CODEXWATCH_DRY_RUN"),
            default=True,
        ),
        github_token=source.get("GITHUB_TOKEN"),
        openai_api_key=source.get("OPENAI_API_KEY"),
        discord_webhook_url=source.get("DISCORD_WEBHOOK_URL"),
    )
