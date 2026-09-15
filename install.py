"""Installer and uninstaller for a source-based Codex Indicator checkout."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

if sys.platform == "win32":
    import winreg
else:
    winreg = None

PROJECT_ROOT = Path(__file__).resolve().parent
CONFIG_PATH = PROJECT_ROOT / "config.json"
RUNTIME_PATH = PROJECT_ROOT / "runtime"
MANIFEST_PATH = PROJECT_ROOT / "uninstall-manifest.json"
REQUIREMENTS = ("PySide6", "psutil", "win32api")
STARTUP_VALUE_NAME = "CodexIndicator"


def missing_dependencies() -> tuple[str, ...]:
    return tuple(
        name for name in REQUIREMENTS if importlib.util.find_spec(name) is None
    )


def backup_config() -> Path | None:
    if not CONFIG_PATH.exists():
        return None
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    target = CONFIG_PATH.with_name(f"config.json.backup-{timestamp}")
    shutil.copy2(CONFIG_PATH, target)
    return target


def _pythonw() -> Path:
    candidate = Path(sys.executable).with_name("pythonw.exe")
    return candidate if candidate.exists() else Path(sys.executable)


def _shortcut(path: Path) -> None:
    try:
        import win32com.client
    except ImportError as error:
        raise RuntimeError("pywin32 is required to create shortcuts") from error
    path.parent.mkdir(parents=True, exist_ok=True)
    shell = win32com.client.Dispatch("WScript.Shell")
    shortcut = shell.CreateShortCut(str(path))
    shortcut.Targetpath = str(
        Path(os.environ.get("WINDIR", r"C:\Windows")) / "System32/wscript.exe"
    )
    shortcut.Arguments = f'"{PROJECT_ROOT / "launch_silent.vbs"}"'
    shortcut.WorkingDirectory = str(PROJECT_ROOT)
    shortcut.Description = "Floating status overlay for Codex CLI"
    icon_path = PROJECT_ROOT / "assets" / "codex_indicator.ico"
    shortcut.IconLocation = f"{icon_path},0"
    shortcut.save()


def _set_startup(enabled: bool) -> None:
    if winreg is None:
        raise RuntimeError("The source installer is available only on Windows")
    key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path) as key:
        if enabled:
            wscript = (
                Path(os.environ.get("WINDIR", r"C:\Windows")) / "System32/wscript.exe"
            )
            launcher = PROJECT_ROOT / "launch_silent.vbs"
            command = f'"{wscript}" "{launcher}"'
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


def _known_shortcuts() -> dict[str, Path]:
    appdata = Path(os.environ.get("APPDATA", ""))
    desktop = Path(os.environ.get("USERPROFILE", "")) / "Desktop"
    return {
        "start_menu": (
            appdata / "Microsoft/Windows/Start Menu/Programs/Codex Indicator.lnk"
        ),
        "startup": (
            appdata
            / "Microsoft/Windows/Start Menu/Programs/Startup/Codex Indicator.lnk"
        ),
        "desktop": desktop / "Codex Indicator.lnk",
    }


def install(arguments: argparse.Namespace) -> int:
    missing = missing_dependencies()
    if missing and arguments.install_dependencies:
        subprocess.run(
            [
                sys.executable,
                "-m",
                "pip",
                "install",
                "-r",
                str(PROJECT_ROOT / "requirements.txt"),
            ],
            check=True,
        )
        missing = missing_dependencies()
    if missing:
        print("Missing dependencies:", ", ".join(missing))
        print("Run: python install.py --install-dependencies")
        return 2

    (RUNTIME_PATH / "sessions").mkdir(parents=True, exist_ok=True)
    created: list[str] = []
    shortcuts = _known_shortcuts()
    _shortcut(shortcuts["start_menu"])
    created.append(str(shortcuts["start_menu"]))
    if arguments.startup:
        _set_startup(True)
    if arguments.desktop:
        _shortcut(shortcuts["desktop"])
        created.append(str(shortcuts["desktop"]))

    backup = None if arguments.no_config_backup else backup_config()
    manifest = {
        "schema_version": 1,
        "installed_at": datetime.now(UTC).isoformat(),
        "project_root": str(PROJECT_ROOT),
        "shortcuts": created,
        "config_backup": str(backup) if backup else None,
    }
    MANIFEST_PATH.write_text(
        json.dumps(manifest, indent=2) + "\n",
        encoding="utf-8",
    )
    print("Codex Indicator installed.")
    print(f"Launch: {_pythonw()} {PROJECT_ROOT / 'indicator.py'}")
    return 0


def uninstall(arguments: argparse.Namespace) -> int:
    _set_startup(False)
    for shortcut in _known_shortcuts().values():
        try:
            shortcut.unlink(missing_ok=True)
        except OSError as error:
            print(f"Warning: could not remove {shortcut}: {error}")
    MANIFEST_PATH.unlink(missing_ok=True)

    if arguments.purge_data and RUNTIME_PATH.resolve().parent == PROJECT_ROOT:
        shutil.rmtree(RUNTIME_PATH, ignore_errors=True)
    if arguments.purge_config:
        backup_config()
        CONFIG_PATH.unlink(missing_ok=True)
    print("Codex Indicator shortcuts and startup registration removed.")
    if not arguments.purge_data:
        print("Runtime data was retained. Use --purge-data to remove it.")
    return 0


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Install or remove Codex Indicator")
    subparsers = parser.add_subparsers(dest="command")
    install_parser = subparsers.add_parser("install")
    install_parser.add_argument("--startup", action="store_true")
    install_parser.add_argument("--desktop", action="store_true")
    install_parser.add_argument("--no-config-backup", action="store_true")
    install_parser.add_argument("--install-dependencies", action="store_true")
    uninstall_parser = subparsers.add_parser("uninstall")
    uninstall_parser.add_argument("--purge-data", action="store_true")
    uninstall_parser.add_argument("--purge-config", action="store_true")
    command_line = sys.argv[1:] or ["install"]
    return parser.parse_args(command_line)


def main() -> int:
    if sys.platform != "win32":
        print(
            "install.py is the legacy Windows source installer; see README.md for macOS."
        )
        return 2
    arguments = parse_arguments()
    return (
        uninstall(arguments) if arguments.command == "uninstall" else install(arguments)
    )


if __name__ == "__main__":
    raise SystemExit(main())
