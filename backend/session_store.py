"""Atomic on-disk session store with corrupt-file quarantine."""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime
from pathlib import Path

from models.session import CodexSession
from utils.atomic_json import AtomicJsonError, atomic_write_json, read_json_mapping

LOGGER = logging.getLogger(__name__)


class SessionStore:
    """Persist one canonical JSON document per session."""

    def __init__(self, directory: str | Path) -> None:
        self.directory = Path(directory)
        self.quarantine_directory = self.directory / "quarantine"

    def initialize(self) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)

    def path_for(self, session_id: str) -> Path:
        # CodexSession validation guarantees a filename-safe ID.
        return self.directory / f"{session_id}.json"

    def save(self, session: CodexSession) -> Path:
        self.initialize()
        return atomic_write_json(self.path_for(session.session_id), session.to_dict())

    def remove(self, session_id: str) -> bool:
        path = self.path_for(session_id)
        try:
            path.unlink()
            return True
        except FileNotFoundError:
            return False
        except OSError as error:
            LOGGER.warning("Unable to remove session file %s: %s", path, error)
            return False

    def load_all(self) -> tuple[CodexSession, ...]:
        self.initialize()
        sessions: list[CodexSession] = []
        for path in sorted(self.directory.glob("*.json")):
            try:
                sessions.append(
                    CodexSession.from_dict(
                        read_json_mapping(path),
                        default_provider="store",
                    )
                )
            except (AtomicJsonError, ValueError, TypeError, OSError) as error:
                LOGGER.error("Quarantining corrupt session %s: %s", path, error)
                self._quarantine(path)
        return tuple(sessions)

    def _quarantine(self, path: Path) -> Path | None:
        try:
            self.quarantine_directory.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S.%fZ")
            target = self.quarantine_directory / f"{path.stem}.{timestamp}.invalid.json"
            os.replace(path, target)
            return target
        except OSError as error:
            LOGGER.error("Unable to quarantine %s: %s", path, error)
            return None


__all__ = ["SessionStore"]
