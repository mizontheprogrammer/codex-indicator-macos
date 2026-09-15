from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

from PySide6.QtNetwork import QLocalServer

from indicator import (
    IndicatorRuntime,
    _effective_config,
    _fallback_tray_icon,
    _should_manage_startup,
    _single_instance_server,
)
from models.config import AppConfig
from models.events import SessionSnapshot
from models.session import CodexSession, SessionStatus


def test_single_instance_server_rejects_a_second_owner(qapp) -> None:
    name = "CodexIndicatorTest-single-instance"
    QLocalServer.removeServer(name)
    first = _single_instance_server(name)
    try:
        assert first is not None
        assert _single_instance_server(name) is None
    finally:
        if first is not None:
            first.close()
        QLocalServer.removeServer(name)


def test_only_installed_frozen_app_manages_startup(tmp_path: Path) -> None:
    local_app_data = tmp_path / "LocalAppData"
    installed = local_app_data / "Programs" / "CodexIndicator" / "CodexIndicator.exe"
    portable = tmp_path / "Portable" / "CodexIndicator.exe"

    assert _should_manage_startup(
        installed,
        local_app_data,
        frozen=True,
        smoke_test=False,
    )
    assert not _should_manage_startup(
        installed,
        local_app_data,
        frozen=True,
        smoke_test=True,
    )
    assert not _should_manage_startup(
        installed,
        local_app_data,
        frozen=False,
        smoke_test=False,
    )
    assert not _should_manage_startup(
        portable,
        local_app_data,
        frozen=True,
        smoke_test=False,
    )


def test_normal_runtime_preserves_every_user_setting() -> None:
    original = replace(
        AppConfig(),
        poll_interval_ms=1_750,
        auto_hide_enabled=True,
        display_size="expanded",
        display_mode="low_opacity",
        low_opacity=0.10,
        theme=replace(AppConfig().theme, width=412, opacity=0.77),
        animations=replace(AppConfig().animations, enabled=True),
    )

    assert _effective_config(original, smoke_test=False) is original


def test_smoke_runtime_disables_external_activity_in_memory() -> None:
    original = AppConfig()
    smoke = _effective_config(original, smoke_test=True)

    assert smoke.sounds.enabled is False
    assert smoke.providers.ipc.enabled is False
    assert smoke.providers.logs.enabled is False
    assert smoke.providers.stream.enabled is False
    assert smoke.providers.hooks.enabled is False
    assert original.providers.ipc.enabled is True
    assert original.providers.logs.enabled is True


def test_fallback_tray_icon_uses_current_branding(qapp) -> None:
    icon = _fallback_tray_icon()
    assert not icon.isNull()
    assert not icon.pixmap(64, 64).isNull()


def test_muted_runtime_suppresses_sound_and_popup() -> None:
    sound = SimpleNamespace(
        play=lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("muted runtime must not play a sound")
        )
    )
    tray = SimpleNamespace(
        showMessage=lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("muted runtime must not show a popup")
        )
    )
    runtime = SimpleNamespace(
        _notifications_muted=True,
        sound=sound,
        tray=tray,
    )
    session = CodexSession(
        session_id="muted-test",
        workspace="C:/workspace",
        status=SessionStatus.NEEDS_YOU,
    )
    snapshot = SessionSnapshot.create((session,), 1)

    IndicatorRuntime._notify_status_changes(runtime, snapshot, {})
