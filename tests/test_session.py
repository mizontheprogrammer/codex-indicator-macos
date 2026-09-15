from datetime import UTC, datetime, timedelta

import pytest

from models.events import SessionStateChange
from models.session import CodexSession, SessionStatus


def test_session_round_trip_and_transition() -> None:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    session = CodexSession.create(
        "session-1",
        workspace=r"C:\work\demo",
        status=SessionStatus.READY,
        now=start,
        pid=42,
    )
    working = session.transition(
        SessionStatus.WORKING,
        now=start + timedelta(seconds=73),
        activity="Running Tests...",
    )
    working = working.with_usage(
        context_remaining_percent=62.5,
        rate_limit_remaining_percent=80,
        rate_limit_resets_at=start + timedelta(hours=2),
    )
    restored = CodexSession.from_dict(working.to_dict())
    assert restored == working
    assert restored.formatted_elapsed(now=start + timedelta(seconds=206)) == "2m 13s"
    assert restored.status is SessionStatus.WORKING
    assert restored.rate_limit_remaining_percent == 80


def test_status_priority_and_aliases() -> None:
    assert SessionStatus.parse("needs input") is SessionStatus.NEEDS_YOU
    assert SessionStatus.NEEDS_YOU.priority > SessionStatus.WORKING.priority
    assert SessionStatus.WORKING.priority > SessionStatus.READY.priority
    assert SessionStatus.READY.display_name == "Codex is ready"
    assert SessionStatus.NEEDS_YOU.display_name == "Codex needs you"


def test_partial_usage_preserves_last_known_limits() -> None:
    session = CodexSession.create("usage").with_usage(
        context_remaining_percent=50,
        rate_limit_remaining_percent=80,
        secondary_remaining_percent=70,
    )
    updated = session.with_usage(context_remaining_percent=40)

    assert updated.context_remaining_percent == 40
    assert updated.rate_limit_remaining_percent == 80
    assert updated.secondary_remaining_percent == 70


def test_ready_transition_requests_completion_notification() -> None:
    working = CodexSession.create("ready", status=SessionStatus.WORKING)
    ready = working.transition(SessionStatus.READY)
    change = SessionStateChange(
        session=ready,
        previous_status=SessionStatus.WORKING,
        current_status=SessionStatus.READY,
        occurred_at=ready.last_activity,
    )

    assert change.requires_notification


def test_invalid_session_id_is_rejected() -> None:
    with pytest.raises(ValueError):
        CodexSession.create("../unsafe")
