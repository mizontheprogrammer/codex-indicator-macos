"""Build clean portable and installer releases with PyInstaller."""

from __future__ import annotations

import hashlib
import json
import runpy
import shutil

# The builder launches only a fixed PyInstaller argv without a command shell.
import subprocess  # nosec B404
import sys
import zipfile
from importlib.metadata import PackageNotFoundError, distribution
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RELEASE_ROOT = PROJECT_ROOT / "release"
BUILD_ROOT = PROJECT_ROOT / "work" / "release-build"
APP_NAME = "CodexIndicator"
SETUP_NAME = "CodexIndicatorSetup"
_METADATA = runpy.run_path(str(PROJECT_ROOT / "app_metadata.py"))
APP_VERSION = str(_METADATA["APP_VERSION"])
APP_VERSION_TUPLE = tuple(int(item) for item in _METADATA["APP_VERSION_TUPLE"])


def _safe_clean(path: Path) -> None:
    resolved = path.resolve()
    if resolved not in {
        RELEASE_ROOT.resolve(),
        BUILD_ROOT.resolve(),
    }:
        raise RuntimeError(f"Refusing to clean unexpected path: {resolved}")
    if resolved.exists():
        shutil.rmtree(resolved)
    resolved.mkdir(parents=True, exist_ok=True)


def _run_pyinstaller(
    script: Path,
    name: str,
    *,
    dist: Path,
    work: Path,
    extra: tuple[str, ...] = (),
) -> None:
    dist.mkdir(parents=True, exist_ok=True)
    work.mkdir(parents=True, exist_ok=True)
    (work / "spec").mkdir(parents=True, exist_ok=True)
    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onefile",
        "--windowed",
        "--name",
        name,
        "--distpath",
        str(dist),
        "--workpath",
        str(work),
        "--specpath",
        str(work / "spec"),
        "--icon",
        str(PROJECT_ROOT / "assets" / "codex_indicator.ico"),
        *extra,
        str(script),
    ]
    subprocess.run(command, cwd=PROJECT_ROOT, check=True)  # nosec B603


def _write_version_file(
    path: Path,
    *,
    description: str,
    original_filename: str,
) -> Path:
    """Write deterministic Windows version metadata for PyInstaller."""

    numeric_version = ", ".join(str(item) for item in APP_VERSION_TUPLE)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(
            (
                "VSVersionInfo(",
                "  ffi=FixedFileInfo(",
                f"    filevers=({numeric_version}),",
                f"    prodvers=({numeric_version}),",
                "    mask=0x3f,",
                "    flags=0x0,",
                "    OS=0x40004,",
                "    fileType=0x1,",
                "    subtype=0x0,",
                "    date=(0, 0),",
                "  ),",
                "  kids=[",
                "    StringFileInfo([",
                "      StringTable(",
                "        u'040904B0',",
                "        [",
                "          StringStruct(u'CompanyName', u'Codex Indicator Community'),",
                f"          StringStruct(u'FileDescription', u'{description}'),",
                f"          StringStruct(u'FileVersion', u'{APP_VERSION}.0'),",
                "          StringStruct(u'InternalName', u'CodexIndicator'),",
                f"          StringStruct(u'OriginalFilename', u'{original_filename}'),",
                "          StringStruct(u'ProductName', u'Codex Indicator'),",
                f"          StringStruct(u'ProductVersion', u'{APP_VERSION}'),",
                "          StringStruct(u'LegalCopyright', "
                "u'Copyright (c) 2026 Codex Indicator contributors'),",
                "        ],",
                "      ),",
                "    ]),",
                "    VarFileInfo([VarStruct(u'Translation', [1033, 1200])]),",
                "  ],",
                ")",
                "",
            )
        ),
        encoding="utf-8",
    )
    return path


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _copy_installed_license(
    distribution_name: str,
    filename: str,
    destination: Path,
) -> None:
    """Copy a license shipped by an installed build dependency."""

    try:
        package = distribution(distribution_name)
    except PackageNotFoundError as error:
        raise RuntimeError(
            f"{distribution_name} is required to build the release"
        ) from error

    candidates = [
        item
        for item in (package.files or ())
        if item.name.casefold() == filename.casefold()
        and ".dist-info" in item.as_posix()
    ]
    if not candidates:
        raise RuntimeError(f"Unable to locate {filename} for {distribution_name}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(package.locate_file(candidates[0]), destination)


def _prepare_legal_bundle() -> Path:
    """Stage notices that must accompany every binary distribution."""

    destination = BUILD_ROOT / "Legal"
    destination.mkdir(parents=True, exist_ok=True)
    shutil.copy2(PROJECT_ROOT / "LICENSE", destination / "LICENSE.txt")
    shutil.copy2(
        PROJECT_ROOT / "PRIVACY.md",
        destination / "PRIVACY.md",
    )
    shutil.copy2(
        PROJECT_ROOT / "THIRD_PARTY_NOTICES.md",
        destination / "THIRD_PARTY_NOTICES.md",
    )
    shutil.copytree(
        PROJECT_ROOT / "LICENSES",
        destination / "LICENSES",
        dirs_exist_ok=True,
    )
    _copy_installed_license(
        "pyinstaller",
        "COPYING.txt",
        destination / "LICENSES" / "PyInstaller-COPYING.txt",
    )
    return destination


def main() -> int:
    _safe_clean(RELEASE_ROOT)
    _safe_clean(BUILD_ROOT)
    legal_bundle = _prepare_legal_bundle()
    app_version_file = _write_version_file(
        BUILD_ROOT / "version" / "app-version.txt",
        description="Codex status, usage, and attention indicator",
        original_filename=f"{APP_NAME}.exe",
    )
    setup_version_file = _write_version_file(
        BUILD_ROOT / "version" / "setup-version.txt",
        description="Codex Indicator installer",
        original_filename=f"{SETUP_NAME}.exe",
    )

    app_dist = BUILD_ROOT / "app-dist"
    app_extra = [
        "--version-file",
        str(app_version_file),
        "--hidden-import",
        "win32timezone",
        "--add-data",
        f"{PROJECT_ROOT / 'assets' / 'codex_indicator.ico'};assets",
    ]
    notification_sound = PROJECT_ROOT / "assets" / "notification.mp3"
    if notification_sound.is_file():
        app_extra.extend(
            (
                "--add-data",
                f"{notification_sound};assets",
            )
        )
    _run_pyinstaller(
        PROJECT_ROOT / "indicator.py",
        APP_NAME,
        dist=app_dist,
        work=BUILD_ROOT / "app-work",
        extra=tuple(app_extra),
    )
    app_executable = app_dist / f"{APP_NAME}.exe"

    setup_dist = BUILD_ROOT / "setup-dist"
    _run_pyinstaller(
        PROJECT_ROOT / "packaging" / "setup_app.py",
        SETUP_NAME,
        dist=setup_dist,
        work=BUILD_ROOT / "setup-work",
        extra=(
            "--version-file",
            str(setup_version_file),
            "--add-data",
            f"{app_executable};.",
            "--add-data",
            f"{PROJECT_ROOT / 'assets' / 'codex_indicator.ico'};.",
            "--add-data",
            f"{legal_bundle};Legal",
            "--hidden-import",
            "win32timezone",
        ),
    )
    setup_executable = RELEASE_ROOT / f"{SETUP_NAME}.exe"
    shutil.copy2(setup_dist / f"{SETUP_NAME}.exe", setup_executable)
    # Keep the user-facing copy beside the source folder synchronized with the
    # canonical release artifact. This copy is gitignored and exists only as a
    # convenient local download/launch target.
    local_setup_executable = PROJECT_ROOT / f"{SETUP_NAME}.exe"
    shutil.copy2(setup_executable, local_setup_executable)

    portable_zip = RELEASE_ROOT / "CodexIndicator-Windows-x64.zip"
    with zipfile.ZipFile(
        portable_zip,
        "w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=9,
    ) as archive:
        archive.write(app_executable, app_executable.name)
        for path in sorted(item for item in legal_bundle.rglob("*") if item.is_file()):
            archive.write(
                path,
                (Path("Legal") / path.relative_to(legal_bundle)).as_posix(),
            )

    release_files = (
        setup_executable,
        portable_zip,
    )
    checksums = "\n".join(f"{_sha256(path)}  {path.name}" for path in release_files)
    (RELEASE_ROOT / "SHA256SUMS.txt").write_text(
        f"{checksums}\n",
        encoding="utf-8",
    )
    (RELEASE_ROOT / "release-manifest.json").write_text(
        json.dumps(
            {
                "application": "Codex Indicator",
                "version": APP_VERSION,
                "artifacts": {
                    path.name: {
                        "sha256": _sha256(path),
                        "size_bytes": path.stat().st_size,
                    }
                    for path in release_files
                },
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    print("Release ready:")
    for path in (
        *release_files,
        local_setup_executable,
        RELEASE_ROOT / "SHA256SUMS.txt",
        RELEASE_ROOT / "release-manifest.json",
    ):
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
