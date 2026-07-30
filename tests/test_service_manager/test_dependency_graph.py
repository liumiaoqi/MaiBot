"""依赖图引擎单元测试。"""


import pytest

from src.core.service_manager.dependency_graph import DependencyGraph
from src.core.service_manager.exceptions import DependencyCycleError
from src.core.service_manager.types import DependencyKind, DependencyRelation


class TestTopologicalSort:
    """拓扑排序测试。"""

    def test_chain(self) -> None:
        """链式依赖 A←B←C（C 依赖 B，B 依赖 A）。"""
        g = DependencyGraph()
        g.add_relation(DependencyRelation("B", "A"))
        g.add_relation(DependencyRelation("C", "B"))
        result = g.topological_sort()
        assert result == ["A", "B", "C"]

    def test_branch(self) -> None:
        """分支依赖：B 依赖 A，C 依赖 A。"""
        g = DependencyGraph()
        g.add_relation(DependencyRelation("B", "A"))
        g.add_relation(DependencyRelation("C", "A"))
        result = g.topological_sort()
        assert result[0] == "A"
        assert set(result[1:]) == {"B", "C"}

    def test_independent_nodes(self) -> None:
        """独立多图。"""
        g = DependencyGraph()
        g.add_relation(DependencyRelation("B", "A"))
        g.add_relation(DependencyRelation("D", "C"))
        result = g.topological_sort()
        assert "A" in result and "B" in result and "C" in result and "D" in result
        assert result.index("A") < result.index("B")
        assert result.index("C") < result.index("D")

    def test_cache_invalidation(self) -> None:
        """add_relation 后缓存失效。"""
        g = DependencyGraph()
        g.add_relation(DependencyRelation("B", "A"))
        first = g.topological_sort()
        g.add_relation(DependencyRelation("C", "B"))
        second = g.topological_sort()
        assert first == ["A", "B"]
        assert second == ["A", "B", "C"]


class TestCycleDetection:
    """环检测测试。"""

    def test_no_cycle(self) -> None:
        g = DependencyGraph()
        g.add_relation(DependencyRelation("B", "A"))
        assert g.detect_cycle() is None

    def test_two_node_cycle(self) -> None:
        g = DependencyGraph()
        g.add_relation(DependencyRelation("A", "B"))
        g.add_relation(DependencyRelation("B", "A"))
        cycle = g.detect_cycle()
        assert cycle is not None
        assert set(cycle) == {"A", "B"}

    def test_three_node_cycle(self) -> None:
        g = DependencyGraph()
        g.add_relation(DependencyRelation("B", "A"))
        g.add_relation(DependencyRelation("C", "B"))
        g.add_relation(DependencyRelation("A", "C"))
        cycle = g.detect_cycle()
        assert cycle is not None
        assert set(cycle) == {"A", "B", "C"}

    def test_cycle_raises_on_topo_sort(self) -> None:
        g = DependencyGraph()
        g.add_relation(DependencyRelation("A", "B"))
        g.add_relation(DependencyRelation("B", "A"))
        with pytest.raises(DependencyCycleError) as exc_info:
            g.topological_sort()
        assert exc_info.value.cycle is not None


class TestCascadeStopOrder:
    """级联停止顺序测试。"""

    def test_strong_dependency(self) -> None:
        """B 强依赖 A，停 A 时 B 级联停止。"""
        g = DependencyGraph()
        g.add_relation(DependencyRelation("B", "A", DependencyKind.STRONG))
        strong, weak = g.cascade_stop_order("A")
        assert strong == ["B"]
        assert weak == []

    def test_weak_dependency(self) -> None:
        """C 弱依赖 A，停 A 时 C 降级。"""
        g = DependencyGraph()
        g.add_relation(DependencyRelation("C", "A", DependencyKind.WEAK))
        strong, weak = g.cascade_stop_order("A")
        assert strong == []
        assert weak == ["C"]

    def test_mixed(self) -> None:
        """B 强依赖 A，C 弱依赖 A。"""
        g = DependencyGraph()
        g.add_relation(DependencyRelation("B", "A", DependencyKind.STRONG))
        g.add_relation(DependencyRelation("C", "A", DependencyKind.WEAK))
        strong, weak = g.cascade_stop_order("A")
        assert strong == ["B"]
        assert weak == ["C"]

    def test_transitive_strong(self) -> None:
        """D 强依赖 B，B 强依赖 A，停 A 时 D 和 B 都级联停止。"""
        g = DependencyGraph()
        g.add_relation(DependencyRelation("B", "A", DependencyKind.STRONG))
        g.add_relation(DependencyRelation("D", "B", DependencyKind.STRONG))
        strong, weak = g.cascade_stop_order("A")
        assert set(strong) == {"B", "D"}
        # D 应在 B 之前（拓扑序逆序，依赖方先停）
        assert strong.index("D") < strong.index("B")

    def test_no_dependents(self) -> None:
        """A 无依赖方。"""
        g = DependencyGraph()
        g.add_relation(DependencyRelation("B", "A"))
        strong, weak = g.cascade_stop_order("B")
        assert strong == []
        assert weak == []


class TestCascadeStartOrder:
    """级联启动顺序测试。"""

    def test_direct_dependency(self) -> None:
        """B 依赖 A，启动 B 时需校验 A 就绪。"""
        g = DependencyGraph()
        g.add_relation(DependencyRelation("B", "A"))
        result = g.cascade_start_order("B")
        assert result == ["A"]

    def test_transitive(self) -> None:
        """C 依赖 B，B 依赖 A，启动 C 时需校验 A 和 B。"""
        g = DependencyGraph()
        g.add_relation(DependencyRelation("B", "A"))
        g.add_relation(DependencyRelation("C", "B"))
        result = g.cascade_start_order("C")
        assert result == ["A", "B"]

    def test_no_dependencies(self) -> None:
        """A 无依赖。"""
        g = DependencyGraph()
        g.add_relation(DependencyRelation("B", "A"))
        result = g.cascade_start_order("A")
        assert result == []


class TestQueryMethods:
    """查询方法测试。"""

    def test_dependents_of(self) -> None:
        g = DependencyGraph()
        g.add_relation(DependencyRelation("B", "A"))
        g.add_relation(DependencyRelation("C", "A"))
        assert g.dependents_of("A") == {"B", "C"}
        assert g.dependents_of("B") == set()

    def test_dependencies_of(self) -> None:
        g = DependencyGraph()
        g.add_relation(DependencyRelation("B", "A"))
        g.add_relation(DependencyRelation("B", "C"))
        assert g.dependencies_of("B") == {"A", "C"}
        assert g.dependencies_of("A") == set()

    def test_dependencies_with_kind(self) -> None:
        g = DependencyGraph()
        g.add_relation(DependencyRelation("B", "A", DependencyKind.STRONG))
        g.add_relation(DependencyRelation("B", "C", DependencyKind.WEAK))
        result = g.dependencies_with_kind("B")
        assert result["A"] == DependencyKind.STRONG
        assert result["C"] == DependencyKind.WEAK