"""_StartupItemRegistry 单元测试。"""


import pytest

from src.core.startup.declaration import StartupItemDesc, _registry
from src.core.startup.types import StartupPhase


async def _noop_init() -> None:
    """空异步初始化函数。"""


def _make_desc(name: str) -> StartupItemDesc:
    return StartupItemDesc(
        name=name,
        phase=StartupPhase.CORE_SERVICES,
        init_fn=_noop_init,
    )


@pytest.fixture(autouse=True)
def _reset_registry() -> None:
    """每个用例前重置单例状态，避免用例间相互污染。"""
    _registry._items = {}
    _registry._running = False
    yield
    _registry._items = {}
    _registry._running = False


def test_register_then_drain_returns_all() -> None:
    """注册后 drain 返回全部已注册项。"""
    _registry.register(_make_desc("alpha"))
    _registry.register(_make_desc("beta"))

    assert _registry.drain() == {
        "alpha": _make_desc("alpha"),
        "beta": _make_desc("beta"),
    }


def test_duplicate_name_raises_value_error() -> None:
    """同名重复注册抛 ValueError。"""
    _registry.register(_make_desc("alpha"))

    with pytest.raises(ValueError):
        _registry.register(_make_desc("alpha"))


def test_register_after_drain_raises_runtime_error() -> None:
    """drain 后（_running=True）注册抛 RuntimeError。"""
    _registry.register(_make_desc("alpha"))
    _registry.drain()
    _registry._running = True

    with pytest.raises(RuntimeError):
        _registry.register(_make_desc("beta"))


def test_drain_clears_internal_storage() -> None:
    """drain 清空内部存储，二次 drain 返回空。"""
    _registry.register(_make_desc("alpha"))
    _registry.drain()

    assert _registry.drain() == {}


def test_empty_registry_drain_returns_empty() -> None:
    """空 registry drain 返回空 dict。"""
    assert _registry.drain() == {}
