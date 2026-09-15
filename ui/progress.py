"""Truthful Codex usage semantics and progress-line geometry."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from PySide6.QtCore import QRectF

from models.session import CodexSession


class PercentageSource(StrEnum):
    RATE_LIMIT = "rate_limit"
    CONTEXT = "context"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class UsagePresentation:
    value: float | None
    source: PercentageSource

    @property
    def percentage_text(self) -> str:
        return "—" if self.value is None else f"{self.value:.0f}%"

    @property
    def description(self) -> str:
        if self.source is PercentageSource.RATE_LIMIT:
            return f"Usage remaining: {self.percentage_text}"
        if self.source is PercentageSource.CONTEXT:
            return f"Context remaining: {self.percentage_text}"
        return "Usage unavailable"


def usage_presentation(session: CodexSession) -> UsagePresentation:
    """Select the only permitted progress value in the documented priority."""

    if session.rate_limit_remaining_percent is not None:
        return UsagePresentation(
            session.rate_limit_remaining_percent,
            PercentageSource.RATE_LIMIT,
        )
    if session.context_remaining_percent is not None:
        return UsagePresentation(
            session.context_remaining_percent,
            PercentageSource.CONTEXT,
        )
    return UsagePresentation(None, PercentageSource.UNAVAILABLE)


def determinate_fill_rect(track: QRectF, value: float) -> QRectF:
    """Return a clamped fill rectangle representing exactly 0–100 percent."""

    percent = max(0.0, min(100.0, float(value)))
    return QRectF(
        track.left(), track.top(), track.width() * percent / 100.0, track.height()
    )


def indeterminate_segment_rect(track: QRectF, phase: float) -> QRectF:
    """Return a gently bouncing segment without implying task completion."""

    normalized = max(0.0, min(1.0, float(phase)))
    segment_width = min(track.width(), max(track.height(), track.width() * 0.22))
    travel = max(0.0, track.width() - segment_width)
    position = normalized * 2.0
    if position > 1.0:
        position = 2.0 - position
    return QRectF(
        track.left() + travel * position,
        track.top(),
        segment_width,
        track.height(),
    )


__all__ = [
    "PercentageSource",
    "UsagePresentation",
    "determinate_fill_rect",
    "indeterminate_segment_rect",
    "usage_presentation",
]
