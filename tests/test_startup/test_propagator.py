"""FailurePropagator 失败传播单元测试（ZG-10 T41）。"""

from src.core.service_manager.dependency_graph import DependencyGraph
from src.core.service_manager.types import DependencyKind, DependencyRelation
from src.core.startup.propagator import FailurePropagator
from src.core.startup.types import ComponentStatus


def _mk_graph(edges: list[tuple[str, str, DependencyKind]]) -> DependencyGraph:
    """构造依赖图：edges = (dependent, dependency, kind)。"""
    g = DependencyGraph()
    for dep, base, kind in edges:
        g.add_relation(DependencyRelation(dep, base, kind))
    return g


def _states(names: list[str]) -> dict[str, ComponentStatus]:
    return {n: ComponentStatus.PENDING for n in names}


class TestFailurePropagator:
    def test_strong_dependent_skipped(self) -> None:
        """B 失败 + A(STRONG on B) → A=SKIPPED，链 A→B。"""
        g = _mk_graph([("A", "B", DependencyKind.STRONG)])
        result = FailurePropagator().propagate("B", g, _states(["A", "B"]))
        assert result.state_updates == {"A": ComponentStatus.SKIPPED}
        assert result.failure_chains == {"A": "B"}

    def test_recursive_strong_propagation(self) -> None:
        """B 失败 + A(STRONG on B) + C(STRONG on A) → A/C 均 SKIPPED（递归）。"""
        g = _mk_graph([
            ("A", "B", DependencyKind.STRONG),
            ("C", "A", DependencyKind.STRONG),
        ])
        result = FailurePropagator().propagate("B", g, _states(["A", "B", "C"]))
        assert result.state_updates == {
            "A": ComponentStatus.SKIPPED,
            "C": ComponentStatus.SKIPPED,
        }
        assert result.failure_chains == {"A": "B", "C": "B"}

    def test_weak_dependent_degraded_no_recursion(self) -> None:
        """B 失败 + D(WEAK on B) → D=DEGRADED（不递归：E on D 不受影响）。"""
        g = _mk_graph([
            ("D", "B", DependencyKind.WEAK),
            ("E", "D", DependencyKind.STRONG),
        ])
        result = FailurePropagator().propagate("B", g, _states(["B", "D", "E"]))
        assert result.state_updates == {"D": ComponentStatus.DEGRADED}
        assert "E" not in result.state_updates

    def test_mixed_strong_wins(self) -> None:
        """A 同时 STRONG on B（失败）+ WEAK on C（失败）→ A=SKIPPED（STRONG 优先）。"""
        g = _mk_graph([
            ("A", "B", DependencyKind.STRONG),
            ("A", "C", DependencyKind.WEAK),
        ])
        result = FailurePropagator().propagate("B", g, _states(["A", "B", "C"]))
        assert result.state_updates["A"] == ComponentStatus.SKIPPED
        # WEAK 路径（C 失败）不应把 A 降为 DEGRADED
        assert result.state_updates["A"] is not ComponentStatus.DEGRADED

    def test_no_dependents_only_self(self) -> None:
        """无依赖方的失败项仅标记自身（无传播更新）。"""
        g = _mk_graph([])
        result = FailurePropagator().propagate("B", g, _states(["B"]))
        assert result.state_updates == {}
        assert result.failure_chains == {}

    def test_cycle_visited_guard(self) -> None:
        """环图 BFS visited 防环（不无限循环）。"""
        g = _mk_graph([
            ("A", "B", DependencyKind.STRONG),
            ("B", "A", DependencyKind.STRONG),
        ])
        result = FailurePropagator().propagate("B", g, _states(["A", "B"]))
        # A 被标记 SKIPPED；B 已在 visited（根）不重复
        assert result.state_updates == {"A": ComponentStatus.SKIPPED}

    def test_chains_record_full_path(self) -> None:
        """failure_chains 记录完整传播路径（多级均指向根因）。"""
        g = _mk_graph([
            ("A", "B", DependencyKind.STRONG),
            ("C", "A", DependencyKind.STRONG),
            ("D", "C", DependencyKind.WEAK),
        ])
        result = FailurePropagator().propagate("B", g, _states(["A", "B", "C", "D"]))
        assert result.failure_chains == {"A": "B", "C": "B", "D": "B"}
