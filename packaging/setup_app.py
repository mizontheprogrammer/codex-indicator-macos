"""Windowed installer and uninstaller for packaged Codex Indicator releases."""

from __future__ import annotations

import ctypes
import os
import shutil

# Installer launches use absolute local executable paths and never use a shell.
import subprocess  # nosec B404
import sys
import time
import uuid
from pathlib import Path

import psutil

if sys.platform == "win32":
    import winreg

    import win32com.client as win32com_client
else:

    class _UnavailableWinReg:
        HKEY_CURRENT_USER = 0
        REG_SZ = 1
        REG_DWORD = 4

        @staticmethod
        def _unavailable(*args: object, **kwargs: object) -> object:
            del args, kwargs
            raise OSError("Windows registry APIs are unavailable")

        CreateKey = OpenKey = SetValueEx = DeleteValue = DeleteKey = _unavailable

    class _UnavailableWin32ComClient:
        Dispatch = staticmethod(_UnavailableWinReg._unavailable)

    winreg = _UnavailableWinReg()
    win32com_client = _UnavailableWin32ComClient()

from app_metadata import APP_VERSION

APP_NAME = "Codex Indicator"
APP_EXECUTABLE = "CodexIndicator.exe"
APP_ICON_NAME = f"CodexIndicator-{APP_VERSION}.ico"
BUNDLED_ICON_NAME = "codex_indicator.ico"
STARTUP_VALUE_NAME = "CodexIndicator"
UNINSTALL_KEY_PATH = (
    r"Software\Microsoft\Windows\CurrentVersion\Uninstall\CodexIndicator"
)
MB_ICONINFORMATION = 0x40
MB_ICONERROR = 0x10
MB_YESNO = 0x04
IDYES = 6


def _message(text: str, *, error: bool = False, yes_no: bool = False) -> int:
    flags = MB_ICONERROR if error else MB_ICONINFORMATION
    if yes_no:
        flags |= MB_YESNO
    return int(ctypes.windll.user32.MessageBoxW(None, text, APP_NAME, flags))


def _local_app_data() -> Path:
    value = os.environ.get("LOCALAPPDATA")
    if not value:
        raise RuntimeError("LOCALAPPDATA is unavailable")
    return Path(value)


def _install_directory() -> Path:
    return _local_app_data() / "Programs" / "CodexIndicator"


def _data_directory() -> Path:
    return _local_app_data() / "CodexIndicator"


def _bundle_directory() -> Path:
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))


def _bundled_app() -> Path:
    return _bundle_directory() / APP_EXECUTABLE


def _install_icon(install_directory: Path) -> Path:
    source = _bundle_directory() / BUNDLED_ICON_NAME
    if not source.is_file():
        raise FileNotFoundError("Bundled application icon is missing")
    destination = install_directory / APP_ICON_NAME
    shutil.copy2(source, destination)
    return destination


def _install_legal_files(install_directory: Path) -> None:
    source = _bundle_directory() / "Legal"
    if not source.is_dir():
        raise FileNotFoundError("Bundled legal notices are missing")
    destination = install_directory / "Legal"
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(source, destination)


def _same_executable(left: str | Path, right: str | Path) -> bool:
    try:
        left_path = os.path.normcase(os.path.abspath(os.fspath(left)))
        right_path = os.path.normcase(os.path.abspath(os.fspath(right)))
    except (OSError, TypeError, ValueError):
        return False
    return left_path == right_path


def _stop_running_app(executable: Path) -> None:
    """Stop only processes launched from the installed application path."""

    matches: list[psutil.Process] = []
    for process in psutil.process_iter(("pid", "exe")):
        if process.pid == os.getpid():
            continue
        try:
            process_executable = process.info.get("exe")
            if process_executable and _same_executable(
                process_executable,
                executable,
            ):
                matches.append(process)
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            continue

    for process in matches:
        try:
            process.terminate()
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            continue

    _, alive = psutil.wait_procs(matches, timeout=5.0)
    for process in alive:
        try:
            process.kill()
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            continue
    _, alive = psutil.wait_procs(alive, timeout=3.0)
    if alive:
        raise PermissionError(
            "Close Codex Indicator from its tray menu and run the installer again."
        )


def _shortcut(
    path: Path,
    target: Path,
    *,
    arguments: str = "",
    icon: Path | None = None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # Recreating an existing .lnk in place can preserve Windows link-tracking
    # metadata from an older installation and silently resolve to a stale path.
    path.unlink(missing_ok=True)
    shell = win32com_client.Dispatch("WScript.Shell")
    shortcut = shell.CreateShortCut(str(path))
    shortcut.Targetpath = str(target)
    shortcut.Arguments = arguments
    shortcut.WorkingDirectory = str(target.parent)
    shortcut.Description = APP_NAME
    shortcut.IconLocation = f"{icon or target},0"
    shortcut.save()


def _shortcut_paths() -> tuple[Path | None, Path, Path]:
    shell = win32com_client.Dispatch("WScript.Shell")
    desktop_value = str(shell.SpecialFolders("Desktop") or "").strip()
    desktop = Path(desktop_value) if desktop_value else None
    programs = (
        Path(os.environ["APPDATA"])
        / "Microsoft"
        / "Windows"
        / "Start Menu"
        / "Programs"
        / APP_NAME
    )
    return (
        desktop / f"{APP_NAME}.lnk" if desktop is not None else None,
        programs / f"{APP_NAME}.lnk",
        programs / f"Uninstall {APP_NAME}.lnk",
    )


def _set_startup(executable: Path | None) -> None:
    key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path) as key:
        if executable is not None:
            winreg.SetValueEx(
                key,
                STARTUP_VALUE_NAME,
                0,
                winreg.REG_SZ,
                f'"{executable}"',
            )
        else:
            try:
                winreg.DeleteValue(key, STARTUP_VALUE_NAME)
            except FileNotFoundError:
                pass


def _estimated_size_kib(directory: Path) -> int:
    """Return a bounded installed-size estimate for Windows Apps settings."""

    total = 0
    for path in directory.rglob("*"):
        try:
            if path.is_file():
                total += path.stat().st_size
        except OSError:
            continue
    return max(1, min(0xFFFFFFFF, (total + 1023) // 1024))


def _register_uninstaller(
    install_directory: Path,
    executable: Path,
    uninstaller: Path,
    icon: Path,
) -> None:
    """Register the per-user app with Control Panel and Windows Settings."""

    string_values = {
        "DisplayName": APP_NAME,
        "DisplayVersion": APP_VERSION,
        "Publisher": "Codex Indicator Community",
        "InstallLocation": str(install_directory),
        "DisplayIcon": f"{icon},0",
        "UninstallString": f'"{uninstaller}" --uninstall',
        "URLInfoAbout": "https://github.com/mizontheprogrammer/codex-indicator",
    }
    dword_values = {
        "EstimatedSize": _estimated_size_kib(install_directory),
        "NoModify": 1,
        "NoRepair": 1,
    }
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY_PATH) as key:
        for name, value in string_values.items():
            winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)
        for name, value in dword_values.items():
            winreg.SetValueEx(key, name, 0, winreg.REG_DWORD, value)


def _remove_uninstall_registration() -> None:
    try:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY_PATH)
    except FileNotFoundError:
        pass


def install() -> int:
    try:
        source = _bundled_app()
        if not source.is_file():
            raise FileNotFoundError(f"Bundled application is missing: {source}")
        install_directory = _install_directory()
        install_directory.mkdir(parents=True, exist_ok=True)
        destination = install_directory / APP_EXECUTABLE
        _stop_running_app(destination)
        temporary = install_directory / f".{APP_EXECUTABLE}.{uuid.uuid4().hex}.tmp"
        shutil.copy2(source, temporary)
        os.replace(temporary, destination)
        _install_legal_files(install_directory)
        icon = _install_icon(install_directory)

        uninstaller = install_directory / "Uninstall Codex Indicator.exe"
        if Path(sys.executable).resolve() != uninstaller.resolve():
            shutil.copy2(sys.executable, uninstaller)
        _register_uninstaller(install_directory, destination, uninstaller, icon)

        desktop, start_menu, uninstall_shortcut = _shortcut_paths()
        if desktop is not None:
            _shortcut(desktop, destination, icon=icon)
        _shortcut(start_menu, destination, icon=icon)
        _shortcut(
            uninstall_shortcut,
            uninstaller,
            arguments="--uninstall",
            icon=icon,
        )
        _set_startup(destination)
        _data_directory().mkdir(parents=True, exist_ok=True)

        subprocess.Popen(  # nosec B603
            [str(destination)],
            cwd=install_directory,
            creationflags=(
                subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
            ),
            close_fds=True,
        )
        _message(
            "Codex Indicator is installed and running.\n\n"
            "It will start automatically with Windows and remain in the tray."
        )
        return 0
    except (OSError, RuntimeError) as error:
        _message(f"Installation failed:\n\n{error}", error=True)
        return 1


def begin_uninstall() -> int:
    purge_data = (
        _message(
            "Remove saved settings, logs, and session data too?\n\n"
            "Choose No to keep your preferences.",
            yes_no=True,
        )
        == IDYES
    )
    temporary = Path(os.environ.get("TEMP", _local_app_data())) / (
        f"CodexIndicatorUninstall-{uuid.uuid4().hex}.exe"
    )
    try:
        shutil.copy2(sys.executable, temporary)
        subprocess.Popen(  # nosec B603
            [
                str(temporary),
                "--finish-uninstall",
                str(_install_directory()),
                "1" if purge_data else "0",
            ],
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
            close_fds=True,
        )
        return 0
    except OSError as error:
        _message(f"Unable to start uninstall:\n\n{error}", error=True)
        return 1


def finish_uninstall(target: Path, purge_data: bool) -> int:
    expected = _install_directory().resolve()
    if target.resolve() != expected:
        _message("Uninstall target validation failed.", error=True)
        return 1
    time.sleep(1.0)
    try:
        _set_startup(None)
        for shortcut in _shortcut_paths():
            if shortcut is not None:
                shortcut.unlink(missing_ok=True)
        shutil.rmtree(expected, ignore_errors=False)
        _remove_uninstall_registration()
        if purge_data:
            shutil.rmtree(_data_directory(), ignore_errors=True)
        ctypes.windll.kernel32.MoveFileExW(
            str(Path(sys.executable)),
            None,
            0x4,
        )
        _message("Codex Indicator was removed successfully.")
        return 0
    except OSError as error:
        _message(f"Uninstall failed:\n\n{error}", error=True)
        return 1


def main() -> int:
    arguments = sys.argv[1:]
    if arguments[:1] == ["--uninstall"]:
        return begin_uninstall()
    if len(arguments) == 3 and arguments[0] == "--finish-uninstall":
        return finish_uninstall(Path(arguments[1]), arguments[2] == "1")
    return install()


if __name__ == "__main__":
    raise SystemExit(main())
