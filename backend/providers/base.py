"""Provider interface and common lifecycle behavior."""

from __future__ import annotations

import threading
from abc import ABC, abstractmethod

from models.events import ProviderEvent, ProviderFault


class SessionProvider(ABC):
    """Synchronous poll contract executed by the backend coordinator."""

    def __init__(self, name: str) -> None:
        if not name.strip():
            raise ValueError("provider name must not be empty")
        self._name = name.strip()
        self._stopped = threading.Event()
        self._sequence = 0

    @property
    def name(self) -> str:
        return self._name

    @property
    def stopped(self) -> bool:
        return self._stopped.is_set()

    def start(self) -> None:
        self._stopped.clear()

    def stop(self) -> None:
        self._stopped.set()

    def next_sequence(self) -> int:
        self._sequence += 1
        return self._sequence

    @abstractmethod
    def poll(self) -> tuple[ProviderEvent, ...]:
        """Return all events currently available without blocking."""

    def fault(self, error: BaseException, *, retry: float = 1.0) -> ProviderFault:
        return ProviderFault.from_exception(
            self.name,
            error,
            sequence=self.next_sequence(),
            retry_in_seconds=retry,
        )


__all__ = ["SessionProvider"]
