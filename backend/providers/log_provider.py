"""Incremental, rotation-aware Codex text-log provider."""

from __future__ import annotations

import glob
import hashlib
import json
import logging
import re
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from backend.providers.base import SessionProvider
from models.events import ProviderEvent, SessionObservation
from models.session import CodexSession, SessionStatus

LOGGER = logging.getLogger(__name__)

DEFAULT_DISCOVERY_INTERVAL_SECONDS = 1.0
DEFAULT_MAXIMUM_READ_BYTES = 2 * 1024 * 1024
DEFAULT_MAXIMUM_LINE_BYTES = 512 * 1024

_BUILTIN_ATTENTION_PATTERNS = (
    (
        r"\b(do|would|could|can|should|may) you "
        r"(want|like|prefer|allow|approve|confirm|choose)\b"
    ),
    r"\bplease (reply|respond|choose|select|confirm|approve|allow)\b",
    (
        r"\b(waiting|need) (for )?(your )?"
        r"(reply|response|answer|input|approval|permission)\b"
    ),
    r"\b(access|connect to|use) (the )?(network|internet|wi-?fi)\b",
)


@dataclass(slots=True)
class _Cursor:
    identity: tuple[int, int]
    offset: int


class LogProvider(SessionProvider):
    """Tail configured logs and infer session state from bounded regexes."""

    def __init__(
        self,
        paths: tuple[str, ...],
        *,
        ready_patterns: tuple[str, ...],
        working_patterns: tuple[str, ...],
        needs_you_patterns: tuple[str, ...],
        encoding: str = "utf-8",
        start_at_end: bool = True,
        maximum_file_age_seconds: float = 86_400.0,
        discovery_interval_seconds: float = DEFAULT_DISCOVERY_INTERVAL_SECONDS,
        maximum_read_bytes: int = DEFAULT_MAXIMUM_READ_BYTES,
        maximum_line_bytes: int = DEFAULT_MAXIMUM_LINE_BYTES,
    ) -> None:
        super().__init__("logs")
        if discovery_interval_seconds <= 0:
            raise ValueError("discovery_interval_seconds must be positive")
        if maximum_line_bytes < 1:
            raise ValueError("maximum_line_bytes must be positive")
        if maximum_read_bytes <= maximum_line_bytes:
            raise ValueError(
                "maximum_read_bytes must be greater than maximum_line_bytes"
            )
        self.paths = paths
        self.encoding = encoding
        self.start_at_end = start_at_end
        self.maximum_file_age_seconds = maximum_file_age_seconds
        self.discovery_interval_seconds = discovery_interval_seconds
        self.maximum_read_bytes = maximum_read_bytes
        self.maximum_line_bytes = maximum_line_bytes
        self._patterns = (
            (
                SessionStatus.NEEDS_YOU,
                self._compile(
                    tuple(
                        dict.fromkeys(
                            (*needs_you_patterns, *_BUILTIN_ATTENTION_PATTERNS)
                        )
                    )
                ),
            ),
            (SessionStatus.WORKING, self._compile(working_patterns)),
            (SessionStatus.READY, self._compile(ready_patterns)),
        )
        self._cursors: dict[Path, _Cursor] = {}
        self._sessions: dict[Path, CodexSession] = {}
        self._metadata: dict[Path, tuple[str, str]] = {}
        self._attention_calls: dict[Path, dict[str, str]] = {}
        self._awaiting_reply: set[Path] = set()
        self._known_files: tuple[Path, ...] = ()
        self._next_discovery_at = 0.0
        self._discarding_oversized_line: set[Path] = set()
        self._oversized_line_warned: set[Path] = set()

    @staticmethod
    def _compile(patterns: tuple[str, ...]) -> tuple[re.Pattern[str], ...]:
        compiled: list[re.Pattern[str]] = []
        for pattern in patterns:
            try:
                compiled.append(re.compile(pattern, re.IGNORECASE))
            except re.error as error:
                LOGGER.warning("Ignoring invalid log pattern %r: %s", pattern, error)
        return tuple(compiled)

    def _status(self, line: str) -> SessionStatus | None:
        for status, patterns in self._patterns:
            if any(pattern.search(line) for pattern in patterns):
                return status
        return None

    @staticmethod
    def _session_id(path: Path) -> str:
        digest = hashlib.sha256(str(path).casefold().encode("utf-8")).hexdigest()[:20]
        return f"log-{digest}"

    def _files(self) -> tuple[Path, ...]:
        monotonic_now = time.monotonic()
        if monotonic_now < self._next_discovery_at:
            return self._known_files

        found: set[Path] = set()
        cutoff = datetime.now(UTC).timestamp() - self.maximum_file_age_seconds
        for pattern in self.paths:
            found.update(Path(item) for item in glob.glob(pattern, recursive=True))
        recent: list[Path] = []
        for path in found:
            try:
                if path.stat().st_mtime >= cutoff:
                    recent.append(path)
            except OSError:
                continue
        discovered = tuple(sorted(recent))
        active = set(discovered)
        removed = set(self._cursors) - active
        for path in removed:
            self._cursors.pop(path, None)
            self._sessions.pop(path, None)
            self._metadata.pop(path, None)
            self._attention_calls.pop(path, None)
            self._awaiting_reply.discard(path)
            self._discarding_oversized_line.discard(path)
            self._oversized_line_warned.discard(path)
        self._known_files = discovered
        self._next_discovery_at = monotonic_now + self.discovery_interval_seconds
        return discovered

    def _read_complete_lines(
        self,
        path: Path,
        cursor: _Cursor,
        *,
        file_size: int,
    ) -> tuple[str, ...]:
        """Read a bounded batch without consuming an incomplete JSONL record."""

        lines: list[str] = []
        remaining = self.maximum_read_bytes
        with path.open("rb") as stream:
            stream.seek(cursor.offset)
            while remaining > 0:
                line_start = stream.tell()
                limit = min(self.maximum_line_bytes + 1, remaining)
                raw = stream.readline(limit)
                if not raw:
                    break
                consumed = stream.tell() - line_start
                remaining -= consumed

                if path in self._discarding_oversized_line:
                    cursor.offset = stream.tell()
                    if raw.endswith(b"\n"):
                        self._discarding_oversized_line.discard(path)
                    continue

                if len(raw) > self.maximum_line_bytes:
                    cursor.offset = stream.tell()
                    if not raw.endswith(b"\n"):
                        self._discarding_oversized_line.add(path)
                    if path not in self._oversized_line_warned:
                        LOGGER.warning(
                            "Skipping oversized log record in %s (limit %s bytes)",
                            path,
                            self.maximum_line_bytes,
                        )
                        self._oversized_line_warned.add(path)
                    continue

                complete = raw.endswith(b"\n")
                at_end = stream.tell() >= file_size
                if not complete and at_end and path.suffix.casefold() == ".jsonl":
                    try:
                        json.loads(raw.decode(self.encoding))
                    except (
                        UnicodeDecodeError,
                        json.JSONDecodeError,
                        LookupError,
                    ):
                        stream.seek(line_start)
                        cursor.offset = line_start
                        break
                    complete = True
                elif not complete and at_end:
                    complete = True

                if not complete:
                    stream.seek(line_start)
                    cursor.offset = line_start
                    break

                cursor.offset = stream.tell()
                lines.append(raw.decode(self.encoding, errors="replace"))
        return tuple(lines)

    def _native_event(
        self,
        path: Path,
        line: str,
    ) -> tuple[SessionStatus | None, str, datetime, dict[str, object] | None]:
        """Interpret native Codex rollout JSONL records."""

        now = datetime.now(UTC)
        try:
            record = json.loads(line)
        except (json.JSONDecodeError, TypeError):
            return None, "", now, None
        if not isinstance(record, dict):
            return None, "", now, None
        raw_timestamp = record.get("timestamp")
        if isinstance(raw_timestamp, str):
            try:
                candidate = raw_timestamp.replace("Z", "+00:00")
                now = datetime.fromisoformat(candidate).astimezone(UTC)
            except ValueError:
                pass
        payload = record.get("payload")
        if not isinstance(payload, dict):
            payload = {}
        record_type = str(record.get("type") or "")
        payload_type = str(payload.get("type") or "")

        if record_type == "session_meta":
            session_id = str(payload.get("id") or self._session_id(path))
            workspace = str(payload.get("cwd") or path.parent)
            self._metadata[path] = (session_id, workspace)
            return None, "", now, None

        if payload_type == "token_count":
            return None, "", now, self._usage(payload)

        if record_type == "response_item" and payload_type in {
            "function_call",
            "custom_tool_call",
        }:
            tool_name = str(payload.get("name") or "").casefold()
            activity = self._attention_activity(tool_name, payload)
            if activity:
                call_id = str(payload.get("call_id") or payload.get("id") or "")
                if call_id:
                    self._attention_calls.setdefault(path, {})[call_id] = activity
                return SessionStatus.NEEDS_YOU, activity, now, None
            return SessionStatus.WORKING, "Running Tool...", now, None

        if record_type == "response_item" and payload_type in {
            "function_call_output",
            "custom_tool_call_output",
        }:
            call_id = str(payload.get("call_id") or "")
            pending = self._attention_calls.get(path, {})
            if call_id:
                pending.pop(call_id, None)
            if pending:
                return (
                    SessionStatus.NEEDS_YOU,
                    next(iter(pending.values())),
                    now,
                    None,
                )
            return SessionStatus.WORKING, "Continuing...", now, None

        if record_type == "response_item" and payload_type == "message":
            role = str(payload.get("role") or "").casefold()
            if role == "user":
                self._awaiting_reply.discard(path)
                return SessionStatus.WORKING, "Reading reply...", now, None
            if role == "assistant" and self._message_needs_reply(payload):
                self._awaiting_reply.add(path)
                return SessionStatus.NEEDS_YOU, "Reply needed", now, None

        attention_types = {
            "apply_patch_approval_request",
            "exec_approval_request",
            "mcp_elicitation",
            "permission_request",
            "request_permissions",
            "request_user_input",
        }
        if payload_type in attention_types or "approval_request" in payload_type:
            return (
                SessionStatus.NEEDS_YOU,
                self._attention_activity(payload_type, payload) or "Approval needed",
                now,
                None,
            )
        if payload_type in {"task_complete", "turn_complete"}:
            pending = self._attention_calls.get(path, {})
            if pending:
                return (
                    SessionStatus.NEEDS_YOU,
                    next(iter(pending.values())),
                    now,
                    None,
                )
            if path in self._awaiting_reply:
                return SessionStatus.NEEDS_YOU, "Reply needed", now, None
            return SessionStatus.READY, "Codex is ready", now, None
        if payload_type == "turn_aborted":
            self._attention_calls.pop(path, None)
            self._awaiting_reply.discard(path)
            return SessionStatus.READY, "Codex is ready", now, None
        if payload_type == "task_started":
            self._attention_calls.pop(path, None)
            self._awaiting_reply.discard(path)
            return SessionStatus.WORKING, "Planning...", now, None
        if payload_type in {
            "agent_reasoning",
            "function_call",
            "reasoning",
            "tool_call",
        }:
            return SessionStatus.WORKING, "Reasoning...", now, None
        return None, "", now, None

    @staticmethod
    def _message_needs_reply(payload: dict[str, object]) -> bool:
        """Return whether an assistant message explicitly waits for an answer."""

        content = payload.get("content")
        if not isinstance(content, list):
            return False
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text.strip())
        message = "\n".join(part for part in parts if part).strip()
        if not message:
            return False
        if message.endswith("?"):
            return True
        return bool(
            re.search(
                r"(please (reply|respond|choose|select)|"
                r"reply with|let me know (which|whether|if))[^.]*[.!]?\s*$",
                message,
                re.IGNORECASE,
            )
        )

    @staticmethod
    def _attention_activity(
        name: str,
        payload: dict[str, object],
    ) -> str:
        """Return a concise activity label for a user-blocking Codex event."""

        normalized = name.casefold()
        if any(
            marker in normalized
            for marker in ("request_user_input", "ask_user", "elicitation")
        ):
            return "Reply needed"

        details = payload
        arguments = payload.get("arguments")
        if isinstance(arguments, str):
            try:
                decoded = json.loads(arguments)
                if isinstance(decoded, dict):
                    details = decoded
            except json.JSONDecodeError:
                pass
        serialized = json.dumps(details, default=str).casefold()

        requires_escalation = (
            isinstance(details, dict)
            and str(details.get("sandbox_permissions") or "").casefold()
            == "require_escalated"
            and bool(str(details.get("justification") or "").strip())
        )
        permission_markers = (
            "request_permissions",
            "permission_request",
            "approval_request",
        )
        if not requires_escalation and not any(
            marker in normalized for marker in permission_markers
        ):
            return ""
        if any(word in serialized for word in ('"network"', "internet", "wi-fi")):
            return "Network access needed"
        if any(
            word in serialized
            for word in ('"file_system"', "filesystem", '"read"', '"write"')
        ):
            return "File access needed"
        if "apply_patch" in normalized:
            return "File change approval"
        if requires_escalation or "exec" in normalized or "command" in serialized:
            return "Command approval needed"
        return "Permission needed"

    @staticmethod
    def _usage(payload: dict[str, object]) -> dict[str, object] | None:
        """Normalize native context and rate-limit data."""

        info = payload.get("info")
        rate_limits = payload.get("rate_limits")
        if not isinstance(info, dict) and not isinstance(rate_limits, dict):
            return None

        context_remaining: float | None = None
        if isinstance(info, dict):
            last_usage = info.get("last_token_usage")
            window = info.get("model_context_window")
            if isinstance(last_usage, dict):
                try:
                    used = float(last_usage.get("total_tokens", 0))
                    capacity = float(window)
                    if capacity > 0:
                        context_remaining = max(
                            0.0,
                            min(100.0, 100.0 * (capacity - used) / capacity),
                        )
                except (TypeError, ValueError, OverflowError):
                    context_remaining = None

        def limit(
            value: object,
        ) -> tuple[float | None, datetime | None]:
            if not isinstance(value, dict):
                return None, None
            try:
                remaining = max(
                    0.0,
                    min(100.0, 100.0 - float(value.get("used_percent", 0))),
                )
            except (TypeError, ValueError, OverflowError):
                remaining = None
            try:
                reset = datetime.fromtimestamp(
                    float(value.get("resets_at")),
                    tz=UTC,
                )
            except (TypeError, ValueError, OverflowError, OSError):
                reset = None
            return remaining, reset

        primary_remaining: float | None = None
        primary_reset: datetime | None = None
        secondary_remaining: float | None = None
        secondary_reset: datetime | None = None
        plan_type = ""
        if isinstance(rate_limits, dict):
            primary_remaining, primary_reset = limit(rate_limits.get("primary"))
            secondary_remaining, secondary_reset = limit(rate_limits.get("secondary"))
            plan_type = str(rate_limits.get("plan_type") or "")

        return {
            "context_remaining_percent": context_remaining,
            "rate_limit_remaining_percent": primary_remaining,
            "rate_limit_resets_at": primary_reset,
            "secondary_remaining_percent": secondary_remaining,
            "secondary_resets_at": secondary_reset,
            "plan_type": plan_type,
        }

    def poll(self) -> tuple[ProviderEvent, ...]:
        if self.stopped:
            return ()
        events: list[ProviderEvent] = []
        for path in self._files():
            try:
                stat = path.stat()
                identity = (int(stat.st_dev), int(stat.st_ino))
                cursor = self._cursors.get(path)
                if (
                    cursor is None
                    or cursor.identity != identity
                    or stat.st_size < cursor.offset
                ):
                    offset = stat.st_size if self.start_at_end and cursor is None else 0
                    cursor = _Cursor(identity=identity, offset=offset)
                    self._cursors[path] = cursor
                elif stat.st_size == cursor.offset:
                    continue
                lines = self._read_complete_lines(
                    path,
                    cursor,
                    file_size=stat.st_size,
                )
            except (OSError, LookupError) as error:
                events.append(self.fault(error))
                continue

            observed_at: datetime | None = None
            changed = False
            for line in lines:
                status, activity, now, usage = self._native_event(path, line)
                if status is None and path.suffix.casefold() != ".jsonl":
                    status = self._status(line)
                    activity = ""
                if status is None and usage is None:
                    continue
                session = self._sessions.get(path)
                session_id, workspace = self._metadata.get(
                    path,
                    (self._session_id(path), str(path.parent)),
                )
                if session is None:
                    session = CodexSession.create(
                        session_id,
                        workspace=workspace,
                        provider=self.name,
                        status=status or SessionStatus.WORKING,
                        now=now,
                        activity=activity or "Working...",
                    )
                elif status is not None:
                    session = session.transition(
                        status,
                        now=now,
                        provider=self.name,
                        activity=activity,
                    )
                if usage is not None:
                    session = session.with_usage(**usage, now=now)
                self._sessions[path] = session
                observed_at = now
                changed = True

            if changed:
                session = self._sessions[path]
                events.append(
                    SessionObservation.create(
                        self.name,
                        session,
                        occurred_at=observed_at,
                        sequence=self.next_sequence(),
                    )
                )
        return tuple(events)


__all__ = ["LogProvider"]
