"""Future native-hook provider with a stable in-process ingestion API."""

from __future__ import annotations

import queue

from backend.providers.base import SessionProvider
from models.events import ProviderEvent


class HookProvider(SessionProvider):
    """Bounded queue that future Codex hooks can publish normalized events to."""

    def __init__(self, *, queue_limit: int = 1_024) -> None:
        super().__init__("hooks")
        self._events: queue.Queue[ProviderEvent] = queue.Queue(maxsize=queue_limit)

    def publish(self, event: ProviderEvent) -> bool:
        if self.stopped:
            return False
        try:
            self._events.put_nowait(event)
            return True
        except queue.Full:
            return False

    def poll(self) -> tuple[ProviderEvent, ...]:
        events: list[ProviderEvent] = []
        while not self.stopped:
            try:
                events.append(self._events.get_nowait())
            except queue.Empty:
                break
        return tuple(events)


__all__ = ["HookProvider"]
