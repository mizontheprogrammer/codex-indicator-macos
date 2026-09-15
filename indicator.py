"""Codex Indicator application entry point."""

from __future__ import annotations

import argparse
import getpass
import logging
import os
import sys
import tempfile
from dataclasses import replace
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QObject, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (
    QAction,
    QActionGroup,
    QColor,
    QIcon,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from app_metadata import APP_NAME, APP_VERSION
from backend.coordinator import BackendCoordinator
from backend.providers.hook_provider import HookProvider
from backend.providers.ipc_provider import IpcProvider
from backend.providers.log_provider import LogProvider
from backend.providers.stream_provider import StreamProvider
from backend.session_store import SessionStore
from backend.stale_monitor import StaleMonitor
from models.config import AppConfig, OverlayPosition, load_config
from models.events import ProviderFault, SessionSnapshot
from models.session import SessionStatus
from ui.overlay import IndicatorOverlay
from utils.atomic_json import AtomicJsonError, atomic_write_json
from utils.logging_setup import (
    ExceptionHookHandle,
    configure_logging,
    install_exception_hooks,
    shutdown_logging,
)
from utils.notifications import DesktopNotifier
from utils.platform import (
    PlatformKind,
    application_data_directory,
    configure_accessory_application,
    current_platform,
    focus_process_window,
    open_path,
)
from utils.sound import NotificationSound
from utils.startup import LoginItemManager

LOGGER = logging.getLogger(__name__)
APPLICATION_ID = "com.codexindicator.community"


def _fallback_tray_icon() -> QIcon:
    """Draw the current conversation-orbit logo when its ICO is unavailable."""

    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    macos = current_platform() is PlatformKind.MACOS
    if not macos:
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#1C1F24"))
        painter.drawRoundedRect(QRectF(2, 2, 60, 60), 14, 14)

    orbit_pen = QPen(
        QColor("#FFFFFF" if macos else "#F7F3EA"),
        7,
        Qt.PenStyle.SolidLine,
        Qt.PenCapStyle.RoundCap,
    )
    painter.setPen(orbit_pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawArc(QRectF(14, 14, 36, 36), 45 * 16, 270 * 16)

    spark = QPainterPath()
    spark.moveTo(32, 23)
    spark.cubicTo(33, 29, 35, 31, 41, 32)
    spark.cubicTo(35, 33, 33, 35, 32, 41)
    spark.cubicTo(31, 35, 29, 33, 23, 32)
    spark.cubicTo(29, 31, 31, 29, 32, 23)
    spark.closeSubpath()
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor("#FFFFFF" if macos else "#FF6846"))
    painter.drawPath(spark)
    painter.end()
    return QIcon(pixmap)


def _tray_icon() -> QIcon:
    bundle_root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    icon_name = (
        "CodexIndicatorTemplate.png"
        if current_platform() is PlatformKind.MACOS
        else "codex_indicator.ico"
    )
    icon_path = bundle_root / "assets" / icon_name
    if icon_path.is_file():
        icon = QIcon(str(icon_path))
        if not icon.isNull():
            return icon

    return _fallback_tray_icon()


def _single_instance_server(name: str) -> QLocalServer | None:
    probe = QLocalSocket()
    probe.connectToServer(name)
    if probe.waitForConnected(250):
        probe.write(b"show")
        probe.waitForBytesWritten(150)
        probe.disconnectFromServer()
        return None
    QLocalServer.removeServer(name)
    server = QLocalServer()
    return server if server.listen(name) else None


def _installed_executable(local_app_data: Path) -> Path:
    """Return the only executable allowed to maintain the startup entry."""

    return local_app_data / "Programs" / "CodexIndicator" / "CodexIndicator.exe"


def _same_path(left: Path, right: Path) -> bool:
    """Compare Windows paths without requiring either path to exist."""

    return os.path.normcase(os.path.abspath(left)) == os.path.normcase(
        os.path.abspath(right)
    )


def _should_manage_startup(
    executable: Path,
    local_app_data: Path,
    *,
    frozen: bool,
    smoke_test: bool,
) -> bool:
    """Allow startup repair only for the installed, non-test application."""

    return (
        frozen
        and not smoke_test
        and _same_path(executable, _installed_executable(local_app_data))
    )


def _effective_config(config: AppConfig, *, smoke_test: bool) -> AppConfig:
    """Return runtime settings without mutating normal user preferences."""

    if not smoke_test:
        return config
    providers = config.providers
    return replace(
        config,
        sounds=replace(config.sounds, enabled=False),
        providers=replace(
            providers,
            ipc=replace(providers.ipc, enabled=False),
            logs=replace(providers.logs, enabled=False),
            stream=replace(providers.stream, enabled=False),
            hooks=replace(providers.hooks, enabled=False),
        ),
    )


class IndicatorRuntime(QObject):
    """Own all long-lived application components."""

    shutdown_requested = Signal()

    def __init__(
        self,
        app: QApplication,
        project_root: Path,
        config_path: Path,
        server: QLocalServer,
        *,
        manage_startup: bool = False,
        smoke_test: bool = False,
    ) -> None:
        super().__init__()
        self.app = app
        self.project_root = project_root
        self.config_path = config_path
        self.server = server
        self.manage_startup = manage_startup
        self.smoke_test = smoke_test
        self._stopped = False
        self._indicator_hidden = False
        self._notifications_muted = False
        self.snapshot = SessionSnapshot.create((), 0)

        load_result = load_config(config_path)
        self.config = _effective_config(
            load_result.config,
            smoke_test=smoke_test,
        )
        if (load_result.used_defaults or load_result.migrated) and not smoke_test:
            try:
                atomic_write_json(config_path, self.config.to_dict())
            except AtomicJsonError as error:
                LOGGER.error("Unable to persist recovered configuration: %s", error)

        self.data_root = config_path.parent
        self.runtime_directory = self.data_root / "runtime"
        configure_logging(self.runtime_directory)
        self.exception_hooks: ExceptionHookHandle = install_exception_hooks()
        if load_result.warning:
            LOGGER.warning(load_result.warning)

        sessions_directory = self.config.resolve_path(
            self.config.providers.ipc.directory,
            self.data_root,
        )
        providers = []
        if self.config.providers.ipc.enabled:
            providers.append(IpcProvider(sessions_directory))
        if self.config.providers.logs.enabled:
            logs = self.config.providers.logs
            providers.append(
                LogProvider(
                    logs.paths,
                    ready_patterns=logs.ready_patterns,
                    working_patterns=logs.working_patterns,
                    needs_you_patterns=logs.needs_you_patterns,
                    encoding=logs.encoding,
                    start_at_end=logs.start_at_end,
                    maximum_file_age_seconds=logs.maximum_file_age_seconds,
                )
            )
        if self.config.providers.stream.enabled:
            providers.append(
                StreamProvider(
                    maximum_line_bytes=(self.config.providers.stream.maximum_line_bytes)
                )
            )
        if self.config.providers.hooks.enabled:
            providers.append(
                HookProvider(queue_limit=self.config.providers.hooks.queue_limit)
            )

        self.store = SessionStore(sessions_directory)
        timeouts = self.config.timeouts
        self.coordinator = BackendCoordinator(
            tuple(providers),
            self.store,
            StaleMonitor(
                stale_after_seconds=timeouts.stale_after_seconds,
                dead_process_grace_seconds=timeouts.dead_process_grace_seconds,
                remove_after_seconds=timeouts.remove_after_seconds,
            ),
            poll_interval_ms=self.config.poll_interval_ms,
        )
        self.sound = NotificationSound(
            enabled=self.config.sounds.enabled,
            alias=self.config.sounds.alias,
            minimum_interval_seconds=(self.config.sounds.minimum_interval_seconds),
            file_path=self.project_root / "assets" / "notification.mp3",
        )
        self.overlay = IndicatorOverlay(self.config)
        self.overlay.position_changed.connect(self._save_position)
        self.overlay.session_activated.connect(self._activate_session)
        self.coordinator.provider_fault.connect(self._provider_fault)
        self.coordinator.snapshot_changed.connect(self._snapshot_changed)

        self.tray = QSystemTrayIcon(_tray_icon(), self)
        self.notifier = DesktopNotifier(
            self.tray,
            enabled=self.config.notifications_enabled,
        )
        self.login_items = LoginItemManager(
            bundle_identifier=APPLICATION_ID,
            executable=Path(sys.executable),
            project_root=self.project_root,
        )
        self.tray.setToolTip("Codex Indicator")
        self.menu = self._build_menu()
        self.tray.setContextMenu(self.menu)
        self.tray.activated.connect(self._tray_activated)
        self.overlay.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.overlay.customContextMenuRequested.connect(
            lambda point: self.menu.popup(self.overlay.mapToGlobal(point))
        )
        server.newConnection.connect(self._instance_message)
        app.aboutToQuit.connect(self.stop)

    def start(self) -> None:
        self.overlay.restore_position()
        self.overlay.sync_visibility()
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray.show()
        self.coordinator.start()
        self._sync_snapshot()
        if self.manage_startup:
            self._ensure_startup()
        elif self.config.launch_at_login and not self.smoke_test:
            if not self.login_items.set_enabled(True):
                LOGGER.warning("Unable to enable launch at login")
        LOGGER.info("Codex Indicator started")

    def stop(self) -> None:
        if self._stopped:
            return
        self._stopped = True
        LOGGER.info("Codex Indicator stopping")
        self.coordinator.stop()
        self.sound.close()
        self.tray.hide()
        self.server.close()
        self.exception_hooks.restore()
        shutdown_logging()

    @staticmethod
    def _provider_fault(fault: ProviderFault) -> None:
        LOGGER.warning("Provider %s: %s", fault.provider, fault.message)

    def _save_position(self, x: int, y: int, screen_name: str) -> None:
        self.config = replace(
            self.config,
            position=OverlayPosition(
                x=x,
                y=y,
                screen_name=screen_name,
                mode="custom",
            ),
        )
        self.overlay.apply_config(self.config)
        self._persist_config()

    def _persist_config(self) -> None:
        try:
            atomic_write_json(self.config_path, self.config.to_dict())
        except AtomicJsonError as error:
            LOGGER.error("Unable to save configuration: %s", error)

    def _snapshot_changed(self, snapshot: SessionSnapshot) -> None:
        if snapshot.revision <= self.snapshot.revision:
            return
        previous_statuses = {
            session.session_id: session.status for session in self.snapshot.sessions
        }
        self.snapshot = snapshot
        self.overlay.set_snapshot(snapshot)
        if snapshot.sessions:
            session = snapshot.sessions[0]
            self.tray.setToolTip(
                f"{session.effective_label} · {self.overlay.usage_text(session)}"
            )
        else:
            self.tray.setToolTip("Codex Indicator · Usage unavailable")

        self._notify_status_changes(snapshot, previous_statuses)

    def _sync_snapshot(self) -> None:
        self._snapshot_changed(self.coordinator.current_snapshot())

    def _notify_status_changes(
        self,
        snapshot: SessionSnapshot,
        previous_statuses: dict[str, SessionStatus],
    ) -> None:
        if self._notifications_muted or not self.config.notifications_enabled:
            return

        for session in snapshot.sessions:
            previous = previous_statuses.get(session.session_id)
            if (
                session.status is SessionStatus.NEEDS_YOU
                and previous is not SessionStatus.NEEDS_YOU
            ):
                self.sound.play()
                self.notifier.notify(
                    "Codex needs you",
                    f"{session.effective_label} — switch back to reply or approve.",
                    QSystemTrayIcon.MessageIcon.Warning,
                    6000,
                )
            elif (
                session.status is SessionStatus.READY
                and previous is not None
                and previous is not SessionStatus.READY
            ):
                self.sound.play(force=True)
                workspace = Path(session.workspace).name or "Codex task"
                self.notifier.notify(
                    "Codex is ready",
                    f"{workspace} finished — switch back when you are ready.",
                    QSystemTrayIcon.MessageIcon.Information,
                    6000,
                )

    def _show_overlay(self) -> None:
        if self._indicator_hidden:
            self._indicator_hidden = False
            self.hide_indicator_action.blockSignals(True)
            self.hide_indicator_action.setChecked(False)
            self.hide_indicator_action.blockSignals(False)
            self.overlay.set_manual_hidden(False)
        self.overlay.show_for_user()

    def _tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason in {
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        }:
            self._show_overlay()

    def _instance_message(self) -> None:
        while self.server.hasPendingConnections():
            socket = self.server.nextPendingConnection()
            if socket is not None:
                socket.readAll()
                socket.disconnectFromServer()
        self._show_overlay()

    def _build_menu(self) -> QMenu:
        menu = QMenu()

        self.show_action = QAction("Show Indicator", menu)
        self.show_action.triggered.connect(self._show_overlay)
        menu.addAction(self.show_action)

        self.hide_indicator_action = QAction("Hide Indicator", menu)
        self.hide_indicator_action.setCheckable(True)
        self.hide_indicator_action.toggled.connect(self._toggle_indicator_hidden)
        menu.addAction(self.hide_indicator_action)

        refresh_action = QAction("Refresh Now", menu)
        refresh_action.triggered.connect(self.coordinator.request_refresh)
        menu.addAction(refresh_action)

        self.usage_menu = menu.addMenu("Usage Details")
        self.sessions_menu = menu.addMenu("Sessions")
        menu.addSeparator()

        self.display_menu = menu.addMenu("Display Mode")
        self.display_group = QActionGroup(self.display_menu)
        self.display_group.setExclusive(True)
        self.display_actions: dict[str, QAction] = {}
        for mode, label in (
            ("normal", "Normal"),
            ("low_opacity", "Low Opacity"),
            ("notifications_only", "Notifications Only"),
        ):
            action = QAction(label, self.display_menu)
            action.setCheckable(True)
            action.triggered.connect(
                lambda checked=False, selected=mode: (
                    self._set_display_mode(selected) if checked else None
                )
            )
            self.display_group.addAction(action)
            self.display_menu.addAction(action)
            self.display_actions[mode] = action

        self.opacity_menu = self.display_menu.addMenu("Low opacity level")
        self.opacity_group = QActionGroup(self.opacity_menu)
        self.opacity_group.setExclusive(True)
        self.opacity_actions: dict[float, QAction] = {}
        for opacity, label in (
            (0.10, "10% · Barely visible"),
            (0.15, "15% · Subtle"),
            (0.25, "25% · Readable"),
        ):
            action = QAction(label, self.opacity_menu)
            action.setCheckable(True)
            action.triggered.connect(
                lambda checked=False, selected=opacity: (
                    self._set_low_opacity(selected) if checked else None
                )
            )
            self.opacity_group.addAction(action)
            self.opacity_menu.addAction(action)
            self.opacity_actions[opacity] = action

        menu.addSeparator()
        self.position_menu = menu.addMenu("Position")
        self.position_group = QActionGroup(self.position_menu)
        self.position_group.setExclusive(True)
        self.position_actions: dict[str, QAction] = {}
        for mode, label in (
            ("automatic", "Automatic Top Center"),
            ("custom", "Remember Custom Position"),
        ):
            action = QAction(label, self.position_menu)
            action.setCheckable(True)
            action.triggered.connect(
                lambda checked=False, selected=mode: (
                    self._set_position_mode(selected) if checked else None
                )
            )
            self.position_group.addAction(action)
            self.position_menu.addAction(action)
            self.position_actions[mode] = action

        reset_position = QAction("Reset Position", menu)
        reset_position.triggered.connect(self._reset_position)
        menu.addAction(reset_position)

        menu.addSeparator()
        self.mute_notifications_action = QAction(
            "Mute Notifications (until restart)",
            menu,
        )
        self.mute_notifications_action.setCheckable(True)
        self.mute_notifications_action.toggled.connect(self._toggle_notifications_muted)
        menu.addAction(self.mute_notifications_action)

        self.sound_action = QAction("Notification Sound", menu)
        self.sound_action.setCheckable(True)
        self.sound_action.toggled.connect(self._toggle_sound)
        menu.addAction(self.sound_action)

        self.test_sound_action = QAction("Test Notification Sound", menu)
        self.test_sound_action.triggered.connect(self._test_sound)
        menu.addAction(self.test_sound_action)

        self.launch_at_login_action = QAction("Launch at Login", menu)
        self.launch_at_login_action.setCheckable(True)
        self.launch_at_login_action.toggled.connect(self._toggle_launch_at_login)
        menu.addAction(self.launch_at_login_action)

        menu.addSeparator()
        open_data = QAction("Open Application Data", menu)
        open_data.triggered.connect(lambda: open_path(self.data_root))
        menu.addAction(open_data)

        open_logs = QAction("Open Logs", menu)
        open_logs.triggered.connect(lambda: open_path(self.runtime_directory))
        menu.addAction(open_logs)

        about_action = QAction("About Codex Indicator", menu)
        about_action.triggered.connect(self._show_about)
        menu.addAction(about_action)

        menu.addSeparator()
        quit_action = QAction("Quit Codex Indicator", menu)
        quit_action.triggered.connect(self.app.quit)
        menu.addAction(quit_action)

        menu.aboutToShow.connect(self._refresh_menu)
        self._refresh_menu()
        return menu

    def _refresh_menu(self) -> None:
        self.show_action.setText(
            "Show Indicator"
            if self._indicator_hidden
            else (
                "Show Indicator for 8 seconds"
                if self.config.display_mode == "notifications_only"
                else "Show Indicator"
            )
        )
        self.hide_indicator_action.blockSignals(True)
        self.hide_indicator_action.setChecked(self._indicator_hidden)
        self.hide_indicator_action.blockSignals(False)
        self.mute_notifications_action.blockSignals(True)
        self.mute_notifications_action.setChecked(self._notifications_muted)
        self.mute_notifications_action.blockSignals(False)
        for mode, action in self.display_actions.items():
            action.setChecked(mode == self.config.display_mode)
        for mode, action in self.position_actions.items():
            action.setChecked(mode == self.config.position.mode)
        selected_opacity = min(
            self.opacity_actions,
            key=lambda value: abs(value - self.config.low_opacity),
        )
        for opacity, action in self.opacity_actions.items():
            action.setChecked(opacity == selected_opacity)
        self.sound_action.blockSignals(True)
        self.sound_action.setChecked(self.config.sounds.enabled)
        self.sound_action.blockSignals(False)
        self.test_sound_action.setEnabled(not self._notifications_muted)
        self.launch_at_login_action.blockSignals(True)
        self.launch_at_login_action.setChecked(self.login_items.is_enabled())
        self.launch_at_login_action.blockSignals(False)
        self._refresh_usage_menu()
        self._refresh_sessions_menu()

    def _toggle_indicator_hidden(self, checked: bool) -> None:
        self._indicator_hidden = checked
        self.overlay.set_manual_hidden(checked)
        self._refresh_menu()

    def _toggle_notifications_muted(self, checked: bool) -> None:
        self._notifications_muted = checked
        self._refresh_menu()

    def _set_display_mode(self, mode: str) -> None:
        if mode not in {"normal", "low_opacity", "notifications_only"}:
            return
        self.config = replace(self.config, display_mode=mode)
        self._persist_config()
        self.overlay.apply_config(self.config)

    def _set_low_opacity(self, opacity: float) -> None:
        self.config = replace(
            self.config,
            display_mode="low_opacity",
            low_opacity=opacity,
        )
        self._persist_config()
        self.overlay.apply_config(self.config)

    def _set_position_mode(self, mode: str) -> None:
        if mode not in {"automatic", "custom"}:
            return
        position = replace(self.config.position, mode=mode)
        if mode == "automatic":
            position = OverlayPosition(mode="automatic")
        self.config = replace(self.config, position=position)
        self.overlay.apply_config(self.config)
        self.overlay.restore_position()
        self._persist_config()

    def _reset_position(self) -> None:
        self.config = replace(
            self.config,
            position=OverlayPosition(mode="automatic"),
        )
        self.overlay.apply_config(self.config)
        self.overlay.reset_position()
        self._persist_config()

    def _refresh_usage_menu(self) -> None:
        self.usage_menu.clear()
        session = self.snapshot.sessions[0] if self.snapshot.sessions else None
        if session is None:
            unavailable = self.usage_menu.addAction("Usage unavailable")
            unavailable.setEnabled(False)
            return

        self._add_readonly(
            self.usage_menu,
            "Rate limit",
            (
                f"{session.rate_limit_remaining_percent:.0f}% left"
                if session.rate_limit_remaining_percent is not None
                else "Unavailable"
            ),
        )
        self._add_readonly(
            self.usage_menu,
            "Resets",
            self._format_reset(session.rate_limit_resets_at),
        )
        self._add_readonly(
            self.usage_menu,
            "Context",
            (
                f"{session.context_remaining_percent:.0f}% left"
                if session.context_remaining_percent is not None
                else "Unavailable"
            ),
        )
        self._add_readonly(
            self.usage_menu,
            "Weekly",
            (
                f"{session.secondary_remaining_percent:.0f}% left · "
                f"{self._format_reset(session.secondary_resets_at)}"
                if session.secondary_remaining_percent is not None
                else "Unavailable"
            ),
        )

    @staticmethod
    def _add_readonly(menu: QMenu, label: str, value: str) -> None:
        action = menu.addAction(f"{label}: {value}")
        action.setEnabled(False)

    @staticmethod
    def _format_reset(value: datetime | None) -> str:
        if value is None:
            return "Unavailable"
        local = value.astimezone()
        return local.strftime("%a %I:%M %p").replace(" 0", " ")

    def _refresh_sessions_menu(self) -> None:
        self.sessions_menu.clear()
        if not self.snapshot.sessions:
            action = self.sessions_menu.addAction("No active sessions")
            action.setEnabled(False)
            return
        for session in self.snapshot.sessions:
            label = Path(session.workspace).name or session.session_id
            submenu = self.sessions_menu.addMenu(
                f"{session.status.display_name} · {label}"
            )
            submenu.setToolTipsVisible(True)
            submenu.setToolTip(session.workspace or "Workspace unavailable")
            focus = submenu.addAction("Activate Application")
            focus.triggered.connect(
                lambda checked=False, item=session: self._activate_session(
                    item.session_id
                )
            )
            open_workspace = submenu.addAction("Show Workspace in Finder")
            open_workspace.setEnabled(Path(session.workspace).is_dir())
            open_workspace.triggered.connect(
                lambda checked=False, item=session: open_path(item.workspace)
            )
            copy_path = submenu.addAction("Copy Workspace Path")
            copy_path.triggered.connect(
                lambda checked=False, item=session: self.app.clipboard().setText(
                    item.workspace
                )
            )
            submenu.addSeparator()
            remove = submenu.addAction("Remove Session")
            remove.triggered.connect(
                lambda checked=False, item=session: self.coordinator.dismiss_session(
                    item.session_id
                )
            )

    def _toggle_sound(self, checked: bool) -> None:
        self.config = replace(
            self.config,
            sounds=replace(self.config.sounds, enabled=checked),
        )
        self.sound.enabled = checked
        self._persist_config()

    def _test_sound(self) -> None:
        if self.sound.play(force=True):
            self.notifier.notify(
                "Codex Indicator",
                "Notification sound requested.",
                QSystemTrayIcon.MessageIcon.Information,
                2500,
            )
            return
        self.notifier.notify(
            "Codex Indicator",
            "Notification sound is disabled or unavailable.",
            QSystemTrayIcon.MessageIcon.Warning,
            4000,
        )

    def _ensure_startup(self) -> None:
        if not self.login_items.set_enabled(True):
            LOGGER.error("Unable to ensure launch at login")

    def _toggle_launch_at_login(self, checked: bool) -> None:
        if self.smoke_test:
            return
        if not self.login_items.set_enabled(checked):
            LOGGER.warning("Unable to change launch-at-login registration")
            self._refresh_menu()
            return
        self.config = replace(self.config, launch_at_login=checked)
        self._persist_config()

    def _activate_session(self, session_id: str) -> None:
        session = next(
            (item for item in self.snapshot.sessions if item.session_id == session_id),
            None,
        )
        if session is None:
            return
        if focus_process_window(session.pid or 0, session.terminal_hwnd):
            return
        if session.workspace and Path(session.workspace).is_dir():
            open_path(session.workspace)

    def _show_about(self) -> None:
        self.notifier.notify(
            f"{APP_NAME} {APP_VERSION}",
            (
                "Local-only Codex status, usage, and attention overlay.\n"
                "Unofficial community project; not affiliated with or endorsed "
                "by OpenAI."
            ),
            QSystemTrayIcon.MessageIcon.Information,
            6500,
        )


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Codex Indicator")
    parser.add_argument(
        "--config",
        type=Path,
        help="Path to config.json (defaults to the platform application-data folder)",
    )
    parser.add_argument(
        "--smoke-test",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    return parser.parse_args()


def main() -> int:
    arguments = _arguments()
    project_root = Path(__file__).resolve().parent
    data_root = application_data_directory()
    local_app_data = data_root.parent
    smoke_directory: tempfile.TemporaryDirectory[str] | None = None
    if arguments.smoke_test:
        smoke_directory = tempfile.TemporaryDirectory(prefix="CodexIndicatorSmoke-")
        config_path = Path(smoke_directory.name) / "config.json"
    else:
        config_path = (arguments.config or data_root / "config.json").resolve()
    config_path.parent.mkdir(parents=True, exist_ok=True)

    os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")
    app = QApplication(sys.argv)
    app.setApplicationName("Codex Indicator")
    app.setApplicationDisplayName("Codex Indicator")
    app.setApplicationVersion(APP_VERSION)
    app.setOrganizationName("Codex Indicator Community")
    app.setQuitOnLastWindowClosed(False)
    app.setWindowIcon(_tray_icon())
    configure_accessory_application()

    instance_name = f"{APPLICATION_ID}.{getpass.getuser() or 'user'}"
    if arguments.smoke_test:
        instance_name = f"{instance_name}.smoke.{os.getpid()}"
    server = _single_instance_server(instance_name)
    if server is None:
        return 0

    runtime = IndicatorRuntime(
        app,
        project_root,
        config_path,
        server,
        manage_startup=_should_manage_startup(
            Path(sys.executable),
            local_app_data,
            frozen=bool(getattr(sys, "frozen", False)),
            smoke_test=arguments.smoke_test,
        ),
        smoke_test=arguments.smoke_test,
    )
    runtime.start()
    if arguments.smoke_test:
        QTimer.singleShot(1200, app.quit)
    result = app.exec()
    if smoke_directory is not None:
        smoke_directory.cleanup()
    return result


if __name__ == "__main__":
    raise SystemExit(main())
