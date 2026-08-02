"""T23 契约测试 — ControlMessagePort Protocol 接口契约（design §10.4）。"""

import inspect

from src.core.adapters.control_message_adapter import ControlMessageAdapter
from src.core.protocols import ControlMessagePort

# design §10.4：ControlMessagePort 全部 14 个方法
EXPECTED_METHODS = (
    "send",
    "force_send",
    "dequeue_next",
    "set_blocked",
    "set_ignored",
    "get_effective_mask",
    "declare_unkillable",
    "clear_unkillable",
    "list_unkillable_entities",
    "on_session_created",
    "on_session_destroyed",
    "get_pending_view",
    "get_delivery_history",
    "get_diffuse_history",
)


def _make_adapter() -> ControlMessageAdapter:
    return ControlMessageAdapter()


class TestContract:
    def test_isinstance_runtime_check(self) -> None:
        """isinstance(adapter, ControlMessagePort) == True（spec §7.1 微内核隔离）。"""
        assert isinstance(_make_adapter(), ControlMessagePort)

    def test_all_methods_present(self) -> None:
        """全部 14 个方法存在且可调用（design §10.4）。"""
        adapter = _make_adapter()
        for method in EXPECTED_METHODS:
            assert hasattr(adapter, method), f"缺失方法: {method}"
            assert callable(getattr(adapter, method))

    def test_protocol_method_signatures(self) -> None:
        """方法签名与 Protocol 定义一致（参数名/参数个数）。"""
        adapter = _make_adapter()
        for method in EXPECTED_METHODS:
            protocol_sig = inspect.signature(getattr(ControlMessagePort, method))
            impl_sig = inspect.signature(getattr(type(adapter), method))
            protocol_params = [
                p for p in protocol_sig.parameters.values() if p.name != "self"
            ]
            impl_params = [p for p in impl_sig.parameters.values() if p.name != "self"]
            assert len(impl_params) == len(protocol_params), (
                f"{method} 参数个数不符: protocol={len(protocol_params)} impl={len(impl_params)}"
            )
            for p_proto, p_impl in zip(protocol_params, impl_params, strict=True):
                assert p_impl.name == p_proto.name, (
                    f"{method} 参数名不符: {p_proto.name} vs {p_impl.name}"
                )

    def test_hot_path_sync_async_annotation(self) -> None:
        """热路径标注：send/force_send 为 async，dequeue_next 为同步（design §4.1）。"""
        adapter = _make_adapter()
        import asyncio

        assert asyncio.iscoroutinefunction(adapter.send)
        assert asyncio.iscoroutinefunction(adapter.force_send)
        assert not asyncio.iscoroutinefunction(adapter.dequeue_next)
