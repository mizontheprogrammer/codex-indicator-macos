from pathlib import Path

from backend.coordinator import BackendCoordinator
from backend.providers.base import SessionProvider
from backend.session_store import SessionStore
from backend.stale_monitor import StaleMonitor
from models.events import ProviderEvent, SessionObservation
from models.session import CodexSession, SessionStatus


class FakeProvider(SessionProvider):
    def __init__(self) -> None:
        super().__init__("fake")

    def poll(self) -> tuple[ProviderEvent, ...]:
        return ()


def _coordinator(tmp_path: Path) -> BackendCoordinator:
    return BackendCoordinator(
        (FakeProvider(),),
        SessionStore(tmp_path / "sessions"),
        StaleMonitor(
            stale_after_seconds=10,
            dead_process_grace_seconds=0,
            remove_after_seconds=100,
        ),
    )


def test_coordinator_rejects_out_of_order_events(tmp_path: Path) -> None:
    coordinator = _coordinator(tmp_path)
    ready = CodexSession.create("one", status=SessionStatus.READY)
    working = ready.transition(SessionStatus.WORKING)
    assert coordinator._apply(SessionObservation.create("fake", working, sequence=2))
    assert not coordinator._apply(SessionObservation.create("fake", ready, sequence=1))
    assert coordinator._sessions["one"].status is SessionStatus.WORKING


def test_coordinator_persists_changed_session(tmp_path: Path) -> None:
    coordinator = _coordinator(tmp_path)
    session = CodexSession.create("persisted")
    assert coordinator._apply(SessionObservation.create("fake", session, sequence=1))
    assert coordinator.store.load_all() == (session,)


def test_new_needs_you_session_requests_notification(tmp_path: Path) -> None:
    coordinator = _coordinator(tmp_path)
    changes = []
    coordinator.state_changed.connect(changes.append)
    session = CodexSession.create("attention", status=SessionStatus.NEEDS_YOU)

    assert coordinator._apply(SessionObservation.create("fake", session, sequence=1))
    assert len(changes) == 1
    assert changes[0].requires_notification


def test_current_snapshot_exposes_latest_published_state(tmp_path: Path) -> None:
    coordinator = _coordinator(tmp_path)
    session = CodexSession.create("latest", status=SessionStatus.WORKING)
    assert coordinator._apply(SessionObservation.create("fake", session, sequence=1))

    coordinator._publish()
    snapshot = coordinator.current_snapshot()

    assert snapshot.sessions == (session,)
    assert snapshot.revision == 1
