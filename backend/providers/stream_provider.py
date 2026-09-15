"""Non-blocking stdin/stdout event adapter."""

from __future__ import annotations

import json
import queue

from backend.providers.base import SessionProvider
from models.events import ProviderEvent, SessionObservation
from models.session import CodexSession, SessionStatus


class StreamProvider(SessionProvider):
    """Accept lines from an external reader and parse them during polling."""

    def __init__(self, *, maximum_line_bytes: int = 1_048_576) -> None:
        super().__init__("stream")
        self.maximum_line_bytes = maximum_line_bytes
        self._lines: queue.SimpleQueue[bytes] = queue.SimpleQueue()
        self._sessions: dict[str, CodexSession] = {}

    def feed(self, line: str | bytes) -> bool:
        encoded = line.encode("utf-8") if isinstance(line, str) else line
        if len(encoded) > self.maximum_line_bytes:
            return False
        self._lines.put(encoded)
        return True

    def poll(self) -> tuple[ProviderEvent, ...]:
        events: list[ProviderEvent] = []
        while not self.stopped:
            try:
                raw = self._lines.get_nowait()
            except queue.Empty:
                break
            try:
                payload = json.loads(raw.decode("utf-8-sig"))
                if not isinstance(payload, dict):
                    raise TypeError("stream event must be a JSON object")
                session = CodexSession.from_dict(payload, default_provider=self.name)
                self._sessions[session.session_id] = session
                events.append(
                    SessionObservation.create(
                        self.name,
                        session,
                        sequence=self.next_sequence(),
                    )
                )
            except (UnicodeError, json.JSONDecodeError, ValueError, TypeError) as error:
                text = raw.decode("utf-8", errors="replace").strip()
                parts = text.split("|", 2)
                if len(parts) == 3:
                    session_id, status_text, workspace = parts
                    try:
                        status = SessionStatus.parse(status_text)
                        prior = self._sessions.get(session_id)
                        session = (
                            prior.transition(status)
                            if prior
                            else CodexSession.create(
                                session_id,
                                workspace=workspace,
                                status=status,
                                provider=self.name,
                            )
                        )
                        self._sessions[session_id] = session
                        events.append(
                            SessionObservation.create(
                                self.name,
                                session,
                                sequence=self.next_sequence(),
                            )
                        )
                        continue
                    except ValueError:
                        pass
                events.append(self.fault(error))
        return tuple(events)


__all__ = ["StreamProvider"]
