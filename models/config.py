"""Typed, validated configuration for Codex Indicator."""

from __future__ import annotations

import json
import logging
import math
import os
import re
import shutil
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from utils.platform import codex_log_paths

LOGGER = logging.getLogger(__name__)

_HEX_COLOR = re.compile(r"^#[0-9a-fA-F]{6}([0-9a-fA-F]{2})?$")
DEFAULT_WORKING_COLOR = "#4F7DE8"
LEGACY_WORKING_COLOR = "#C96D45"
DEFAULT_HIDE_ON_PROCESSES = (
    "Code.exe",
    "Cursor.exe",
    "WindowsTerminal.exe",
    "powershell.exe",
    "pwsh.exe",
    "cmd.exe",
    "codex.exe",
)

DEFAULT_WORKING_LABELS = (
    "Thinking...",
    "Reasoning...",
    "Planning...",
    "Searching...",
    "Reading Files...",
    "Writing Code...",
    "Editing...",
    "Refactoring...",
    "Debugging...",
    "Running Tests...",
    "Generating...",
    "Analyzing...",
    "Optimizing...",
)


def _mapping(value: object) -> Mapping[str, Any]:
    """Return a string-keyed mapping view or an empty mapping."""

    if isinstance(value, Mapping):
        return {str(key): item for key, item in value.items()}
    return {}


def _boolean(value: object, default: bool) -> bool:
    """Parse JSON-like boolean values without Python truthiness surprises."""

    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().casefold()
        if normalized in {"true", "yes", "on", "1"}:
            return True
        if normalized in {"false", "no", "off", "0"}:
            return False
    if isinstance(value, int) and value in {0, 1}:
        return bool(value)
    return default


def _integer(value: object, default: int, minimum: int, maximum: int) -> int:
    """Parse and clamp an integer setting."""

    if isinstance(value, bool):
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError, OverflowError):
        return default
    return max(minimum, min(maximum, parsed))


def _number(
    value: object,
    default: float,
    minimum: float,
    maximum: float,
) -> float:
    """Parse and clamp a finite floating-point setting."""

    if isinstance(value, bool):
        return default
    try:
        parsed = float(value)
    except (TypeError, ValueError, OverflowError):
        return default
    if not math.isfinite(parsed):
        return default
    return max(minimum, min(maximum, parsed))


def _text(value: object, default: str, maximum: int) -> str:
    """Normalize optional bounded configuration text."""

    if value is None:
        return default
    normalized = str(value).replace("\x00", "").strip()
    return normalized[:maximum] if normalized else default


def _choice(value: object, default: str, allowed: set[str]) -> str:
    """Normalize a string choice against a fixed set."""

    normalized = str(value or "").strip().casefold()
    return normalized if normalized in allowed else default


def _color(value: object, default: str) -> str:
    """Return a normalized RGB/RGBA hex color."""

    candidate = str(value or "").strip()
    return candidate.upper() if _HEX_COLOR.fullmatch(candidate) else default


def _string_tuple(
    value: object,
    default: tuple[str, ...],
    *,
    maximum_items: int = 128,
    maximum_length: int = 1_024,
) -> tuple[str, ...]:
    """Normalize a string sequence while preserving order and uniqueness."""

    if isinstance(value, str) or not isinstance(value, Sequence):
        return default

    result: list[str] = []
    seen: set[str] = set()
    for item in value:
        normalized = str(item or "").replace("\x00", "").strip()[:maximum_length]
        identity = normalized.casefold()
        if normalized and identity not in seen:
            result.append(normalized)
            seen.add(identity)
        if len(result) >= maximum_items:
            break
    return tuple(result) if result else default


def _relative_or_expanded_path(value: object, default: str) -> str:
    """Normalize a configurable path without requiring it to exist."""

    text = _text(value, default, 32_767)
    return os.path.expandvars(os.path.expanduser(text))


@dataclass(frozen=True, slots=True)
class OverlayPosition:
    """Saved logical overlay position and display identity."""

    x: int | None = None
    y: int | None = None
    screen_name: str = ""
    mode: str = "automatic"

    @classmethod
    def from_mapping(cls, source: object) -> OverlayPosition:
        data = _mapping(source)
        x_value = data.get("x")
        y_value = data.get("y")

        def optional_coordinate(value: object) -> int | None:
            if value is None or isinstance(value, bool):
                return None
            try:
                parsed = int(value)
            except (TypeError, ValueError, OverflowError):
                return None
            return max(-100_000, min(100_000, parsed))

        x = optional_coordinate(x_value)
        y = optional_coordinate(y_value)
        inferred_mode = "custom" if x is not None and y is not None else "automatic"
        return cls(
            x=x,
            y=y,
            screen_name=_text(data.get("screen_name"), "", 256),
            mode=_choice(
                data.get("mode"),
                inferred_mode,
                {"automatic", "custom"},
            ),
        )


@dataclass(frozen=True, slots=True)
class ColorSettings:
    """State and surface colors in RGB or RGBA notation."""

    ready: str = "#2FAF72"
    working: str = DEFAULT_WORKING_COLOR
    needs_you: str = "#D89B16"
    background: str = "#FCFBF8FA"
    border: str = "#D8D3CB"
    primary_text: str = "#24211E"
    secondary_text: str = "#77716A"
    shadow: str = "#19120C2E"

    @classmethod
    def from_mapping(cls, source: object) -> ColorSettings:
        data = _mapping(source)
        defaults = cls()
        working = _color(data.get("working"), defaults.working)
        if working == LEGACY_WORKING_COLOR:
            working = defaults.working
        return cls(
            ready=_color(data.get("ready"), defaults.ready),
            working=working,
            needs_you=_color(data.get("needs_you"), defaults.needs_you),
            background=_color(data.get("background"), defaults.background),
            border=_color(data.get("border"), defaults.border),
            primary_text=_color(
                data.get("primary_text"),
                defaults.primary_text,
            ),
            secondary_text=_color(
                data.get("secondary_text"),
                defaults.secondary_text,
            ),
            shadow=_color(data.get("shadow"), defaults.shadow),
        )


@dataclass(frozen=True, slots=True)
class ThemeSettings:
    """Validated visual dimensions and optional material preferences."""

    name: str = "porcelain"
    opacity: float = 0.98
    use_acrylic: bool = False
    width: int = 300
    height: int = 48
    row_height: int = 48
    corner_radius: int = 24
    outer_padding: int = 4
    row_spacing: int = 3
    font_family: str = "Segoe UI Variable Text"

    @classmethod
    def from_mapping(cls, source: object) -> ThemeSettings:
        data = _mapping(source)
        defaults = cls()
        return cls(
            name=_text(data.get("name"), defaults.name, 64),
            opacity=_number(data.get("opacity"), defaults.opacity, 0.25, 1.0),
            use_acrylic=_boolean(
                data.get("use_acrylic"),
                defaults.use_acrylic,
            ),
            width=_integer(data.get("width"), defaults.width, 220, 720),
            height=_integer(data.get("height"), defaults.height, 40, 128),
            row_height=_integer(
                data.get("row_height"),
                defaults.row_height,
                36,
                128,
            ),
            corner_radius=_integer(
                data.get("corner_radius"),
                defaults.corner_radius,
                0,
                40,
            ),
            outer_padding=_integer(
                data.get("outer_padding"),
                defaults.outer_padding,
                4,
                40,
            ),
            row_spacing=_integer(
                data.get("row_spacing"),
                defaults.row_spacing,
                0,
                24,
            ),
            font_family=_text(
                data.get("font_family"),
                defaults.font_family,
                256,
            ),
        )


@dataclass(frozen=True, slots=True)
class AnimationSettings:
    """Animation switches and durations in milliseconds."""

    enabled: bool = True
    respect_reduce_motion: bool = True
    fade_duration_ms: int = 180
    layout_duration_ms: int = 220
    spark_period_ms: int = 1_100
    pulse_period_ms: int = 1_400
    position_save_debounce_ms: int = 450

    @classmethod
    def from_mapping(cls, source: object) -> AnimationSettings:
        data = _mapping(source)
        defaults = cls()
        return cls(
            enabled=_boolean(data.get("enabled"), defaults.enabled),
            respect_reduce_motion=_boolean(
                data.get("respect_reduce_motion"),
                defaults.respect_reduce_motion,
            ),
            fade_duration_ms=_integer(
                data.get("fade_duration_ms"),
                defaults.fade_duration_ms,
                0,
                2_000,
            ),
            layout_duration_ms=_integer(
                data.get("layout_duration_ms"),
                defaults.layout_duration_ms,
                0,
                2_000,
            ),
            spark_period_ms=_integer(
                data.get("spark_period_ms"),
                defaults.spark_period_ms,
                250,
                10_000,
            ),
            pulse_period_ms=_integer(
                data.get("pulse_period_ms"),
                defaults.pulse_period_ms,
                250,
                10_000,
            ),
            position_save_debounce_ms=_integer(
                data.get("position_save_debounce_ms"),
                defaults.position_save_debounce_ms,
                100,
                5_000,
            ),
        )


@dataclass(frozen=True, slots=True)
class SoundSettings:
    """Cross-platform attention notification-sound behavior."""

    enabled: bool = True
    alias: str = "SystemExclamation"
    minimum_interval_seconds: float = 3.0

    @classmethod
    def from_mapping(cls, source: object) -> SoundSettings:
        data = _mapping(source)
        defaults = cls()
        return cls(
            enabled=_boolean(data.get("enabled"), defaults.enabled),
            alias=_text(data.get("alias"), defaults.alias, 128),
            minimum_interval_seconds=_number(
                data.get("minimum_interval_seconds"),
                defaults.minimum_interval_seconds,
                0.0,
                3_600.0,
            ),
        )


@dataclass(frozen=True, slots=True)
class TimeoutSettings:
    """Session lifecycle timeouts in seconds."""

    stale_after_seconds: float = 20.0
    dead_process_grace_seconds: float = 5.0
    remove_after_seconds: float = 300.0
    provider_retry_initial_seconds: float = 1.0
    provider_retry_max_seconds: float = 30.0

    @classmethod
    def from_mapping(cls, source: object) -> TimeoutSettings:
        data = _mapping(source)
        defaults = cls()
        initial_retry = _number(
            data.get("provider_retry_initial_seconds"),
            defaults.provider_retry_initial_seconds,
            0.1,
            300.0,
        )
        maximum_retry = _number(
            data.get("provider_retry_max_seconds"),
            defaults.provider_retry_max_seconds,
            initial_retry,
            3_600.0,
        )
        return cls(
            stale_after_seconds=_number(
                data.get("stale_after_seconds"),
                defaults.stale_after_seconds,
                1.0,
                86_400.0,
            ),
            dead_process_grace_seconds=_number(
                data.get("dead_process_grace_seconds"),
                defaults.dead_process_grace_seconds,
                0.0,
                3_600.0,
            ),
            remove_after_seconds=_number(
                data.get("remove_after_seconds"),
                defaults.remove_after_seconds,
                5.0,
                604_800.0,
            ),
            provider_retry_initial_seconds=initial_retry,
            provider_retry_max_seconds=maximum_retry,
        )


@dataclass(frozen=True, slots=True)
class IpcProviderSettings:
    """JSON IPC provider configuration."""

    enabled: bool = True
    directory: str = "runtime/sessions"

    @classmethod
    def from_mapping(cls, source: object) -> IpcProviderSettings:
        data = _mapping(source)
        defaults = cls()
        return cls(
            enabled=_boolean(data.get("enabled"), defaults.enabled),
            directory=_relative_or_expanded_path(
                data.get("directory"),
                defaults.directory,
            ),
        )


@dataclass(frozen=True, slots=True)
class LogProviderSettings:
    """Incremental Codex log parser configuration."""

    enabled: bool = True
    paths: tuple[str, ...] = field(default_factory=codex_log_paths)
    encoding: str = "utf-8"
    start_at_end: bool = False
    maximum_file_age_seconds: float = 86_400.0
    ready_patterns: tuple[str, ...] = (
        r"\bwaiting for (input|prompt)\b",
        r"\bturn completed\b",
        r"\bidle\b",
    )
    working_patterns: tuple[str, ...] = (
        r"\b(thinking|reasoning|planning|searching)\b",
        r"\b(reading|writing|editing|running|analyzing)\b",
    )
    needs_you_patterns: tuple[str, ...] = (
        r"\b(permission|approval) (required|requested|needed)\b",
        r"\bconfirm(ation)? required\b",
        r"\binput required\b",
        r"\bcontinue\?\s*$",
        (
            r"\b(do|would|could|can|should|may) you "
            r"(want|like|prefer|allow|approve|confirm|choose)\b"
        ),
        r"\bplease (reply|respond|choose|select|confirm|approve|allow)\b",
        r"\b(access|connect to|use) (the )?(network|internet|wi-?fi)\b",
    )

    @classmethod
    def from_mapping(cls, source: object) -> LogProviderSettings:
        data = _mapping(source)
        defaults = cls()
        raw_paths = _string_tuple(
            data.get("paths"),
            defaults.paths,
            maximum_items=32,
        )
        return cls(
            enabled=_boolean(data.get("enabled"), defaults.enabled),
            paths=tuple(
                os.path.expandvars(os.path.expanduser(item)) for item in raw_paths
            ),
            encoding=_text(data.get("encoding"), defaults.encoding, 64),
            start_at_end=_boolean(
                data.get("start_at_end"),
                defaults.start_at_end,
            ),
            maximum_file_age_seconds=_number(
                data.get("maximum_file_age_seconds"),
                defaults.maximum_file_age_seconds,
                60.0,
                2_592_000.0,
            ),
            ready_patterns=_string_tuple(
                data.get("ready_patterns"),
                defaults.ready_patterns,
                maximum_items=64,
                maximum_length=512,
            ),
            working_patterns=_string_tuple(
                data.get("working_patterns"),
                defaults.working_patterns,
                maximum_items=64,
                maximum_length=512,
            ),
            needs_you_patterns=_string_tuple(
                data.get("needs_you_patterns"),
                defaults.needs_you_patterns,
                maximum_items=64,
                maximum_length=512,
            ),
        )


@dataclass(frozen=True, slots=True)
class StreamProviderSettings:
    """stdin/stdout monitor configuration."""

    enabled: bool = False
    maximum_line_bytes: int = 1_048_576

    @classmethod
    def from_mapping(cls, source: object) -> StreamProviderSettings:
        data = _mapping(source)
        defaults = cls()
        return cls(
            enabled=_boolean(data.get("enabled"), defaults.enabled),
            maximum_line_bytes=_integer(
                data.get("maximum_line_bytes"),
                defaults.maximum_line_bytes,
                1_024,
                16_777_216,
            ),
        )


@dataclass(frozen=True, slots=True)
class HookProviderSettings:
    """Future native-hook adapter configuration."""

    enabled: bool = False
    queue_limit: int = 1_024

    @classmethod
    def from_mapping(cls, source: object) -> HookProviderSettings:
        data = _mapping(source)
        defaults = cls()
        return cls(
            enabled=_boolean(data.get("enabled"), defaults.enabled),
            queue_limit=_integer(
                data.get("queue_limit"),
                defaults.queue_limit,
                16,
                65_536,
            ),
        )


@dataclass(frozen=True, slots=True)
class ProviderSettings:
    """Settings for every built-in provider."""

    ipc: IpcProviderSettings = field(default_factory=IpcProviderSettings)
    logs: LogProviderSettings = field(default_factory=LogProviderSettings)
    stream: StreamProviderSettings = field(default_factory=StreamProviderSettings)
    hooks: HookProviderSettings = field(default_factory=HookProviderSettings)

    @classmethod
    def from_mapping(cls, source: object) -> ProviderSettings:
        data = _mapping(source)
        return cls(
            ipc=IpcProviderSettings.from_mapping(data.get("ipc")),
            logs=LogProviderSettings.from_mapping(data.get("logs")),
            stream=StreamProviderSettings.from_mapping(data.get("stream")),
            hooks=HookProviderSettings.from_mapping(data.get("hooks")),
        )


@dataclass(frozen=True, slots=True)
class AppConfig:
    """Complete validated application configuration."""

    CURRENT_SCHEMA_VERSION = 3

    schema_version: int = CURRENT_SCHEMA_VERSION
    poll_interval_ms: int = 250
    auto_hide_enabled: bool = False
    monitoring_enabled: bool = True
    notifications_enabled: bool = True
    launch_at_login: bool = False
    display_size: str = "compact"
    display_mode: str = "normal"
    low_opacity: float = 0.15
    hide_on_processes: tuple[str, ...] = DEFAULT_HIDE_ON_PROCESSES
    working_labels: tuple[str, ...] = DEFAULT_WORKING_LABELS
    position: OverlayPosition = field(default_factory=OverlayPosition)
    theme: ThemeSettings = field(default_factory=ThemeSettings)
    colors: ColorSettings = field(default_factory=ColorSettings)
    animations: AnimationSettings = field(default_factory=AnimationSettings)
    sounds: SoundSettings = field(default_factory=SoundSettings)
    timeouts: TimeoutSettings = field(default_factory=TimeoutSettings)
    providers: ProviderSettings = field(default_factory=ProviderSettings)

    @classmethod
    def from_mapping(cls, source: object) -> AppConfig:
        """Validate a decoded JSON object one setting at a time."""

        data = _mapping(source)
        defaults = cls()
        return cls(
            schema_version=_integer(
                data.get("schema_version"),
                defaults.schema_version,
                1,
                cls.CURRENT_SCHEMA_VERSION,
            ),
            poll_interval_ms=_integer(
                data.get("poll_interval_ms"),
                defaults.poll_interval_ms,
                100,
                60_000,
            ),
            auto_hide_enabled=_boolean(
                data.get("auto_hide_enabled"),
                defaults.auto_hide_enabled,
            ),
            monitoring_enabled=_boolean(
                data.get("monitoring_enabled"),
                defaults.monitoring_enabled,
            ),
            notifications_enabled=_boolean(
                data.get("notifications_enabled"),
                defaults.notifications_enabled,
            ),
            launch_at_login=_boolean(
                data.get("launch_at_login"),
                defaults.launch_at_login,
            ),
            display_size=_choice(
                data.get("display_size"),
                defaults.display_size,
                {"compact", "small", "expanded"},
            ),
            display_mode=_choice(
                data.get("display_mode"),
                defaults.display_mode,
                {"normal", "low_opacity", "notifications_only"},
            ),
            low_opacity=_number(
                data.get("low_opacity"),
                defaults.low_opacity,
                0.05,
                0.50,
            ),
            hide_on_processes=_string_tuple(
                data.get("hide_on_processes"),
                defaults.hide_on_processes,
                maximum_items=128,
                maximum_length=260,
            ),
            working_labels=_string_tuple(
                data.get("working_labels"),
                defaults.working_labels,
                maximum_items=128,
                maximum_length=128,
            ),
            position=OverlayPosition.from_mapping(data.get("position")),
            theme=ThemeSettings.from_mapping(data.get("theme")),
            colors=ColorSettings.from_mapping(data.get("colors")),
            animations=AnimationSettings.from_mapping(data.get("animations")),
            sounds=SoundSettings.from_mapping(data.get("sounds")),
            timeouts=TimeoutSettings.from_mapping(data.get("timeouts")),
            providers=ProviderSettings.from_mapping(data.get("providers")),
        )

    def to_dict(self) -> dict[str, Any]:
        """Return a canonical JSON-compatible configuration mapping."""

        return asdict(self)

    def resolve_path(self, configured_path: str, project_root: Path) -> Path:
        """Resolve a configured path relative to the application directory."""

        expanded = Path(os.path.expandvars(os.path.expanduser(configured_path)))
        if expanded.is_absolute():
            return expanded
        return (project_root / expanded).resolve()


@dataclass(frozen=True, slots=True)
class ConfigLoadResult:
    """Outcome of loading a configuration file without raising to the UI."""

    config: AppConfig
    source_path: Path
    used_defaults: bool
    migrated: bool = False
    backup_path: Path | None = None
    warning: str = ""


def load_config(path: str | Path) -> ConfigLoadResult:
    """Load configuration safely and back up malformed files.

    Missing files use defaults and are not considered errors. A malformed file
    is copied beside the original with a UTC timestamp before defaults are
    returned. The installer or application lifecycle layer can then persist the
    returned canonical configuration through the atomic JSON utility.
    """

    source_path = Path(path)
    defaults = AppConfig()

    try:
        raw_text = source_path.read_text(encoding="utf-8-sig")
    except FileNotFoundError:
        return ConfigLoadResult(
            config=defaults,
            source_path=source_path,
            used_defaults=True,
            warning="Configuration file not found; using defaults.",
        )
    except OSError as error:
        message = f"Unable to read configuration; using defaults: {error}"
        LOGGER.warning(message)
        return ConfigLoadResult(
            config=defaults,
            source_path=source_path,
            used_defaults=True,
            warning=message,
        )

    try:
        decoded = json.loads(raw_text)
        if not isinstance(decoded, Mapping):
            raise TypeError("configuration root must be a JSON object")
        source_schema_version = _integer(
            decoded.get("schema_version"),
            1,
            1,
            AppConfig.CURRENT_SCHEMA_VERSION,
        )
        source_colors = _mapping(decoded.get("colors"))
        legacy_working_color = (
            str(source_colors.get("working", "")).strip().upper()
            == LEGACY_WORKING_COLOR
        )
        config = AppConfig.from_mapping(decoded)
        migrated = (
            source_schema_version < AppConfig.CURRENT_SCHEMA_VERSION
            or legacy_working_color
        )
        if migrated:
            config = replace(
                config,
                schema_version=AppConfig.CURRENT_SCHEMA_VERSION,
            )
    except (json.JSONDecodeError, TypeError, ValueError) as error:
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S.%fZ")
        backup_path = source_path.with_name(
            f"{source_path.name}.invalid-{timestamp}.bak"
        )
        try:
            shutil.copy2(source_path, backup_path)
        except OSError as backup_error:
            LOGGER.error(
                "Failed to back up invalid configuration %s: %s",
                source_path,
                backup_error,
            )
            backup_path = None

        message = f"Invalid configuration; using defaults: {error}"
        LOGGER.warning(message)
        return ConfigLoadResult(
            config=defaults,
            source_path=source_path,
            used_defaults=True,
            backup_path=backup_path,
            warning=message,
        )

    return ConfigLoadResult(
        config=config,
        source_path=source_path,
        used_defaults=False,
        migrated=migrated,
    )


__all__ = [
    "AnimationSettings",
    "AppConfig",
    "ColorSettings",
    "ConfigLoadResult",
    "HookProviderSettings",
    "IpcProviderSettings",
    "LogProviderSettings",
    "OverlayPosition",
    "ProviderSettings",
    "SoundSettings",
    "StreamProviderSettings",
    "ThemeSettings",
    "TimeoutSettings",
    "load_config",
]
