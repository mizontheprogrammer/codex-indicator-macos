from pathlib import Path

import pytest

from utils.atomic_json import (
    AtomicJsonError,
    JsonDocumentError,
    atomic_write_json,
    read_json_mapping,
)


def test_atomic_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "value.json"
    atomic_write_json(path, {"message": "✓", "count": 3})
    assert read_json_mapping(path) == {"count": 3, "message": "✓"}
    assert not tuple(path.parent.glob("*.tmp"))


def test_serialization_failure_preserves_existing_file(tmp_path: Path) -> None:
    path = tmp_path / "value.json"
    atomic_write_json(path, {"good": True})
    original = path.read_bytes()
    with pytest.raises(AtomicJsonError):
        atomic_write_json(path, {"bad": object()})
    assert path.read_bytes() == original


def test_invalid_json_has_specific_error(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    path.write_text("{", encoding="utf-8")
    with pytest.raises(JsonDocumentError):
        read_json_mapping(path)
