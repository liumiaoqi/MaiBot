"""maisaka 测试目录的公共装配。

只做一件事：按**生产方式**接上 TokenMeter 单例。

TokenMeter 是 `@startup_item` 创建的单例（`src/main.py:768` 的 `_set_instance(TokenMeter())`），
消费方一律经 `get_token_meter()` 取。单独跑本目录时没有任何用例走启动路径，单例为空，
所有估算类调用都会拿到 `RuntimeError: TokenMeter 未接线`。

这里装配**真实实例**而不是 MagicMock：mock 能造出生产造不出的形状，本仓
`watchdog.runner_health` 那次事故就是这么被测试掩盖的（`AGENTS.md` §七）。
"""

import pytest

from src.core.token_meter import TokenMeter, _set_instance


@pytest.fixture(autouse=True)
def wire_token_meter():
    """每个用例前装配 TokenMeter 单例，结束后清空，避免跨文件污染。"""
    _set_instance(TokenMeter())
    yield
    _set_instance(None)  # type: ignore[arg-type]  # 清理用，生产路径不会传 None
