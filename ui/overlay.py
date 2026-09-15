"""Always-on-top floating multi-session overlay."""

from __future__ import annotations

from PySide6.QtCore import (
    QEasingCurve,
    QEvent,
    QPoint,
    QPropertyAnimation,
    QRectF,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import QCursor, QMouseEvent, QPainter, QPaintEvent, QScreen
from PySide6.QtWidgets import QApplication, QWidget

from models.config import AppConfig
from models.events import SessionSnapshot
from models.session import CodexSession, SessionStatus
from ui.animations import AnimationClock
from ui.painter import OverlayPainter
from ui.palette import IndicatorPalette
from ui.progress import usage_presentation
from utils.display import DisplayGeometry, clamp_position, top_center_position
from utils.platform import (
    PlatformKind,
    apply_overlay_window_behavior,
    current_platform,
    foreground_window,
    reduce_motion_enabled,
)
from utils.process_utils import normalized_process_name


class IndicatorOverlay(QWidget):
    """Frameless, draggable and custom-painted session indicator."""

    position_changed = Signal(int, int, str)
    session_activated = Signal(str)

    def __init__(self, config: AppConfig) -> None:
        super().__init__(None)
        self.config = config
        self.palette = IndicatorPalette.from_settings(config.colors)
        self.renderer = OverlayPainter(config, self.palette)
        self.snapshot = SessionSnapshot.create((), 0)
        self.spark_phase = 0.0
        self.pulse_phase = 0.0
        self._row_rects: list[tuple[QRectF, CodexSession]] = []
        self._drag_origin: QPoint | None = None
        self._window_origin: QPoint | None = None
        self._pressed_session: CodexSession | None = None
        self._pressed_count = False
        self._dragged = False
        self._wanted_visible = True
        self._manually_hidden = False
        self._manual_reveal_active = False
        self._expanded = False
        self._ready_labels: set[str] = set()
        self._count_rect: QRectF | None = None
        self._native_behavior_applied = False
        self._last_auto_screen = ""

        flags = (
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        self.setWindowFlags(flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setWindowTitle("Codex Indicator")
        self.setAccessibleName("Codex Indicator floating status")
        self.setAccessibleDescription(
            "Shows the highest-priority Codex session and truthful usage remaining."
        )
        self.setMouseTracking(True)

        animations_enabled = config.animations.enabled and not (
            config.animations.respect_reduce_motion and reduce_motion_enabled()
        )

        self._clock = AnimationClock(
            spark_period_ms=config.animations.spark_period_ms,
            pulse_period_ms=config.animations.pulse_period_ms,
            enabled=animations_enabled,
            parent=self,
        )
        self._clock.tick.connect(self._animation_tick)
        self._clock.start()

        self._visibility_timer = QTimer(self)
        self._visibility_timer.setInterval(config.poll_interval_ms)
        self._visibility_timer.timeout.connect(self._refresh_visibility)
        self._visibility_timer.start()

        self._manual_reveal_timer = QTimer(self)
        self._manual_reveal_timer.setSingleShot(True)
        self._manual_reveal_timer.timeout.connect(self._end_manual_reveal)

        self._ready_label_timer = QTimer(self)
        self._ready_label_timer.setSingleShot(True)
        self._ready_label_timer.setInterval(2_500)
        self._ready_label_timer.timeout.connect(self._clear_ready_labels)

        self._fade = QPropertyAnimation(self, b"windowOpacity", self)
        self._fade.setDuration(config.animations.fade_duration_ms)
        self._fade.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._fade.finished.connect(self._fade_finished)
        application = QApplication.instance()
        if application is not None:
            application.installEventFilter(self)
            application.screenAdded.connect(self._screen_added)
            application.screenRemoved.connect(self._screen_removed)
            application.primaryScreenChanged.connect(self._screen_configuration_changed)
            for screen in application.screens():
                self._connect_screen(screen)
        self._resize_for_rows()

    def showEvent(self, event: object) -> None:
        super().showEvent(event)
        if self.config.theme.use_acrylic and current_platform() is PlatformKind.WINDOWS:
            from ui.windows_effects import enable_acrylic

            enable_acrylic(int(self.winId()))
        if not self._native_behavior_applied:
            self._native_behavior_applied = apply_overlay_window_behavior(self)

    def eventFilter(self, watched: object, event: QEvent) -> bool:
        if self._expanded and (
            event.type() == QEvent.Type.ApplicationDeactivate
            or (event.type() == QEvent.Type.MouseButtonPress and watched is not self)
        ):
            self._expanded = False
            self._resize_for_rows()
            self.update()
        return super().eventFilter(watched, event)

    def set_snapshot(self, snapshot: SessionSnapshot) -> None:
        previous_statuses = {
            session.session_id: session.status for session in self.snapshot.sessions
        }
        newly_ready = {
            session.session_id
            for session in snapshot.sessions
            if session.status is SessionStatus.READY
            and previous_statuses.get(session.session_id) is not SessionStatus.READY
        }
        if newly_ready:
            self._ready_labels.update(newly_ready)
            self._ready_label_timer.start()
        active_ids = {session.session_id for session in snapshot.sessions}
        self._ready_labels.intersection_update(active_ids)
        self.snapshot = snapshot
        if len(snapshot.sessions) <= 1:
            self._expanded = False
        self._resize_for_rows()
        self._update_accessibility()
        self.update()
        self._refresh_visibility()

    def _clear_ready_labels(self) -> None:
        self._ready_labels.clear()
        self.update()

    def apply_config(self, config: AppConfig) -> None:
        """Apply visual and behavioral settings without restarting."""

        self.config = config
        self.palette = IndicatorPalette.from_settings(config.colors)
        self.renderer = OverlayPainter(config, self.palette)
        self._clock.enabled = config.animations.enabled and not (
            config.animations.respect_reduce_motion and reduce_motion_enabled()
        )
        self._clock.spark_period = max(
            0.25,
            config.animations.spark_period_ms / 1_000,
        )
        self._clock.pulse_period = max(
            0.25,
            config.animations.pulse_period_ms / 1_000,
        )
        if self._clock.enabled:
            self._clock.start()
        else:
            self._clock.stop()
        self._visibility_timer.setInterval(config.poll_interval_ms)
        self._fade.setDuration(config.animations.fade_duration_ms)
        if config.display_mode != "notifications_only":
            self._manual_reveal_active = False
            self._manual_reveal_timer.stop()
        self._resize_for_rows()
        self.setWindowOpacity(self.target_opacity())
        self.update()
        self._refresh_visibility()

    def target_opacity(self) -> float:
        """Return the opacity for the selected persistent display mode."""

        if self.config.display_mode == "low_opacity":
            return self.config.low_opacity
        return self.config.theme.opacity

    def sync_visibility(self) -> None:
        """Apply the configured display mode at startup."""

        self._refresh_visibility()

    @property
    def is_manually_hidden(self) -> bool:
        """Return whether the user temporarily hid the overlay."""

        return self._manually_hidden

    def set_manual_hidden(self, hidden: bool) -> None:
        """Hide or restore the overlay without changing saved display settings."""

        self._manually_hidden = hidden
        if hidden:
            self._manual_reveal_active = False
            self._manual_reveal_timer.stop()
        self._refresh_visibility()

    def show_for_user(self, duration_ms: int = 8_000) -> None:
        """Reveal the overlay, temporarily when notifications-only is active."""

        if self.config.display_mode == "notifications_only":
            self._manual_reveal_active = True
            self._manual_reveal_timer.start(max(1_000, duration_ms))
        self._set_wanted_visible(True)
        self.raise_()

    def _end_manual_reveal(self) -> None:
        self._manual_reveal_active = False
        self._refresh_visibility()

    def _visible_sessions(self) -> tuple[CodexSession, ...]:
        if self._expanded or len(self.snapshot.sessions) <= 1:
            return self.snapshot.sessions
        return self.snapshot.sessions[:1]

    def _resize_for_rows(self) -> None:
        count = max(1, len(self._visible_sessions()))
        padding = (
            0
            if current_platform() is PlatformKind.MACOS
            else self.config.theme.outer_padding
        )
        content_height = (
            padding * 2
            + count * self.config.theme.row_height
            + max(0, count - 1) * self.config.theme.row_spacing
        )
        height = max(self.config.theme.height, content_height) + 12
        self.resize(self.config.theme.width, height)
        if self.config.position.mode == "automatic":
            self._move_automatic()
        else:
            self._clamp_to_screen()

    @staticmethod
    def usage_text(session: CodexSession) -> str:
        """Return the always-visible compact usage summary."""

        remaining = session.rate_limit_remaining_percent
        reset = session.rate_limit_resets_at
        if remaining is not None:
            summary = f"{remaining:.0f}% left"
            if reset is not None:
                reset_text = reset.astimezone().strftime("%I:%M %p").lstrip("0")
                summary += f" · {reset_text}"
            return summary
        if session.context_remaining_percent is not None:
            return f"Context {session.context_remaining_percent:.0f}% left"
        return "Usage unavailable"

    def _update_accessibility(self) -> None:
        if not self.snapshot.sessions:
            description = "Codex is ready. Usage unavailable."
        else:
            session = self.snapshot.sessions[0]
            description = (
                f"{session.status.display_name}. "
                f"{usage_presentation(session).description}."
            )
        self.setToolTip(description)
        self.setAccessibleDescription(description)

    def _animation_tick(self, spark: float, pulse: float) -> None:
        self.spark_phase = spark
        self.pulse_phase = pulse
        if any(
            item.status in {SessionStatus.WORKING, SessionStatus.NEEDS_YOU}
            for item in self.snapshot.sessions
        ):
            self.update()

    def paintEvent(self, event: QPaintEvent) -> None:
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        padding = (
            0
            if current_platform() is PlatformKind.MACOS
            else self.config.theme.outer_padding
        )
        surface = QRectF(6, 6, self.width() - 12, self.height() - 12)
        self.renderer.draw_surface(painter, surface)
        content = surface.adjusted(padding, padding, -padding, -padding)
        self._row_rects.clear()
        self._count_rect = None
        if not self.snapshot.sessions:
            self.renderer.draw_empty(painter, content)
            return

        y = content.top()
        visible_sessions = self._visible_sessions()
        for index, session in enumerate(visible_sessions):
            row = QRectF(
                content.left(),
                y,
                content.width(),
                self.config.theme.row_height,
            )
            badge_text = ""
            if index == 0 and len(self.snapshot.sessions) > 1:
                badge_text = (
                    "−" if self._expanded else f"+{len(self.snapshot.sessions) - 1}"
                )
            badge_rect = self.renderer.draw_session(
                painter,
                row,
                session,
                spark_phase=self.spark_phase,
                pulse_phase=self.pulse_phase,
                working_label=session.activity or "Codex is working",
                usage_text=self.usage_text(session),
                badge_text=badge_text,
                show_workspace=self._expanded,
                show_ready_label=session.session_id in self._ready_labels,
            )
            if index == 0:
                self._count_rect = badge_rect
            self._row_rects.append((row, session))
            y += self.config.theme.row_height + self.config.theme.row_spacing

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return
        self._drag_origin = event.globalPosition().toPoint()
        self._window_origin = self.pos()
        self._dragged = False
        point = event.position()
        first_row = self._row_rects[0][0] if self._row_rects else QRectF()
        self._pressed_count = len(self.snapshot.sessions) > 1 and first_row.contains(
            point
        )
        self._pressed_session = next(
            (
                session
                for rect, session in self._row_rects
                if rect.contains(point) and not self._pressed_count
            ),
            None,
        )
        event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._drag_origin is None or self._window_origin is None:
            return
        delta = event.globalPosition().toPoint() - self._drag_origin
        if delta.manhattanLength() > QApplication.startDragDistance():
            self._dragged = True
        if self._dragged:
            self.move(self._window_origin + delta)
        event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return
        if self._dragged:
            self._clamp_to_screen()
            screen = self.screen()
            self.position_changed.emit(
                self.x(),
                self.y(),
                screen.name() if screen else "",
            )
        elif self._pressed_count:
            self._expanded = not self._expanded
            self._resize_for_rows()
            self.update()
        elif self._pressed_session is not None:
            self.session_activated.emit(self._pressed_session.session_id)
        self._drag_origin = None
        self._window_origin = None
        self._pressed_session = None
        self._pressed_count = False
        event.accept()

    def _clamp_to_screen(self) -> None:
        screen = self._screen_named(self.config.position.screen_name)
        screen = screen or self.screen() or QApplication.primaryScreen()
        if screen is None:
            return
        x, y = clamp_position(
            self._display_geometry(screen),
            self.x(),
            self.y(),
            self.width(),
            self.height(),
        )
        self.move(x, y)

    def restore_position(self) -> None:
        position = self.config.position
        if (
            position.mode == "custom"
            and position.x is not None
            and position.y is not None
        ):
            self.move(position.x, position.y)
            self._clamp_to_screen()
            return
        self._move_automatic()

    def reset_position(self) -> None:
        """Return to automatic top-center placement."""

        self._last_auto_screen = ""
        self._move_automatic()

    def _move_automatic(self) -> None:
        screen = QApplication.screenAt(QCursor.pos()) or QApplication.primaryScreen()
        if screen is None:
            return
        x, y = top_center_position(
            self._display_geometry(screen),
            self.width(),
            self.height(),
            safe_gap=6,
        )
        self.move(x, y)
        self._last_auto_screen = screen.name()

    @staticmethod
    def _display_geometry(screen: QScreen) -> DisplayGeometry:
        area = screen.availableGeometry()
        return DisplayGeometry(
            name=screen.name(),
            x=area.x(),
            y=area.y(),
            width=area.width(),
            height=area.height(),
        )

    @staticmethod
    def _screen_named(name: str) -> QScreen | None:
        if not name:
            return None
        return next(
            (screen for screen in QApplication.screens() if screen.name() == name), None
        )

    def _connect_screen(self, screen: QScreen) -> None:
        screen.geometryChanged.connect(self._screen_configuration_changed)
        screen.availableGeometryChanged.connect(self._screen_configuration_changed)

    def _screen_added(self, screen: QScreen) -> None:
        self._connect_screen(screen)
        self._screen_configuration_changed()

    def _screen_removed(self, screen: QScreen) -> None:
        del screen
        if (
            self.config.position.mode == "custom"
            and self._screen_named(self.config.position.screen_name) is None
        ):
            self._move_automatic()
        else:
            self._screen_configuration_changed()

    def _screen_configuration_changed(self, *args: object) -> None:
        del args
        if self.config.position.mode == "automatic":
            self._move_automatic()
        else:
            self._clamp_to_screen()

    def _refresh_visibility(self) -> None:
        if self.config.position.mode == "automatic":
            active = QApplication.screenAt(QCursor.pos())
            if active is not None and active.name() != self._last_auto_screen:
                self._move_automatic()
        needs_attention = self.snapshot.needs_attention
        foreground = foreground_window()
        hidden_names = {
            normalized_process_name(name) for name in self.config.hide_on_processes
        }
        should_hide = (
            self._manually_hidden
            or (
                self.config.display_mode == "notifications_only"
                and not self._manual_reveal_active
            )
            or (
                self.config.auto_hide_enabled
                and not needs_attention
                and foreground is not None
                and normalized_process_name(foreground.process_name) in hidden_names
            )
        )
        self._set_wanted_visible(not should_hide)
        self.update()

    def _set_wanted_visible(self, visible: bool) -> None:
        if self._wanted_visible == visible and (self.isVisible() or not visible):
            return
        self._wanted_visible = visible
        self._fade.stop()
        if visible:
            if not self.isVisible():
                self.setWindowOpacity(0.0 if self.config.animations.enabled else 1.0)
                self.show()
            if self.config.animations.enabled:
                self._fade.setStartValue(self.windowOpacity())
                self._fade.setEndValue(self.target_opacity())
                self._fade.start()
            else:
                self.setWindowOpacity(self.target_opacity())
        elif self.isVisible():
            if self.config.animations.enabled:
                self._fade.setStartValue(self.windowOpacity())
                self._fade.setEndValue(0.0)
                self._fade.start()
            else:
                self.hide()

    def _fade_finished(self) -> None:
        if not self._wanted_visible:
            self.hide()


__all__ = ["IndicatorOverlay"]
