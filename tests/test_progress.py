from __future__ import annotations

from dataclasses import replace

import pytest
from PySide6.QtCore import QRectF

from models.session import CodexSession, SessionStatus
from ui.progress import (
    PercentageSource,
    determinate_fill_rect,
    indeterminate_segment_rect,
    usage_presentation,
)


@pytest.mark.parametrize("value", (0, 1, 50, 99, 100))
def test_rate_limit_percentage_priority_and_geometry(value: int) -> None:
    session = replace(
        CodexSession.create("usage", status=SessionStatus.WORKING),
        rate_limit_remaining_percent=value,
        context_remaining_percent=42,
    )
    presentation = usage_presentation(session)
    assert presentation.source is PercentageSource.RATE_LIMIT
    assert presentation.value == value
    assert presentation.percentage_text == f"{value}%"
    assert presentation.description == f"Usage remaining: {value}%"
    fill = determinate_fill_rect(QRectF(10, 4, 200, 3), value)
    assert fill.left() == 10
    assert fill.width() == pytest.approx(value * 2)


def test_context_percentage_is_second_priority() -> None:
    session = replace(
        CodexSession.create("context"),
        context_remaining_percent=48,
    )
    presentation = usage_presentation(session)
    assert presentation.source is PercentageSource.CONTEXT
    assert presentation.percentage_text == "48%"
    assert presentation.description == "Context remaining: 48%"


@pytest.mark.parametrize(
    "status",
    (SessionStatus.READY, SessionStatus.WORKING, SessionStatus.NEEDS_YOU),
)
def test_unavailable_percentage_never_invents_progress(status: SessionStatus) -> None:
    presentation = usage_presentation(CodexSession.create(status.value, status=status))
    assert presentation.source is PercentageSource.UNAVAILABLE
    assert presentation.value is None
    assert presentation.percentage_text == "—"
    assert presentation.description == "Usage unavailable"


def test_indeterminate_progress_bounces_inside_track() -> None:
    track = QRectF(10, 4, 200, 3)
    start = indeterminate_segment_rect(track, 0)
    middle = indeterminate_segment_rect(track, 0.5)
    end = indeterminate_segment_rect(track, 1)
    assert start.left() == track.left()
    assert middle.right() == pytest.approx(track.right())
    assert end.left() == track.left()
    assert start.width() == middle.width() == end.width()


def test_multiple_sessions_keep_existing_priority_order() -> None:
    from models.events import SessionSnapshot

    ready = CodexSession.create("ready", status=SessionStatus.READY)
    working = CodexSession.create("working", status=SessionStatus.WORKING)
    attention = CodexSession.create("attention", status=SessionStatus.NEEDS_YOU)
    snapshot = SessionSnapshot.create((ready, working, attention), 1)
    assert [item.status for item in snapshot.sessions] == [
        SessionStatus.NEEDS_YOU,
        SessionStatus.WORKING,
        SessionStatus.READY,
    ]
