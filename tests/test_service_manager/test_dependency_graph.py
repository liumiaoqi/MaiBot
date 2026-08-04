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

class TestAddNode:
    """add_node 独立节点（ZG-10 T8）。"""

    def test_add_independent_node(self) -> None:
        """无依赖边节点加入图并出现在拓扑序。"""
        g = DependencyGraph()
        g.add_node("image_port")
        assert "image_port" in g._all_nodes()
        assert "image_port" in g.topological_sort()

    def test_add_node_idempotent(self) -> None:
        """重复 add_node 同一 ID 不报错。"""
        g = DependencyGraph()
        g.add_node("x")
        g.add_node("x")
        assert "x" in g._all_nodes()

    def test_add_node_invalidates_cache(self) -> None:
        """add_node 后拓扑缓存失效。"""
        g = DependencyGraph()
        g.add_relation(DependencyRelation("B", "A"))
        assert g.topological_sort() == ["A", "B"]
        g.add_node("C")
        assert "C" in g.topological_sort()


class TestComputeWaves:
    """compute_waves 零入度分波（ZG-10 T9）。"""

    def test_chain_waves(self) -> None:
        """线性链 A←B←C → 3 波次 [A],[B],[C]。"""
        g = DependencyGraph()
        g.add_relation(DependencyRelation("B", "A"))
        g.add_relation(DependencyRelation("C", "B"))
        assert g.compute_waves() == [["A"], ["B"], ["C"]]

    def test_diamond_waves(self) -> None:
        """菱形：B/C 依赖 A，D 依赖 B/C → [A],[B,C],[D]。"""
        g = DependencyGraph()
        g.add_relation(DependencyRelation("B", "A"))
        g.add_relation(DependencyRelation("C", "A"))
        g.add_relation(DependencyRelation("D", "B"))
        g.add_relation(DependencyRelation("D", "C"))
        assert g.compute_waves() == [["A"], ["B", "C"], ["D"]]

    def test_wave_alpha_order(self) -> None:
        """同波次内按字母序：C/B 依赖 A → 波次 1 为 [B, C]。"""
        g = DependencyGraph()
        g.add_relation(DependencyRelation("C", "A"))
        g.add_relation(DependencyRelation("B", "A"))
        assert g.compute_waves() == [["A"], ["B", "C"]]

    def test_node_filter_subset(self) -> None:
        """node_filter 子集：子集外节点视为已完成，其出边不贡献入度。"""
        g = DependencyGraph()
        g.add_relation(DependencyRelation("B", "A"))
        g.add_relation(DependencyRelation("C", "B"))
        # 子集 {A, C}：A 依赖 B（B 不在子集，不算）；C 依赖 B（同上）→ 两者零入度
        assert g.compute_waves(node_filter={"A", "C"}) == [["A", "C"]]

    def test_cycle_raises(self) -> None:
        """环图抛 DependencyCycleError。"""
        g = DependencyGraph()
        g.add_relation(DependencyRelation("B", "A"))
        g.add_relation(DependencyRelation("A", "B"))
        with pytest.raises(DependencyCycleError):
            g.compute_waves()

    def test_empty_graph(self) -> None:
        """空图返回空列表。"""
        assert DependencyGraph().compute_waves() == []

    def test_real_33_components(self) -> None:
        """33 组件 + 19 条真实依赖边 → 6 波次（与原型实验一致）。"""
        edges = [
            ("replyer_port", "chat_manager_adapter"),
            ("replyer_port", "agent_registry"),
            ("session_lifecycle", "chat_manager_adapter"),
            ("interaction_scheduler", "message_handlers"),
            ("message_ingestion_port", "chat_manager_adapter"),
            ("memory_automation", "a_memorix"),
            ("emoji_manager", "llm_service_port"),
            ("plugin_runtime", "llm_service_port"),
            ("plugin_runtime_v2", "llm_service_port"),
            ("session_submodules", "agent_registry"),
            ("chat_manager_adapter", "session_submodules"),
            ("chat_manager_adapter", "agent_registry"),
            ("model_config_port", "agent_registry"),
            ("ipc_bridge_port", "plugin_runtime"),
            ("a_memorix", "model_config_port_inject"),
            ("a_memorix", "model_config_port"),
            ("interaction_scheduler", "a_memorix"),
            ("plugin_runtime_v2", "app_config_port"),
            ("message_handlers", "message_ingestion_port"),
        ]
        all_items = [
            "config_manager", "config_validator", "file_watcher", "tool_record_vacuum",
            "agent_registry", "session_submodules", "chat_manager_adapter", "replyer_port",
            "image_port", "runtime_port", "model_config_port", "llm_service_port",
            "message_ingestion_port", "person_info_port", "bot_config_port", "chat_config_port",
            "app_config_port", "event_bus_port", "prompt_manager", "message_port_v2",
            "plugin_runtime", "ipc_bridge_port", "plugin_runtime_v2", "emoji_manager",
            "model_config_port_inject", "a_memorix", "session_lifecycle", "memory_automation",
            "message_handlers", "on_start_event", "webui_server", "scheduled_tasks",
            "interaction_scheduler",
        ]
        g = DependencyGraph()
        for n in all_items:
            g.add_node(n)
        for dep, base in edges:
            g.add_relation(DependencyRelation(dep, base))
        waves = g.compute_waves()
        assert len(waves) == 6  # 与原型实验一致
        flat = [n for wave in waves for n in wave]
        assert set(flat) == set(all_items)

    def test_real_subsystems_two_waves(self) -> None:
        """SUBSYSTEMS 6 组件补边后 2 波次（与原型实验一致）。"""
        g = DependencyGraph()
        subs = {"plugin_runtime", "ipc_bridge_port", "plugin_runtime_v2",
                "emoji_manager", "model_config_port_inject", "a_memorix"}
        for n in subs:
            g.add_node(n)
        g.add_relation(DependencyRelation("ipc_bridge_port", "plugin_runtime"))
        g.add_relation(DependencyRelation("a_memorix", "model_config_port_inject"))
        g.add_relation(DependencyRelation("a_memorix", "model_config_port"))
        g.add_relation(DependencyRelation("plugin_runtime_v2", "app_config_port"))
        g.add_relation(DependencyRelation("emoji_manager", "llm_service_port"))
        g.add_relation(DependencyRelation("plugin_runtime", "llm_service_port"))
        g.add_relation(DependencyRelation("plugin_runtime_v2", "llm_service_port"))
        waves = g.compute_waves(node_filter=subs)
        assert len(waves) == 2
        assert set(waves[0]) == {"emoji_manager", "model_config_port_inject",
                                 "plugin_runtime", "plugin_runtime_v2"}
        assert set(waves[1]) == {"a_memorix", "ipc_bridge_port"}
