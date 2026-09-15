"""Opt-in, per-user launch-at-login registration."""

from __future__ import annotations

import os
import plistlib
import sys
import tempfile
from pathlib import Path

from utils.platform import PlatformKind, current_platform

STARTUP_VALUE_NAME = "CodexIndicator"


class LoginItemManager:
    """Manage only Codex Indicator's own per-user startup registration."""

    def __init__(
        self,
        *,
        bundle_identifier: str,
        executable: Path,
        project_root: Path,
        home: Path | None = None,
        platform_name: str | None = None,
    ) -> None:
        self.bundle_identifier = bundle_identifier
        self.executable = executable.resolve()
        self.project_root = project_root.resolve()
        self.home = (home or Path.home()).expanduser()
        self.kind = current_platform(platform_name)

    @property
    def launch_agent_path(self) -> Path:
        return (
            self.home / "Library" / "LaunchAgents" / f"{self.bundle_identifier}.plist"
        )

    def _program_arguments(self) -> list[str]:
        if getattr(sys, "frozen", False):
            return [str(self.executable)]
        return [str(self.executable), str(self.project_root / "indicator.py")]

    def is_enabled(self) -> bool:
        if self.kind is PlatformKind.MACOS:
            try:
                with self.launch_agent_path.open("rb") as stream:
                    document = plistlib.load(stream)
            except (OSError, plistlib.InvalidFileException):
                return False
            return (
                document.get("Label") == self.bundle_identifier
                and document.get("ProgramArguments") == self._program_arguments()
            )
        if self.kind is PlatformKind.WINDOWS:
            return self._windows_value() is not None
        return False

    def set_enabled(self, enabled: bool) -> bool:
        if self.kind is PlatformKind.MACOS:
            return self._set_macos(enabled)
        if self.kind is PlatformKind.WINDOWS:
            return self._set_windows(enabled)
        return False

    def _set_macos(self, enabled: bool) -> bool:
        path = self.launch_agent_path
        if not enabled:
            try:
                path.unlink(missing_ok=True)
                return True
            except OSError:
                return False
        document = {
            "Label": self.bundle_identifier,
            "ProgramArguments": self._program_arguments(),
            "RunAtLoad": True,
            "KeepAlive": False,
            "ProcessType": "Interactive",
        }
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            descriptor, temporary_name = tempfile.mkstemp(
                prefix=f".{path.name}.",
                suffix=".tmp",
                dir=path.parent,
            )
            try:
                with os.fdopen(descriptor, "wb") as stream:
                    plistlib.dump(document, stream, sort_keys=True)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.chmod(temporary_name, 0o600)
                os.replace(temporary_name, path)
            except BaseException:
                Path(temporary_name).unlink(missing_ok=True)
                raise
            return True
        except OSError:
            return False

    def _windows_value(self) -> str | None:
        try:
            import winreg

            key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
                value, _ = winreg.QueryValueEx(key, STARTUP_VALUE_NAME)
            return str(value)
        except (ImportError, OSError):
            return None

    def _set_windows(self, enabled: bool) -> bool:
        try:
            import winreg

            key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path) as key:
                if enabled:
                    command = " ".join(
                        f'"{part}"' for part in self._program_arguments()
                    )
                    winreg.SetValueEx(
                        key,
                        STARTUP_VALUE_NAME,
                        0,
                        winreg.REG_SZ,
                        command,
                    )
                else:
                    try:
                        winreg.DeleteValue(key, STARTUP_VALUE_NAME)
                    except FileNotFoundError:
                        pass
            return True
        except (ImportError, OSError):
            return False


__all__ = ["LoginItemManager", "STARTUP_VALUE_NAME"]
