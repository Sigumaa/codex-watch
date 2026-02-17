from __future__ import annotations

from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from codexwatch.config import load_settings


def test_load_settings_defaults() -> None:
    settings = load_settings(env={})

    assert settings.github_repo == "openai/codex"
    assert settings.github_base_branch == "main"
    assert settings.github_api_url == "https://api.github.com"
    assert settings.poll_interval_minutes == 10
    assert settings.dry_run is True
    assert settings.github_token is None
    assert settings.openai_api_key is None
    assert settings.discord_webhook_url is None


def test_load_settings_overrides() -> None:
    settings = load_settings(
        env={
            "CODEXWATCH_GITHUB_REPO": "example/repo",
            "CODEXWATCH_GITHUB_BASE_BRANCH": "develop",
            "CODEXWATCH_GITHUB_API_URL": "https://example.com/api",
            "CODEXWATCH_POLL_INTERVAL_MINUTES": "15",
            "CODEXWATCH_DRY_RUN": "false",
            "GITHUB_TOKEN": "ghp_xxx",
            "OPENAI_API_KEY": "sk-test",
            "DISCORD_WEBHOOK_URL": "https://discord.test/webhook",
        }
    )

    assert settings.github_repo == "example/repo"
    assert settings.github_base_branch == "develop"
    assert settings.github_api_url == "https://example.com/api"
    assert settings.poll_interval_minutes == 15
    assert settings.dry_run is False
    assert settings.github_token == "ghp_xxx"
    assert settings.openai_api_key == "sk-test"
    assert settings.discord_webhook_url == "https://discord.test/webhook"


def test_load_settings_invalid_interval() -> None:
    with pytest.raises(ValueError, match="CODEXWATCH_POLL_INTERVAL_MINUTES"):
        load_settings(env={"CODEXWATCH_POLL_INTERVAL_MINUTES": "abc"})


def test_load_settings_invalid_dry_run() -> None:
    with pytest.raises(ValueError, match="CODEXWATCH_DRY_RUN"):
        load_settings(env={"CODEXWATCH_DRY_RUN": "not-bool"})
