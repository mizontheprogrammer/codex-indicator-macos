from __future__ import annotations

import plistlib
import runpy
from pathlib import Path


def test_macos_packaging_metadata(tmp_path: Path) -> None:
    project = Path(__file__).resolve().parents[1]
    module = runpy.run_path(str(project / "packaging" / "build_macos.py"))
    bundle = tmp_path / "Codex Indicator.app"
    contents = bundle / "Contents"
    contents.mkdir(parents=True)
    plist = contents / "Info.plist"
    with plist.open("wb") as stream:
        plistlib.dump({"CFBundleExecutable": "Codex Indicator"}, stream)

    module["_patch_info_plist"](bundle, ("arm64",))

    with plist.open("rb") as stream:
        metadata = plistlib.load(stream)
    assert metadata["CFBundleIdentifier"] == "com.codexindicator.community"
    assert metadata["CFBundleDisplayName"] == "Codex Indicator"
    assert metadata["LSUIElement"] is True
    assert metadata["NSHighResolutionCapable"] is True
    assert metadata["LSMinimumSystemVersion"] == "13.0"
    assert metadata["CodexIndicatorArchitectures"] == ["arm64"]
