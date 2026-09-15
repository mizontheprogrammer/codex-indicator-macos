"""Crash-resistant JSON persistence using same-volume atomic replacement."""

from __future__ import annotations

import json
import logging
import os
import tempfile
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any

LOGGER = logging.getLogger(__name__)

DEFAULT_MAXIMUM_BYTES = 8 * 1024 * 1024


class AtomicJsonError(RuntimeError):
    """Base exception for JSON persistence failures."""


class JsonTooLargeError(AtomicJsonError):
    """Raised when a JSON document exceeds the configured read limit."""


class JsonDocumentError(AtomicJsonError):
    """Raised when a file is not valid JSON or has an unexpected root type."""


def _replace_with_retry(
    source: Path,
    destination: Path,
    *,
    attempts: int,
    initial_delay_seconds: float,
) -> None:
    """Replace a file atomically, retrying transient Windows sharing failures."""

    delay = initial_delay_seconds
    for attempt in range(1, attempts + 1):
        try:
            os.replace(source, destination)
            return
        except PermissionError:
            if attempt >= attempts:
                raise
            time.sleep(delay)
            delay = min(delay * 2.0, 0.5)


def atomic_write_json(
    path: str | os.PathLike[str],
    value: object,
    *,
    indent: int | None = 2,
    sort_keys: bool = True,
    create_parents: bool = True,
    replace_attempts: int = 5,
    initial_retry_delay_seconds: float = 0.025,
) -> Path:
    """Serialize JSON and atomically replace ``path``.

    The temporary file is created in the destination directory, guaranteeing
    that replacement stays on the same volume. Data is flushed and synchronized
    before replacement. If serialization or replacement fails, the existing
    destination remains untouched and the temporary file is removed.

    Args:
        path: Destination JSON path.
        value: JSON-serializable value.
        indent: Pretty-print indentation, or ``None`` for compact output.
        sort_keys: Whether mapping keys should be written deterministically.
        create_parents: Create missing parent directories when true.
        replace_attempts: Attempts for transient Windows sharing violations.
        initial_retry_delay_seconds: Initial bounded replacement retry delay.

    Returns:
        The normalized destination ``Path``.

    Raises:
        AtomicJsonError: If serialization, writing, flushing, or replacement
            fails.
        ValueError: If retry arguments are invalid.
    """

    if replace_attempts < 1:
        raise ValueError("replace_attempts must be at least 1")
    if initial_retry_delay_seconds < 0:
        raise ValueError("initial_retry_delay_seconds must be non-negative")

    destination = Path(path)
    parent = destination.parent
    if create_parents:
        try:
            parent.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            raise AtomicJsonError(
                f"Unable to create JSON directory {parent}: {error}"
            ) from error
    elif not parent.is_dir():
        raise AtomicJsonError(f"JSON directory does not exist: {parent}")

    try:
        serialized = json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            indent=indent,
            sort_keys=sort_keys,
            separators=None if indent is not None else (",", ":"),
        )
    except (TypeError, ValueError, OverflowError) as error:
        raise AtomicJsonError(
            f"Unable to serialize JSON for {destination}: {error}"
        ) from error

    encoded = f"{serialized}\n".encode()
    temporary_path: Path | None = None

    try:
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{destination.name}.",
            suffix=".tmp",
            dir=parent,
        )
        temporary_path = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "wb", closefd=True) as temporary_file:
                temporary_file.write(encoded)
                temporary_file.flush()
                os.fsync(temporary_file.fileno())
        except BaseException:
            # fdopen owns the descriptor after successful construction. If it
            # fails before taking ownership, close the original descriptor.
            try:
                os.close(descriptor)
            except OSError:
                pass
            raise

        _replace_with_retry(
            temporary_path,
            destination,
            attempts=replace_attempts,
            initial_delay_seconds=initial_retry_delay_seconds,
        )
        temporary_path = None
        return destination
    except (OSError, UnicodeError) as error:
        raise AtomicJsonError(
            f"Unable to atomically write JSON file {destination}: {error}"
        ) from error
    finally:
        if temporary_path is not None:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError as cleanup_error:
                LOGGER.warning(
                    "Unable to remove temporary JSON file %s: %s",
                    temporary_path,
                    cleanup_error,
                )


def read_json(
    path: str | os.PathLike[str],
    *,
    maximum_bytes: int = DEFAULT_MAXIMUM_BYTES,
    require_mapping: bool = False,
) -> Any:
    """Read a complete UTF-8 JSON file with a bounded memory footprint.

    UTF-8 files with a byte-order mark are accepted for compatibility with
    Windows editors. The function does not retry malformed content because an
    atomic writer can never expose a partial destination; callers may quarantine
    corrupt files according to their own retention policy.
    """

    if maximum_bytes < 1:
        raise ValueError("maximum_bytes must be positive")

    source = Path(path)
    try:
        size = source.stat().st_size
    except OSError as error:
        raise AtomicJsonError(
            f"Unable to inspect JSON file {source}: {error}"
        ) from error

    if size > maximum_bytes:
        raise JsonTooLargeError(
            f"JSON file {source} is {size} bytes; limit is {maximum_bytes}"
        )

    try:
        with source.open("rb") as stream:
            raw = stream.read(maximum_bytes + 1)
    except OSError as error:
        raise AtomicJsonError(f"Unable to read JSON file {source}: {error}") from error

    if len(raw) > maximum_bytes:
        raise JsonTooLargeError(
            f"JSON file {source} changed while reading and exceeds "
            f"{maximum_bytes} bytes"
        )

    try:
        decoded = raw.decode("utf-8-sig")
        value = json.loads(decoded)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise JsonDocumentError(f"Invalid JSON file {source}: {error}") from error

    if require_mapping and not isinstance(value, Mapping):
        raise JsonDocumentError(f"JSON root in {source} must be an object")
    return value


def read_json_mapping(
    path: str | os.PathLike[str],
    *,
    maximum_bytes: int = DEFAULT_MAXIMUM_BYTES,
) -> dict[str, Any]:
    """Read a JSON object and normalize its keys to strings."""

    value = read_json(
        path,
        maximum_bytes=maximum_bytes,
        require_mapping=True,
    )
    return {str(key): item for key, item in value.items()}


__all__ = [
    "DEFAULT_MAXIMUM_BYTES",
    "AtomicJsonError",
    "JsonDocumentError",
    "JsonTooLargeError",
    "atomic_write_json",
    "read_json",
    "read_json_mapping",
]
