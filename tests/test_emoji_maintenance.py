from pathlib import Path
from typing import Any

import asyncio
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.emoji_system import emoji_manager as emoji_module  # noqa: E402


class _Result:
    def __init__(self, records: list[Any]) -> None:
        self._records = records

    def all(self) -> list[Any]:
        return self._records


class _Session:
    def __init__(self, records: list[Any]) -> None:
        self.records = records
        self.deleted: list[Any] = []

    def __enter__(self) -> "_Session":
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> bool:
        return False

    def exec(self, _statement: Any) -> _Result:
        return _Result(self.records)

    def delete(self, record: Any) -> None:
        self.deleted.append(record)


def test_integrity_preserves_unknown_files_and_removes_known_orphans(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(emoji_module, "EMOJI_DIR", tmp_path)
    new_file = tmp_path / "new.png"
    known_orphan = tmp_path / "known.png"
    new_file.write_bytes(b"new")
    known_orphan.write_bytes(b"known")

    session = _Session(records=[])
    monkeypatch.setattr(emoji_module, "get_db_session", lambda: session)

    manager = emoji_module.EmojiManager()
    try:
        manager._known_emoji_file_paths = {known_orphan.absolute().resolve()}

        manager.check_emoji_file_integrity()

        assert new_file.exists()
        assert not known_orphan.exists()
    finally:
        manager.shutdown()


@pytest.mark.asyncio
async def test_periodic_maintenance_scans_unknown_files_before_integrity(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(emoji_module, "EMOJI_DIR", tmp_path)
    known_file = tmp_path / "known.png"
    new_file = tmp_path / "new.png"
    known_file.write_bytes(b"known")
    new_file.write_bytes(b"new")

    monkeypatch.setattr(emoji_module.global_config.emoji, "steal_emoji", True)
    monkeypatch.setattr(emoji_module.global_config.emoji, "check_interval", 0)
    monkeypatch.setattr(emoji_module.global_config.emoji, "max_reg_num", 10)
    monkeypatch.setattr(emoji_module.global_config.emoji, "do_replace", False)

    events: list[tuple[str, str]] = []
    first_check = asyncio.Event()

    manager = emoji_module.EmojiManager()
    manager._known_emoji_file_paths = {known_file.absolute().resolve()}

    async def _register_emoji_by_filename(path: Path | str) -> emoji_module.EmojiRegisterStatus:
        emoji_path = Path(path)
        events.append(("scan", emoji_path.name))
        registered_emoji = type("_Emoji", (), {"full_path": emoji_path.absolute().resolve()})()
        manager.emojis.append(registered_emoji)
        manager._emoji_num = len(manager.emojis)
        return "registered"

    def _check_emoji_file_integrity() -> None:
        events.append(("check", ""))
        first_check.set()

    monkeypatch.setattr(manager, "register_emoji_by_filename", _register_emoji_by_filename)
    monkeypatch.setattr(manager, "check_emoji_file_integrity", _check_emoji_file_integrity)

    task = asyncio.create_task(manager.periodic_emoji_maintenance())
    try:
        await asyncio.wait_for(first_check.wait(), timeout=1)
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        manager.shutdown()

    assert events[0] == ("scan", "new.png")
    assert events[1] == ("check", "")
    assert ("scan", "known.png") not in events
