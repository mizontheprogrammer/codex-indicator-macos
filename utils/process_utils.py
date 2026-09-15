"""Safe process inspection helpers built on psutil."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import psutil

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ProcessInfo:
    pid: int
    name: str
    executable: str
    command_line: tuple[str, ...]
    create_time: float


def process_info(pid: int) -> ProcessInfo | None:
    """Return a stable process snapshot, or ``None`` if inaccessible/dead."""

    if pid <= 0:
        return None
    try:
        process = psutil.Process(pid)
        with process.oneshot():
            return ProcessInfo(
                pid=pid,
                name=process.name(),
                executable=process.exe(),
                command_line=tuple(process.cmdline()),
                create_time=process.create_time(),
            )
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess, OSError):
        return None


def is_process_alive(pid: int, *, expected_create_time: float | None = None) -> bool:
    """Check liveness while optionally guarding against PID reuse."""

    info = process_info(pid)
    if info is None:
        # AccessDenied must not be mistaken for process exit.
        return expected_create_time is None and psutil.pid_exists(pid)
    if expected_create_time is not None:
        return abs(info.create_time - expected_create_time) < 0.01
    return True


def normalized_process_name(name: str) -> str:
    """Normalize configured process names for case-insensitive matching."""

    return Path(str(name).strip()).name.casefold()


def process_matches(pid: int, names: tuple[str, ...]) -> bool:
    """Return whether a process name is in a configured allow-list."""

    info = process_info(pid)
    if info is None:
        return False
    expected = {normalized_process_name(name) for name in names}
    return normalized_process_name(info.name) in expected


def discover_codex_processes() -> tuple[ProcessInfo, ...]:
    """Discover likely Codex CLI processes without raising access errors."""

    discovered: list[ProcessInfo] = []
    for process in psutil.process_iter(
        attrs=["pid", "name", "exe", "cmdline", "create_time"],
        ad_value=None,
    ):
        try:
            data = process.info
            name = str(data.get("name") or "")
            command_line = tuple(str(item) for item in (data.get("cmdline") or ()))
            haystack = " ".join((name, *command_line)).casefold()
            if "codex" not in haystack:
                continue
            discovered.append(
                ProcessInfo(
                    pid=int(data["pid"]),
                    name=name,
                    executable=str(data.get("exe") or ""),
                    command_line=command_line,
                    create_time=float(data.get("create_time") or 0.0),
                )
            )
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
        except (TypeError, ValueError, OSError) as error:
            LOGGER.debug("Skipping malformed process entry: %s", error)
    return tuple(discovered)


__all__ = [
    "ProcessInfo",
    "discover_codex_processes",
    "is_process_alive",
    "normalized_process_name",
    "process_info",
    "process_matches",
]
