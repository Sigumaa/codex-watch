from __future__ import annotations

import argparse
from collections.abc import Sequence
from dataclasses import replace
import logging
import os

from codexwatch.config import Settings, load_settings
from codexwatch.pipeline import PipelineRunner
from dotenv import load_dotenv


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="codexwatch",
        description="Run codexwatch pipeline.",
    )
    dry_run_group = parser.add_mutually_exclusive_group()
    dry_run_group.add_argument(
        "--dry-run",
        action="store_true",
        help="Run without side effects.",
    )
    dry_run_group.add_argument(
        "--no-dry-run",
        action="store_true",
        help="Disable dry-run mode.",
    )
    return parser


def _apply_cli_overrides(settings: Settings, args: argparse.Namespace) -> Settings:
    if args.dry_run:
        return replace(settings, dry_run=True)
    if args.no_dry_run:
        return replace(settings, dry_run=False)
    return settings


def _load_settings_with_cli_dry_run(args: argparse.Namespace) -> Settings:
    if args.dry_run or args.no_dry_run:
        load_dotenv()
        env = dict(os.environ)
        env["CODEXWATCH_DRY_RUN"] = "true" if args.dry_run else "false"
        return load_settings(env=env)
    return load_settings()


def _configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    _configure_logging()
    settings = _apply_cli_overrides(_load_settings_with_cli_dry_run(args), args)
    logger = logging.getLogger("codexwatch.main")

    logger.info(
        "Starting codexwatch runner repo=%s branch=%s dry_run=%s interval_min=%s",
        settings.github_repo,
        settings.github_base_branch,
        settings.dry_run,
        settings.poll_interval_minutes,
    )

    result = PipelineRunner(settings=settings).run()
    if not result.success:
        logger.error("Pipeline failed: %s", result.message)
        return 1

    logger.info(
        "Pipeline completed processed_pr_count=%s message=%s",
        result.processed_pr_count,
        result.message,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
