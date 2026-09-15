import importlib.util
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "codex_indicator_setup_app",
    PROJECT_ROOT / "packaging" / "setup_app.py",
)
assert SPEC is not None and SPEC.loader is not None
setup_app = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(setup_app)


class FakeProcess:
    def __init__(self, pid: int, executable: Path) -> None:
        self.pid = pid
        self.info = {"pid": pid, "exe": str(executable)}
        self.terminated = False
        self.killed = False

    def terminate(self) -> None:
        self.terminated = True

    def kill(self) -> None:
        self.killed = True


def test_stop_running_app_targets_only_installed_path(
    tmp_path: Path,
    monkeypatch,
) -> None:
    installed = tmp_path / "installed" / "CodexIndicator.exe"
    other = tmp_path / "portable" / "CodexIndicator.exe"
    installed_process = FakeProcess(100, installed)
    other_process = FakeProcess(200, other)

    monkeypatch.setattr(setup_app.os, "getpid", lambda: 999)
    monkeypatch.setattr(
        setup_app.psutil,
        "process_iter",
        lambda attributes: (installed_process, other_process),
    )
    monkeypatch.setattr(
        setup_app.psutil,
        "wait_procs",
        lambda processes, timeout: (list(processes), []),
    )

    setup_app._stop_running_app(installed)

    assert installed_process.terminated
    assert not other_process.terminated


class FakeRegistryKey:
    def __enter__(self):
        return self

    def __exit__(self, exception_type, exception, traceback) -> None:
        return None


def test_uninstall_registration_uses_app_icon(
    tmp_path: Path,
    monkeypatch,
) -> None:
    install_directory = tmp_path / "CodexIndicator"
    install_directory.mkdir()
    executable = install_directory / "CodexIndicator.exe"
    uninstaller = install_directory / "Uninstall Codex Indicator.exe"
    icon = install_directory / setup_app.APP_ICON_NAME
    executable.write_bytes(b"app")
    uninstaller.write_bytes(b"uninstaller")
    icon.write_bytes(b"icon")
    values: dict[str, object] = {}

    monkeypatch.setattr(
        setup_app.winreg,
        "CreateKey",
        lambda hive, path: FakeRegistryKey(),
    )
    monkeypatch.setattr(
        setup_app.winreg,
        "SetValueEx",
        lambda key, name, reserved, value_type, value: values.__setitem__(
            name,
            value,
        ),
    )

    setup_app._register_uninstaller(
        install_directory,
        executable,
        uninstaller,
        icon,
    )

    assert values["DisplayName"] == setup_app.APP_NAME
    assert values["DisplayVersion"] == setup_app.APP_VERSION
    assert values["DisplayIcon"] == f"{icon},0"
    assert values["UninstallString"] == f'"{uninstaller}" --uninstall'


def test_installed_icon_name_is_versioned() -> None:
    assert setup_app.APP_VERSION in setup_app.APP_ICON_NAME
