"""Custom drawing primitives for the floating indicator."""

from __future__ import annotations

import math
from pathlib import Path

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPen

from models.config import AppConfig
from models.session import CodexSession, SessionStatus
from ui.palette import IndicatorPalette
from ui.progress import (
    determinate_fill_rect,
    indeterminate_segment_rect,
    usage_presentation,
)
from utils.platform import PlatformKind, current_platform


class OverlayPainter:
    """Render the compact warm-white indicator without stock Qt controls."""

    def __init__(self, config: AppConfig, palette: IndicatorPalette) -> None:
        self.config = config
        self.palette = palette

    def draw_surface(self, painter: QPainter, rect: QRectF) -> None:
        if current_platform() is PlatformKind.MACOS:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor("#050505"))
            radius = min(rect.height() / 2.0, self.config.theme.corner_radius)
            painter.drawRoundedRect(rect, radius, radius)
            return
        radius = self.config.theme.corner_radius
        for spread, alpha in ((6, 10), (3, 16), (1, 22)):
            shadow = QColor(self.palette.shadow)
            shadow.setAlpha(alpha)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(shadow)
            painter.drawRoundedRect(
                rect.adjusted(-spread, -spread, spread, spread),
                radius + spread,
                radius + spread,
            )
        painter.setBrush(self.palette.background)
        painter.setPen(QPen(self.palette.border, 1.0))
        painter.drawRoundedRect(rect, radius, radius)

    def draw_empty(self, painter: QPainter, rect: QRectF) -> None:
        if current_platform() is PlatformKind.MACOS:
            self._draw_macos_empty(painter, rect)
            return
        icon_x = rect.left() + 20
        icon_y = rect.center().y()
        self._draw_halo(painter, icon_x, icon_y, self.palette.ready)
        self._draw_conversation_loop(
            painter,
            icon_x,
            icon_y,
            self.palette.ready,
        )
        primary = QFont(self.config.theme.font_family, 9)
        primary.setWeight(QFont.Weight.DemiBold)
        painter.setFont(primary)
        painter.setPen(self.palette.primary_text)
        painter.drawText(
            QRectF(rect.left() + 38, rect.top() + 2, rect.width() - 48, 18),
            Qt.AlignmentFlag.AlignVCenter,
            "Codex is ready",
        )
        painter.setFont(QFont(self.config.theme.font_family, 7))
        painter.setPen(self.palette.secondary_text)
        painter.drawText(
            QRectF(rect.left() + 38, rect.top() + 19, rect.width() - 48, 16),
            Qt.AlignmentFlag.AlignVCenter,
            "Usage unavailable",
        )

    def draw_session(
        self,
        painter: QPainter,
        rect: QRectF,
        session: CodexSession,
        *,
        spark_phase: float,
        pulse_phase: float,
        working_label: str,
        usage_text: str,
        badge_text: str = "",
        show_workspace: bool = False,
        show_ready_label: bool = True,
    ) -> QRectF | None:
        if current_platform() is PlatformKind.MACOS:
            return self._draw_macos_session(
                painter,
                rect,
                session,
                spark_phase=spark_phase,
                badge_text=badge_text,
                show_workspace=show_workspace,
                show_ready_label=show_ready_label,
            )
        color = self.palette.for_status(session.status)
        if session.status is SessionStatus.NEEDS_YOU:
            glow = QColor(color)
            glow.setAlpha(int(10 + 14 * (0.5 - 0.5 * math.cos(pulse_phase * math.tau))))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(glow)
            painter.drawRoundedRect(rect.adjusted(1, 1, -1, -1), 16, 16)

        icon_x = rect.left() + 20
        icon_y = rect.center().y()
        self._draw_halo(painter, icon_x, icon_y, color)
        glyph_scale = 1.0
        if session.status is SessionStatus.NEEDS_YOU:
            glyph_scale += 0.08 * math.sin(pulse_phase * math.pi) ** 2
        self._draw_conversation_loop(
            painter,
            icon_x,
            icon_y,
            color,
            phase=spark_phase if session.status is SessionStatus.WORKING else 0.0,
            scale=glyph_scale,
        )

        elapsed = session.formatted_elapsed()
        if session.status is SessionStatus.READY:
            title = "Codex is ready"
        elif session.status is SessionStatus.NEEDS_YOU:
            title = "Codex needs you"
        else:
            title = working_label

        text_left = rect.left() + 38
        text_right = rect.right() - 10
        elapsed_font = QFont(self.config.theme.font_family, 7)
        elapsed_width = QFontMetrics(elapsed_font).horizontalAdvance(elapsed)
        badge_rect: QRectF | None = None
        badge_space = 0.0
        if badge_text:
            badge_width = 24.0
            badge_rect = QRectF(
                text_right - elapsed_width - badge_width - 8,
                rect.center().y() - 9,
                badge_width,
                18,
            )
            badge_space = badge_width + 8

        title_font = QFont(self.config.theme.font_family, 9)
        title_font.setWeight(QFont.Weight.DemiBold)
        painter.setFont(title_font)
        painter.setPen(self.palette.primary_text)
        title_rect = QRectF(
            text_left,
            rect.top() + 2,
            text_right - text_left - elapsed_width - badge_space - 8,
            18,
        )
        elided_title = QFontMetrics(title_font).elidedText(
            title,
            Qt.TextElideMode.ElideRight,
            int(title_rect.width()),
        )
        painter.drawText(title_rect, Qt.AlignmentFlag.AlignVCenter, elided_title)

        painter.setFont(elapsed_font)
        painter.setPen(self.palette.secondary_text)
        painter.drawText(
            QRectF(text_right - elapsed_width, rect.top() + 9, elapsed_width, 20),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
            elapsed,
        )

        secondary_font = QFont(self.config.theme.font_family, 7)
        painter.setFont(secondary_font)
        painter.setPen(self.palette.secondary_text)
        secondary_rect = QRectF(
            text_left,
            rect.top() + 19,
            text_right - text_left - elapsed_width - badge_space - 8,
            16,
        )
        usage_text = QFontMetrics(secondary_font).elidedText(
            usage_text,
            Qt.TextElideMode.ElideMiddle,
            int(secondary_rect.width()),
        )
        painter.drawText(secondary_rect, Qt.AlignmentFlag.AlignVCenter, usage_text)

        if badge_rect is not None:
            badge_fill = QColor(color)
            badge_fill.setAlpha(24)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(badge_fill)
            painter.drawRoundedRect(badge_rect, 9, 9)
            painter.setFont(QFont(self.config.theme.font_family, 7))
            painter.setPen(color)
            painter.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, badge_text)
        return badge_rect

    def _draw_macos_empty(self, painter: QPainter, rect: QRectF) -> None:
        self._draw_brand_mark(painter, rect.left() + 18, rect.center().y(), 16)
        font = QFont(".AppleSystemUIFont", 12)
        font.setWeight(QFont.Weight.DemiBold)
        painter.setFont(font)
        painter.setPen(QColor("#FFFFFF"))
        painter.drawText(
            rect.adjusted(40, 0, -16, 0),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            "Ready",
        )
        painter.drawText(
            rect.adjusted(0, 0, -14, 0),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
            "—",
        )

    def _draw_macos_session(
        self,
        painter: QPainter,
        rect: QRectF,
        session: CodexSession,
        *,
        spark_phase: float,
        badge_text: str,
        show_workspace: bool,
        show_ready_label: bool,
    ) -> QRectF | None:
        white = QColor("#FFFFFF")
        muted = QColor("#A8A8A8")
        track_color = QColor("#393939")
        self._draw_brand_mark(painter, rect.left() + 18, rect.center().y(), 16)

        presentation = usage_presentation(session)
        percent_font = QFont(".AppleSystemUIFont", 13)
        percent_font.setWeight(QFont.Weight.DemiBold)
        painter.setFont(percent_font)
        painter.setPen(white)
        percent_rect = QRectF(rect.right() - 52, rect.top(), 40, rect.height())
        painter.drawText(
            percent_rect,
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
            presentation.percentage_text,
        )

        badge_rect: QRectF | None = None
        track_right = percent_rect.left() - 12
        if badge_text:
            badge_rect = QRectF(rect.left() + 34, rect.center().y() - 8, 25, 16)
            painter.setBrush(QColor("#202020"))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(badge_rect, 8, 8)
            badge_font = QFont(".AppleSystemUIFont", 8)
            badge_font.setWeight(QFont.Weight.DemiBold)
            painter.setFont(badge_font)
            painter.setPen(white)
            painter.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, badge_text)

        text_left = rect.left() + (68 if badge_text else 42)
        track = QRectF(text_left, rect.center().y() - 1.5, track_right - text_left, 3)
        status_text = ""
        if session.status is SessionStatus.NEEDS_YOU:
            status_text = "Needs you"
        elif session.status is SessionStatus.READY and show_ready_label:
            status_text = "Ready"
        if show_workspace:
            workspace = Path(session.workspace).name or session.session_id
            status_text = f"{session.status.display_name} · {workspace}"
        if status_text:
            status_font = QFont(".AppleSystemUIFont", 10)
            status_font.setWeight(QFont.Weight.Medium)
            painter.setFont(status_font)
            painter.setPen(
                white if session.status is SessionStatus.NEEDS_YOU else muted
            )
            status_rect = QRectF(text_left, rect.top() + 5, track.width(), 16)
            status_text = QFontMetrics(status_font).elidedText(
                status_text,
                Qt.TextElideMode.ElideMiddle,
                int(status_rect.width()),
            )
            painter.drawText(status_rect, Qt.AlignmentFlag.AlignVCenter, status_text)
            track.moveTop(rect.bottom() - 12)

        self._draw_progress_track(painter, track, track_color)
        if presentation.value is not None:
            fill = determinate_fill_rect(track, presentation.value)
            self._draw_progress_track(painter, fill, white)
        elif session.status is SessionStatus.WORKING:
            segment = indeterminate_segment_rect(track, spark_phase)
            self._draw_progress_track(painter, segment, white)

        if show_workspace:
            elapsed_font = QFont(".AppleSystemUIFont", 8)
            painter.setFont(elapsed_font)
            painter.setPen(muted)
            detail = f"{presentation.description} · {session.formatted_elapsed()}"
            detail_rect = QRectF(text_left, rect.top() + 21, track.width(), 13)
            detail = QFontMetrics(elapsed_font).elidedText(
                detail,
                Qt.TextElideMode.ElideRight,
                int(detail_rect.width()),
            )
            painter.drawText(detail_rect, Qt.AlignmentFlag.AlignVCenter, detail)
        return badge_rect

    @staticmethod
    def _draw_progress_track(painter: QPainter, rect: QRectF, color: QColor) -> None:
        if rect.width() <= 0 or rect.height() <= 0:
            return
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        radius = rect.height() / 2.0
        painter.drawRoundedRect(rect, radius, radius)

    @staticmethod
    def _draw_brand_mark(
        painter: QPainter,
        x: float,
        y: float,
        size: float,
    ) -> None:
        """Draw the repository's conversation-orbit C and sparkle in white."""

        painter.save()
        painter.translate(x, y)
        scale = size / 18.0
        painter.scale(scale, scale)
        pen = QPen(QColor("#FFFFFF"), 2.7)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawArc(QRectF(-7, -7, 14, 14), 42 * 16, 276 * 16)
        sparkle = QPainterPath()
        sparkle.moveTo(0, -3.0)
        sparkle.cubicTo(0.3, -0.8, 0.8, -0.3, 3.0, 0)
        sparkle.cubicTo(0.8, 0.3, 0.3, 0.8, 0, 3.0)
        sparkle.cubicTo(-0.3, 0.8, -0.8, 0.3, -3.0, 0)
        sparkle.cubicTo(-0.8, -0.3, -0.3, -0.8, 0, -3.0)
        sparkle.closeSubpath()
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#FFFFFF"))
        painter.drawPath(sparkle)
        painter.restore()

    @staticmethod
    def _draw_halo(
        painter: QPainter,
        x: float,
        y: float,
        color: QColor,
    ) -> None:
        halo = QColor(color)
        halo.setAlpha(28)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(halo)
        painter.drawEllipse(QRectF(x - 11, y - 11, 22, 22))

    @staticmethod
    def _draw_conversation_loop(
        painter: QPainter,
        x: float,
        y: float,
        color: object,
        *,
        phase: float = 0.0,
        scale: float = 1.0,
    ) -> None:
        """Draw an original six-link conversation loop at status-glyph scale."""

        painter.save()
        painter.translate(x, y)
        painter.rotate(phase * 60.0)
        painter.scale(scale, scale)
        pen = QPen(QColor(color), 1.55)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)

        for index in range(6):
            painter.save()
            painter.rotate(index * 60.0)
            link = QPainterPath()
            link.moveTo(0.0, -5.8)
            link.cubicTo(2.8, -5.8, 5.2, -4.0, 5.7, -1.4)
            link.cubicTo(5.9, -0.2, 5.6, 1.0, 4.9, 2.0)
            link.lineTo(2.8, 0.8)
            link.cubicTo(3.2, 0.1, 3.3, -0.6, 3.0, -1.3)
            link.cubicTo(2.5, -2.5, 1.4, -3.2, 0.0, -3.2)
            painter.drawPath(link)
            painter.restore()
        painter.restore()


__all__ = ["OverlayPainter"]
