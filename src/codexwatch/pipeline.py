from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import logging

from codexwatch.config import Settings
from codexwatch.discord_client import DiscordClient
from codexwatch.github_client import (
    GitHubClient,
    PullRequest,
    Release,
    select_unprocessed_pull_requests,
    select_unprocessed_releases,
)
from codexwatch.state_store import (
    StateSnapshot,
    StateStore,
    compute_next_release_state,
    compute_next_state,
)
from codexwatch.summarizer import PullRequestSummary, Summarizer


@dataclass(frozen=True)
class RunResult:
    success: bool
    processed_pr_count: int = 0
    message: str = ""


class PipelineRunner:
    def __init__(
        self,
        settings: Settings,
        logger: logging.Logger | None = None,
        *,
        github_client: GitHubClient | None = None,
        state_store: StateStore | None = None,
        summarizer: Summarizer | None = None,
        discord_client: DiscordClient | None = None,
    ) -> None:
        self.settings = settings
        self.logger = logger or logging.getLogger(__name__)
        self._github_client = github_client or GitHubClient(settings=settings)
        self._state_store = state_store or StateStore()
        self._summarizer = summarizer or Summarizer(settings=settings)
        self._discord_client = discord_client or DiscordClient(settings=settings)

    def run(self) -> RunResult:
        if self.settings.dry_run:
            self.logger.info("Dry-run enabled. Skipping GitHub/OpenAI/Discord calls.")
            return RunResult(success=True, processed_pr_count=0, message="dry-run no-op")

        if not self.settings.discord_webhook_url:
            self.logger.error("DISCORD_WEBHOOK_URL is not configured")
            return RunResult(success=False, processed_pr_count=0, message="missing discord webhook")

        sent_pull_requests: list[PullRequest] = []
        sent_releases: list[Release] = []
        try:
            state = self._state_store.load()
            merged_pull_requests = self._github_client.fetch_merged_pull_requests()
            releases = self._github_client.fetch_releases()

            pull_requests_bootstrapped = False
            releases_bootstrapped = False

            if _should_bootstrap_pull_requests_without_backfill(state):
                next_state = _build_pull_request_bootstrap_state(state, merged_pull_requests)
                if next_state != state:
                    state = next_state
                    self._state_store.save(state)
                    pull_requests_bootstrapped = True

            if _should_bootstrap_releases_without_backfill(state):
                next_state = _build_release_bootstrap_state(state, releases)
                if next_state != state:
                    state = next_state
                    self._state_store.save(state)
                    releases_bootstrapped = True

            last_merged_at = _parse_last_merged_at(state.last_merged_at)
            last_release_published_at = _parse_last_merged_at(state.last_release_published_at)

            unprocessed_pull_requests: list[PullRequest]
            if pull_requests_bootstrapped:
                unprocessed_pull_requests = []
            else:
                unprocessed_pull_requests = select_unprocessed_pull_requests(
                    merged_pull_requests,
                    last_merged_at=last_merged_at,
                    processed_pr_ids=set(state.processed_pr_ids),
                )

            unprocessed_releases: list[Release]
            if releases_bootstrapped:
                unprocessed_releases = []
            else:
                unprocessed_releases = select_unprocessed_releases(
                    releases,
                    last_published_at=last_release_published_at,
                    processed_release_ids=set(state.processed_release_ids),
                )

            if not unprocessed_pull_requests and not unprocessed_releases:
                if pull_requests_bootstrapped or releases_bootstrapped:
                    self.logger.info("Bootstrapped state without backfill notifications")
                    return RunResult(
                        success=True,
                        processed_pr_count=0,
                        message="bootstrapped without backfill",
                    )

                self.logger.info("No unprocessed merged pull requests or releases")
                return RunResult(success=True, processed_pr_count=0, message="no updates")

            for pull_request in unprocessed_pull_requests[: self.settings.max_notifications_per_run]:
                detail = self._github_client.fetch_pull_request_detail(pull_request.number)
                summary = self._summarizer.summarize_pull_request(
                    pull_request,
                    detail=detail,
                )
                self._discord_client.send_message(_build_pull_request_discord_message(detail, summary))
                state = compute_next_state(state, [pull_request])
                self._state_store.save(state)
                sent_pull_requests.append(pull_request)

            remaining_notification_slots = (
                self.settings.max_notifications_per_run - len(sent_pull_requests)
            )
            if remaining_notification_slots > 0:
                for release in unprocessed_releases[:remaining_notification_slots]:
                    summary = self._summarizer.summarize_release(release)
                    self._discord_client.send_message(_build_release_discord_message(release, summary))
                    state = compute_next_release_state(state, [release])
                    self._state_store.save(state)
                    sent_releases.append(release)

            return RunResult(
                success=True,
                processed_pr_count=len(sent_pull_requests) + len(sent_releases),
                message="processed notifications",
            )
        except Exception as exc:
            self.logger.exception("Pipeline execution failed")
            return RunResult(
                success=False,
                processed_pr_count=len(sent_pull_requests) + len(sent_releases),
                message=str(exc),
            )


def _parse_last_merged_at(raw: str | None) -> datetime | None:
    if raw is None:
        return None

    text = raw.strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"

    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _should_bootstrap_pull_requests_without_backfill(state: StateSnapshot) -> bool:
    return state.last_merged_at is None and not state.processed_pr_ids


def _should_bootstrap_releases_without_backfill(state: StateSnapshot) -> bool:
    return state.last_release_published_at is None and not state.processed_release_ids


def _build_pull_request_bootstrap_state(
    state: StateSnapshot,
    pull_requests: list[PullRequest],
) -> StateSnapshot:
    if not pull_requests:
        return state
    return compute_next_state(state, pull_requests)


def _build_release_bootstrap_state(
    state: StateSnapshot,
    releases: list[Release],
) -> StateSnapshot:
    if not releases:
        return state
    return compute_next_release_state(state, releases)


def _build_pull_request_discord_message(pull_request: object, summary: PullRequestSummary) -> str:
    number = _read_pull_request_field(pull_request, "number")
    title = _read_pull_request_field(pull_request, "title")
    html_url = _read_pull_request_field(pull_request, "html_url")
    merged_at = _read_datetime_field(pull_request, "merged_at")
    lines = [
        "### PRがマージされました",
        f"- PR: #{number} {title}",
        f"- URL: {html_url}",
        f"- マージ日時: {merged_at}",
        "",
        "概要",
        summary.overview,
        "",
        "機能内容",
        summary.feature_details,
        "",
        "できるようになること",
        summary.enabled_outcomes,
    ]
    return "\n".join(lines)


def _build_release_discord_message(release: object, summary: PullRequestSummary) -> str:
    tag_name = _read_pull_request_field(release, "tag_name")
    name = _read_pull_request_field(release, "name")
    html_url = _read_pull_request_field(release, "html_url")
    published_at = _read_datetime_field(release, "published_at")
    lines = [
        "### Releaseが公開されました",
        f"- Release: {tag_name} ({name})",
        f"- URL: {html_url}",
        f"- 公開日時: {published_at}",
        "",
        "概要",
        summary.overview,
        "",
        "機能内容",
        summary.feature_details,
        "",
        "できるようになること",
        summary.enabled_outcomes,
    ]
    return "\n".join(lines)


def _read_pull_request_field(source: object, field_name: str) -> str:
    if not hasattr(source, field_name):
        raise ValueError(f"Pull request object must provide '{field_name}'")

    value = getattr(source, field_name)
    text = str(value).strip()
    if not text:
        raise ValueError(f"Pull request field '{field_name}' must not be empty")
    return text


def _read_datetime_field(source: object, field_name: str) -> str:
    if not hasattr(source, field_name):
        raise ValueError(f"Pull request object must provide '{field_name}'")

    value = getattr(source, field_name)
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        text = value.strip()
        if not text:
            raise ValueError(f"Pull request field '{field_name}' must not be empty")
        if text.endswith("Z"):
            text = f"{text[:-1]}+00:00"
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError as exc:
            raise ValueError(
                f"Pull request field '{field_name}' must be ISO8601 datetime text"
            ) from exc
    else:
        raise ValueError(
            f"Pull request field '{field_name}' must be datetime or ISO8601 datetime text"
        )

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)

    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
