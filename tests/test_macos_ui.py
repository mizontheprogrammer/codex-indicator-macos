from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
from PySide6.QtCore import QRectF
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtNetwork import QLocalServer

from indicator import IndicatorRuntime
from models.config import AppConfig
from models.events import SessionSnapshot
from models.session import CodexSession, SessionStatus
from ui.painter import OverlayPainter
from ui.palette import IndicatorPalette


@pytest.mark.parametrize(
    "status",
    (SessionStatus.READY, SessionStatus.WORKING, SessionStatus.NEEDS_YOU),
)
def test_macos_states_render_in_black_and_white(qapp, status: SessionStatus) -> None:
    config = AppConfig()
    renderer = OverlayPainter(config, IndicatorPalette.from_settings(config.colors))
    image = QImage(320, 64, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(0)
    painter = QPainter(image)
    renderer.draw_surface(painter, QRectF(6, 6, 308, 52))
    session = replace(
        CodexSession.create(status.value, status=status),
        rate_limit_remaining_percent=72,
    )
    renderer.draw_session(
        painter,
        QRectF(10, 8, 300, 48),
        session,
        spark_phase=0.5,
        pulse_phase=0.5,
        working_label="Working",
        usage_text="72% left",
    )
    painter.end()
    assert QColor.fromRgba(image.pixel(160, 32)).alpha() > 0
    assert QColor.fromRgba(image.pixel(7, 32)).value() < 20


def test_long_workspace_and_empty_session_render_safely(qapp) -> None:
    config = AppConfig()
    renderer = OverlayPainter(config, IndicatorPalette.from_settings(config.colors))
    image = QImage(320, 128, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(0)
    painter = QPainter(image)
    renderer.draw_empty(painter, QRectF(10, 8, 300, 48))
    session = CodexSession.create(
        "long",
        workspace="/Users/example/" + "very-long-workspace-name-" * 30,
        status=SessionStatus.WORKING,
    )
    renderer.draw_session(
        painter,
        QRectF(10, 64, 300, 48),
        session,
        spark_phase=0.25,
        pulse_phase=0,
        working_label="Working",
        usage_text="Usage unavailable",
        show_workspace=True,
    )
    painter.end()
    assert any(image.pixelColor(x, 88).alpha() for x in range(image.width()))


def test_menu_exposes_required_macos_actions(qapp, tmp_path: Path) -> None:
    server = QLocalServer()
    runtime = IndicatorRuntime(
        qapp,
        Path(__file__).resolve().parents[1],
        tmp_path / "config.json",
        server,
        smoke_test=True,
    )
    labels = {action.text() for action in runtime.menu.actions()}
    assert {
        "Show Indicator",
        "Hide Indicator",
        "Reset Position",
        "Refresh Now",
        "Display Mode",
        "Sessions",
        "Usage Details",
        "Notification Sound",
        "Launch at Login",
        "Open Application Data",
        "Open Logs",
        "About Codex Indicator",
        "Quit Codex Indicator",
    }.issubset(labels)
    runtime.stop()


def test_disappearing_session_interaction_is_safe() -> None:
    runtime = type("Runtime", (), {"snapshot": SessionSnapshot.create((), 1)})()
    IndicatorRuntime._activate_session(runtime, "already-gone")
