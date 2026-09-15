"""Atomic JSON session-file provider."""

from __future__ import annotations

import logging
from pathlib import Path

from backend.providers.base import SessionProvider
from models.events import ProviderEvent, SessionObservation, SessionRemoval
from models.session import CodexSession
from utils.atomic_json import AtomicJsonError, read_json_mapping

LOGGER = logging.getLogger(__name__)


class IpcProvider(SessionProvider):
    """Read one canonical session document per file."""

    def __init__(self, directory: str | Path) -> None:
        super().__init__("ipc")
        self.directory = Path(directory)
        self._known: set[str] = set()
        self._signatures: dict[Path, tuple[int, int]] = {}

    def poll(self) -> tuple[ProviderEvent, ...]:
        if self.stopped:
            return ()
        events: list[ProviderEvent] = []
        try:
            self.directory.mkdir(parents=True, exist_ok=True)
            files = tuple(self.directory.glob("*.json"))
        except OSError as error:
            return (self.fault(error),)

        current: set[str] = set()
        for path in files:
            try:
                stat = path.stat()
                signature = (stat.st_mtime_ns, stat.st_size)
                data = read_json_mapping(path)
                session = CodexSession.from_dict(data, default_provider=self.name)
                current.add(session.session_id)
                if self._signatures.get(path) == signature:
                    continue
                self._signatures[path] = signature
                events.append(
                    SessionObservation.create(
                        self.name,
                        session,
                        sequence=self.next_sequence(),
                    )
                )
            except (AtomicJsonError, OSError, ValueError, TypeError) as error:
                LOGGER.warning("Skipping invalid IPC session %s: %s", path, error)
                events.append(self.fault(error))

        for session_id in sorted(self._known - current):
            events.append(
                SessionRemoval.create(
                    self.name,
                    session_id,
                    sequence=self.next_sequence(),
                    reason="IPC session file removed",
                )
            )
        self._known = current
        self._signatures = {
            path: signature
            for path, signature in self._signatures.items()
            if path in files
        }
        return tuple(events)


__all__ = ["IpcProvider"]
