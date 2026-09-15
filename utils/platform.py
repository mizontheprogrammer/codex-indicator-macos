"""Platform detection, paths, and desktop integration entry points."""

from __future__ import annotations

import os

# No shell; platform openers receive one local path.
import subprocess  # nosec B404
import sys
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from utils.windows import ForegroundWindow


class PlatformKind(StrEnum):
    WINDOWS = "windows"
    MACOS = "macos"
    OTHER = "other"


def current_platform(value: str | None = None) -> PlatformKind:
    """Return a stable platform identifier, accepting an override for tests."""

    candidate = sys.platform if value is None else value
    if candidate == "win32":
        return PlatformKind.WINDOWS
    if candidate == "darwin":
        return PlatformKind.MACOS
    return PlatformKind.OTHER


def application_data_directory(
    *,
    platform_name: str | None = None,
    home: Path | None = None,
    environ: dict[str, str] | None = None,
) -> Path:
    """Return the per-user data directory without consulting app-bundle paths."""

    kind = current_platform(platform_name)
    user_home = (home or Path.home()).expanduser()
    environment = os.environ if environ is None else environ
    if kind is PlatformKind.MACOS:
        return user_home / "Library" / "Application Support" / "CodexIndicator"
    if kind is PlatformKind.WINDOWS:
        local = environment.get("LOCALAPPDATA")
        root = Path(local) if local else user_home / "AppData" / "Local"
        return root / "CodexIndicator"
    xdg = environment.get("XDG_DATA_HOME")
    root = Path(xdg) if xdg else user_home / ".local" / "share"
    return root / "CodexIndicator"


def codex_log_paths(*, home: Path | None = None) -> tuple[str, ...]:
    """Return expanded, cross-platform Codex session discovery patterns."""

    codex_root = (home or Path.home()).expanduser() / ".codex"
    return (
        str(codex_root / "sessions" / "*" / "*" / "*" / "rollout-*.jsonl"),
        str(codex_root / "log" / "codex-tui.log"),
        str(codex_root / "logs" / "*.log"),
        str(codex_root / "log" / "*.log"),
    )


def open_path(path: str | Path) -> bool:
    """Open a local path with the platform file manager, without a shell."""

    target = str(Path(path).expanduser())
    try:
        if current_platform() is PlatformKind.WINDOWS:
            startfile = getattr(os, "startfile", None)
            if startfile is None:
                return False
            startfile(target)
            return True
        command = (
            ["/usr/bin/open", target]
            if sys.platform == "darwin"
            else ["/usr/bin/xdg-open", target]
        )
        subprocess.Popen(  # noqa: S603  # nosec B603
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        return True
    except (OSError, subprocess.SubprocessError):
        return False


def focus_process_window(pid: int, hwnd: int | None = None) -> bool:
    """Activate a process through the selected platform implementation."""

    if current_platform() is PlatformKind.WINDOWS:
        from utils.windows import focus_process_window as windows_focus

        return windows_focus(pid, hwnd)
    if current_platform() is PlatformKind.MACOS:
        from utils.macos import activate_process

        return activate_process(pid)
    return False


def foreground_window() -> ForegroundWindow | None:
    """Return foreground-window metadata where supported without permissions."""

    if current_platform() is PlatformKind.WINDOWS:
        from utils.windows import foreground_window as windows_foreground

        return windows_foreground()
    return None


def configure_accessory_application() -> bool:
    """Hide the Dock presence for an interactive source run on macOS."""

    if current_platform() is not PlatformKind.MACOS:
        return False
    from utils.macos import configure_accessory_application as configure

    return configure()


def apply_overlay_window_behavior(widget: object) -> bool:
    """Apply optional native overlay behavior after the Qt window exists."""

    if current_platform() is not PlatformKind.MACOS:
        return False
    from utils.macos import apply_overlay_window_behavior as apply_behavior

    return apply_behavior(widget)


def reduce_motion_enabled() -> bool:
    """Return the system accessibility preference when it can be read safely."""

    if current_platform() is not PlatformKind.MACOS:
        return False
    from utils.macos import reduce_motion_enabled as macos_reduce_motion

    return macos_reduce_motion()


__all__ = [
    "PlatformKind",
    "application_data_directory",
    "apply_overlay_window_behavior",
    "codex_log_paths",
    "configure_accessory_application",
    "current_platform",
    "focus_process_window",
    "foreground_window",
    "open_path",
    "reduce_motion_enabled",
]
