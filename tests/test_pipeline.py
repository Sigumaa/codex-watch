from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from codexwatch.config import Settings
from codexwatch.github_client import PullRequest, PullRequestDetail
from codexwatch.pipeline import PipelineRunner
from codexwatch.state_store import StateSnapshot
from codexwatch.summarizer import PullRequestSummary


def _utc(raw: str) -> datetime:
    return datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(timezone.utc)


class _FakeStateStore:
    def __init__(self, state: StateSnapshot, events: list[str]) -> None:
        self._state = state
        self._events = events
        self.saved: list[StateSnapshot] = []

    def load(self) -> StateSnapshot:
        self._events.append("state.load")
        return self._state

    def save(self, state: StateSnapshot) -> None:
        self._events.append("state.save")
        self._state = state
        self.saved.append(state)


class _FakeGitHubClient:
    def __init__(
        self,
        pull_requests: list[PullRequest],
        details: dict[int, PullRequestDetail],
        events: list[str],
    ) -> None:
        self._pull_requests = pull_requests
        self._details = details
        self._events = events

    def fetch_merged_pull_requests(self) -> list[PullRequest]:
        self._events.append("github.list")
        return list(self._pull_requests)

    def fetch_pull_request_detail(self, number: int) -> PullRequestDetail:
        self._events.append(f"github.detail:{number}")
        return self._details[number]


class _FakeSummarizer:
    def __init__(self, events: list[str], raise_for_number: int | None = None) -> None:
        self._events = events
        self._raise_for_number = raise_for_number

    def summarize_pull_request(
        self,
        pull_request: PullRequest,
        *,
        detail: PullRequestDetail | None = None,
    ) -> PullRequestSummary:
        self._events.append(f"summarize:{pull_request.number}")
        if self._raise_for_number == pull_request.number:
            raise RuntimeError("summarizer failed")
        return PullRequestSummary(
            overview=f"overview-{pull_request.number}",
            feature_details=f"feature-{pull_request.number}",
            enabled_outcomes=f"outcome-{pull_request.number}",
        )


class _FakeDiscordClient:
    def __init__(self, events: list[str], fail_on_call: int | None = None) -> None:
        self._events = events
        self._fail_on_call = fail_on_call
        self.calls = 0
        self.messages: list[str] = []

    def send_message(self, content: str) -> None:
        self.calls += 1
        self._events.append(f"discord.send:{self.calls}")
        if self._fail_on_call is not None and self.calls == self._fail_on_call:
            raise RuntimeError("discord failed")
        self.messages.append(content)


def test_pipeline_non_dry_run_sends_notifications_and_saves_state() -> None:
    events: list[str] = []
    state_store = _FakeStateStore(
        StateSnapshot(last_merged_at="2026-02-17T10:00:00Z", processed_pr_ids=[100]),
        events,
    )
    pull_requests = [
        PullRequest(
            id=100,
            number=100,
            title="already processed",
            html_url="https://github.com/openai/codex/pull/100",
            merged_at=_utc("2026-02-17T10:00:00Z"),
        ),
        PullRequest(
            id=101,
            number=101,
            title="first new",
            html_url="https://github.com/openai/codex/pull/101",
            merged_at=_utc("2026-02-17T10:00:00Z"),
        ),
        PullRequest(
            id=102,
            number=102,
            title="latest",
            html_url="https://github.com/openai/codex/pull/102",
            merged_at=_utc("2026-02-17T10:05:00Z"),
        ),
    ]
    details = {
        101: PullRequestDetail(
            id=101,
            number=101,
            title="first new",
            html_url="https://github.com/openai/codex/pull/101",
            merged_at=_utc("2026-02-17T10:00:00Z"),
            body="body-101",
        ),
        102: PullRequestDetail(
            id=102,
            number=102,
            title="latest",
            html_url="https://github.com/openai/codex/pull/102",
            merged_at=_utc("2026-02-17T10:05:00Z"),
            body="body-102",
        ),
    }

    runner = PipelineRunner(
        settings=Settings(dry_run=False, discord_webhook_url="https://discord.test/webhook"),
        github_client=_FakeGitHubClient(pull_requests, details, events),
        state_store=state_store,
        summarizer=_FakeSummarizer(events),
        discord_client=_FakeDiscordClient(events),
    )

    result = runner.run()

    assert result.success is True
    assert result.processed_pr_count == 2
    assert events == [
        "state.load",
        "github.list",
        "github.detail:101",
        "summarize:101",
        "discord.send:1",
        "state.save",
        "github.detail:102",
        "summarize:102",
        "discord.send:2",
        "state.save",
    ]

    assert len(state_store.saved) == 2
    assert state_store.saved[0] == StateSnapshot(
        last_merged_at="2026-02-17T10:00:00Z",
        processed_pr_ids=[100, 101],
    )
    assert state_store.saved[1] == StateSnapshot(
        last_merged_at="2026-02-17T10:05:00Z",
        processed_pr_ids=[102],
    )


def test_pipeline_bootstraps_state_without_backfill_on_first_run() -> None:
    events: list[str] = []
    state_store = _FakeStateStore(StateSnapshot(last_merged_at=None, processed_pr_ids=[]), events)
    pull_requests = [
        PullRequest(
            id=500,
            number=500,
            title="past-1",
            html_url="https://github.com/openai/codex/pull/500",
            merged_at=_utc("2026-02-17T09:00:00Z"),
        ),
        PullRequest(
            id=501,
            number=501,
            title="latest-a",
            html_url="https://github.com/openai/codex/pull/501",
            merged_at=_utc("2026-02-17T09:05:00Z"),
        ),
        PullRequest(
            id=502,
            number=502,
            title="latest-b",
            html_url="https://github.com/openai/codex/pull/502",
            merged_at=_utc("2026-02-17T09:05:00Z"),
        ),
    ]
    discord_client = _FakeDiscordClient(events)

    runner = PipelineRunner(
        settings=Settings(dry_run=False, discord_webhook_url="https://discord.test/webhook"),
        github_client=_FakeGitHubClient(pull_requests, {}, events),
        state_store=state_store,
        summarizer=_FakeSummarizer(events),
        discord_client=discord_client,
    )

    result = runner.run()

    assert result.success is True
    assert result.processed_pr_count == 0
    assert result.message == "bootstrapped without backfill"
    assert discord_client.messages == []
    assert events == ["state.load", "github.list", "state.save"]
    assert state_store.saved == [
        StateSnapshot(last_merged_at="2026-02-17T09:05:00Z", processed_pr_ids=[501, 502])
    ]


def test_pipeline_after_bootstrap_sends_only_new_pull_requests() -> None:
    bootstrap_events: list[str] = []
    bootstrap_store = _FakeStateStore(
        StateSnapshot(last_merged_at=None, processed_pr_ids=[]),
        bootstrap_events,
    )
    initial_pull_requests = [
        PullRequest(
            id=600,
            number=600,
            title="past",
            html_url="https://github.com/openai/codex/pull/600",
            merged_at=_utc("2026-02-17T08:00:00Z"),
        ),
        PullRequest(
            id=601,
            number=601,
            title="latest",
            html_url="https://github.com/openai/codex/pull/601",
            merged_at=_utc("2026-02-17T08:05:00Z"),
        ),
    ]

    bootstrap_runner = PipelineRunner(
        settings=Settings(dry_run=False, discord_webhook_url="https://discord.test/webhook"),
        github_client=_FakeGitHubClient(initial_pull_requests, {}, bootstrap_events),
        state_store=bootstrap_store,
        summarizer=_FakeSummarizer(bootstrap_events),
        discord_client=_FakeDiscordClient(bootstrap_events),
    )
    bootstrap_result = bootstrap_runner.run()

    assert bootstrap_result.success is True
    assert bootstrap_result.processed_pr_count == 0
    assert bootstrap_store.saved[-1] == StateSnapshot(
        last_merged_at="2026-02-17T08:05:00Z",
        processed_pr_ids=[601],
    )

    events: list[str] = []
    state_store = _FakeStateStore(bootstrap_store.saved[-1], events)
    pull_requests = [
        PullRequest(
            id=600,
            number=600,
            title="past",
            html_url="https://github.com/openai/codex/pull/600",
            merged_at=_utc("2026-02-17T08:00:00Z"),
        ),
        PullRequest(
            id=601,
            number=601,
            title="latest",
            html_url="https://github.com/openai/codex/pull/601",
            merged_at=_utc("2026-02-17T08:05:00Z"),
        ),
        PullRequest(
            id=602,
            number=602,
            title="new",
            html_url="https://github.com/openai/codex/pull/602",
            merged_at=_utc("2026-02-17T08:10:00Z"),
        ),
    ]
    details = {
        602: PullRequestDetail(
            id=602,
            number=602,
            title="new",
            html_url="https://github.com/openai/codex/pull/602",
            merged_at=_utc("2026-02-17T08:10:00Z"),
            body="body-602",
        )
    }
    discord_client = _FakeDiscordClient(events)

    runner = PipelineRunner(
        settings=Settings(dry_run=False, discord_webhook_url="https://discord.test/webhook"),
        github_client=_FakeGitHubClient(pull_requests, details, events),
        state_store=state_store,
        summarizer=_FakeSummarizer(events),
        discord_client=discord_client,
    )

    result = runner.run()

    assert result.success is True
    assert result.processed_pr_count == 1
    assert len(discord_client.messages) == 1
    assert events == [
        "state.load",
        "github.list",
        "github.detail:602",
        "summarize:602",
        "discord.send:1",
        "state.save",
    ]
    assert state_store.saved == [
        StateSnapshot(last_merged_at="2026-02-17T08:10:00Z", processed_pr_ids=[602])
    ]


def test_pipeline_non_dry_run_saves_only_successful_notifications_if_discord_send_fails() -> None:
    events: list[str] = []
    state_store = _FakeStateStore(
        StateSnapshot(last_merged_at="2026-02-17T10:00:00Z", processed_pr_ids=[]),
        events,
    )
    pull_requests = [
        PullRequest(
            id=200,
            number=200,
            title="first",
            html_url="https://github.com/openai/codex/pull/200",
            merged_at=_utc("2026-02-17T11:00:00Z"),
        ),
        PullRequest(
            id=201,
            number=201,
            title="second",
            html_url="https://github.com/openai/codex/pull/201",
            merged_at=_utc("2026-02-17T11:05:00Z"),
        ),
    ]
    details = {
        200: PullRequestDetail(
            id=200,
            number=200,
            title="first",
            html_url="https://github.com/openai/codex/pull/200",
            merged_at=_utc("2026-02-17T11:00:00Z"),
            body="body-200",
        ),
        201: PullRequestDetail(
            id=201,
            number=201,
            title="second",
            html_url="https://github.com/openai/codex/pull/201",
            merged_at=_utc("2026-02-17T11:05:00Z"),
            body="body-201",
        ),
    }

    runner = PipelineRunner(
        settings=Settings(dry_run=False, discord_webhook_url="https://discord.test/webhook"),
        github_client=_FakeGitHubClient(pull_requests, details, events),
        state_store=state_store,
        summarizer=_FakeSummarizer(events),
        discord_client=_FakeDiscordClient(events, fail_on_call=2),
    )

    result = runner.run()

    assert result.success is False
    assert result.processed_pr_count == 1
    assert events == [
        "state.load",
        "github.list",
        "github.detail:200",
        "summarize:200",
        "discord.send:1",
        "state.save",
        "github.detail:201",
        "summarize:201",
        "discord.send:2",
    ]
    assert state_store.saved == [
        StateSnapshot(last_merged_at="2026-02-17T11:00:00Z", processed_pr_ids=[200])
    ]


def test_pipeline_non_dry_run_returns_success_when_no_updates() -> None:
    events: list[str] = []
    state_store = _FakeStateStore(
        StateSnapshot(last_merged_at="2026-02-17T12:00:00Z", processed_pr_ids=[300]),
        events,
    )
    pull_request = PullRequest(
        id=300,
        number=300,
        title="already",
        html_url="https://github.com/openai/codex/pull/300",
        merged_at=_utc("2026-02-17T12:00:00Z"),
    )

    discord_client = _FakeDiscordClient(events)
    runner = PipelineRunner(
        settings=Settings(dry_run=False, discord_webhook_url="https://discord.test/webhook"),
        github_client=_FakeGitHubClient([pull_request], {}, events),
        state_store=state_store,
        summarizer=_FakeSummarizer(events),
        discord_client=discord_client,
    )

    result = runner.run()

    assert result.success is True
    assert result.processed_pr_count == 0
    assert discord_client.messages == []
    assert state_store.saved == []


def test_pipeline_respects_max_notifications_per_run() -> None:
    events: list[str] = []
    state_store = _FakeStateStore(
        StateSnapshot(last_merged_at="2026-02-17T12:00:00Z", processed_pr_ids=[]),
        events,
    )
    pull_requests = [
        PullRequest(
            id=310,
            number=310,
            title="new-1",
            html_url="https://github.com/openai/codex/pull/310",
            merged_at=_utc("2026-02-17T12:01:00Z"),
        ),
        PullRequest(
            id=311,
            number=311,
            title="new-2",
            html_url="https://github.com/openai/codex/pull/311",
            merged_at=_utc("2026-02-17T12:02:00Z"),
        ),
        PullRequest(
            id=312,
            number=312,
            title="new-3",
            html_url="https://github.com/openai/codex/pull/312",
            merged_at=_utc("2026-02-17T12:03:00Z"),
        ),
    ]
    details = {
        310: PullRequestDetail(
            id=310,
            number=310,
            title="new-1",
            html_url="https://github.com/openai/codex/pull/310",
            merged_at=_utc("2026-02-17T12:01:00Z"),
            body="body-310",
        ),
        311: PullRequestDetail(
            id=311,
            number=311,
            title="new-2",
            html_url="https://github.com/openai/codex/pull/311",
            merged_at=_utc("2026-02-17T12:02:00Z"),
            body="body-311",
        ),
        312: PullRequestDetail(
            id=312,
            number=312,
            title="new-3",
            html_url="https://github.com/openai/codex/pull/312",
            merged_at=_utc("2026-02-17T12:03:00Z"),
            body="body-312",
        ),
    }

    runner = PipelineRunner(
        settings=Settings(
            dry_run=False,
            discord_webhook_url="https://discord.test/webhook",
            max_notifications_per_run=2,
        ),
        github_client=_FakeGitHubClient(pull_requests, details, events),
        state_store=state_store,
        summarizer=_FakeSummarizer(events),
        discord_client=_FakeDiscordClient(events),
    )

    result = runner.run()

    assert result.success is True
    assert result.processed_pr_count == 2
    assert events == [
        "state.load",
        "github.list",
        "github.detail:310",
        "summarize:310",
        "discord.send:1",
        "state.save",
        "github.detail:311",
        "summarize:311",
        "discord.send:2",
        "state.save",
    ]
    assert state_store.saved[-1] == StateSnapshot(
        last_merged_at="2026-02-17T12:02:00Z",
        processed_pr_ids=[311],
    )


def test_pipeline_discord_message_contains_required_sections() -> None:
    events: list[str] = []
    state_store = _FakeStateStore(
        StateSnapshot(last_merged_at="2026-02-17T12:00:00Z", processed_pr_ids=[]),
        events,
    )
    pull_request = PullRequest(
        id=400,
        number=400,
        title="new",
        html_url="https://github.com/openai/codex/pull/400",
        merged_at=_utc("2026-02-17T13:00:00Z"),
    )
    detail = PullRequestDetail(
        id=400,
        number=400,
        title="new",
        html_url="https://github.com/openai/codex/pull/400",
        merged_at=_utc("2026-02-17T13:00:00Z"),
        body="body",
    )

    discord_client = _FakeDiscordClient(events)
    runner = PipelineRunner(
        settings=Settings(dry_run=False, discord_webhook_url="https://discord.test/webhook"),
        github_client=_FakeGitHubClient([pull_request], {400: detail}, events),
        state_store=state_store,
        summarizer=_FakeSummarizer(events),
        discord_client=discord_client,
    )

    runner.run()

    assert len(discord_client.messages) == 1
    message = discord_client.messages[0]
    assert "### PRがマージされました" in message
    assert "- マージ日時: 2026-02-17T13:00:00Z" in message
    assert "概要" in message
    assert "機能内容" in message
    assert "できるようになること" in message


def test_pipeline_dry_run_skips_external_calls() -> None:
    class _NeverCallGitHubClient:
        def fetch_merged_pull_requests(self) -> list[PullRequest]:
            raise AssertionError("unexpected call")

        def fetch_pull_request_detail(self, number: int) -> PullRequestDetail:
            raise AssertionError(f"unexpected call: {number}")

    runner = PipelineRunner(
        settings=Settings(dry_run=True),
        github_client=_NeverCallGitHubClient(),
        state_store=object(),
        summarizer=object(),
        discord_client=object(),
    )

    result = runner.run()

    assert result.success is True
    assert result.processed_pr_count == 0


def test_pipeline_non_dry_run_requires_discord_webhook() -> None:
    runner = PipelineRunner(settings=Settings(dry_run=False, discord_webhook_url=None))

    result = runner.run()

    assert result.success is False
    assert result.processed_pr_count == 0


@pytest.mark.parametrize(
    "value",
    ["2026-02-17T10:00:00Z", "2026-02-17T10:00:00+00:00", "2026-02-17T10:00:00"],
)
def test_pipeline_accepts_iso8601_state_timestamp(value: str) -> None:
    events: list[str] = []
    state_store = _FakeStateStore(StateSnapshot(last_merged_at=value, processed_pr_ids=[1]), events)
    pull_request = PullRequest(
        id=1,
        number=1,
        title="already",
        html_url="https://github.com/openai/codex/pull/1",
        merged_at=_utc("2026-02-17T10:00:00Z"),
    )

    runner = PipelineRunner(
        settings=Settings(dry_run=False, discord_webhook_url="https://discord.test/webhook"),
        github_client=_FakeGitHubClient([pull_request], {}, events),
        state_store=state_store,
        summarizer=_FakeSummarizer(events),
        discord_client=_FakeDiscordClient(events),
    )

    result = runner.run()

    assert result.success is True
    assert result.processed_pr_count == 0
