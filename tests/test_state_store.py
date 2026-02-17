from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from codexwatch.state_store import (
    StateSnapshot,
    StateStore,
    compute_next_release_state,
    compute_next_state,
    is_pr_already_processed,
)


def test_load_returns_default_when_file_is_missing(tmp_path: Path) -> None:
    store = StateStore(tmp_path / "state" / "state.json")

    state = store.load()

    assert state == StateSnapshot(last_merged_at=None, processed_pr_ids=[])


def test_save_and_load_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "state" / "state.json"
    store = StateStore(path)
    original = StateSnapshot(
        last_merged_at="2026-02-17T09:00:00Z",
        processed_pr_ids=[101, 102],
    )

    store.save(original)
    restored = store.load()

    assert json.loads(path.read_text(encoding="utf-8")) == {
        "last_merged_at": "2026-02-17T09:00:00Z",
        "processed_pr_ids": [101, 102],
    }
    assert restored == original


def test_save_uses_temp_file_and_replace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "state" / "state.json"
    store = StateStore(path)
    replace_calls: list[tuple[Path, Path]] = []
    original_replace = Path.replace

    def spy_replace(source: Path, target: str | Path) -> Path:
        replace_calls.append((source, Path(target)))
        return original_replace(source, target)

    monkeypatch.setattr(Path, "replace", spy_replace)

    store.save(
        StateSnapshot(
            last_merged_at="2026-02-17T09:00:00Z",
            processed_pr_ids=[7],
        )
    )

    assert len(replace_calls) == 1
    source, target = replace_calls[0]
    assert target == path
    assert source.parent == path.parent
    assert source != path
    assert not source.exists()


def test_save_raises_and_cleans_temp_file_when_replace_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "state" / "state.json"
    store = StateStore(path)

    def broken_replace(_source: Path, _target: str | Path) -> Path:
        raise OSError("replace failed")

    monkeypatch.setattr(Path, "replace", broken_replace)

    with pytest.raises(OSError, match="Failed to save state file atomically"):
        store.save(
            StateSnapshot(
                last_merged_at="2026-02-17T09:00:00Z",
                processed_pr_ids=[7],
            )
        )

    assert not list(path.parent.glob(f".{path.name}.*.tmp"))


def test_load_raises_for_invalid_schema(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    path.write_text(
        json.dumps(
            {
                "last_merged_at": 123,
                "processed_pr_ids": ["1"],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="last_merged_at"):
        StateStore(path).load()


def test_load_returns_default_when_file_disappears_during_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "state.json"
    path.write_text("{}", encoding="utf-8")

    def raise_file_not_found(_path: Path, encoding: str = "utf-8") -> str:
        raise FileNotFoundError("gone")

    monkeypatch.setattr(Path, "read_text", raise_file_not_found)

    assert StateStore(path).load() == StateSnapshot(last_merged_at=None, processed_pr_ids=[])


def test_load_raises_for_io_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "state.json"

    def raise_permission_error(_path: Path, encoding: str = "utf-8") -> str:
        raise PermissionError("denied")

    monkeypatch.setattr(Path, "read_text", raise_permission_error)

    with pytest.raises(OSError, match="Failed to read state file"):
        StateStore(path).load()


def test_load_raises_for_invalid_json(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    path.write_text("{", encoding="utf-8")

    with pytest.raises(ValueError, match="Invalid JSON in state file"):
        StateStore(path).load()


def test_load_normalizes_processed_pr_ids(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    path.write_text(
        json.dumps(
            {
                "last_merged_at": "2026-02-17T10:00:00+00:00",
                "processed_pr_ids": ["3", 1, "2", "1", 2],
            }
        ),
        encoding="utf-8",
    )

    state = StateStore(path).load()

    assert state == StateSnapshot(
        last_merged_at="2026-02-17T10:00:00Z",
        processed_pr_ids=[1, 2, 3],
    )


def test_load_raises_for_invalid_processed_pr_ids(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    path.write_text(
        json.dumps(
            {
                "last_merged_at": "2026-02-17T10:00:00Z",
                "processed_pr_ids": ["x"],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="processed_pr_ids"):
        StateStore(path).load()


def test_load_normalizes_release_state_fields(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    path.write_text(
        json.dumps(
            {
                "last_merged_at": "2026-02-17T10:00:00Z",
                "processed_pr_ids": [1],
                "last_release_published_at": "2026-02-17T11:00:00+00:00",
                "processed_release_ids": ["3", 2, "2"],
            }
        ),
        encoding="utf-8",
    )

    state = StateStore(path).load()

    assert state == StateSnapshot(
        last_merged_at="2026-02-17T10:00:00Z",
        processed_pr_ids=[1],
        last_release_published_at="2026-02-17T11:00:00Z",
        processed_release_ids=[2, 3],
    )


def test_is_pr_already_processed_uses_timestamp_and_boundary_ids() -> None:
    state = StateSnapshot(
        last_merged_at="2026-02-17T10:00:00Z",
        processed_pr_ids=[11, 12],
    )

    assert is_pr_already_processed(state, pr_id=10, merged_at="2026-02-17T09:59:59Z")
    assert is_pr_already_processed(state, pr_id=11, merged_at="2026-02-17T10:00:00Z")
    assert not is_pr_already_processed(state, pr_id=13, merged_at="2026-02-17T10:00:00Z")
    assert not is_pr_already_processed(state, pr_id=99, merged_at="2026-02-17T10:00:01Z")


def test_compute_next_state_keeps_only_latest_timestamp_ids() -> None:
    current = StateSnapshot(
        last_merged_at="2026-02-17T09:00:00Z",
        processed_pr_ids=[1, 2],
    )
    processed_prs = [
        {"number": 200, "merged_at": "2026-02-17T11:30:00Z"},
        {"pr_id": 201, "merged_at": "2026-02-17T11:30:00+00:00"},
        {"id": 150, "merged_at": "2026-02-17T11:00:00Z"},
    ]

    next_state = compute_next_state(current, processed_prs)

    assert next_state == StateSnapshot(
        last_merged_at="2026-02-17T11:30:00Z",
        processed_pr_ids=[200, 201],
    )


@dataclass
class _ProcessedPR:
    id: int
    merged_at: datetime


def test_compute_next_state_merges_existing_ids_on_same_latest_timestamp() -> None:
    current = StateSnapshot(
        last_merged_at="2026-02-17T11:30:00Z",
        processed_pr_ids=[200],
    )
    processed_prs = [
        _ProcessedPR(
            id=201,
            merged_at=datetime(2026, 2, 17, 11, 30, tzinfo=timezone.utc),
        ),
        _ProcessedPR(
            id=150,
            merged_at=datetime(2026, 2, 17, 11, 0, tzinfo=timezone.utc),
        ),
    ]

    next_state = compute_next_state(current, processed_prs)

    assert next_state == StateSnapshot(
        last_merged_at="2026-02-17T11:30:00Z",
        processed_pr_ids=[200, 201],
    )


def test_compute_next_state_keeps_current_state_when_only_older_prs_processed() -> None:
    current = StateSnapshot(
        last_merged_at="2026-02-17T11:30:00Z",
        processed_pr_ids=[200, 201],
    )

    next_state = compute_next_state(
        current,
        [{"number": 120, "merged_at": "2026-02-17T11:00:00Z"}],
    )

    assert next_state == current


def test_compute_next_release_state_keeps_only_latest_timestamp_ids() -> None:
    current = StateSnapshot(
        last_merged_at="2026-02-17T09:00:00Z",
        processed_pr_ids=[1],
        last_release_published_at="2026-02-17T10:00:00Z",
        processed_release_ids=[10],
    )
    processed_releases = [
        {"id": 11, "published_at": "2026-02-17T10:00:00Z"},
        {"id": 20, "published_at": "2026-02-17T11:00:00Z"},
        {"id": 21, "published_at": "2026-02-17T11:00:00+00:00"},
    ]

    next_state = compute_next_release_state(current, processed_releases)

    assert next_state == StateSnapshot(
        last_merged_at="2026-02-17T09:00:00Z",
        processed_pr_ids=[1],
        last_release_published_at="2026-02-17T11:00:00Z",
        processed_release_ids=[20, 21],
    )


def test_compute_next_release_state_keeps_current_when_only_older_releases_processed() -> None:
    current = StateSnapshot(
        last_merged_at="2026-02-17T09:00:00Z",
        processed_pr_ids=[1],
        last_release_published_at="2026-02-17T11:00:00Z",
        processed_release_ids=[20, 21],
    )

    next_state = compute_next_release_state(
        current,
        [{"id": 19, "published_at": "2026-02-17T10:30:00Z"}],
    )

    assert next_state == current
