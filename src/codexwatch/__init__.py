"""codexwatch package."""

from codexwatch.config import Settings, load_settings
from codexwatch.discord_client import DiscordClient
from codexwatch.github_client import (
    GitHubClient,
    PullRequest,
    PullRequestDetail,
    select_unprocessed_pull_requests,
)
from codexwatch.pipeline import PipelineRunner, RunResult
from codexwatch.summarizer import PullRequestSummary, Summarizer

__all__ = [
    "DiscordClient",
    "GitHubClient",
    "PipelineRunner",
    "PullRequest",
    "PullRequestDetail",
    "PullRequestSummary",
    "RunResult",
    "Settings",
    "Summarizer",
    "load_settings",
    "select_unprocessed_pull_requests",
]
__version__ = "0.1.0"
