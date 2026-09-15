from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import utils.macos
from utils.notifications import DesktopNotifier
from utils.platform import (
    PlatformKind,
    application_data_directory,
    codex_log_paths,
    current_platform,
)
from utils.startup import LoginItemManager


def test_platform_detection() -> None:
    assert current_platform("darwin") is PlatformKind.MACOS
    assert current_platform("win32") is PlatformKind.WINDOWS
    assert current_platform("linux") is PlatformKind.OTHER


def test_macos_application_support_path() -> None:
    home = Path("/Users/example")
    assert application_data_directory(platform_name="darwin", home=home) == (
        home / "Library" / "Application Support" / "CodexIndicator"
    )


def test_macos_codex_log_globs_use_home() -> None:
    paths = codex_log_paths(home=Path("/Users/example"))
    assert paths == (
        "/Users/example/.codex/sessions/*/*/*/rollout-*.jsonl",
        "/Users/example/.codex/log/codex-tui.log",
        "/Users/example/.codex/logs/*.log",
        "/Users/example/.codex/log/*.log",
    )
    assert all("%USERPROFILE%" not in path for path in paths)


def test_indicator_import_does_not_load_windows_module_on_macos() -> None:
    command = (
        "import sys; import indicator; "
        "raise SystemExit(1 if 'utils.windows' in sys.modules else 0)"
    )
    result = subprocess.run(  # noqa: S603  # nosec B603
        [sys.executable, "-c", command],
        check=False,
        cwd=Path(__file__).resolve().parents[1],
    )
    assert result.returncode == 0


def test_launch_at_login_is_idempotent(tmp_path: Path) -> None:
    executable = tmp_path / "python"
    executable.write_text("", encoding="utf-8")
    manager = LoginItemManager(
        bundle_identifier="com.codexindicator.community",
        executable=executable,
        project_root=tmp_path,
        home=tmp_path,
        platform_name="darwin",
    )
    assert not manager.is_enabled()
    assert manager.set_enabled(True)
    assert manager.is_enabled()
    assert manager.set_enabled(True)
    assert manager.is_enabled()
    assert manager.set_enabled(False)
    assert not manager.is_enabled()


class _UnavailableTray:
    @staticmethod
    def supportsMessages() -> bool:
        return False

    @staticmethod
    def showMessage(*args: object) -> None:
        del args
        raise AssertionError("unsupported notifications must not be sent")


def test_notification_permission_fallback() -> None:
    notifier = DesktopNotifier(_UnavailableTray())
    assert not notifier.notify("Title", "Message", object(), 1000)


def test_reduce_motion_uses_mocked_macos_preference(monkeypatch) -> None:
    monkeypatch.setattr(
        utils.macos.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout="1\n"),
    )

    assert utils.macos.reduce_motion_enabled()
