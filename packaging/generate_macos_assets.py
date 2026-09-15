"""Generate deterministic macOS assets from the repository's existing logo."""

from __future__ import annotations

# Fixed Apple tool path and argument list only.
import subprocess  # nosec B404
import tempfile
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QImage

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ASSETS = PROJECT_ROOT / "assets"
SOURCE = ASSETS / "codex_indicator_logo.png"
TEMPLATE = ASSETS / "CodexIndicatorTemplate.png"
ICNS = ASSETS / "CodexIndicator.icns"


def _template_image(source: QImage) -> QImage:
    image = source.convertToFormat(QImage.Format.Format_ARGB32)
    result = QImage(image.size(), QImage.Format.Format_ARGB32)
    result.fill(Qt.GlobalColor.transparent)
    for y in range(image.height()):
        for x in range(image.width()):
            color = QColor.fromRgba(image.pixel(x, y))
            bright_mark = min(color.red(), color.green(), color.blue()) >= 150
            orange_mark = (
                color.red() >= 150
                and color.red() > color.green() * 1.35
                and color.green() > color.blue() * 1.15
            )
            if bright_mark or orange_mark:
                result.setPixelColor(x, y, QColor(255, 255, 255, color.alpha()))
    return result


def generate() -> tuple[Path, Path]:
    source = QImage(str(SOURCE))
    if source.isNull():
        raise RuntimeError(f"Unable to read source logo: {SOURCE}")
    template = _template_image(source).scaled(
        64,
        64,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )
    if not template.save(str(TEMPLATE), "PNG"):
        raise RuntimeError(f"Unable to write menu-bar template: {TEMPLATE}")

    icon_sizes = (
        (16, "16x16"),
        (32, "16x16@2x"),
        (32, "32x32"),
        (64, "32x32@2x"),
        (128, "128x128"),
        (256, "128x128@2x"),
        (256, "256x256"),
        (512, "256x256@2x"),
        (512, "512x512"),
        (1024, "512x512@2x"),
    )
    with tempfile.TemporaryDirectory(prefix="CodexIndicatorIcon-") as temporary:
        iconset = Path(temporary) / "CodexIndicator.iconset"
        iconset.mkdir()
        for pixels, label in icon_sizes:
            destination = iconset / f"icon_{label}.png"
            scaled = source.scaled(
                pixels,
                pixels,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            if not scaled.save(str(destination), "PNG"):
                raise RuntimeError(f"Unable to write icon layer: {destination}")
        iconutil = Path("/usr/bin/iconutil")
        if not iconutil.is_file():
            raise RuntimeError("iconutil is required to generate the ICNS asset")
        subprocess.run(  # noqa: S603  # nosec B603
            [iconutil, "-c", "icns", str(iconset), "-o", str(ICNS)],
            check=True,
        )
    return TEMPLATE, ICNS


if __name__ == "__main__":
    for output in generate():
        print(output)
