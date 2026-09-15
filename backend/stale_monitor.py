"""Session staleness and dead-process lifecycle decisions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from models.session import CodexSession
from utils.process_utils import is_process_alive


@dataclass(frozen=True, slots=True)
class LifecycleResult:
    stale_ids: frozenset[str]
    dead_ids: frozenset[str]
    remove_ids: frozenset[str]


class StaleMonitor:
    """Track dead-process grace periods without inventing a fourth UI state."""

    def __init__(
        self,
        *,
        stale_after_seconds: float,
        dead_process_grace_seconds: float,
        remove_after_seconds: float,
    ) -> None:
        self.stale_after_seconds = stale_after_seconds
        self.dead_process_grace_seconds = dead_process_grace_seconds
        self.remove_after_seconds = remove_after_seconds
        self._dead_since: dict[str, datetime] = {}

    def evaluate(
        self,
        sessions: tuple[CodexSession, ...],
        *,
        now: datetime | None = None,
    ) -> LifecycleResult:
        timestamp = (now or datetime.now(UTC)).astimezone(UTC)
        active_ids = {session.session_id for session in sessions}
        self._dead_since = {
            key: value for key, value in self._dead_since.items() if key in active_ids
        }
        stale: set[str] = set()
        dead: set[str] = set()
        remove: set[str] = set()

        for session in sessions:
            idle_seconds = max(
                0.0,
                (timestamp - session.last_activity).total_seconds(),
            )
            if idle_seconds > self.stale_after_seconds:
                stale.add(session.session_id)

            if session.pid is not None and not is_process_alive(session.pid):
                dead.add(session.session_id)
                first_seen = self._dead_since.setdefault(
                    session.session_id,
                    timestamp,
                )
                if (
                    timestamp - first_seen
                ).total_seconds() >= self.dead_process_grace_seconds:
                    remove.add(session.session_id)
            else:
                self._dead_since.pop(session.session_id, None)
                if idle_seconds >= self.remove_after_seconds:
                    remove.add(session.session_id)

        return LifecycleResult(
            stale_ids=frozenset(stale),
            dead_ids=frozenset(dead),
            remove_ids=frozenset(remove),
        )


__all__ = ["LifecycleResult", "StaleMonitor"]
