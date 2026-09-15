"""Build a self-contained, ad-hoc-signed macOS app and release archive."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import plistlib
import runpy
import shutil

# Fixed executable paths and argument lists only.
import subprocess  # nosec B404
import sys
import tempfile
from importlib.metadata import PackageNotFoundError, distribution
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RELEASE_ROOT = PROJECT_ROOT / "release" / "macos"
BUILD_ROOT = Path(tempfile.gettempdir()) / "codex-indicator-macos-release-build"
APP_BUNDLE = RELEASE_ROOT / "Codex Indicator.app"
APP_IDENTIFIER = "com.codexindicator.community"
MINIMUM_MACOS = "13.0"
_METADATA = runpy.run_path(str(PROJECT_ROOT / "app_metadata.py"))
APP_VERSION = str(_METADATA["APP_VERSION"])


def _safe_clean(path: Path) -> None:
    resolved = path.resolve()
    if resolved not in {RELEASE_ROOT.resolve(), BUILD_ROOT.resolve()}:
        raise RuntimeError(f"Refusing to clean unexpected path: {resolved}")
    if resolved.exists():
        shutil.rmtree(resolved)
    resolved.mkdir(parents=True, exist_ok=True)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _copy_pyinstaller_license(destination: Path) -> None:
    try:
        package = distribution("pyinstaller")
    except PackageNotFoundError as error:
        raise RuntimeError("PyInstaller is required to build the release") from error
    candidates = [
        item
        for item in (package.files or ())
        if item.name.casefold() == "copying.txt" and ".dist-info" in item.as_posix()
    ]
    if not candidates:
        raise RuntimeError("Unable to locate PyInstaller COPYING.txt")
    shutil.copy2(package.locate_file(candidates[0]), destination)


def _legal_bundle() -> Path:
    destination = BUILD_ROOT / "Legal"
    destination.mkdir(parents=True, exist_ok=True)
    shutil.copy2(PROJECT_ROOT / "LICENSE", destination / "LICENSE.txt")
    for name in ("PRIVACY.md", "THIRD_PARTY_NOTICES.md"):
        shutil.copy2(PROJECT_ROOT / name, destination / name)
    shutil.copytree(
        PROJECT_ROOT / "LICENSES",
        destination / "LICENSES",
        dirs_exist_ok=True,
    )
    _copy_pyinstaller_license(destination / "LICENSES" / "PyInstaller-COPYING.txt")
    return destination


def _architectures(executable: Path) -> tuple[str, ...]:
    result = subprocess.run(  # noqa: S603  # nosec B603
        ["/usr/bin/lipo", "-archs", str(executable)],
        capture_output=True,
        check=True,
        text=True,
    )
    return tuple(result.stdout.strip().split())


def _patch_info_plist(bundle: Path, architectures: tuple[str, ...]) -> None:
    path = bundle / "Contents" / "Info.plist"
    with path.open("rb") as stream:
        document = plistlib.load(stream)
    document.update(
        {
            "CFBundleDisplayName": "Codex Indicator",
            "CFBundleIdentifier": APP_IDENTIFIER,
            "CFBundleName": "Codex Indicator",
            "CFBundleShortVersionString": APP_VERSION,
            "CFBundleVersion": APP_VERSION,
            "LSMinimumSystemVersion": MINIMUM_MACOS,
            "LSUIElement": True,
            "NSHighResolutionCapable": True,
            "NSHumanReadableCopyright": (
                "Copyright © 2026 Codex Indicator contributors. "
                "Unofficial community project."
            ),
            "CodexIndicatorArchitectures": list(architectures),
        }
    )
    with path.open("wb") as stream:
        plistlib.dump(document, stream, sort_keys=True)


def _adhoc_sign(bundle: Path) -> None:
    """Create a locally launchable development bundle without claiming identity."""

    forbidden_attributes = (
        "com.apple.FinderInfo",
        "com.apple.ResourceFork",
        "com.apple.fileprovider.fpfs#P",
    )
    for root, directories, files in os.walk(bundle):
        for candidate in (
            Path(root),
            *(Path(root) / item for item in directories + files),
        ):
            for attribute in forbidden_attributes:
                try:
                    os.removexattr(candidate, attribute, follow_symlinks=False)
                except (OSError, AttributeError):
                    pass
    signing_error = ""
    # File-provider volumes can restore Finder metadata immediately after a
    # recursive copy. Retry the strip/sign pair as one tight operation.
    for _ in range(3):
        subprocess.run(  # noqa: S603  # nosec B603
            ["/usr/bin/xattr", "-cr", str(bundle)],
            check=True,
        )
        result = subprocess.run(  # noqa: S603  # nosec B603
            ["/usr/bin/codesign", "--force", "--deep", "--sign", "-", str(bundle)],
            capture_output=True,
            check=False,
            text=True,
        )
        if result.returncode == 0:
            break
        signing_error = result.stderr.strip() or result.stdout.strip()
    else:
        raise RuntimeError(f"Unable to ad-hoc sign development bundle: {signing_error}")
    subprocess.run(  # noqa: S603  # nosec B603
        ["/usr/bin/codesign", "--verify", "--deep", "--strict", str(bundle)],
        check=True,
    )


def main() -> int:
    if sys.platform != "darwin":
        raise RuntimeError("The macOS release builder must run on macOS")
    _safe_clean(RELEASE_ROOT)
    _safe_clean(BUILD_ROOT)
    generator = runpy.run_path(
        str(PROJECT_ROOT / "packaging" / "generate_macos_assets.py")
    )
    _, icon = generator["generate"]()
    legal = _legal_bundle()
    detected = platform.machine().casefold()
    target = "arm64" if detected in {"arm64", "aarch64"} else "x86_64"
    dist = BUILD_ROOT / "dist"
    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--windowed",
        "--name",
        "Codex Indicator",
        "--osx-bundle-identifier",
        APP_IDENTIFIER,
        "--target-architecture",
        target,
        "--icon",
        str(icon),
        "--add-data",
        f"{PROJECT_ROOT / 'assets'}:assets",
        "--add-data",
        f"{legal}:Legal",
        "--distpath",
        str(dist),
        "--workpath",
        str(BUILD_ROOT / "work"),
        "--specpath",
        str(BUILD_ROOT / "spec"),
        str(PROJECT_ROOT / "indicator.py"),
    ]
    subprocess.run(command, cwd=PROJECT_ROOT, check=True)  # noqa: S603  # nosec B603
    built_bundle = dist / "Codex Indicator.app"
    executable = built_bundle / "Contents" / "MacOS" / "Codex Indicator"
    architectures = _architectures(executable)
    _patch_info_plist(built_bundle, architectures)
    _adhoc_sign(built_bundle)
    shutil.copytree(built_bundle, APP_BUNDLE, symlinks=True)

    architecture_label = (
        "universal2"
        if set(architectures) == {"arm64", "x86_64"}
        else "-".join(architectures)
    )
    archive = RELEASE_ROOT / f"CodexIndicator-macOS-{architecture_label}.zip"
    subprocess.run(  # noqa: S603  # nosec B603
        [
            "/usr/bin/ditto",
            "--norsrc",
            "-c",
            "-k",
            "--keepParent",
            str(built_bundle),
            str(archive),
        ],
        check=True,
    )
    checksums = RELEASE_ROOT / "SHA256SUMS.txt"
    checksums.write_text(f"{_sha256(archive)}  {archive.name}\n", encoding="utf-8")
    manifest = RELEASE_ROOT / "release-manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "application": "Codex Indicator",
                "bundle_identifier": APP_IDENTIFIER,
                "version": APP_VERSION,
                "minimum_macos": MINIMUM_MACOS,
                "architectures": architectures,
                "artifact": {
                    "name": archive.name,
                    "sha256": _sha256(archive),
                    "size_bytes": archive.stat().st_size,
                },
                "developer_id_signed": False,
                "signature": "ad-hoc development signature",
                "notarized": False,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    for output in (APP_BUNDLE, archive, checksums, manifest):
        print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
