"""ZG-27 测试：ProfileSnapshotShrinker count/scan（测试组 6——真实对象测试）。"""

import time

import pytest

from src.A_memorix.core.runtime.shrinker import ShrinkControl
from src.A_memorix.core.runtime.shrinkers.profile import ProfileSnapshotShrinker


class _FakeSnapshot:
    def __init__(self, expires_at, is_pinned=False):
        self.expires_at = expires_at
        self.is_pinned = is_pinned


class _FakeProfileService:
    def __init__(self, snapshots=None):
        self._snapshots = snapshots if snapshots is not None else {}

    def _is_snapshot_stale(self, snapshot):
        return snapshot.expires_at < time.monotonic()


@pytest.mark.asyncio
async def test_profile_count_stale():
    now = time.monotonic()
    snapshots = {
        "a": _FakeSnapshot(expires_at=now - 10),
        "b": _FakeSnapshot(expires_at=now + 100),
    }
    service = _FakeProfileService(snapshots)
    shrinker = ProfileSnapshotShrinker(service)
    sc = ShrinkControl()
    assert await shrinker.count_objects(sc) == 1


@pytest.mark.asyncio
async def test_profile_scan_deletes():
    now = time.monotonic()
    snapshots = {
        "a": _FakeSnapshot(expires_at=now - 10),
        "b": _FakeSnapshot(expires_at=now + 100),
    }
    service = _FakeProfileService(snapshots)
    shrinker = ProfileSnapshotShrinker(service)
    sc = ShrinkControl()
    freed = await shrinker.scan_objects(sc)
    assert freed == 1
    assert "a" not in snapshots