from dataclasses import replace
from types import SimpleNamespace

from models.config import AppConfig, OverlayPosition
from models.events import SessionSnapshot
from models.session import CodexSession, SessionStatus
from ui.overlay import IndicatorOverlay


def test_manual_hide_is_temporary_runtime_state(qapp) -> None:
    config = replace(
        AppConfig(),
        animations=replace(AppConfig().animations, enabled=False),
    )
    overlay = IndicatorOverlay(config)

    overlay.set_manual_hidden(True)
    assert overlay.is_manually_hidden

    overlay.set_manual_hidden(False)
    assert not overlay.is_manually_hidden
    overlay.close()


def test_ready_label_is_transient(qapp) -> None:
    config = replace(
        AppConfig(),
        animations=replace(AppConfig().animations, enabled=False),
    )
    overlay = IndicatorOverlay(config)
    ready = CodexSession.create("ready-label", status=SessionStatus.READY)
    overlay.set_snapshot(SessionSnapshot.create((ready,), 1))
    assert ready.session_id in overlay._ready_labels

    overlay._clear_ready_labels()
    assert not overlay._ready_labels
    overlay.close()


def test_removed_custom_display_falls_back_to_automatic() -> None:
    calls: list[str] = []
    overlay = SimpleNamespace(
        config=replace(
            AppConfig(),
            position=OverlayPosition(
                mode="custom",
                x=100,
                y=100,
                screen_name="Removed Display",
            ),
        ),
        _screen_named=lambda name: None,
        _move_automatic=lambda: calls.append("automatic"),
        _screen_configuration_changed=lambda: calls.append("configuration"),
    )

    IndicatorOverlay._screen_removed(overlay, object())

    assert calls == ["automatic"]
