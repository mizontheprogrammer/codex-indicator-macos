from utils.display import (
    DisplayGeometry,
    clamp_position,
    has_camera_notch,
    island_position,
    top_center_position,
)


def test_notched_display_uses_visible_frame_below_safe_area() -> None:
    visible = DisplayGeometry("Built-in", 0, 38, 1512, 944)
    assert top_center_position(visible, 300, 60) == (606, 44)


def test_non_notched_display_uses_menu_bar_visible_frame() -> None:
    visible = DisplayGeometry("Studio Display", 0, 25, 2560, 1415)
    assert top_center_position(visible, 300, 60) == (1130, 31)


def test_external_monitor_negative_coordinates_are_supported() -> None:
    visible = DisplayGeometry("External", -1920, 23, 1920, 1057)
    assert top_center_position(visible, 300, 60) == (-1110, 29)


def test_retina_geometry_remains_in_logical_points() -> None:
    visible = DisplayGeometry("Retina", 0, 38, 1512, 944)
    x, y = top_center_position(visible, 300, 60)
    assert (x, y) == (606, 44)
    assert x != 1212


def test_custom_position_restores_and_clamps_after_geometry_change() -> None:
    visible = DisplayGeometry("Built-in", 0, 38, 1512, 944)
    assert clamp_position(visible, 800, 300, 300, 200) == (800, 300)
    assert clamp_position(visible, 5000, -100, 300, 200) == (1212, 38)


def test_oversize_panel_is_clamped_to_display_origin() -> None:
    visible = DisplayGeometry("Removed fallback", 100, 50, 200, 100)
    assert clamp_position(visible, -500, 900, 400, 300) == (100, 50)


def test_notch_detection_uses_top_safe_inset() -> None:
    full = DisplayGeometry("Built-in", 0, 0, 1512, 982)
    notched = DisplayGeometry("Built-in", 0, 38, 1512, 944)
    ordinary = DisplayGeometry("External", 0, 25, 1512, 957)

    assert has_camera_notch(full, notched)
    assert not has_camera_notch(full, ordinary)


def test_island_attaches_to_full_display_top_center() -> None:
    full = DisplayGeometry("Built-in", 100, -20, 1512, 982)
    assert island_position(full, 176) == (768, -20)
