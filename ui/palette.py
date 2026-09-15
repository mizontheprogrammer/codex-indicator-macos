"""Qt color palette derived from validated application settings."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtGui import QColor

from models.config import ColorSettings
from models.session import SessionStatus


@dataclass(frozen=True, slots=True)
class IndicatorPalette:
    ready: QColor
    working: QColor
    needs_you: QColor
    background: QColor
    border: QColor
    primary_text: QColor
    secondary_text: QColor
    shadow: QColor

    @classmethod
    def from_settings(cls, settings: ColorSettings) -> IndicatorPalette:
        return cls(
            ready=QColor(settings.ready),
            working=QColor(settings.working),
            needs_you=QColor(settings.needs_you),
            background=QColor(settings.background),
            border=QColor(settings.border),
            primary_text=QColor(settings.primary_text),
            secondary_text=QColor(settings.secondary_text),
            shadow=QColor(settings.shadow),
        )

    def for_status(self, status: SessionStatus) -> QColor:
        return {
            SessionStatus.READY: self.ready,
            SessionStatus.WORKING: self.working,
            SessionStatus.NEEDS_YOU: self.needs_you,
        }[status]


__all__ = ["IndicatorPalette"]
