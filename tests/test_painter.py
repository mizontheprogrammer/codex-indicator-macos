from PySide6.QtGui import QColor, QImage, QPainter

from ui.painter import OverlayPainter


def test_conversation_loop_renders_as_an_open_knot() -> None:
    image = QImage(32, 32, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(0)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    OverlayPainter._draw_conversation_loop(
        painter,
        16,
        16,
        QColor("#4F7DE8"),
        phase=0.25,
    )
    painter.end()

    painted_pixels = sum(
        QColor.fromRgba(image.pixel(x, y)).alpha() > 0
        for y in range(image.height())
        for x in range(image.width())
    )
    assert painted_pixels > 40
    assert QColor.fromRgba(image.pixel(16, 16)).alpha() == 0
