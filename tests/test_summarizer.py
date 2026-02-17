from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
import sys

from openai import OpenAIError
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from codexwatch.config import Settings
from codexwatch.github_client import PullRequest, Release
from codexwatch.summarizer import FALLBACK_RELEASE_SUMMARY, FALLBACK_SUMMARY, Summarizer


def _pull_request() -> PullRequest:
    return PullRequest(
        id=101,
        number=42,
        title="Add improved diff analyzer",
        html_url="https://github.com/openai/codex/pull/42",
        merged_at=datetime(2026, 2, 17, 1, 2, 3, tzinfo=timezone.utc),
    )


def _release() -> Release:
    return Release(
        id=201,
        tag_name="v1.2.3",
        name="v1.2.3",
        html_url="https://github.com/openai/codex/releases/tag/v1.2.3",
        published_at=datetime(2026, 2, 17, 4, 5, 6, tzinfo=timezone.utc),
        body="Release note body",
        prerelease=False,
    )


class _FakeCompletions:
    def __init__(self, *, content: str | None = None, raise_error: Exception | None = None) -> None:
        self._content = content
        self._raise_error = raise_error
        self.calls: list[dict[str, object]] = []

    def create(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        if self._raise_error is not None:
            raise self._raise_error

        message = SimpleNamespace(content=self._content)
        choice = SimpleNamespace(message=message)
        return SimpleNamespace(choices=[choice])


class _FakeOpenAIClient:
    def __init__(self, completions: _FakeCompletions) -> None:
        self.chat = SimpleNamespace(completions=completions)


def test_summarize_pull_request_returns_structured_summary() -> None:
    completions = _FakeCompletions(
        content=(
            '{"overview": "概要1", "feature_details": "機能2", "enabled_outcomes": "成果3"}'
        )
    )
    summarizer = Summarizer(
        settings=Settings(openai_api_key="sk-test", openai_model="gpt-test"),
        openai_client=_FakeOpenAIClient(completions),
    )

    summary = summarizer.summarize_pull_request(
        _pull_request(),
        detail={"body": "This PR improves diff parsing."},
    )

    assert summary.overview == "概要1"
    assert summary.feature_details == "機能2"
    assert summary.enabled_outcomes == "成果3"

    assert len(completions.calls) == 1
    request = completions.calls[0]
    assert request["model"] == "gpt-test"
    assert request["response_format"] == {"type": "json_object"}

    messages = request["messages"]
    assert isinstance(messages, list)
    assert "Summarize this merged PR in Japanese." in str(messages[1]["content"])


def test_summarize_pull_request_falls_back_when_openai_raises() -> None:
    completions = _FakeCompletions(raise_error=OpenAIError("boom"))
    summarizer = Summarizer(
        settings=Settings(openai_api_key="sk-test"),
        openai_client=_FakeOpenAIClient(completions),
    )

    summary = summarizer.summarize_pull_request(_pull_request())

    assert summary == FALLBACK_SUMMARY


def test_summarize_pull_request_re_raises_non_openai_error() -> None:
    completions = _FakeCompletions(raise_error=RuntimeError("boom"))
    summarizer = Summarizer(
        settings=Settings(openai_api_key="sk-test"),
        openai_client=_FakeOpenAIClient(completions),
    )

    with pytest.raises(RuntimeError, match="boom"):
        summarizer.summarize_pull_request(_pull_request())


def test_summarize_pull_request_falls_back_when_key_is_missing() -> None:
    summarizer = Summarizer(settings=Settings(openai_api_key=None))

    summary = summarizer.summarize_pull_request(_pull_request())

    assert summary == FALLBACK_SUMMARY


def test_summarize_pull_request_falls_back_on_invalid_json_response() -> None:
    completions = _FakeCompletions(content='{"overview": "x"}')
    summarizer = Summarizer(
        settings=Settings(openai_api_key="sk-test"),
        openai_client=_FakeOpenAIClient(completions),
    )

    summary = summarizer.summarize_pull_request(_pull_request())

    assert summary == FALLBACK_SUMMARY


def test_summarize_release_returns_structured_summary() -> None:
    completions = _FakeCompletions(
        content=(
            '{"overview": "概要R", "feature_details": "機能R", "enabled_outcomes": "成果R"}'
        )
    )
    summarizer = Summarizer(
        settings=Settings(openai_api_key="sk-test", openai_model="gpt-test"),
        openai_client=_FakeOpenAIClient(completions),
    )

    summary = summarizer.summarize_release(_release())

    assert summary.overview == "概要R"
    assert summary.feature_details == "機能R"
    assert summary.enabled_outcomes == "成果R"

    assert len(completions.calls) == 1
    request = completions.calls[0]
    messages = request["messages"]
    assert isinstance(messages, list)
    assert "Summarize this GitHub release in Japanese." in str(messages[1]["content"])


def test_summarize_release_falls_back_when_openai_raises() -> None:
    completions = _FakeCompletions(raise_error=OpenAIError("boom"))
    summarizer = Summarizer(
        settings=Settings(openai_api_key="sk-test"),
        openai_client=_FakeOpenAIClient(completions),
    )

    summary = summarizer.summarize_release(_release())

    assert summary == FALLBACK_RELEASE_SUMMARY
