import json
from pathlib import Path

from models.config import AppConfig, load_config


def test_invalid_values_fall_back_independently() -> None:
    config = AppConfig.from_mapping(
        {
            "poll_interval_ms": -10,
            "display_mode": "invisible-ish",
            "low_opacity": 0,
            "theme": {"opacity": 9, "width": "bad"},
            "sounds": {"enabled": "false"},
        }
    )
    assert config.poll_interval_ms == 100
    assert config.theme.opacity == 1.0
    assert config.theme.width == AppConfig().theme.width
    assert config.display_mode == "normal"
    assert config.low_opacity == 0.05
    assert config.sounds.enabled is False


def test_invalid_config_is_backed_up(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text("{broken", encoding="utf-8")
    result = load_config(path)
    assert result.used_defaults
    assert result.backup_path is not None
    assert result.backup_path.exists()


def test_default_config_file_matches_schema() -> None:
    project = Path(__file__).resolve().parents[1]
    raw = json.loads((project / "config.example.json").read_text(encoding="utf-8"))
    config = AppConfig.from_mapping(raw)
    assert config.schema_version == AppConfig.CURRENT_SCHEMA_VERSION
    assert config.working_labels
    assert config.auto_hide_enabled is False
    assert config.animations.enabled is True
    assert config.animations.respect_reduce_motion is True
    assert config.display_mode == "normal"
    assert config.low_opacity == 0.15
    assert config.colors.working == "#4F7DE8"


def test_legacy_orange_working_color_migrates_to_blue(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "colors": {"working": "#C96D45"},
            }
        ),
        encoding="utf-8",
    )

    result = load_config(path)

    assert result.migrated
    assert result.config.schema_version == AppConfig.CURRENT_SCHEMA_VERSION
    assert result.config.colors.working == "#4F7DE8"


def test_windows_config_migrates_without_losing_known_values(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "display_mode": "low_opacity",
                "low_opacity": 0.10,
                "position": {"x": 410, "y": 82, "screen_name": "DISPLAY1"},
                "theme": {"width": 412, "opacity": 0.77},
                "sounds": {"enabled": False},
            }
        ),
        encoding="utf-8",
    )
    result = load_config(path)
    assert result.migrated
    assert result.config.schema_version == 3
    assert result.config.display_mode == "low_opacity"
    assert result.config.low_opacity == 0.10
    assert result.config.position.x == 410
    assert result.config.position.mode == "custom"
    assert result.config.position.screen_name == "DISPLAY1"
    assert result.config.theme.width == 412
    assert result.config.theme.opacity == 0.77
    assert result.config.sounds.enabled is False
