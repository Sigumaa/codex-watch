from __future__ import annotations

from dataclasses import dataclass
import logging

from codexwatch.config import Settings


@dataclass(frozen=True)
class RunResult:
    success: bool
    processed_pr_count: int = 0
    message: str = ""


class PipelineRunner:
    """C-01 step runner skeleton.

    C-02/C-03/C-04 will replace this no-op behavior with real pipeline logic.
    """

    def __init__(self, settings: Settings, logger: logging.Logger | None = None) -> None:
        self.settings = settings
        self.logger = logger or logging.getLogger(__name__)

    def run(self) -> RunResult:
        if self.settings.dry_run:
            self.logger.info(
                "Dry-run enabled. Scheduler/Runner skeleton executed with no external calls."
            )
            return RunResult(success=True, processed_pr_count=0, message="dry-run no-op")

        self.logger.error(
            "Non-dry-run mode is not implemented yet. Refusing to run as success."
        )
        return RunResult(
            success=False,
            processed_pr_count=0,
            message="non-dry-run mode is not implemented",
        )
