"""Threaded provider polling and deterministic session reconciliation."""

from __future__ import annotations

import logging
import queue
import threading
from datetime import UTC, datetime

from PySide6.QtCore import QObject, Signal

from backend.providers.base import SessionProvider
from backend.session_store import SessionStore
from backend.stale_monitor import StaleMonitor
from models.events import (
    ProviderFault,
    ProviderRecovered,
    SessionObservation,
    SessionRemoval,
    SessionSnapshot,
    SessionStateChange,
)
from models.session import CodexSession, SessionStatus

LOGGER = logging.getLogger(__name__)


class BackendCoordinator(QObject):
    """Own providers and emit immutable snapshots across the Qt thread boundary."""

    snapshot_changed = Signal(object)
    state_changed = Signal(object)
    provider_fault = Signal(object)

    def __init__(
        self,
        providers: tuple[SessionProvider, ...],
        store: SessionStore,
        stale_monitor: StaleMonitor,
        *,
        poll_interval_ms: int = 500,
    ) -> None:
        super().__init__()
        self.providers = providers
        self.store = store
        self.stale_monitor = stale_monitor
        self.poll_interval = poll_interval_ms / 1_000.0
        self._sessions: dict[str, CodexSession] = {}
        self._source: dict[str, str] = {}
        self._last_sequence: dict[str, int] = {}
        self._revision = 0
        self._latest_snapshot = SessionSnapshot.create((), 0)
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._paused = threading.Event()
        self._dismissals: queue.SimpleQueue[str] = queue.SimpleQueue()
        self._thread: threading.Thread | None = None
        self._lock = threading.RLock()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._wake.clear()
        try:
            for session in self.store.load_all():
                self._sessions[session.session_id] = session
                self._source[session.session_id] = session.provider
        except OSError:
            LOGGER.exception("Unable to load stored sessions")
        for provider in self.providers:
            provider.start()
        self._publish()
        self._thread = threading.Thread(
            target=self._run,
            name="CodexIndicatorBackend",
            daemon=True,
        )
        self._thread.start()

    def stop(self, timeout_seconds: float = 3.0) -> None:
        self._stop.set()
        self._wake.set()
        for provider in self.providers:
            provider.stop()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=max(0.0, timeout_seconds))

    def _run(self) -> None:
        while not self._stop.is_set():
            changed = False
            while True:
                try:
                    session_id = self._dismissals.get_nowait()
                except queue.Empty:
                    break
                if self._sessions.pop(session_id, None) is not None:
                    self._source.pop(session_id, None)
                    self.store.remove(session_id)
                    changed = True

            if not self._paused.is_set():
                for provider in self.providers:
                    try:
                        events = provider.poll()
                    except Exception as error:
                        LOGGER.exception("Provider %s poll failed", provider.name)
                        events = (provider.fault(error),)
                    for event in events:
                        changed = self._apply(event) or changed

                lifecycle = self.stale_monitor.evaluate(tuple(self._sessions.values()))
                for session_id in lifecycle.remove_ids:
                    if self._sessions.pop(session_id, None) is not None:
                        self._source.pop(session_id, None)
                        self.store.remove(session_id)
                        changed = True
            if changed:
                self._publish()
            self._wake.wait(self.poll_interval)
            self._wake.clear()

    def request_refresh(self) -> None:
        """Wake the provider loop for an immediate refresh."""

        self._wake.set()

    def current_snapshot(self) -> SessionSnapshot:
        """Return the latest immutable snapshot for main-thread UI syncing."""

        with self._lock:
            return self._latest_snapshot

    def set_paused(self, paused: bool) -> None:
        """Pause or resume provider polling without discarding sessions."""

        if paused:
            self._paused.set()
        else:
            self._paused.clear()
        self._wake.set()

    def dismiss_session(self, session_id: str) -> None:
        """Queue a user-requested stale session removal."""

        self._dismissals.put(session_id)
        self._wake.set()

    def _apply(self, event: object) -> bool:
        if isinstance(event, (ProviderFault, ProviderRecovered)):
            if isinstance(event, ProviderFault):
                self.provider_fault.emit(event)
            return False
        if not isinstance(event, (SessionObservation, SessionRemoval)):
            return False
        last = self._last_sequence.get(event.provider, -1)
        if event.sequence <= last:
            return False
        self._last_sequence[event.provider] = event.sequence

        if isinstance(event, SessionRemoval):
            if self._source.get(event.session_id) != event.provider:
                return False
            removed = self._sessions.pop(event.session_id, None)
            self._source.pop(event.session_id, None)
            if removed:
                self.store.remove(event.session_id)
                return True
            return False

        session = event.session
        previous = self._sessions.get(session.session_id)
        if previous is not None and event.occurred_at < previous.last_activity:
            return False
        if previous == session:
            return False
        self._sessions[session.session_id] = session
        self._source[session.session_id] = event.provider
        try:
            self.store.save(session)
        except Exception:
            LOGGER.exception("Unable to persist session %s", session.session_id)
        previous_status = (
            previous.status if previous is not None else SessionStatus.READY
        )
        if previous_status is not session.status and (
            previous is not None or session.status is SessionStatus.NEEDS_YOU
        ):
            self.state_changed.emit(
                SessionStateChange(
                    session=session,
                    previous_status=previous_status,
                    current_status=session.status,
                    occurred_at=event.occurred_at,
                )
            )
        return True

    def _publish(self) -> None:
        with self._lock:
            self._revision += 1
            snapshot = SessionSnapshot.create(
                tuple(self._sessions.values()),
                self._revision,
                occurred_at=datetime.now(UTC),
            )
            self._latest_snapshot = snapshot
        self.snapshot_changed.emit(snapshot)


__all__ = ["BackendCoordinator"]
