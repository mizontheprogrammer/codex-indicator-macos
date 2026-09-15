"""Permission-tolerant desktop notifications through Qt's public API."""

from __future__ import annotations

import logging

from PySide6.QtWidgets import QSystemTrayIcon

LOGGER = logging.getLogger(__name__)


class DesktopNotifier:
    """Send notifications when supported and never make monitoring depend on them."""

    def __init__(self, tray: QSystemTrayIcon, *, enabled: bool = True) -> None:
        self.tray = tray
        self.enabled = enabled

    def notify(
        self,
        title: str,
        message: str,
        icon: QSystemTrayIcon.MessageIcon,
        duration_ms: int,
    ) -> bool:
        if not self.enabled:
            return False
        try:
            if not self.tray.supportsMessages():
                return False
            self.tray.showMessage(title, message, icon, duration_ms)
            return True
        except (RuntimeError, TypeError) as error:
            LOGGER.debug("Desktop notification unavailable: %s", error)
            return False


__all__ = ["DesktopNotifier"]
