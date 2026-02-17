from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import codexwatch.main as main_module
from codexwatch.config import Settings
from codexwatch.github_client import Release
from codexwatch.pipeline import RunResult
from codexwatch.summarizer import PullRequestSummary


def _release() -> Release:
    return Release(
        id=1002,
        tag_name="rust-v0.102.0",
        name="0.102.0",
        html_url="https://github.com/openai/codex/releases/tag/rust-v0.102.0",
        published_at=datetime(2026, 2, 17, 20, 2, 35, tzinfo=timezone.utc),
        body="release-body",
        prerelease=False,
    )


def test_main_dry_run_flag_overrides_env(monkeypatch) -> None:
    observed: dict[str, bool] = {}

    class DummyRunner:
        def __init__(self, settings: Settings) -> None:
            observed["dry_run"] = settings.dry_run

        def run(self) -> RunResult:
            return RunResult(success=True, processed_pr_count=0, message="ok")

    monkeypatch.setattr(main_module, "load_settings", lambda env=None: Settings(dry_run=False))
    monkeypatch.setattr(main_module, "PipelineRunner", DummyRunner)

    exit_code = main_module.main(["--dry-run"])

    assert exit_code == 0
    assert observed["dry_run"] is True


def test_main_no_dry_run_flag_overrides_env(monkeypatch) -> None:
    observed: dict[str, bool] = {}

    class DummyRunner:
        def __init__(self, settings: Settings) -> None:
            observed["dry_run"] = settings.dry_run

        def run(self) -> RunResult:
            return RunResult(success=True, processed_pr_count=0, message="ok")

    monkeypatch.setattr(main_module, "load_settings", lambda env=None: Settings(dry_run=True))
    monkeypatch.setattr(main_module, "PipelineRunner", DummyRunner)

    exit_code = main_module.main(["--no-dry-run"])

    assert exit_code == 0
    assert observed["dry_run"] is False


def test_main_returns_non_zero_when_pipeline_fails(monkeypatch) -> None:
    class FailingRunner:
        def __init__(self, settings: Settings) -> None:
            self.settings = settings

        def run(self) -> RunResult:
            return RunResult(success=False, processed_pr_count=0, message="failed")

    monkeypatch.setattr(main_module, "load_settings", lambda env=None: Settings(dry_run=True))
    monkeypatch.setattr(main_module, "PipelineRunner", FailingRunner)

    exit_code = main_module.main([])

    assert exit_code == 1


def test_main_dry_run_flag_starts_with_invalid_env_dry_run(monkeypatch) -> None:
    observed: dict[str, bool] = {}

    class DummyRunner:
        def __init__(self, settings: Settings) -> None:
            observed["dry_run"] = settings.dry_run

        def run(self) -> RunResult:
            return RunResult(success=True, processed_pr_count=0, message="ok")

    monkeypatch.setenv("CODEXWATCH_DRY_RUN", "not-bool")
    monkeypatch.setattr(main_module, "PipelineRunner", DummyRunner)

    exit_code = main_module.main(["--dry-run"])

    assert exit_code == 0
    assert observed["dry_run"] is True


def test_main_no_dry_run_flag_starts_with_invalid_env_dry_run(monkeypatch) -> None:
    observed: dict[str, bool] = {}

    class DummyRunner:
        def __init__(self, settings: Settings) -> None:
            observed["dry_run"] = settings.dry_run

        def run(self) -> RunResult:
            return RunResult(success=True, processed_pr_count=0, message="ok")

    monkeypatch.setenv("CODEXWATCH_DRY_RUN", "not-bool")
    monkeypatch.setattr(main_module, "PipelineRunner", DummyRunner)

    exit_code = main_module.main(["--no-dry-run"])

    assert exit_code == 0
    assert observed["dry_run"] is False


def test_main_raises_for_invalid_env_dry_run_without_cli_override(monkeypatch) -> None:
    monkeypatch.setenv("CODEXWATCH_DRY_RUN", "not-bool")

    with pytest.raises(ValueError, match="CODEXWATCH_DRY_RUN"):
        main_module.main([])


def test_main_returns_non_zero_for_non_dry_run_without_required_settings(monkeypatch) -> None:
    monkeypatch.setattr(main_module, "load_settings", lambda env=None: Settings(dry_run=False))

    exit_code = main_module.main([])

    assert exit_code == 1


def test_main_release_tag_prints_summary_without_pipeline(monkeypatch, capsys) -> None:
    class PipelineShouldNotRun:
        def __init__(self, settings: Settings) -> None:
            self.settings = settings

        def run(self) -> RunResult:
            raise AssertionError("PipelineRunner should not run in release-tag mode")

    class DummyGitHubClient:
        def __init__(self, settings: Settings) -> None:
            self.settings = settings

        def fetch_release_by_tag(self, tag_name: str) -> Release:
            assert tag_name == "rust-v0.102.0"
            return _release()

    class DummySummarizer:
        def __init__(self, settings: Settings) -> None:
            self.settings = settings

        def summarize_release(self, release: Release) -> PullRequestSummary:
            assert release.tag_name == "rust-v0.102.0"
            return PullRequestSummary(
                overview="overview",
                feature_details="features",
                enabled_outcomes="outcomes",
            )

    monkeypatch.setattr(main_module, "PipelineRunner", PipelineShouldNotRun)
    monkeypatch.setattr(main_module, "GitHubClient", DummyGitHubClient)
    monkeypatch.setattr(main_module, "Summarizer", DummySummarizer)
    monkeypatch.setattr(main_module, "load_settings", lambda env=None: Settings(dry_run=True))

    exit_code = main_module.main(["--release-tag", "rust-v0.102.0"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "### Releaseが公開されました" in captured.out
    assert "rust-v0.102.0" in captured.out
    assert "overview" in captured.out


def test_main_release_tag_can_send_summary_to_discord(monkeypatch) -> None:
    sent_messages: list[str] = []

    class DummyGitHubClient:
        def __init__(self, settings: Settings) -> None:
            self.settings = settings

        def fetch_release_by_tag(self, tag_name: str) -> Release:
            assert tag_name == "rust-v0.102.0"
            return _release()

    class DummySummarizer:
        def __init__(self, settings: Settings) -> None:
            self.settings = settings

        def summarize_release(self, release: Release) -> PullRequestSummary:
            return PullRequestSummary(
                overview="overview",
                feature_details="features",
                enabled_outcomes="outcomes",
            )

    class DummyDiscordClient:
        def __init__(self, settings: Settings) -> None:
            self.settings = settings

        def send_message(self, content: str) -> None:
            sent_messages.append(content)

    monkeypatch.setattr(main_module, "GitHubClient", DummyGitHubClient)
    monkeypatch.setattr(main_module, "Summarizer", DummySummarizer)
    monkeypatch.setattr(main_module, "DiscordClient", DummyDiscordClient)
    monkeypatch.setattr(
        main_module,
        "load_settings",
        lambda env=None: Settings(
            dry_run=False,
            discord_webhook_url="https://discord.test/webhook",
        ),
    )

    exit_code = main_module.main(
        [
            "--release-tag",
            "rust-v0.102.0",
            "--send-release-to-discord",
            "--no-dry-run",
        ]
    )

    assert exit_code == 0
    assert len(sent_messages) == 1
    assert "### Releaseが公開されました" in sent_messages[0]


def test_main_release_tag_send_fails_without_webhook(monkeypatch) -> None:
    class DummyGitHubClient:
        def __init__(self, settings: Settings) -> None:
            self.settings = settings

        def fetch_release_by_tag(self, tag_name: str) -> Release:
            assert tag_name == "rust-v0.102.0"
            return _release()

    class DummySummarizer:
        def __init__(self, settings: Settings) -> None:
            self.settings = settings

        def summarize_release(self, release: Release) -> PullRequestSummary:
            return PullRequestSummary(
                overview="overview",
                feature_details="features",
                enabled_outcomes="outcomes",
            )

    monkeypatch.setattr(main_module, "GitHubClient", DummyGitHubClient)
    monkeypatch.setattr(main_module, "Summarizer", DummySummarizer)
    monkeypatch.setattr(
        main_module,
        "load_settings",
        lambda env=None: Settings(
            dry_run=False,
            discord_webhook_url=None,
        ),
    )

    exit_code = main_module.main(
        [
            "--release-tag",
            "rust-v0.102.0",
            "--send-release-to-discord",
            "--no-dry-run",
        ]
    )

    assert exit_code == 1


def test_main_send_release_to_discord_requires_release_tag() -> None:
    with pytest.raises(SystemExit, match="2"):
        main_module.main(["--send-release-to-discord"])
