import json
from pathlib import Path

import pytest

from backend.providers.log_provider import LogProvider
from models.events import SessionObservation
from models.session import SessionStatus


def _provider(path: Path) -> LogProvider:
    return LogProvider(
        (str(path),),
        ready_patterns=(r"idle",),
        working_patterns=(r"thinking",),
        needs_you_patterns=(r"approval required",),
        start_at_end=False,
    )


def test_log_provider_tracks_incremental_state(tmp_path: Path) -> None:
    log = tmp_path / "codex.log"
    log.write_text("thinking\n", encoding="utf-8")
    provider = _provider(log)
    first = provider.poll()
    observations = [event for event in first if isinstance(event, SessionObservation)]
    assert observations[-1].session.status is SessionStatus.WORKING

    with log.open("a", encoding="utf-8") as stream:
        stream.write("approval required\n")
    second = provider.poll()
    observation = next(
        event for event in second if isinstance(event, SessionObservation)
    )
    assert observation.session.status is SessionStatus.NEEDS_YOU


def test_log_rotation_resets_cursor(tmp_path: Path) -> None:
    log = tmp_path / "codex.log"
    log.write_text("thinking\n", encoding="utf-8")
    provider = _provider(log)
    provider.poll()
    log.write_text("idle\n", encoding="utf-8")
    events = provider.poll()
    observation = next(
        event for event in events if isinstance(event, SessionObservation)
    )
    assert observation.session.status is SessionStatus.READY


def test_poll_coalesces_many_records_into_one_observation(tmp_path: Path) -> None:
    log = tmp_path / "codex.log"
    log.write_text(
        "thinking\napproval required\nidle\n",
        encoding="utf-8",
    )
    provider = _provider(log)

    observations = [
        event for event in provider.poll() if isinstance(event, SessionObservation)
    ]

    assert len(observations) == 1
    assert observations[0].session.status is SessionStatus.READY


def test_partial_jsonl_record_is_not_consumed(tmp_path: Path) -> None:
    log = tmp_path / "rollout-partial.jsonl"
    log.write_text(
        '{"timestamp":"2026-07-25T00:00:00Z","type":"event_msg",',
        encoding="utf-8",
    )
    provider = LogProvider(
        (str(log),),
        ready_patterns=(),
        working_patterns=(),
        needs_you_patterns=(),
        start_at_end=False,
    )

    assert provider.poll() == ()
    assert provider._cursors[log].offset == 0

    with log.open("a", encoding="utf-8") as stream:
        stream.write('"payload":{"type":"task_complete"}}\n')

    observations = [
        event for event in provider.poll() if isinstance(event, SessionObservation)
    ]
    assert len(observations) == 1
    assert observations[0].session.status is SessionStatus.READY


def test_log_backlog_is_read_in_bounded_batches(tmp_path: Path) -> None:
    log = tmp_path / "codex.log"
    log.write_text("thinking\n" * 2_000, encoding="utf-8")
    provider = LogProvider(
        (str(log),),
        ready_patterns=(r"idle",),
        working_patterns=(r"thinking",),
        needs_you_patterns=(r"approval required",),
        start_at_end=False,
        maximum_read_bytes=4_096,
        maximum_line_bytes=256,
    )

    first = provider.poll()
    first_offset = provider._cursors[log].offset

    assert len([event for event in first if isinstance(event, SessionObservation)]) == 1
    assert 0 < first_offset <= 4_096
    assert first_offset < log.stat().st_size

    for _ in range(100):
        provider.poll()
        if provider._cursors[log].offset == log.stat().st_size:
            break
    assert provider._cursors[log].offset == log.stat().st_size


def test_unchanged_log_is_not_reopened(tmp_path: Path, monkeypatch) -> None:
    log = tmp_path / "codex.log"
    log.write_text("thinking\n", encoding="utf-8")
    provider = _provider(log)
    provider.poll()

    def unexpected_read(*args, **kwargs):
        del args, kwargs
        raise AssertionError("unchanged log should not be reopened")

    monkeypatch.setattr(provider, "_read_complete_lines", unexpected_read)

    assert provider.poll() == ()


def test_native_token_count_exposes_usage(tmp_path: Path) -> None:
    log = tmp_path / "rollout-test.jsonl"
    records = [
        {
            "timestamp": "2026-07-25T00:00:00Z",
            "type": "session_meta",
            "payload": {"id": "native-1", "cwd": str(tmp_path)},
        },
        {
            "timestamp": "2026-07-25T00:00:01Z",
            "type": "event_msg",
            "payload": {"type": "task_started"},
        },
        {
            "timestamp": "2026-07-25T00:00:02Z",
            "type": "event_msg",
            "payload": {
                "type": "token_count",
                "info": {
                    "last_token_usage": {"total_tokens": 25_000},
                    "model_context_window": 100_000,
                },
                "rate_limits": {
                    "primary": {
                        "used_percent": 20,
                        "resets_at": 1_900_000_000,
                    },
                    "secondary": {
                        "used_percent": 35,
                        "resets_at": 1_900_100_000,
                    },
                    "plan_type": "test",
                },
            },
        },
    ]
    log.write_text(
        "\n".join(json.dumps(record) for record in records),
        encoding="utf-8",
    )
    provider = LogProvider(
        (str(log),),
        ready_patterns=(),
        working_patterns=(),
        needs_you_patterns=(),
        start_at_end=False,
    )
    observations = [
        event for event in provider.poll() if isinstance(event, SessionObservation)
    ]
    session = observations[-1].session
    assert session.context_remaining_percent == 75
    assert session.rate_limit_remaining_percent == 80
    assert session.secondary_remaining_percent == 65
    assert session.plan_type == "test"


@pytest.mark.parametrize(
    ("tool_name", "arguments", "expected_activity"),
    (
        (
            "request_permissions",
            {"permissions": {"network": {"enabled": True}}},
            "Network access needed",
        ),
        (
            "request_permissions",
            {"permissions": {"file_system": {"write": ["C:/outside"]}}},
            "File access needed",
        ),
        (
            "request_user_input",
            {"questions": [{"question": "Which design do you want?"}]},
            "Reply needed",
        ),
        (
            "shell_command",
            {
                "command": "example-command",
                "sandbox_permissions": "require_escalated",
                "justification": "May I run the requested command?",
            },
            "Command approval needed",
        ),
    ),
)
def test_native_attention_tool_calls_need_user(
    tmp_path: Path,
    tool_name: str,
    arguments: dict[str, object],
    expected_activity: str,
) -> None:
    log = tmp_path / "rollout-attention.jsonl"
    records = [
        {
            "timestamp": "2026-07-25T00:00:00Z",
            "type": "session_meta",
            "payload": {"id": "native-attention", "cwd": str(tmp_path)},
        },
        {
            "timestamp": "2026-07-25T00:00:01Z",
            "type": "response_item",
            "payload": {
                "type": "function_call",
                "name": tool_name,
                "arguments": json.dumps(arguments),
                "call_id": "attention-call",
            },
        },
    ]
    log.write_text(
        "\n".join(json.dumps(record) for record in records),
        encoding="utf-8",
    )
    provider = _provider(log)
    observations = [
        event for event in provider.poll() if isinstance(event, SessionObservation)
    ]
    assert observations[-1].session.status is SessionStatus.NEEDS_YOU
    assert observations[-1].session.activity == expected_activity


def test_native_normal_shell_command_stays_working(tmp_path: Path) -> None:
    log = tmp_path / "rollout-normal-command.jsonl"
    record = {
        "timestamp": "2026-07-25T00:00:00Z",
        "type": "response_item",
        "payload": {
            "type": "function_call",
            "name": "shell_command",
            "arguments": json.dumps({"command": "example-command"}),
            "call_id": "normal-command",
        },
    }
    log.write_text(json.dumps(record), encoding="utf-8")
    provider = _provider(log)

    observations = [
        event for event in provider.poll() if isinstance(event, SessionObservation)
    ]

    assert observations[-1].session.status is SessionStatus.WORKING


def test_permission_output_returns_to_working(tmp_path: Path) -> None:
    log = tmp_path / "rollout-permission.jsonl"
    request = {
        "timestamp": "2026-07-25T00:00:00Z",
        "type": "response_item",
        "payload": {
            "type": "function_call",
            "name": "request_permissions",
            "arguments": json.dumps({"permissions": {"network": {"enabled": True}}}),
            "call_id": "permission-call",
        },
    }
    log.write_text(json.dumps(request), encoding="utf-8")
    provider = _provider(log)
    requested = [
        event for event in provider.poll() if isinstance(event, SessionObservation)
    ]
    assert requested[-1].session.status is SessionStatus.NEEDS_YOU

    output = {
        "timestamp": "2026-07-25T00:00:01Z",
        "type": "response_item",
        "payload": {
            "type": "function_call_output",
            "call_id": "permission-call",
            "output": '{"permissions":{"network":{"enabled":true}}}',
        },
    }
    with log.open("a", encoding="utf-8") as stream:
        stream.write(f"\n{json.dumps(output)}")
    continued = [
        event for event in provider.poll() if isinstance(event, SessionObservation)
    ]
    assert continued[-1].session.status is SessionStatus.WORKING


def test_assistant_question_stays_needs_you_until_reply(tmp_path: Path) -> None:
    log = tmp_path / "rollout-question.jsonl"
    records = [
        {
            "timestamp": "2026-07-25T00:00:00Z",
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "assistant",
                "content": [
                    {
                        "type": "output_text",
                        "text": "Do you want the program to be compact?",
                    }
                ],
            },
        },
        {
            "timestamp": "2026-07-25T00:00:01Z",
            "type": "event_msg",
            "payload": {"type": "turn_complete"},
        },
    ]
    log.write_text(
        "\n".join(json.dumps(record) for record in records),
        encoding="utf-8",
    )
    provider = _provider(log)
    waiting = [
        event for event in provider.poll() if isinstance(event, SessionObservation)
    ]
    assert waiting[-1].session.status is SessionStatus.NEEDS_YOU
    assert waiting[-1].session.activity == "Reply needed"

    reply = {
        "timestamp": "2026-07-25T00:00:02Z",
        "type": "response_item",
        "payload": {
            "type": "message",
            "role": "user",
            "content": [{"type": "input_text", "text": "Yes, compact."}],
        },
    }
    with log.open("a", encoding="utf-8") as stream:
        stream.write(f"\n{json.dumps(reply)}")
    continued = [
        event for event in provider.poll() if isinstance(event, SessionObservation)
    ]
    assert continued[-1].session.status is SessionStatus.WORKING


def test_plain_text_question_is_needs_you(tmp_path: Path) -> None:
    log = tmp_path / "codex.log"
    log.write_text(
        "Do you want the program to be compact?\n",
        encoding="utf-8",
    )
    provider = _provider(log)
    observations = [
        event for event in provider.poll() if isinstance(event, SessionObservation)
    ]
    assert observations[-1].session.status is SessionStatus.NEEDS_YOU
