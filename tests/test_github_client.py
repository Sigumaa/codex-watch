from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sys

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from codexwatch.config import Settings
from codexwatch.github_client import (
    GitHubClient,
    PullRequest,
    PullRequestDetail,
    Release,
    select_unprocessed_pull_requests,
    select_unprocessed_releases,
)


def _utc(raw: str) -> datetime:
    return datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(timezone.utc)


def _pull_request(*, pr_id: int, number: int, merged_at: datetime) -> PullRequest:
    return PullRequest(
        id=pr_id,
        number=number,
        title=f"PR-{number}",
        html_url=f"https://github.com/openai/codex/pull/{number}",
        merged_at=merged_at,
    )


def _release(*, release_id: int, tag_name: str, published_at: datetime, name: str | None = None) -> Release:
    return Release(
        id=release_id,
        tag_name=tag_name,
        name=name or tag_name,
        html_url=f"https://github.com/openai/codex/releases/tag/{tag_name}",
        published_at=published_at,
        body=None,
        prerelease=False,
    )


def test_fetch_merged_pull_requests_uses_expected_query_and_filters_rows() -> None:
    observed_headers: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        observed_headers["authorization"] = request.headers.get("Authorization", "")
        observed_headers["accept"] = request.headers.get("Accept", "")
        observed_headers["api_version"] = request.headers.get("X-GitHub-Api-Version", "")

        assert request.url.path == "/repos/openai/codex/pulls"
        assert request.url.params["state"] == "closed"
        assert request.url.params["base"] == "main"
        assert request.url.params["sort"] == "updated"
        assert request.url.params["direction"] == "desc"
        assert request.url.params["per_page"] == "100"
        assert request.url.params["page"] == "1"

        payload = [
            {
                "id": 22,
                "number": 102,
                "title": "new",
                "html_url": "https://example.test/pull/102",
                "merged_at": "2026-02-16T11:00:00Z",
                "base": {"ref": "main"},
            },
            {
                "id": 11,
                "number": 101,
                "title": "older",
                "html_url": "https://example.test/pull/101",
                "merged_at": "2026-02-16T10:00:00Z",
                "base": {"ref": "main"},
            },
            {
                "id": 33,
                "number": 103,
                "title": "not merged",
                "html_url": "https://example.test/pull/103",
                "merged_at": None,
                "base": {"ref": "main"},
            },
            {
                "id": 44,
                "number": 104,
                "title": "other base",
                "html_url": "https://example.test/pull/104",
                "merged_at": "2026-02-16T12:00:00Z",
                "base": {"ref": "develop"},
            },
        ]
        return httpx.Response(200, json=payload)

    settings = Settings(github_token="ghp_test")
    client = GitHubClient(settings=settings, transport=httpx.MockTransport(handler))

    pull_requests = client.fetch_merged_pull_requests()

    assert observed_headers["authorization"] == "Bearer ghp_test"
    assert observed_headers["accept"] == "application/vnd.github+json"
    assert observed_headers["api_version"] == "2022-11-28"
    assert [pr.id for pr in pull_requests] == [11, 22]
    assert pull_requests[0].merged_at == _utc("2026-02-16T10:00:00Z")
    assert pull_requests[1].merged_at == _utc("2026-02-16T11:00:00Z")


def test_fetch_merged_pull_requests_raises_on_http_error() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"message": "server error"})

    client = GitHubClient(settings=Settings(), transport=httpx.MockTransport(handler))

    with pytest.raises(httpx.HTTPStatusError):
        client.fetch_merged_pull_requests()


def test_fetch_pull_request_detail_returns_expected_shape() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/repos/openai/codex/pulls/123"
        payload = {
            "id": 123000,
            "number": 123,
            "title": "Improve planner",
            "html_url": "https://example.test/pull/123",
            "merged_at": "2026-02-16T12:00:00Z",
            "body": "Implements better scheduling.",
        }
        return httpx.Response(200, json=payload)

    client = GitHubClient(settings=Settings(), transport=httpx.MockTransport(handler))

    detail = client.fetch_pull_request_detail(123)

    assert detail == PullRequestDetail(
        id=123000,
        number=123,
        title="Improve planner",
        html_url="https://example.test/pull/123",
        merged_at=_utc("2026-02-16T12:00:00Z"),
        body="Implements better scheduling.",
    )


def test_fetch_pull_request_detail_rejects_unmerged_payload() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "id": 123000,
                "number": 123,
                "title": "Improve planner",
                "html_url": "https://example.test/pull/123",
                "merged_at": None,
            },
        )

    client = GitHubClient(settings=Settings(), transport=httpx.MockTransport(handler))

    with pytest.raises(ValueError, match="merged_at"):
        client.fetch_pull_request_detail(123)


def test_fetch_releases_filters_alpha_prerelease_and_draft() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/repos/openai/codex/releases"
        assert request.url.params["per_page"] == "100"
        assert request.url.params["page"] == "1"
        payload = [
            {
                "id": 200,
                "tag_name": "v1.0.0",
                "name": "v1.0.0",
                "html_url": "https://example.test/release/v1.0.0",
                "published_at": "2026-02-16T09:00:00Z",
                "body": "stable",
                "prerelease": False,
                "draft": False,
            },
            {
                "id": 201,
                "tag_name": "v1.1.0-alpha.1",
                "name": "v1.1.0-alpha.1",
                "html_url": "https://example.test/release/v1.1.0-alpha.1",
                "published_at": "2026-02-16T10:00:00Z",
                "body": "alpha",
                "prerelease": False,
                "draft": False,
            },
            {
                "id": 202,
                "tag_name": "v1.1.0-rc.1",
                "name": "v1.1.0-rc.1",
                "html_url": "https://example.test/release/v1.1.0-rc.1",
                "published_at": "2026-02-16T11:00:00Z",
                "body": "rc",
                "prerelease": True,
                "draft": False,
            },
            {
                "id": 203,
                "tag_name": "v1.2.0",
                "name": "v1.2.0",
                "html_url": "https://example.test/release/v1.2.0",
                "published_at": "2026-02-16T12:00:00Z",
                "body": "draft",
                "prerelease": False,
                "draft": True,
            },
            {
                "id": 204,
                "tag_name": "v1.0.1",
                "name": "v1.0.1",
                "html_url": "https://example.test/release/v1.0.1",
                "published_at": "2026-02-16T09:30:00Z",
                "body": "stable patch",
                "prerelease": False,
                "draft": False,
            },
        ]
        return httpx.Response(200, json=payload)

    client = GitHubClient(settings=Settings(), transport=httpx.MockTransport(handler))

    releases = client.fetch_releases()

    assert [release.id for release in releases] == [200, 204]
    assert releases[0].tag_name == "v1.0.0"
    assert releases[1].tag_name == "v1.0.1"
    assert releases[0].published_at == _utc("2026-02-16T09:00:00Z")
    assert releases[1].published_at == _utc("2026-02-16T09:30:00Z")


def test_select_unprocessed_pull_requests_filters_by_last_merged_at_and_processed_ids() -> None:
    last_merged_at = _utc("2026-02-16T10:00:00Z")
    pull_requests = [
        _pull_request(pr_id=10, number=100, merged_at=_utc("2026-02-16T09:59:59Z")),
        _pull_request(pr_id=20, number=101, merged_at=_utc("2026-02-16T10:00:00Z")),
        _pull_request(pr_id=21, number=102, merged_at=_utc("2026-02-16T10:00:00Z")),
        _pull_request(pr_id=30, number=103, merged_at=_utc("2026-02-16T10:00:01Z")),
        _pull_request(pr_id=30, number=103, merged_at=_utc("2026-02-16T10:00:01Z")),
    ]

    unprocessed = select_unprocessed_pull_requests(
        pull_requests,
        last_merged_at=last_merged_at,
        processed_pr_ids={20},
    )

    assert [pr.id for pr in unprocessed] == [21, 30]


def test_select_unprocessed_pull_requests_without_last_merged_at_returns_sorted_unique_rows() -> None:
    pull_requests = [
        _pull_request(pr_id=3, number=103, merged_at=_utc("2026-02-16T10:00:01Z")),
        _pull_request(pr_id=2, number=102, merged_at=_utc("2026-02-16T10:00:00Z")),
        _pull_request(pr_id=2, number=102, merged_at=_utc("2026-02-16T10:00:00Z")),
    ]

    unprocessed = select_unprocessed_pull_requests(
        pull_requests,
        last_merged_at=None,
        processed_pr_ids=set(),
    )

    assert [pr.id for pr in unprocessed] == [2, 3]


def test_select_unprocessed_pull_requests_normalizes_naive_last_merged_at() -> None:
    naive_last_merged_at = datetime(2026, 2, 16, 10, 0, 0)
    pull_requests = [
        _pull_request(pr_id=11, number=101, merged_at=_utc("2026-02-16T10:00:00Z")),
        _pull_request(pr_id=12, number=102, merged_at=_utc("2026-02-16T10:00:00Z")),
    ]

    unprocessed = select_unprocessed_pull_requests(
        pull_requests,
        last_merged_at=naive_last_merged_at,
        processed_pr_ids={11},
    )

    assert [pr.id for pr in unprocessed] == [12]


def test_select_unprocessed_releases_filters_by_last_published_at_and_ids() -> None:
    last_published_at = _utc("2026-02-16T10:00:00Z")
    releases = [
        _release(
            release_id=1,
            tag_name="v1.0.0",
            published_at=_utc("2026-02-16T09:59:59Z"),
        ),
        _release(
            release_id=2,
            tag_name="v1.0.1",
            published_at=_utc("2026-02-16T10:00:00Z"),
        ),
        _release(
            release_id=3,
            tag_name="v1.0.2",
            published_at=_utc("2026-02-16T10:00:00Z"),
        ),
        _release(
            release_id=4,
            tag_name="v1.1.0",
            published_at=_utc("2026-02-16T10:10:00Z"),
        ),
        _release(
            release_id=4,
            tag_name="v1.1.0",
            published_at=_utc("2026-02-16T10:10:00Z"),
        ),
    ]

    unprocessed = select_unprocessed_releases(
        releases,
        last_published_at=last_published_at,
        processed_release_ids={2},
    )

    assert [release.id for release in unprocessed] == [3, 4]
