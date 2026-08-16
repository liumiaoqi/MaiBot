"""ZG16-6a: SDK ctx.config 测试——ConfigContext get/watch/update/revision。

覆盖 design 4.3 全部 11 个场景。
"""

from unittest.mock import AsyncMock


from src.plugin_runtime_v2.sdk.context import ConfigContext


def _make_mock_endpoint():
    """构造 mock RunnerEndpoint。"""
    endpoint = AsyncMock()
    return endpoint


def test_get_returns_merged_config():
    """get 返回合并后配置（spec 5.2.1 规则 2）。"""
    ctx = ConfigContext("X", _make_mock_endpoint())
    ctx._apply_update({"port": 3002}, 1)
    assert ctx.get()["port"] == 3002


def test_get_empty_before_ready():
    """配置未就绪返回空 dict（spec 5.2.3 场景 3）。"""
    ctx = ConfigContext("X", _make_mock_endpoint())
    assert ctx.get() == {}


def test_watch_register_and_cancel():
    """watch 注册 + 取消（spec 5.2.1 规则 4）。"""
    ctx = ConfigContext("X", _make_mock_endpoint())
    calls = []
    unsubscribe = ctx.watch(lambda new, prev: calls.append((new, prev)))
    ctx._apply_update({"port": 3002}, 1)
    assert len(calls) == 1
    unsubscribe()
    ctx._apply_update({"port": 3003}, 2)
    assert len(calls) == 1  # 取消后不再调用


def test_revision_property():
    """revision 查询（spec 5.4.1 规则 5b）。"""
    ctx = ConfigContext("X", _make_mock_endpoint())
    ctx._apply_update({"port": 3002}, 5)
    assert ctx.revision == 5


def test_revision_default_zero():
    """初始 revision 为 0。"""
    ctx = ConfigContext("X", _make_mock_endpoint())
    assert ctx.revision == 0


async def test_update_calls_endpoint():
    """update 发起 gRPC 请求到 Host（spec 5.2.1 规则 3）。"""
    endpoint = _make_mock_endpoint()
    ctx = ConfigContext("X", endpoint)
    await ctx.update({"port": 3002})
    endpoint.update_plugin_config.assert_called_once_with("X", {"port": 3002})


def test_watch_callback_receives_new_and_prev():
    """watch callback 接收 (new_config, prev_config)。"""
    ctx = ConfigContext("X", _make_mock_endpoint())
    calls = []
    ctx.watch(lambda new, prev: calls.append((new, prev)))
    ctx._apply_update({"port": 3001}, 1)
    ctx._apply_update({"port": 3002}, 2)
    assert calls[0] == ({"port": 3001}, {})
    assert calls[1] == ({"port": 3002}, {"port": 3001})


def test_watch_multiple_callbacks_fanout():
    """多个 watch callback 均被调用（spec 5.3.1 规则 9）。"""
    ctx = ConfigContext("X", _make_mock_endpoint())
    calls_a = []
    calls_b = []
    calls_c = []
    ctx.watch(lambda new, prev: calls_a.append(1))
    ctx.watch(lambda new, prev: calls_b.append(1))
    ctx.watch(lambda new, prev: calls_c.append(1))
    ctx._apply_update({"port": 3002}, 1)
    assert len(calls_a) == 1 and len(calls_b) == 1 and len(calls_c) == 1


def test_watch_callback_exception_not_crash():
    """watch callback 异常不崩溃（spec 5.3.3 场景 3）。"""
    ctx = ConfigContext("X", _make_mock_endpoint())

    def bad_callback(new, prev):
        raise RuntimeError("callback error")

    good_calls = []
    ctx.watch(bad_callback)
    ctx.watch(lambda new, prev: good_calls.append(1))
    # 异常 callback 不影响其他 callback
    ctx._apply_update({"port": 3002}, 1)
    assert len(good_calls) == 1


def test_get_does_not_trigger_grpc():
    """get 不触发 gRPC 请求（内存读取，spec 5.2.1 规则 2）。"""
    endpoint = _make_mock_endpoint()
    ctx = ConfigContext("X", endpoint)
    ctx._apply_update({"port": 3002}, 1)
    ctx.get()
    ctx.get()
    endpoint.update_plugin_config.assert_not_called()


def test_apply_update_sets_ready():
    """_apply_update 后配置就绪。"""
    ctx = ConfigContext("X", _make_mock_endpoint())
    assert ctx._ready is False
    ctx._apply_update({"port": 3002}, 1)
    assert ctx._ready is True


def test_watch_unsubscribe_idempotent():
    """取消订阅可多次调用不抛异常。"""
    ctx = ConfigContext("X", _make_mock_endpoint())
    calls = []
    unsubscribe = ctx.watch(lambda new, prev: calls.append(1))
    unsubscribe()
    unsubscribe()  # 再次取消不抛异常
    ctx._apply_update({"port": 3002}, 1)
    assert len(calls) == 0