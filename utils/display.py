"""Logical-screen positioning helpers shared by Qt and unit tests."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DisplayGeometry:
    name: str
    x: int
    y: int
    width: int
    height: int

    @property
    def right(self) -> int:
        return self.x + self.width

    @property
    def bottom(self) -> int:
        return self.y + self.height


def top_center_position(
    display: DisplayGeometry,
    overlay_width: int,
    overlay_height: int,
    *,
    safe_gap: int = 6,
) -> tuple[int, int]:
    """Place an overlay below the display's menu-bar/notch safe area."""

    width = max(1, min(overlay_width, display.width))
    height = max(1, min(overlay_height, display.height))
    x = display.x + (display.width - width) // 2
    y = min(display.bottom - height, display.y + max(0, safe_gap))
    return x, y


def clamp_position(
    display: DisplayGeometry,
    x: int,
    y: int,
    overlay_width: int,
    overlay_height: int,
) -> tuple[int, int]:
    """Clamp logical coordinates into a display's visible frame."""

    max_x = max(display.x, display.right - max(1, overlay_width))
    max_y = max(display.y, display.bottom - max(1, overlay_height))
    return (
        min(max(x, display.x), max_x),
        min(max(y, display.y), max_y),
    )


__all__ = ["DisplayGeometry", "clamp_position", "top_center_position"]
