"""ZG-27 测试：CognitiveStateShrinker count/scan（测试组 6——真实对象测试）。"""

import time

import pytest

from src.A_memorix.core.runtime.shrinker import ShrinkControl
from src.A_memorix.core.runtime.shrinkers.cognitive import CognitiveStateShrinker


class _FakeStateEntry:
    def __init__(self, expires_at, is_pinned=False):
        self.expires_at = expires_at
        self.is_pinned = is_pinned
        self.status = "active"


class _FakeStratifier:
    def __init__(self, states=None):
        self._states = states if states is not None else {}

    def update_entry(self, key, status):
        self._states[key].status = status


@pytest.mark.asyncio
async def test_cognitive_count_expired():
    now = time.monotonic()
    states = {
        "a": _FakeStateEntry(expires_at=now - 10),
        "b": _FakeStateEntry(expires_at=now + 100),
    }
    stratifier = _FakeStratifier(states)
    shrinker = CognitiveStateShrinker(stratifier)
    sc = ShrinkControl()
    assert await shrinker.count_objects(sc) == 1


@pytest.mark.asyncio
async def test_cognitive_scan_resolves():
    now = time.monotonic()
    states = {
        "a": _FakeStateEntry(expires_at=now - 10),
        "b": _FakeStateEntry(expires_at=now + 100),
    }
    stratifier = _FakeStratifier(states)
    shrinker = CognitiveStateShrinker(stratifier)
    sc = ShrinkControl()
    freed = await shrinker.scan_objects(sc)
    assert freed == 1
    assert states["a"].status == "resolved"