"""ZG-14 错误升级梯测试 — 共享 fixture（时间注入）。"""

import pytest


class FakeClock:
    """可控时钟（time_func 注入点，控制窗口归零/风暴恢复）。"""

    def __init__(self, start: float = 0.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, delta: float) -> None:
        self.now += delta


@pytest.fixture
def fake_clock() -> FakeClock:
    return FakeClock()
