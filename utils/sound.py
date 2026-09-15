"""Rate-limited notification sounds with safe platform fallbacks."""

from __future__ import annotations

import ctypes
import logging

# Fixed afplay path and argument list only.
import subprocess  # nosec B404
import sys
import threading
import time
from pathlib import Path

LOGGER = logging.getLogger(__name__)

if sys.platform == "win32":
    try:
        import winsound
    except ImportError:
        winsound = None
else:
    winsound = None


class NotificationSound:
    """Play a configured system alias without blocking the UI thread."""

    def __init__(
        self,
        *,
        enabled: bool = True,
        alias: str = "SystemExclamation",
        minimum_interval_seconds: float = 3.0,
        file_path: str | Path | None = None,
    ) -> None:
        self.enabled = enabled
        self.alias = alias
        self.minimum_interval_seconds = max(0.0, minimum_interval_seconds)
        self.file_path = Path(file_path).resolve() if file_path else None
        self._last_played = 0.0
        self._lock = threading.Lock()
        self._mci_alias = f"CodexIndicatorSound{id(self):x}"

    def play(self, *, force: bool = False) -> bool:
        """Request a sound, returning whether playback was scheduled."""

        if not self.enabled or sys.platform not in {"win32", "darwin"}:
            return False
        now = time.monotonic()
        with self._lock:
            if not force and now - self._last_played < self.minimum_interval_seconds:
                return False
            played = self._play_file()
            if not played:
                played = self._play_alias()
            if played:
                self._last_played = now
            return played

    def _play_file(self) -> bool:
        if self.file_path is None or not self.file_path.is_file():
            return False
        if sys.platform == "darwin":
            return self._play_macos_path(self.file_path)
        if sys.platform != "win32":
            return False
        try:
            self._send_mci(f"close {self._mci_alias}", log_error=False)
            opened = self._send_mci(
                f'open "{self.file_path}" type mpegvideo alias {self._mci_alias}'
            )
            if not opened:
                return False
            if self._send_mci(f"play {self._mci_alias} from 0"):
                return True
            self._send_mci(f"close {self._mci_alias}", log_error=False)
        except (AttributeError, OSError) as error:
            LOGGER.warning("Unable to play custom notification sound: %s", error)
        return False

    def _play_alias(self) -> bool:
        if sys.platform == "darwin":
            return self._play_macos_path(Path("/System/Library/Sounds/Glass.aiff"))
        if winsound is None:
            return False
        try:
            winsound.PlaySound(
                self.alias,
                winsound.SND_ALIAS | winsound.SND_ASYNC | winsound.SND_NODEFAULT,
            )
            return True
        except RuntimeError as error:
            LOGGER.warning(
                "Unable to play notification sound %r: %s", self.alias, error
            )
            return False

    @staticmethod
    def _play_macos_path(path: Path) -> bool:
        """Schedule playback using the bundled public `afplay` utility."""

        if not path.is_file():
            return False
        try:
            subprocess.Popen(  # noqa: S603  # nosec B603
                ["/usr/bin/afplay", str(path)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            return True
        except (OSError, subprocess.SubprocessError):
            return False

    @staticmethod
    def _mci_error(code: int) -> str:
        buffer = ctypes.create_unicode_buffer(512)
        try:
            if ctypes.windll.winmm.mciGetErrorStringW(
                code,
                buffer,
                len(buffer),
            ):
                return buffer.value
        except (AttributeError, OSError):
            pass
        return f"MCI error {code}"

    def _send_mci(self, command: str, *, log_error: bool = True) -> bool:
        code = int(ctypes.windll.winmm.mciSendStringW(command, None, 0, None))
        if code == 0:
            return True
        if log_error:
            LOGGER.warning(
                "Custom notification command failed: %s",
                self._mci_error(code),
            )
        return False

    def close(self) -> None:
        """Release the custom audio device, if it was opened."""

        if sys.platform != "win32":
            return
        with self._lock:
            try:
                self._send_mci(f"close {self._mci_alias}", log_error=False)
            except (AttributeError, OSError):
                pass


__all__ = ["NotificationSound"]
