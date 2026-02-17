from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile

DEFAULT_STATE_PATH = Path("state/state.json")


@dataclass(slots=True)
class StateSnapshot:
    last_merged_at: str | None = None
    processed_pr_ids: list[int] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "last_merged_at": self.last_merged_at,
            "processed_pr_ids": list(self.processed_pr_ids),
        }


class StateStore:
    def __init__(self, path: str | Path = DEFAULT_STATE_PATH) -> None:
        self.path = Path(path)

    def load(self) -> StateSnapshot:
        try:
            raw_text = self.path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return StateSnapshot()
        except OSError as exc:
            raise OSError(f"Failed to read state file: {self.path}") from exc

        try:
            payload = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON in state file: {self.path}") from exc

        if not isinstance(payload, Mapping):
            raise ValueError(f"State file must contain a JSON object: {self.path}")

        return _snapshot_from_mapping(payload)

    def save(self, state: StateSnapshot) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        serialized = json.dumps(state.to_dict(), ensure_ascii=True, indent=2)
        temp_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self.path.parent,
                prefix=f".{self.path.name}.",
                suffix=".tmp",
                delete=False,
            ) as tmp_file:
                temp_path = Path(tmp_file.name)
                tmp_file.write(f"{serialized}\n")
                tmp_file.flush()
                os.fsync(tmp_file.fileno())

            temp_path.replace(self.path)
        except OSError as exc:
            if temp_path is not None:
                temp_path.unlink(missing_ok=True)
            raise OSError(f"Failed to save state file atomically: {self.path}") from exc


def load_state(path: str | Path = DEFAULT_STATE_PATH) -> StateSnapshot:
    return StateStore(path).load()


def save_state(state: StateSnapshot, path: str | Path = DEFAULT_STATE_PATH) -> None:
    StateStore(path).save(state)


def is_pr_already_processed(
    state: StateSnapshot,
    *,
    pr_id: int,
    merged_at: str | datetime,
) -> bool:
    if state.last_merged_at is None:
        return False

    candidate_merged_at = _to_datetime(merged_at)
    state_merged_at = _to_datetime(state.last_merged_at)
    if candidate_merged_at < state_merged_at:
        return True
    if candidate_merged_at > state_merged_at:
        return False
    return pr_id in state.processed_pr_ids


def compute_next_state(
    current_state: StateSnapshot,
    processed_prs: Sequence[object],
) -> StateSnapshot:
    if not processed_prs:
        return StateSnapshot(
            last_merged_at=current_state.last_merged_at,
            processed_pr_ids=list(current_state.processed_pr_ids),
        )

    if current_state.last_merged_at is None:
        latest_merged_at: datetime | None = None
        latest_ids: set[int] = set()
    else:
        latest_merged_at = _to_datetime(current_state.last_merged_at)
        latest_ids = set(current_state.processed_pr_ids)

    for processed_pr in processed_prs:
        pr_id = _extract_pr_id(processed_pr)
        pr_merged_at = _extract_merged_at(processed_pr)

        if latest_merged_at is None or pr_merged_at > latest_merged_at:
            latest_merged_at = pr_merged_at
            latest_ids = {pr_id}
            continue

        if pr_merged_at == latest_merged_at:
            latest_ids.add(pr_id)

    if latest_merged_at is None:
        return StateSnapshot()

    return StateSnapshot(
        last_merged_at=_to_iso8601(latest_merged_at),
        processed_pr_ids=sorted(latest_ids),
    )


def _snapshot_from_mapping(raw: Mapping[str, object]) -> StateSnapshot:
    raw_last_merged_at = raw.get("last_merged_at")
    if raw_last_merged_at is None:
        last_merged_at = None
    elif isinstance(raw_last_merged_at, str):
        last_merged_at = _to_iso8601(_to_datetime(raw_last_merged_at))
    else:
        raise ValueError("last_merged_at must be an ISO8601 string or null")

    raw_processed_pr_ids = raw.get("processed_pr_ids", [])
    if not isinstance(raw_processed_pr_ids, list):
        raise ValueError("processed_pr_ids must be a list")

    return StateSnapshot(
        last_merged_at=last_merged_at,
        processed_pr_ids=_normalize_processed_pr_ids(raw_processed_pr_ids),
    )


def _normalize_processed_pr_ids(raw_values: Sequence[object]) -> list[int]:
    normalized_ids: set[int] = set()
    for value in raw_values:
        if isinstance(value, bool):
            raise ValueError("processed_pr_ids must contain integers")
        if isinstance(value, int):
            normalized_ids.add(value)
            continue
        if isinstance(value, str):
            text = value.strip()
            if not text:
                raise ValueError("processed_pr_ids must contain integers")
            try:
                normalized_ids.add(int(text))
            except ValueError as exc:
                raise ValueError("processed_pr_ids must contain integers") from exc
            continue
        raise ValueError("processed_pr_ids must contain integers")

    return sorted(normalized_ids)


def _extract_pr_id(processed_pr: object) -> int:
    raw = _read_field(processed_pr, names=("pr_id", "id", "number"))
    if isinstance(raw, bool) or not isinstance(raw, int):
        raise ValueError("Processed PR must provide an integer pr_id/id/number")
    return raw


def _extract_merged_at(processed_pr: object) -> datetime:
    raw = _read_field(processed_pr, names=("merged_at",))
    if isinstance(raw, str | datetime):
        return _to_datetime(raw)
    raise ValueError("Processed PR must provide merged_at as ISO8601 string or datetime")


def _read_field(processed_pr: object, *, names: tuple[str, ...]) -> object | None:
    if isinstance(processed_pr, Mapping):
        for name in names:
            if name in processed_pr:
                return processed_pr[name]
        return None

    for name in names:
        if hasattr(processed_pr, name):
            return getattr(processed_pr, name)
    return None


def _to_datetime(raw: str | datetime) -> datetime:
    if isinstance(raw, datetime):
        parsed = raw
    elif isinstance(raw, str):
        text = raw.strip()
        if not text:
            raise ValueError("ISO8601 datetime string must not be empty")
        if text.endswith("Z"):
            text = f"{text[:-1]}+00:00"
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError as exc:
            raise ValueError(f"Invalid ISO8601 datetime: {raw!r}") from exc
    else:
        raise ValueError("merged_at must be an ISO8601 string or datetime")

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _to_iso8601(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
