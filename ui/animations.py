"""Shared animation clock for custom-painted overlay effects."""

from __future__ import annotations

import time

from PySide6.QtCore import QObject, QTimer, Signal


class AnimationClock(QObject):
    """Emit normalized spark and pulse phases from one efficient timer."""

    tick = Signal(float, float)

    def __init__(
        self,
        *,
        spark_period_ms: int,
        pulse_period_ms: int,
        enabled: bool = True,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.spark_period = max(0.25, spark_period_ms / 1_000)
        self.pulse_period = max(0.25, pulse_period_ms / 1_000)
        self.enabled = enabled
        self._origin = time.monotonic()
        self._timer = QTimer(self)
        self._timer.setInterval(33)
        self._timer.timeout.connect(self._advance)

    def start(self) -> None:
        if self.enabled and not self._timer.isActive():
            self._origin = time.monotonic()
            self._timer.start()

    def stop(self) -> None:
        self._timer.stop()

    def _advance(self) -> None:
        elapsed = time.monotonic() - self._origin
        spark = (elapsed % self.spark_period) / self.spark_period
        pulse = (elapsed % self.pulse_period) / self.pulse_period
        self.tick.emit(spark, pulse)


__all__ = ["AnimationClock"]
