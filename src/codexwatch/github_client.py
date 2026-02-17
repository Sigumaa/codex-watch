from __future__ import annotations

from collections.abc import Sequence, Set
from dataclasses import dataclass
from datetime import datetime, timezone

import httpx

from codexwatch.config import Settings


@dataclass(frozen=True)
class PullRequest:
    id: int
    number: int
    title: str
    html_url: str
    merged_at: datetime


def _normalize_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _parse_github_datetime(raw: str) -> datetime:
    return _normalize_utc(datetime.fromisoformat(raw.replace("Z", "+00:00")))


class GitHubClient:
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

    def fetch_merged_pull_requests(self, *, per_page: int = 100, page: int = 1) -> list[PullRequest]:
        if per_page <= 0:
            raise ValueError("per_page must be greater than 0")
        if page <= 0:
            raise ValueError("page must be greater than 0")

        url = f"{self._settings.github_api_url}/repos/{self._settings.github_repo}/pulls"
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self._settings.github_token:
            headers["Authorization"] = f"Bearer {self._settings.github_token}"

        with httpx.Client(timeout=self._timeout, transport=self._transport, headers=headers) as client:
            response = client.get(
                url,
                params={
                    "state": "closed",
                    "base": self._settings.github_base_branch,
                    "sort": "updated",
                    "direction": "desc",
                    "per_page": per_page,
                    "page": page,
                },
            )
            response.raise_for_status()

        data = response.json()
        if not isinstance(data, list):
            raise ValueError("Unexpected GitHub API response format")

        pull_requests: list[PullRequest] = []
        for item in data:
            if not isinstance(item, dict):
                continue

            merged_at = item.get("merged_at")
            if not isinstance(merged_at, str):
                continue

            base = item.get("base")
            if not isinstance(base, dict) or base.get("ref") != self._settings.github_base_branch:
                continue

            pull_requests.append(
                PullRequest(
                    id=int(item["id"]),
                    number=int(item["number"]),
                    title=str(item["title"]),
                    html_url=str(item["html_url"]),
                    merged_at=_parse_github_datetime(merged_at),
                )
            )

        pull_requests.sort(key=lambda pr: (pr.merged_at, pr.id))
        return pull_requests


def select_unprocessed_pull_requests(
    pull_requests: Sequence[PullRequest],
    *,
    last_merged_at: datetime | None,
    processed_pr_ids: Set[int],
) -> list[PullRequest]:
    normalized_last_merged_at = (
        _normalize_utc(last_merged_at) if last_merged_at is not None else None
    )

    selected: list[PullRequest] = []
    seen_ids: set[int] = set()

    for pull_request in sorted(pull_requests, key=lambda pr: (_normalize_utc(pr.merged_at), pr.id)):
        if pull_request.id in seen_ids:
            continue
        seen_ids.add(pull_request.id)

        merged_at = _normalize_utc(pull_request.merged_at)

        if normalized_last_merged_at is None:
            selected.append(pull_request)
            continue

        if merged_at < normalized_last_merged_at:
            continue

        if merged_at == normalized_last_merged_at and pull_request.id in processed_pr_ids:
            continue

        selected.append(pull_request)

    return selected
