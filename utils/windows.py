"""Defensive wrappers around native Windows window-management APIs."""

from __future__ import annotations

import logging
import os
import sys
from dataclasses import dataclass

from utils.process_utils import process_info

LOGGER = logging.getLogger(__name__)
IS_WINDOWS = sys.platform == "win32"

if IS_WINDOWS:
    try:
        import win32con
        import win32gui
        import win32process
    except ImportError:
        win32con = win32gui = win32process = None
else:
    win32con = win32gui = win32process = None


@dataclass(frozen=True, slots=True)
class ForegroundWindow:
    hwnd: int
    pid: int
    process_name: str
    title: str


def native_apis_available() -> bool:
    return all(api is not None for api in (win32con, win32gui, win32process))


def foreground_window() -> ForegroundWindow | None:
    """Return foreground window identity, tolerating disappearing windows."""

    if not native_apis_available():
        return None
    try:
        hwnd = int(win32gui.GetForegroundWindow())
        if not hwnd:
            return None
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        info = process_info(int(pid))
        return ForegroundWindow(
            hwnd=hwnd,
            pid=int(pid),
            process_name=info.name if info else "",
            title=str(win32gui.GetWindowText(hwnd) or ""),
        )
    except Exception as error:  # noqa: BLE001 - native API boundary
        LOGGER.debug("Unable to inspect foreground window: %s", error)
        return None


def find_main_window(pid: int) -> int | None:
    """Find a visible, unowned top-level window belonging to a process."""

    if pid <= 0 or not native_apis_available():
        return None
    candidates: list[int] = []

    def visitor(hwnd: int, _: object) -> bool:
        try:
            _, window_pid = win32process.GetWindowThreadProcessId(hwnd)
            if (
                int(window_pid) == pid
                and win32gui.IsWindowVisible(hwnd)
                and not win32gui.GetWindow(hwnd, win32con.GW_OWNER)
                and win32gui.GetWindowText(hwnd)
            ):
                candidates.append(int(hwnd))
        except Exception as error:  # noqa: BLE001 - window may disappear
            LOGGER.debug("Skipping window %s during enumeration: %s", hwnd, error)
        return True

    try:
        win32gui.EnumWindows(visitor, None)
    except Exception as error:  # noqa: BLE001 - native API boundary
        LOGGER.debug("Window enumeration failed for PID %s: %s", pid, error)
    return candidates[0] if candidates else None


def focus_window(hwnd: int) -> bool:
    """Restore and focus a window using the least invasive Win32 sequence."""

    if hwnd <= 0 or not native_apis_available():
        return False
    try:
        if not win32gui.IsWindow(hwnd):
            return False
        if win32gui.IsIconic(hwnd):
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        else:
            win32gui.ShowWindow(hwnd, win32con.SW_SHOW)
        win32gui.BringWindowToTop(hwnd)
        win32gui.SetForegroundWindow(hwnd)
        return True
    except Exception as error:  # noqa: BLE001 - native API boundary
        LOGGER.warning("Unable to focus window %s: %s", hwnd, error)
        return False


def focus_process_window(pid: int, hwnd: int | None = None) -> bool:
    """Focus a known handle or discover the process's main window."""

    target = hwnd if hwnd and hwnd > 0 else find_main_window(pid)
    return focus_window(target) if target else False


def current_user_startup_directory() -> str:
    """Return the per-user Startup folder without COM dependencies."""

    appdata = os.environ.get("APPDATA", "")
    return os.path.join(
        appdata,
        "Microsoft",
        "Windows",
        "Start Menu",
        "Programs",
        "Startup",
    )


__all__ = [
    "IS_WINDOWS",
    "ForegroundWindow",
    "current_user_startup_directory",
    "find_main_window",
    "focus_process_window",
    "focus_window",
    "foreground_window",
    "native_apis_available",
]
