from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import json
import logging
from datetime import timezone
from typing import Any

from openai import OpenAI, OpenAIError

from codexwatch.config import Settings
from codexwatch.github_client import PullRequest, Release


@dataclass(frozen=True)
class PullRequestSummary:
    overview: str
    feature_details: str
    enabled_outcomes: str


FALLBACK_SUMMARY = PullRequestSummary(
    overview="このPRの要約を自動生成できなかったため、PR本文を確認してください。",
    feature_details="OpenAI APIの応答取得に失敗したため、機能内容はフォールバック表示です。",
    enabled_outcomes="通知は継続されるため、PRリンクから変更点を追跡できます。",
)

FALLBACK_RELEASE_SUMMARY = PullRequestSummary(
    overview="このReleaseの要約を自動生成できなかったため、Release本文を確認してください。",
    feature_details="OpenAI APIの応答取得に失敗したため、機能内容はフォールバック表示です。",
    enabled_outcomes="通知は継続されるため、Releaseリンクから変更点を追跡できます。",
)


class OpenAISummaryError(RuntimeError):
    pass


class Summarizer:
    def __init__(
        self,
        settings: Settings,
        *,
        logger: logging.Logger | None = None,
        openai_client: Any | None = None,
    ) -> None:
        self._settings = settings
        self._logger = logger or logging.getLogger(__name__)
        self._openai_client = openai_client

    def summarize_pull_request(
        self,
        pull_request: PullRequest,
        *,
        detail: object | None = None,
    ) -> PullRequestSummary:
        try:
            payload = self._request_summary_payload(
                system_prompt=(
                    "You summarize merged GitHub pull requests. Return valid JSON only with keys "
                    "overview, feature_details, enabled_outcomes. Keep each value concise."
                ),
                user_prompt=_build_pull_request_prompt(pull_request, detail=detail),
            )
            try:
                return _parse_summary_payload(payload)
            except ValueError as exc:
                raise OpenAISummaryError(str(exc)) from exc
        except OpenAISummaryError as exc:
            self._logger.warning(
                "Falling back to static summary for PR #%s due to OpenAI failure: %s",
                pull_request.number,
                exc,
            )
            return FALLBACK_SUMMARY

    def summarize_release(self, release: Release) -> PullRequestSummary:
        try:
            payload = self._request_summary_payload(
                system_prompt=(
                    "You summarize GitHub releases. Return valid JSON only with keys "
                    "overview, feature_details, enabled_outcomes. Keep each value concise."
                ),
                user_prompt=_build_release_prompt(release),
            )
            try:
                return _parse_summary_payload(payload)
            except ValueError as exc:
                raise OpenAISummaryError(str(exc)) from exc
        except OpenAISummaryError as exc:
            self._logger.warning(
                "Falling back to static summary for release %s due to OpenAI failure: %s",
                release.tag_name,
                exc,
            )
            return FALLBACK_RELEASE_SUMMARY

    def _request_summary_payload(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
    ) -> Mapping[str, Any]:
        client = self._get_openai_client()
        try:
            completion = client.chat.completions.create(
                model=self._settings.openai_model,
                temperature=0.2,
                response_format={"type": "json_object"},
                messages=[
                    {
                        "role": "system",
                        "content": system_prompt,
                    },
                    {
                        "role": "user",
                        "content": user_prompt,
                    },
                ],
            )
        except OpenAIError as exc:
            raise OpenAISummaryError(str(exc)) from exc

        try:
            content = completion.choices[0].message.content
        except (AttributeError, IndexError, TypeError) as exc:
            raise OpenAISummaryError("OpenAI response payload must include message content") from exc

        if not isinstance(content, str) or not content.strip():
            raise OpenAISummaryError("OpenAI response content must be non-empty text")

        try:
            payload = json.loads(content)
        except json.JSONDecodeError as exc:
            raise OpenAISummaryError("OpenAI response must be valid JSON") from exc
        if not isinstance(payload, Mapping):
            raise OpenAISummaryError("OpenAI response JSON must be an object")
        return payload

    def _get_openai_client(self) -> Any:
        if self._openai_client is not None:
            return self._openai_client
        if not self._settings.openai_api_key:
            raise OpenAISummaryError("OPENAI_API_KEY is not configured")

        self._openai_client = OpenAI(api_key=self._settings.openai_api_key)
        return self._openai_client


def _build_pull_request_prompt(pull_request: PullRequest, *, detail: object | None) -> str:
    body = _extract_optional_text(detail, "body")

    lines = [
        "Summarize this merged PR in Japanese.",
        f"PR number: {pull_request.number}",
        f"Title: {pull_request.title}",
        f"URL: {pull_request.html_url}",
    ]

    if body:
        lines.extend(["Body:", body])

    return "\n".join(lines)


def _build_release_prompt(release: Release) -> str:
    lines = [
        "Summarize this GitHub release in Japanese.",
        f"Release tag: {release.tag_name}",
        f"Release name: {release.name}",
        f"URL: {release.html_url}",
        f"Published at: {release.published_at.astimezone(timezone.utc).isoformat()}",
    ]

    if release.body:
        lines.extend(["Body:", release.body])

    return "\n".join(lines)


def _parse_summary_payload(payload: Mapping[str, Any]) -> PullRequestSummary:
    return PullRequestSummary(
        overview=_normalize_summary_field(payload.get("overview"), field_name="overview"),
        feature_details=_normalize_summary_field(
            payload.get("feature_details"),
            field_name="feature_details",
        ),
        enabled_outcomes=_normalize_summary_field(
            payload.get("enabled_outcomes"),
            field_name="enabled_outcomes",
        ),
    )


def _normalize_summary_field(value: object, *, field_name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"Summary field '{field_name}' must be text")

    normalized = value.strip()
    if not normalized:
        raise ValueError(f"Summary field '{field_name}' must not be empty")
    return normalized


def _extract_optional_text(source: object | None, field_name: str) -> str | None:
    if source is None:
        return None

    if isinstance(source, Mapping):
        raw = source.get(field_name)
    else:
        raw = getattr(source, field_name, None)

    if raw is None:
        return None
    if isinstance(raw, str):
        normalized = raw.strip()
        return normalized or None

    return str(raw)
