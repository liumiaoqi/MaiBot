"""ResourceCounter 单元测试 — 对应 tasks §2.3。"""


import pytest

from src.core.resource_limit.resource_counter import ResourceCounter
from src.core.resource_limit.types import ChargeResult, ResourceDimension


class TestResourceCounter:
    """ResourceCounter 核心功能测试。"""

    def test_charge_single_node(self):
        """单节点充值成功。"""
        rc = ResourceCounter()
        rc.register_plugin("a")
        result = rc.charge("a", ResourceDimension.TOKEN, 10)
        assert result.accepted is True
        snap = rc.get_usage_snapshot("a")
        assert snap.token_usage == 10

    def test_charge_parent_chain(self):
        """父链向上传播（A→B→根，充值 A，B 和根均累加）。"""
        rc = ResourceCounter()
        rc.register_plugin("b")
        rc.register_plugin("a", parent_id="b")
        result = rc.charge("a", ResourceDimension.TOKEN, 10)
        assert result.accepted is True
        assert rc.get_usage_snapshot("a").token_usage == 10
        assert rc.get_usage_snapshot("b").token_usage == 10

    def test_charge_overflow_rollback(self):
        """超父级 max 回滚（A 充值致 B 超 max，A、B 均回滚）。"""
        def max_provider(plugin_id, dim):
            if plugin_id == "b" and dim == ResourceDimension.TOKEN:
                return 15
            return None

        rc = ResourceCounter(max_limit_provider=max_provider)
        rc.register_plugin("b")
        rc.register_plugin("a", parent_id="b")
        # 先充 10（B=10，未超 15）
        r1 = rc.charge("a", ResourceDimension.TOKEN, 10)
        assert r1.accepted is True
        # 再充 10（B=20，超 15，回滚）
        r2 = rc.charge("a", ResourceDimension.TOKEN, 10)
        assert r2.accepted is False
        assert r2.overflow_node_id == "b"
        # 回滚后 B 应为 10（不是 20）
        assert rc.get_usage_snapshot("b").token_usage == 10
        assert rc.get_usage_snapshot("a").token_usage == 10

    def test_charge_multi_dimension_independent(self):
        """四维度独立（超 token 不影响 message）。"""
        def max_provider(plugin_id, dim):
            if plugin_id == "a" and dim == ResourceDimension.TOKEN:
                return 10
            return None

        rc = ResourceCounter(max_limit_provider=max_provider)
        rc.register_plugin("a")
        rc.charge("a", ResourceDimension.TOKEN, 10)
        # token 超限不影响 message
        r = rc.charge("a", ResourceDimension.MESSAGE, 100)
        assert r.accepted is True
        assert rc.get_usage_snapshot("a").message_usage == 100

    def test_charge_non_negative(self):
        """回滚不致负值。"""
        rc = ResourceCounter()
        rc.register_plugin("a")
        rc.charge("a", ResourceDimension.TOKEN, 5)
        rc.uncharge("a", ResourceDimension.TOKEN, 100)
        assert rc.get_usage_snapshot("a").token_usage == 0

    def test_charge_orphan_reparented(self):
        """父链断裂孤儿挂根。"""
        rc = ResourceCounter()
        rc.register_plugin("parent")
        rc.register_plugin("child", parent_id="parent")
        rc.unregister_plugin("parent")
        # child 应挂根，仍可充值
        result = rc.charge("child", ResourceDimension.TOKEN, 5)
        assert result.accepted is True

    def test_charge_plugin_not_found(self):
        """未注册插件拒绝。"""
        rc = ResourceCounter()
        with pytest.raises(KeyError):
            rc.charge("nonexistent", ResourceDimension.TOKEN, 10)

    def test_charge_amount_zero_rejected(self):
        """非正充值量拒绝。"""
        rc = ResourceCounter()
        rc.register_plugin("a")
        with pytest.raises(ValueError):
            rc.charge("a", ResourceDimension.TOKEN, 0)

    def test_register_duplicate_rejected(self):
        """重复注册拒绝。"""
        rc = ResourceCounter()
        rc.register_plugin("a")
        with pytest.raises(ValueError):
            rc.register_plugin("a")

    def test_uncharge_parent_chain(self):
        """uncharge 沿父链递减。"""
        rc = ResourceCounter()
        rc.register_plugin("b")
        rc.register_plugin("a", parent_id="b")
        rc.charge("a", ResourceDimension.TOKEN, 20)
        rc.uncharge("a", ResourceDimension.TOKEN, 5)
        assert rc.get_usage_snapshot("a").token_usage == 15
        assert rc.get_usage_snapshot("b").token_usage == 15