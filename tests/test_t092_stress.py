"""T092 性能压力测试 — 13个智能体同时在线。

验收标准：
① 13个智能体同时在线时内存增量 <2GB
② 单个智能体 Planner/Replyer 响应延迟不超过当前单角色基线的120%
③ 情绪状态计算和关系等级评估在100ms内完成
"""

from __future__ import annotations

import asyncio
import sys
import time
import tracemalloc
from dataclasses import dataclass, field


@dataclass
class BenchmarkResult:
    name: str
    passed: bool = False
    duration_ms: float = 0.0
    detail: str = ""


@dataclass
class StressTestReport:
    results: list[BenchmarkResult] = field(default_factory=list)
    baseline_memory_mb: float = 0.0
    peak_memory_mb: float = 0.0
    memory_delta_mb: float = 0.0

    @property
    def all_passed(self) -> bool:
        return all(r.passed for r in self.results)

    def summary(self) -> str:
        lines = [
            "=" * 60,
            "T092 性能压力测试报告",
            "=" * 60,
            f"基线内存: {self.baseline_memory_mb:.1f} MB",
            f"峰值内存: {self.peak_memory_mb:.1f} MB",
            f"内存增量: {self.memory_delta_mb:.1f} MB",
            "",
        ]
        for r in self.results:
            status = "PASS" if r.passed else "FAIL"
            lines.append(f"  [{status}] {r.name} ({r.duration_ms:.1f}ms) {r.detail}")
        lines.append("")
        lines.append(f"总结果: {'全部通过' if self.all_passed else '存在失败'}")
        return "\n".join(lines)


def _get_all_agent_ids() -> list[str]:
    """获取全部13个智能体ID。"""
    from src.maisaka.agent.registry import AgentConfigRegistry

    registry = AgentConfigRegistry()
    return [a.agent_id for a in registry.list_agents()]


# ========== 场景①: 内存增量测试 ==========


def benchmark_memory() -> BenchmarkResult:
    """测试13个智能体同时加载的内存增量。"""
    tracemalloc.start()
    snapshot_before = tracemalloc.take_snapshot()

    from src.maisaka.agent.registry import AgentConfigRegistry
    from src.maisaka.agent.emotion import EmotionManager
    from src.maisaka.deepseek.budget import TokenBudgetManager
    from src.maisaka.deepseek.prefix_cache import PrefixCacheManager

    registry = AgentConfigRegistry()
    agents = registry.list_agents()

    emotion_managers: dict[str, EmotionManager] = {}
    budget_mgr = TokenBudgetManager()
    cache_mgr = PrefixCacheManager()

    for agent_config in agents:
        aid = agent_config.agent_id
        em = EmotionManager(agent_config)
        emotion_managers[aid] = em
        budget_mgr.get_budget(aid)
        cache_mgr.build_prefix_layers(
            agent_id=aid,
            system_content="system prompt",
            identity_content=agent_config.identity_prompt or "",
            emotion_baseline_content="emotion baseline",
            internal_relationships_content="internal relationships",
        )

    snapshot_after = tracemalloc.take_snapshot()
    tracemalloc.stop()

    stats = snapshot_after.compare_to(snapshot_before, "lineno")
    total_delta = sum(s.size_diff for s in stats) / 1024 / 1024

    passed = total_delta < 2048
    return BenchmarkResult(
        name="内存增量 <2GB",
        passed=passed,
        duration_ms=0,
        detail=f"增量={total_delta:.1f}MB, 智能体数={len(agents)}",
    )


# ========== 场景②: 情绪状态计算延迟 ==========


def benchmark_emotion_computation() -> BenchmarkResult:
    """测试情绪状态计算延迟 <100ms。"""
    from src.maisaka.agent.registry import AgentConfigRegistry
    from src.maisaka.agent.emotion import EmotionManager

    registry = AgentConfigRegistry()
    agents = registry.list_agents()

    max_ms = 0.0
    total_ms = 0.0

    for agent_config in agents:
        em = EmotionManager(agent_config)

        start = time.perf_counter()
        for _ in range(100):
            em.apply_trigger("happy", 0.3)
            state = em.state
        elapsed = (time.perf_counter() - start) / 100 * 1000

        max_ms = max(max_ms, elapsed)
        total_ms += elapsed

    avg_ms = total_ms / max(len(agents), 1)
    passed = max_ms < 100
    return BenchmarkResult(
        name="情绪计算 <100ms",
        passed=passed,
        duration_ms=avg_ms,
        detail=f"平均={avg_ms:.2f}ms, 最大={max_ms:.2f}ms",
    )


# ========== 场景③: 关系等级评估延迟 ==========


def benchmark_relationship_computation() -> BenchmarkResult:
    """测试关系等级评估延迟 <100ms。"""
    from src.maisaka.relationship.level import RelationshipLevel, RelationshipSnapshot
    from src.maisaka.relationship.manager import RelationshipManager

    mgr = RelationshipManager()

    start = time.perf_counter()
    for _ in range(100):
        snapshot = mgr.evaluate("kiana", "test_user", interaction_score=50.0)
    elapsed = (time.perf_counter() - start) / 100 * 1000

    passed = elapsed < 100
    return BenchmarkResult(
        name="关系评估 <100ms",
        passed=passed,
        duration_ms=elapsed,
        detail=f"平均={elapsed:.2f}ms",
    )


# ========== 场景④: Token预算分配延迟 ==========


def benchmark_budget_allocation() -> BenchmarkResult:
    """测试13个智能体Token预算分配延迟。"""
    from src.maisaka.deepseek.budget import TokenBudgetManager

    mgr = TokenBudgetManager()
    agent_ids = _get_all_agent_ids()

    start = time.perf_counter()
    for aid in agent_ids:
        allocation = mgr.get_budget(aid)
        for seg in [
            "identity", "profile", "history", "heuristic",
            "mid_term", "cross_chat", "emotion_state",
        ]:
            allocation.get_token_limit(seg, 128000)
    elapsed = (time.perf_counter() - start) * 1000

    passed = elapsed < 500
    return BenchmarkResult(
        name="Token预算分配 <500ms",
        passed=passed,
        duration_ms=elapsed,
        detail=f"13个智能体总耗时={elapsed:.2f}ms",
    )


# ========== 场景⑤: 前缀缓存构建延迟 ==========


def benchmark_prefix_cache() -> BenchmarkResult:
    """测试13个智能体前缀缓存构建延迟。"""
    from src.maisaka.agent.registry import AgentConfigRegistry
    from src.maisaka.deepseek.prefix_cache import PrefixCacheManager

    registry = AgentConfigRegistry()
    agents = registry.list_agents()
    cache_mgr = PrefixCacheManager()

    start = time.perf_counter()
    for agent_config in agents:
        aid = agent_config.agent_id
        cache_mgr.build_prefix_layers(
            agent_id=aid,
            system_content="system prompt for " + aid,
            identity_content=agent_config.identity_prompt or "",
            emotion_baseline_content="emotion baseline",
            internal_relationships_content="internal relationships",
        )
    elapsed = (time.perf_counter() - start) * 1000

    passed = elapsed < 1000
    return BenchmarkResult(
        name="前缀缓存构建 <1s",
        passed=passed,
        duration_ms=elapsed,
        detail=f"13个智能体总耗时={elapsed:.2f}ms",
    )


# ========== 场景⑥: 智能体配置加载延迟 ==========


def benchmark_config_loading() -> BenchmarkResult:
    """测试智能体配置加载延迟。"""
    start = time.perf_counter()
    from src.maisaka.agent.registry import AgentConfigRegistry

    registry = AgentConfigRegistry()
    agents = registry.list_agents()
    for a in agents:
        _ = a.identity_prompt
        _ = a.emotion_baseline
        _ = a.internal_relationships
    elapsed = (time.perf_counter() - start) * 1000

    passed = elapsed < 2000 and len(agents) == 13
    return BenchmarkResult(
        name="配置加载 <2s (13个智能体)",
        passed=passed,
        duration_ms=elapsed,
        detail=f"耗时={elapsed:.2f}ms, 智能体数={len(agents)}",
    )


# ========== 场景⑦: Distill巩固延迟 ==========


def benchmark_distill() -> BenchmarkResult:
    """测试Distill巩固计算延迟。"""
    from src.maisaka.consolidation.distill import DistillAgent
    from src.maisaka.consolidation.knowledge_store import KnowledgeStore

    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmpdir:
        store = KnowledgeStore(store_dir=Path(tmpdir))
        agent = DistillAgent(knowledge_store=store)

        start = time.perf_counter()
        result = asyncio.run(agent.execute("kiana", window_days=30))
        elapsed = (time.perf_counter() - start) * 1000

    passed = elapsed < 5000
    return BenchmarkResult(
        name="Distill巩固 <5s",
        passed=passed,
        duration_ms=elapsed,
        detail=f"耗时={elapsed:.2f}ms, 资产数={len(result.assets)}",
    )


# ========== 主测试入口 ==========


async def verify_all() -> dict[str, bool]:
    """执行全部性能压力测试。"""
    report = StressTestReport()

    print("=" * 60)
    print("T092 性能压力测试")
    print("=" * 60)

    benchmarks = [
        ("配置加载", benchmark_config_loading),
        ("内存增量", benchmark_memory),
        ("情绪计算", benchmark_emotion_computation),
        ("关系评估", benchmark_relationship_computation),
        ("Token预算", benchmark_budget_allocation),
        ("前缀缓存", benchmark_prefix_cache),
        ("Distill巩固", benchmark_distill),
    ]

    for name, fn in benchmarks:
        print(f"\n--- {name} ---")
        try:
            result = fn()
            report.results.append(result)
            status = "PASS" if result.passed else "FAIL"
            print(f"  [{status}] {result.detail}")
        except Exception as e:
            report.results.append(
                BenchmarkResult(name=name, passed=False, detail=f"异常: {e}")
            )
            print(f"  [FAIL] 异常: {e}")

    print("\n" + report.summary())

    return {r.name: r.passed for r in report.results}


if __name__ == "__main__":
    results = asyncio.run(verify_all())
    sys.exit(0 if all(results.values()) else 1)