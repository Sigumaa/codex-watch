from __future__ import annotations

from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import codexwatch.main as main_module
from codexwatch.config import Settings
from codexwatch.pipeline import RunResult


def test_main_dry_run_flag_overrides_env(monkeypatch) -> None:
    observed: dict[str, bool] = {}

    class DummyRunner:
        def __init__(self, settings: Settings) -> None:
            observed["dry_run"] = settings.dry_run

        def run(self) -> RunResult:
            return RunResult(success=True, processed_pr_count=0, message="ok")

    monkeypatch.setattr(main_module, "load_settings", lambda env=None: Settings(dry_run=False))
    monkeypatch.setattr(main_module, "PipelineRunner", DummyRunner)

    exit_code = main_module.main(["--dry-run"])

    assert exit_code == 0
    assert observed["dry_run"] is True


def test_main_no_dry_run_flag_overrides_env(monkeypatch) -> None:
    observed: dict[str, bool] = {}

    class DummyRunner:
        def __init__(self, settings: Settings) -> None:
            observed["dry_run"] = settings.dry_run

        def run(self) -> RunResult:
            return RunResult(success=True, processed_pr_count=0, message="ok")

    monkeypatch.setattr(main_module, "load_settings", lambda env=None: Settings(dry_run=True))
    monkeypatch.setattr(main_module, "PipelineRunner", DummyRunner)

    exit_code = main_module.main(["--no-dry-run"])

    assert exit_code == 0
    assert observed["dry_run"] is False


def test_main_returns_non_zero_when_pipeline_fails(monkeypatch) -> None:
    class FailingRunner:
        def __init__(self, settings: Settings) -> None:
            self.settings = settings

        def run(self) -> RunResult:
            return RunResult(success=False, processed_pr_count=0, message="failed")

    monkeypatch.setattr(main_module, "load_settings", lambda env=None: Settings(dry_run=True))
    monkeypatch.setattr(main_module, "PipelineRunner", FailingRunner)

    exit_code = main_module.main([])

    assert exit_code == 1


def test_main_dry_run_flag_starts_with_invalid_env_dry_run(monkeypatch) -> None:
    observed: dict[str, bool] = {}

    class DummyRunner:
        def __init__(self, settings: Settings) -> None:
            observed["dry_run"] = settings.dry_run

        def run(self) -> RunResult:
            return RunResult(success=True, processed_pr_count=0, message="ok")

    monkeypatch.setenv("CODEXWATCH_DRY_RUN", "not-bool")
    monkeypatch.setattr(main_module, "PipelineRunner", DummyRunner)

    exit_code = main_module.main(["--dry-run"])

    assert exit_code == 0
    assert observed["dry_run"] is True


def test_main_no_dry_run_flag_starts_with_invalid_env_dry_run(monkeypatch) -> None:
    observed: dict[str, bool] = {}

    class DummyRunner:
        def __init__(self, settings: Settings) -> None:
            observed["dry_run"] = settings.dry_run

        def run(self) -> RunResult:
            return RunResult(success=True, processed_pr_count=0, message="ok")

    monkeypatch.setenv("CODEXWATCH_DRY_RUN", "not-bool")
    monkeypatch.setattr(main_module, "PipelineRunner", DummyRunner)

    exit_code = main_module.main(["--no-dry-run"])

    assert exit_code == 0
    assert observed["dry_run"] is False


def test_main_raises_for_invalid_env_dry_run_without_cli_override(monkeypatch) -> None:
    monkeypatch.setenv("CODEXWATCH_DRY_RUN", "not-bool")

    with pytest.raises(ValueError, match="CODEXWATCH_DRY_RUN"):
        main_module.main([])


def test_main_returns_non_zero_for_non_dry_run_not_implemented(monkeypatch) -> None:
    monkeypatch.setattr(main_module, "load_settings", lambda env=None: Settings(dry_run=False))

    exit_code = main_module.main([])

    assert exit_code == 1
