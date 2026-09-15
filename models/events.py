"""Typed events exchanged by providers, the coordinator, and the UI."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from typing import TypeAlias

from models.session import CodexSession, SessionStatus, utc_now


def _utc(value: datetime) -> datetime:
    """Normalize a timestamp to timezone-aware UTC."""

    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _required_text(value: object, field_name: str, maximum: int) -> str:
    """Normalize bounded event text and reject empty values."""

    text = str(value or "").replace("\x00", "").strip()
    if not text:
        raise ValueError(f"{field_name} must not be empty")
    return text[:maximum]


def _optional_text(value: object, maximum: int) -> str:
    """Normalize optional bounded event text."""

    return str(value or "").replace("\x00", "").strip()[:maximum]


def _sequence(value: object) -> int:
    """Validate a monotonic provider sequence number."""

    if isinstance(value, bool):
        raise TypeError("sequence must be a non-negative integer")
    try:
        parsed = int(value)
    except (TypeError, ValueError, OverflowError) as error:
        raise TypeError("sequence must be a non-negative integer") from error
    if parsed < 0:
        raise ValueError("sequence must be a non-negative integer")
    return parsed


class ProviderEventKind(str, Enum):
    """Kinds of events emitted by a session provider."""

    SESSION_OBSERVED = "session_observed"
    SESSION_REMOVED = "session_removed"
    PROVIDER_FAILED = "provider_failed"
    PROVIDER_RECOVERED = "provider_recovered"


@dataclass(frozen=True, slots=True, kw_only=True)
class SessionObservation:
    """A provider's complete observation of one live session."""

    provider: str
    session: CodexSession
    occurred_at: datetime
    sequence: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "provider",
            _required_text(self.provider, "provider", 128),
        )
        if not isinstance(self.session, CodexSession):
            raise TypeError("session must be a CodexSession")
        object.__setattr__(self, "occurred_at", _utc(self.occurred_at))
        object.__setattr__(self, "sequence", _sequence(self.sequence))

    @classmethod
    def create(
        cls,
        provider: str,
        session: CodexSession,
        *,
        occurred_at: datetime | None = None,
        sequence: int = 0,
    ) -> SessionObservation:
        """Create an observation using the current time by default."""

        return cls(
            provider=provider,
            session=session,
            occurred_at=occurred_at or utc_now(),
            sequence=sequence,
        )

    @property
    def kind(self) -> ProviderEventKind:
        return ProviderEventKind.SESSION_OBSERVED


@dataclass(frozen=True, slots=True, kw_only=True)
class SessionRemoval:
    """A provider's declaration that a session is no longer live."""

    provider: str
    session_id: str
    occurred_at: datetime
    sequence: int = 0
    reason: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "provider",
            _required_text(self.provider, "provider", 128),
        )
        object.__setattr__(
            self,
            "session_id",
            _required_text(self.session_id, "session_id", 128),
        )
        object.__setattr__(self, "occurred_at", _utc(self.occurred_at))
        object.__setattr__(self, "sequence", _sequence(self.sequence))
        object.__setattr__(self, "reason", _optional_text(self.reason, 512))

    @classmethod
    def create(
        cls,
        provider: str,
        session_id: str,
        *,
        occurred_at: datetime | None = None,
        sequence: int = 0,
        reason: str = "",
    ) -> SessionRemoval:
        """Create a removal event using the current time by default."""

        return cls(
            provider=provider,
            session_id=session_id,
            occurred_at=occurred_at or utc_now(),
            sequence=sequence,
            reason=reason,
        )

    @property
    def kind(self) -> ProviderEventKind:
        return ProviderEventKind.SESSION_REMOVED


@dataclass(frozen=True, slots=True, kw_only=True)
class ProviderFault:
    """A contained provider failure reported to the coordinator."""

    provider: str
    message: str
    occurred_at: datetime
    sequence: int = 0
    exception_type: str = ""
    recoverable: bool = True
    retry_in_seconds: float | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "provider",
            _required_text(self.provider, "provider", 128),
        )
        object.__setattr__(
            self,
            "message",
            _required_text(self.message, "message", 2_048),
        )
        object.__setattr__(self, "occurred_at", _utc(self.occurred_at))
        object.__setattr__(self, "sequence", _sequence(self.sequence))
        object.__setattr__(
            self,
            "exception_type",
            _optional_text(self.exception_type, 256),
        )
        if self.retry_in_seconds is not None:
            retry = float(self.retry_in_seconds)
            if retry < 0:
                raise ValueError("retry_in_seconds must be non-negative")
            object.__setattr__(self, "retry_in_seconds", retry)

    @classmethod
    def from_exception(
        cls,
        provider: str,
        error: BaseException,
        *,
        occurred_at: datetime | None = None,
        sequence: int = 0,
        recoverable: bool = True,
        retry_in_seconds: float | None = None,
    ) -> ProviderFault:
        """Create a sanitized provider fault from a caught exception."""

        message = str(error).strip() or error.__class__.__name__
        return cls(
            provider=provider,
            message=message,
            occurred_at=occurred_at or utc_now(),
            sequence=sequence,
            exception_type=error.__class__.__name__,
            recoverable=recoverable,
            retry_in_seconds=retry_in_seconds,
        )

    @property
    def kind(self) -> ProviderEventKind:
        return ProviderEventKind.PROVIDER_FAILED


@dataclass(frozen=True, slots=True, kw_only=True)
class ProviderRecovered:
    """Notification that a previously failing provider is healthy again."""

    provider: str
    occurred_at: datetime
    sequence: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "provider",
            _required_text(self.provider, "provider", 128),
        )
        object.__setattr__(self, "occurred_at", _utc(self.occurred_at))
        object.__setattr__(self, "sequence", _sequence(self.sequence))

    @classmethod
    def create(
        cls,
        provider: str,
        *,
        occurred_at: datetime | None = None,
        sequence: int = 0,
    ) -> ProviderRecovered:
        """Create a recovery event using the current time by default."""

        return cls(
            provider=provider,
            occurred_at=occurred_at or utc_now(),
            sequence=sequence,
        )

    @property
    def kind(self) -> ProviderEventKind:
        return ProviderEventKind.PROVIDER_RECOVERED


ProviderEvent: TypeAlias = (
    SessionObservation | SessionRemoval | ProviderFault | ProviderRecovered
)


@dataclass(frozen=True, slots=True, kw_only=True)
class SessionStateChange:
    """A coordinator-confirmed transition used for animation and sound."""

    session: CodexSession
    previous_status: SessionStatus
    current_status: SessionStatus
    occurred_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.session, CodexSession):
            raise TypeError("session must be a CodexSession")
        previous = SessionStatus.parse(self.previous_status)
        current = SessionStatus.parse(self.current_status)
        if previous is current:
            raise ValueError("a state change requires two different statuses")
        if current is not self.session.status:
            raise ValueError("current_status must match session.status")
        object.__setattr__(self, "previous_status", previous)
        object.__setattr__(self, "current_status", current)
        object.__setattr__(self, "occurred_at", _utc(self.occurred_at))

    @property
    def requires_notification(self) -> bool:
        """Return whether the transition should alert the user."""

        return (
            self.current_status
            in {
                SessionStatus.NEEDS_YOU,
                SessionStatus.READY,
            }
            and self.previous_status is not self.current_status
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class SessionSnapshot:
    """An ordered, immutable view of all sessions for one UI refresh."""

    sessions: tuple[CodexSession, ...]
    revision: int
    occurred_at: datetime

    def __post_init__(self) -> None:
        if any(not isinstance(item, CodexSession) for item in self.sessions):
            raise TypeError("sessions must contain only CodexSession instances")
        if len({item.session_id for item in self.sessions}) != len(self.sessions):
            raise ValueError("sessions must have unique session IDs")
        revision = _sequence(self.revision)
        ordered = tuple(sorted(self.sessions, key=lambda item: item.sort_key))
        object.__setattr__(self, "sessions", ordered)
        object.__setattr__(self, "revision", revision)
        object.__setattr__(self, "occurred_at", _utc(self.occurred_at))

    @classmethod
    def create(
        cls,
        sessions: tuple[CodexSession, ...],
        revision: int,
        *,
        occurred_at: datetime | None = None,
    ) -> SessionSnapshot:
        """Create a priority-sorted snapshot."""

        return cls(
            sessions=sessions,
            revision=revision,
            occurred_at=occurred_at or utc_now(),
        )

    @property
    def needs_attention(self) -> bool:
        """Return whether any session requires user interaction."""

        return any(
            session.status is SessionStatus.NEEDS_YOU for session in self.sessions
        )


__all__ = [
    "ProviderEvent",
    "ProviderEventKind",
    "ProviderFault",
    "ProviderRecovered",
    "SessionObservation",
    "SessionRemoval",
    "SessionSnapshot",
    "SessionStateChange",
]
