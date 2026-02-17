from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import logging

from codexwatch.config import Settings
from codexwatch.discord_client import DiscordClient
from codexwatch.github_client import GitHubClient, PullRequest, select_unprocessed_pull_requests
from codexwatch.state_store import StateStore, compute_next_state
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
        try:
            state = self._state_store.load()
            last_merged_at = _parse_last_merged_at(state.last_merged_at)
            merged_pull_requests = self._github_client.fetch_merged_pull_requests()
            unprocessed_pull_requests = select_unprocessed_pull_requests(
                merged_pull_requests,
                last_merged_at=last_merged_at,
                processed_pr_ids=set(state.processed_pr_ids),
            )

            if not unprocessed_pull_requests:
                self.logger.info("No unprocessed merged pull requests")
                return RunResult(success=True, processed_pr_count=0, message="no updates")

            for pull_request in unprocessed_pull_requests:
                detail = self._github_client.fetch_pull_request_detail(pull_request.number)
                summary = self._summarizer.summarize_pull_request(
                    pull_request,
                    detail=detail,
                )
                self._discord_client.send_message(_build_discord_message(detail, summary))
                sent_pull_requests.append(pull_request)

            next_state = compute_next_state(state, sent_pull_requests)
            self._state_store.save(next_state)

            return RunResult(
                success=True,
                processed_pr_count=len(sent_pull_requests),
                message="processed notifications",
            )
        except Exception as exc:
            self.logger.exception("Pipeline execution failed")
            return RunResult(
                success=False,
                processed_pr_count=len(sent_pull_requests),
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


def _build_discord_message(pull_request: object, summary: PullRequestSummary) -> str:
    number = _read_pull_request_field(pull_request, "number")
    title = _read_pull_request_field(pull_request, "title")
    html_url = _read_pull_request_field(pull_request, "html_url")
    merged_at = _read_pull_request_datetime_field(pull_request, "merged_at")
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


def _read_pull_request_field(source: object, field_name: str) -> str:
    if not hasattr(source, field_name):
        raise ValueError(f"Pull request object must provide '{field_name}'")

    value = getattr(source, field_name)
    text = str(value).strip()
    if not text:
        raise ValueError(f"Pull request field '{field_name}' must not be empty")
    return text


def _read_pull_request_datetime_field(source: object, field_name: str) -> str:
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
