from pathlib import Path

import utils.sound as sound_module
from utils.sound import NotificationSound


def test_custom_sound_is_preferred(
    tmp_path: Path,
    monkeypatch,
) -> None:
    audio = tmp_path / "notification.mp3"
    audio.write_bytes(b"test")
    sound = NotificationSound(
        file_path=audio,
        minimum_interval_seconds=0,
    )
    calls: list[str] = []
    monkeypatch.setattr(sound_module.sys, "platform", "win32")
    monkeypatch.setattr(
        sound,
        "_play_file",
        lambda: calls.append("file") is None or True,
    )
    monkeypatch.setattr(
        sound,
        "_play_alias",
        lambda: calls.append("alias") is None or True,
    )

    assert sound.play()
    assert calls == ["file"]


def test_system_sound_is_the_fallback(
    tmp_path: Path,
    monkeypatch,
) -> None:
    audio = tmp_path / "notification.mp3"
    audio.write_bytes(b"test")
    sound = NotificationSound(
        file_path=audio,
        minimum_interval_seconds=0,
    )
    calls: list[str] = []
    monkeypatch.setattr(sound_module.sys, "platform", "win32")
    monkeypatch.setattr(
        sound,
        "_play_file",
        lambda: calls.append("file") is not None and False,
    )
    monkeypatch.setattr(
        sound,
        "_play_alias",
        lambda: calls.append("alias") is None or True,
    )

    assert sound.play()
    assert calls == ["file", "alias"]


def test_forced_sound_bypasses_rate_limit(monkeypatch) -> None:
    sound = NotificationSound(minimum_interval_seconds=60)
    calls: list[str] = []
    monkeypatch.setattr(sound_module.sys, "platform", "win32")
    monkeypatch.setattr(sound, "_play_file", lambda: False)
    monkeypatch.setattr(
        sound,
        "_play_alias",
        lambda: calls.append("alias") is None or True,
    )

    assert sound.play()
    assert not sound.play()
    assert sound.play(force=True)
    assert calls == ["alias", "alias"]


def test_macos_sound_uses_safe_afplay_fallback(tmp_path: Path, monkeypatch) -> None:
    audio = tmp_path / "sound.aiff"
    audio.write_bytes(b"test")
    calls: list[list[str]] = []

    class FakeProcess:
        pass

    monkeypatch.setattr(
        sound_module.subprocess,
        "Popen",
        lambda command, **kwargs: calls.append(command) or FakeProcess(),
    )
    assert NotificationSound._play_macos_path(audio)
    assert calls == [["/usr/bin/afplay", str(audio)]]
