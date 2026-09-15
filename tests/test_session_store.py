from pathlib import Path

from backend.session_store import SessionStore
from models.session import CodexSession


def test_store_round_trip_and_remove(tmp_path: Path) -> None:
    store = SessionStore(tmp_path / "sessions")
    session = CodexSession.create("abc", workspace="demo")
    store.save(session)
    assert store.load_all() == (session,)
    assert store.remove(session.session_id)
    assert store.load_all() == ()


def test_store_quarantines_corrupt_documents(tmp_path: Path) -> None:
    store = SessionStore(tmp_path / "sessions")
    store.initialize()
    (store.directory / "broken.json").write_text("{", encoding="utf-8")
    assert store.load_all() == ()
    assert tuple(store.quarantine_directory.glob("*.invalid.json"))
