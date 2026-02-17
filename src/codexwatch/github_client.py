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


@dataclass(frozen=True)
class PullRequestDetail:
    id: int
    number: int
    title: str
    html_url: str
    merged_at: datetime
    body: str | None = None


@dataclass(frozen=True)
class Release:
    id: int
    tag_name: str
    name: str
    html_url: str
    published_at: datetime
    body: str | None = None
    prerelease: bool = False


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
        with httpx.Client(
            timeout=self._timeout,
            transport=self._transport,
            headers=self._build_headers(),
        ) as client:
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

    def fetch_pull_request_detail(self, number: int) -> PullRequestDetail:
        if number <= 0:
            raise ValueError("number must be greater than 0")

        url = f"{self._settings.github_api_url}/repos/{self._settings.github_repo}/pulls/{number}"
        with httpx.Client(
            timeout=self._timeout,
            transport=self._transport,
            headers=self._build_headers(),
        ) as client:
            response = client.get(url)
            response.raise_for_status()

        data = response.json()
        if not isinstance(data, dict):
            raise ValueError("Unexpected GitHub API response format")

        merged_at = data.get("merged_at")
        if not isinstance(merged_at, str):
            raise ValueError("Pull request detail must include merged_at")

        return PullRequestDetail(
            id=int(data["id"]),
            number=int(data["number"]),
            title=str(data["title"]),
            html_url=str(data["html_url"]),
            merged_at=_parse_github_datetime(merged_at),
            body=_normalize_optional_text(data.get("body")),
        )

    def fetch_releases(self, *, per_page: int = 100, page: int = 1) -> list[Release]:
        if per_page <= 0:
            raise ValueError("per_page must be greater than 0")
        if page <= 0:
            raise ValueError("page must be greater than 0")

        url = f"{self._settings.github_api_url}/repos/{self._settings.github_repo}/releases"
        with httpx.Client(
            timeout=self._timeout,
            transport=self._transport,
            headers=self._build_headers(),
        ) as client:
            response = client.get(
                url,
                params={
                    "per_page": per_page,
                    "page": page,
                },
            )
            response.raise_for_status()

        data = response.json()
        if not isinstance(data, list):
            raise ValueError("Unexpected GitHub API response format")

        releases: list[Release] = []
        for item in data:
            if not isinstance(item, dict):
                continue

            published_at = item.get("published_at")
            if not isinstance(published_at, str):
                continue

            if bool(item.get("draft", False)):
                continue

            tag_name = _normalize_optional_text(item.get("tag_name"))
            if tag_name is None:
                continue

            name = _normalize_optional_text(item.get("name")) or tag_name
            prerelease = bool(item.get("prerelease", False))
            if _should_ignore_release(tag_name=tag_name, name=name, prerelease=prerelease):
                continue

            html_url = _normalize_optional_text(item.get("html_url"))
            if html_url is None:
                continue

            releases.append(
                Release(
                    id=int(item["id"]),
                    tag_name=tag_name,
                    name=name,
                    html_url=html_url,
                    published_at=_parse_github_datetime(published_at),
                    body=_normalize_optional_text(item.get("body")),
                    prerelease=prerelease,
                )
            )

        releases.sort(key=lambda release: (release.published_at, release.id))
        return releases

    def _build_headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self._settings.github_token:
            headers["Authorization"] = f"Bearer {self._settings.github_token}"
        return headers


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


def select_unprocessed_releases(
    releases: Sequence[Release],
    *,
    last_published_at: datetime | None,
    processed_release_ids: Set[int],
) -> list[Release]:
    normalized_last_published_at = (
        _normalize_utc(last_published_at) if last_published_at is not None else None
    )

    selected: list[Release] = []
    seen_ids: set[int] = set()

    for release in sorted(releases, key=lambda item: (_normalize_utc(item.published_at), item.id)):
        if release.id in seen_ids:
            continue
        seen_ids.add(release.id)

        published_at = _normalize_utc(release.published_at)

        if normalized_last_published_at is None:
            selected.append(release)
            continue

        if published_at < normalized_last_published_at:
            continue

        if published_at == normalized_last_published_at and release.id in processed_release_ids:
            continue

        selected.append(release)

    return selected


def _normalize_optional_text(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        normalized = value.strip()
        return normalized or None
    return str(value)


def _should_ignore_release(*, tag_name: str, name: str, prerelease: bool) -> bool:
    if prerelease:
        return True

    text = f"{tag_name} {name}".lower()
    return "alpha" in text or "α" in text
