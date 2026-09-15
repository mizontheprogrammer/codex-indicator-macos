"""Canonical session state used throughout Codex Indicator."""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from enum import Enum
from typing import Any, ClassVar

_SESSION_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_MAX_WORKSPACE_LENGTH = 32_767
_MAX_TITLE_LENGTH = 1_024
_MAX_ACTIVITY_LENGTH = 256
_MAX_PROVIDER_LENGTH = 128
_UTC_MIN = datetime.min.replace(tzinfo=UTC)


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp.

    The function is intentionally module-level so tests can supply explicit
    clocks to all time-sensitive model methods.
    """

    return datetime.now(UTC)


class SessionStatus(str, Enum):
    """The only states a monitored Codex session can occupy."""

    READY = "ready"
    WORKING = "working"
    NEEDS_YOU = "needs_you"

    @property
    def priority(self) -> int:
        """Return display priority, where a larger number is more important."""

        return {
            SessionStatus.READY: 1,
            SessionStatus.WORKING: 2,
            SessionStatus.NEEDS_YOU: 3,
        }[self]

    @property
    def display_name(self) -> str:
        """Return the stable user-facing state name."""

        return {
            SessionStatus.READY: "Codex is ready",
            SessionStatus.WORKING: "Working",
            SessionStatus.NEEDS_YOU: "Codex needs you",
        }[self]

    @classmethod
    def parse(
        cls,
        value: object,
        *,
        default: SessionStatus | None = None,
    ) -> SessionStatus:
        """Parse common provider spellings into a canonical status.

        Args:
            value: Enum member or string supplied by a provider.
            default: Value returned for unknown input. If omitted, invalid input
                raises ``ValueError``.
        """

        if isinstance(value, cls):
            return value

        normalized = str(value or "").strip().casefold()
        normalized = re.sub(r"[\s-]+", "_", normalized)
        aliases = {
            "ready": cls.READY,
            "idle": cls.READY,
            "waiting": cls.READY,
            "working": cls.WORKING,
            "busy": cls.WORKING,
            "running": cls.WORKING,
            "needs_you": cls.NEEDS_YOU,
            "needs_input": cls.NEEDS_YOU,
            "attention": cls.NEEDS_YOU,
            "approval": cls.NEEDS_YOU,
            "permission": cls.NEEDS_YOU,
        }
        parsed = aliases.get(normalized)
        if parsed is not None:
            return parsed
        if default is not None:
            return default
        raise ValueError(f"Unknown session status: {value!r}")


def _clean_text(
    value: object,
    *,
    field_name: str,
    maximum: int,
    required: bool = False,
) -> str:
    """Normalize external text and reject missing required values."""

    text = str(value or "").replace("\x00", "").strip()
    if required and not text:
        raise ValueError(f"{field_name} must not be empty")
    if len(text) > maximum:
        text = text[:maximum]
    return text


def _parse_optional_positive_int(value: object) -> int | None:
    """Convert an external value to a positive integer or ``None``."""

    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return parsed if parsed > 0 else None


def _parse_optional_percent(value: object) -> float | None:
    """Convert a value to a percentage clamped to 0–100."""

    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if not math.isfinite(parsed):
        return None
    return max(0.0, min(100.0, parsed))


def _as_utc(value: datetime) -> datetime:
    """Return a datetime normalized to aware UTC."""

    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _parse_datetime(value: object, *, default: datetime) -> datetime:
    """Parse a datetime or ISO-8601 string, falling back safely."""

    if isinstance(value, datetime):
        return _as_utc(value)
    if isinstance(value, str):
        candidate = value.strip()
        if candidate:
            if candidate.endswith(("Z", "z")):
                candidate = f"{candidate[:-1]}+00:00"
            try:
                return _as_utc(datetime.fromisoformat(candidate))
            except (TypeError, ValueError, OverflowError):
                pass
    return _as_utc(default)


def _format_datetime(value: datetime) -> str:
    """Serialize an aware datetime as a stable ISO-8601 UTC value."""

    return _as_utc(value).isoformat(timespec="microseconds").replace("+00:00", "Z")


@dataclass(frozen=True, slots=True)
class CodexSession:
    """Immutable, provider-neutral snapshot of one Codex CLI session.

    Providers produce new snapshots rather than mutating existing instances.
    This makes cross-thread delivery predictable and prevents the UI from
    observing partially updated state.
    """

    SCHEMA_VERSION: ClassVar[int] = 1

    session_id: str
    workspace: str
    status: SessionStatus = SessionStatus.READY
    started_at: datetime = _UTC_MIN
    state_started_at: datetime = _UTC_MIN
    last_activity: datetime = _UTC_MIN
    pid: int | None = None
    terminal_hwnd: int | None = None
    window_title: str = ""
    provider: str = "unknown"
    activity: str = ""
    context_remaining_percent: float | None = None
    rate_limit_remaining_percent: float | None = None
    rate_limit_resets_at: datetime | None = None
    secondary_remaining_percent: float | None = None
    secondary_resets_at: datetime | None = None
    plan_type: str = ""

    def __post_init__(self) -> None:
        """Normalize direct construction and enforce persistence invariants."""

        session_id = _clean_text(
            self.session_id,
            field_name="session_id",
            maximum=128,
            required=True,
        )
        if not _SESSION_ID_PATTERN.fullmatch(session_id):
            raise ValueError(
                "session_id must begin with an alphanumeric character and "
                "contain only letters, numbers, '.', '_' or '-'"
            )

        workspace = _clean_text(
            self.workspace,
            field_name="workspace",
            maximum=_MAX_WORKSPACE_LENGTH,
        )
        title = _clean_text(
            self.window_title,
            field_name="window_title",
            maximum=_MAX_TITLE_LENGTH,
        )
        provider = (
            _clean_text(
                self.provider,
                field_name="provider",
                maximum=_MAX_PROVIDER_LENGTH,
            )
            or "unknown"
        )
        activity = _clean_text(
            self.activity,
            field_name="activity",
            maximum=_MAX_ACTIVITY_LENGTH,
        )
        plan_type = _clean_text(
            self.plan_type,
            field_name="plan_type",
            maximum=128,
        )

        status = SessionStatus.parse(self.status)
        started_at = _as_utc(self.started_at)
        state_started_at = _as_utc(self.state_started_at)
        last_activity = _as_utc(self.last_activity)
        pid = _parse_optional_positive_int(self.pid)
        terminal_hwnd = _parse_optional_positive_int(self.terminal_hwnd)
        context_remaining = _parse_optional_percent(self.context_remaining_percent)
        rate_remaining = _parse_optional_percent(self.rate_limit_remaining_percent)
        secondary_remaining = _parse_optional_percent(self.secondary_remaining_percent)
        rate_reset = (
            _as_utc(self.rate_limit_resets_at)
            if self.rate_limit_resets_at is not None
            else None
        )
        secondary_reset = (
            _as_utc(self.secondary_resets_at)
            if self.secondary_resets_at is not None
            else None
        )

        object.__setattr__(self, "session_id", session_id)
        object.__setattr__(self, "workspace", workspace)
        object.__setattr__(self, "status", status)
        object.__setattr__(self, "started_at", started_at)
        object.__setattr__(self, "state_started_at", state_started_at)
        object.__setattr__(self, "last_activity", last_activity)
        object.__setattr__(self, "pid", pid)
        object.__setattr__(self, "terminal_hwnd", terminal_hwnd)
        object.__setattr__(self, "window_title", title)
        object.__setattr__(self, "provider", provider)
        object.__setattr__(self, "activity", activity)
        object.__setattr__(
            self,
            "context_remaining_percent",
            context_remaining,
        )
        object.__setattr__(
            self,
            "rate_limit_remaining_percent",
            rate_remaining,
        )
        object.__setattr__(self, "rate_limit_resets_at", rate_reset)
        object.__setattr__(
            self,
            "secondary_remaining_percent",
            secondary_remaining,
        )
        object.__setattr__(self, "secondary_resets_at", secondary_reset)
        object.__setattr__(self, "plan_type", plan_type)

    @classmethod
    def create(
        cls,
        session_id: str,
        *,
        workspace: str = "",
        status: SessionStatus = SessionStatus.READY,
        now: datetime | None = None,
        pid: int | None = None,
        terminal_hwnd: int | None = None,
        window_title: str = "",
        provider: str = "unknown",
        activity: str = "",
    ) -> CodexSession:
        """Create a new session with internally consistent timestamps."""

        timestamp = _as_utc(now or utc_now())
        return cls(
            session_id=session_id,
            workspace=workspace,
            status=status,
            started_at=timestamp,
            state_started_at=timestamp,
            last_activity=timestamp,
            pid=pid,
            terminal_hwnd=terminal_hwnd,
            window_title=window_title,
            provider=provider,
            activity=activity,
        )

    @classmethod
    def from_dict(
        cls,
        data: Mapping[str, Any],
        *,
        now: datetime | None = None,
        default_provider: str = "unknown",
    ) -> CodexSession:
        """Build a validated session from untrusted JSON-compatible data.

        Unknown fields are ignored for forward compatibility. Invalid optional
        fields are normalized independently; an invalid or absent session ID
        remains a hard error because it is the persistence identity.
        """

        fallback_now = _as_utc(now or utc_now())
        started_at = _parse_datetime(data.get("started_at"), default=fallback_now)
        state_started_at = _parse_datetime(
            data.get("state_started_at"),
            default=started_at,
        )
        last_activity = _parse_datetime(
            data.get("last_activity"),
            default=max(started_at, state_started_at),
        )

        return cls(
            session_id=data.get("session_id", ""),
            workspace=data.get("workspace", ""),
            status=SessionStatus.parse(
                data.get("status"),
                default=SessionStatus.READY,
            ),
            started_at=started_at,
            state_started_at=state_started_at,
            last_activity=last_activity,
            pid=_parse_optional_positive_int(data.get("pid")),
            terminal_hwnd=_parse_optional_positive_int(data.get("terminal_hwnd")),
            window_title=data.get("window_title", ""),
            provider=data.get("provider", default_provider),
            activity=data.get("activity", ""),
            context_remaining_percent=data.get("context_remaining_percent"),
            rate_limit_remaining_percent=data.get("rate_limit_remaining_percent"),
            rate_limit_resets_at=(
                _parse_datetime(
                    data.get("rate_limit_resets_at"),
                    default=fallback_now,
                )
                if data.get("rate_limit_resets_at") is not None
                else None
            ),
            secondary_remaining_percent=data.get("secondary_remaining_percent"),
            secondary_resets_at=(
                _parse_datetime(
                    data.get("secondary_resets_at"),
                    default=fallback_now,
                )
                if data.get("secondary_resets_at") is not None
                else None
            ),
            plan_type=data.get("plan_type", ""),
        )

    def to_dict(self) -> dict[str, object]:
        """Return the canonical JSON-compatible persistence representation."""

        return {
            "schema_version": self.SCHEMA_VERSION,
            "session_id": self.session_id,
            "workspace": self.workspace,
            "status": self.status.value,
            "started_at": _format_datetime(self.started_at),
            "state_started_at": _format_datetime(self.state_started_at),
            "last_activity": _format_datetime(self.last_activity),
            "pid": self.pid,
            "terminal_hwnd": self.terminal_hwnd,
            "window_title": self.window_title,
            "provider": self.provider,
            "activity": self.activity,
            "context_remaining_percent": self.context_remaining_percent,
            "rate_limit_remaining_percent": self.rate_limit_remaining_percent,
            "rate_limit_resets_at": (
                _format_datetime(self.rate_limit_resets_at)
                if self.rate_limit_resets_at is not None
                else None
            ),
            "secondary_remaining_percent": self.secondary_remaining_percent,
            "secondary_resets_at": (
                _format_datetime(self.secondary_resets_at)
                if self.secondary_resets_at is not None
                else None
            ),
            "plan_type": self.plan_type,
        }

    def transition(
        self,
        status: SessionStatus,
        *,
        now: datetime | None = None,
        activity: str | None = None,
        provider: str | None = None,
    ) -> CodexSession:
        """Return a snapshot reflecting a state observation.

        Re-observing the same state preserves its elapsed timer. A genuine state
        change resets ``state_started_at``. Both cases update last activity.
        """

        timestamp = _as_utc(now or utc_now())
        next_status = SessionStatus.parse(status)
        return replace(
            self,
            status=next_status,
            state_started_at=(
                timestamp if next_status is not self.status else self.state_started_at
            ),
            last_activity=max(timestamp, self.last_activity),
            activity=self.activity if activity is None else activity,
            provider=self.provider if provider is None else provider,
        )

    def with_observation(
        self,
        *,
        workspace: str | None = None,
        pid: int | None = None,
        terminal_hwnd: int | None = None,
        window_title: str | None = None,
        provider: str | None = None,
        now: datetime | None = None,
    ) -> CodexSession:
        """Return a snapshot with refreshed provider or process information."""

        timestamp = _as_utc(now or utc_now())
        return replace(
            self,
            workspace=self.workspace if workspace is None else workspace,
            pid=self.pid if pid is None else pid,
            terminal_hwnd=(
                self.terminal_hwnd if terminal_hwnd is None else terminal_hwnd
            ),
            window_title=(self.window_title if window_title is None else window_title),
            provider=self.provider if provider is None else provider,
            last_activity=max(timestamp, self.last_activity),
        )

    def with_usage(
        self,
        *,
        context_remaining_percent: float | None = None,
        rate_limit_remaining_percent: float | None = None,
        rate_limit_resets_at: datetime | None = None,
        secondary_remaining_percent: float | None = None,
        secondary_resets_at: datetime | None = None,
        plan_type: str | None = None,
        now: datetime | None = None,
    ) -> CodexSession:
        """Return a snapshot containing the latest Codex usage limits."""

        timestamp = _as_utc(now or utc_now())
        return replace(
            self,
            context_remaining_percent=(
                self.context_remaining_percent
                if context_remaining_percent is None
                else context_remaining_percent
            ),
            rate_limit_remaining_percent=(
                self.rate_limit_remaining_percent
                if rate_limit_remaining_percent is None
                else rate_limit_remaining_percent
            ),
            rate_limit_resets_at=(
                self.rate_limit_resets_at
                if rate_limit_resets_at is None
                else rate_limit_resets_at
            ),
            secondary_remaining_percent=(
                self.secondary_remaining_percent
                if secondary_remaining_percent is None
                else secondary_remaining_percent
            ),
            secondary_resets_at=(
                self.secondary_resets_at
                if secondary_resets_at is None
                else secondary_resets_at
            ),
            plan_type=self.plan_type if plan_type is None else plan_type,
            last_activity=max(timestamp, self.last_activity),
        )

    def state_elapsed_seconds(self, *, now: datetime | None = None) -> int:
        """Return non-negative whole seconds elapsed in the current state."""

        timestamp = _as_utc(now or utc_now())
        return max(0, int((timestamp - self.state_started_at).total_seconds()))

    def formatted_elapsed(self, *, now: datetime | None = None) -> str:
        """Format state elapsed time compactly for an overlay row."""

        total_seconds = self.state_elapsed_seconds(now=now)
        hours, remainder = divmod(total_seconds, 3_600)
        minutes, seconds = divmod(remainder, 60)
        if hours:
            return f"{hours}h {minutes}m"
        if minutes:
            return f"{minutes}m {seconds}s"
        return f"{seconds}s"

    def is_stale(
        self,
        timeout_seconds: float,
        *,
        now: datetime | None = None,
    ) -> bool:
        """Return whether the session has exceeded an inactivity timeout."""

        if timeout_seconds < 0:
            raise ValueError("timeout_seconds must be non-negative")
        timestamp = _as_utc(now or utc_now())
        return (timestamp - self.last_activity).total_seconds() > timeout_seconds

    @property
    def effective_label(self) -> str:
        """Return provider activity when available, otherwise the state label."""

        return self.activity or self.status.display_name

    @property
    def sort_key(self) -> tuple[int, float, str, str]:
        """Return an ascending key for priority-first overlay ordering."""

        return (
            -self.status.priority,
            -self.last_activity.timestamp(),
            self.workspace.casefold(),
            self.session_id.casefold(),
        )


__all__ = ["CodexSession", "SessionStatus", "utc_now"]
