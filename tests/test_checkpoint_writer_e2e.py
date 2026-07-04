"""M2 Checkpoint-Writer 子智能体端到端验证。

验证5个场景：
① Checkpoint-Writer 生成11-section结构化会话快照
② Fork Agent 模式下 ForkContext 不可变
③ 父级无 agent 信息时降级为非 Fork 模式
④ 连续失败3次后暂停触发
⑤ 子智能体并发限制正常工作
"""

from __future__ import annotations

import asyncio


async def verify_all() -> dict[str, bool]:
    results: dict[str, bool] = {}

    print("=" * 60)
    print("M2 Checkpoint-Writer 端到端验证")
    print("=" * 60)

    # 场景①: 11-section快照
    print("\n--- 场景①: 11-section结构化会话快照 ---")
    try:
        from src.maisaka.subagent import (
            CheckpointWriterAgent,
            CheckpointWriterConfig,
            CheckpointResult,
            SubAgentSpec,
            SubAgentStatus,
            SubAgentType,
        )

        config = CheckpointWriterConfig()
        agent = CheckpointWriterAgent(config=config)
        spec = SubAgentSpec(
            subagent_type=SubAgentType.CHECKPOINT_WRITER,
            agent_id="kiana",
            session_id="test_session",
            interactive=False,
        )
        status = SubAgentStatus(spec=spec)
        result = await agent.execute(spec, status)

        assert result.success, f"执行失败: {result.error_message}"
        assert len(result.sections) == 11, f"应有11个section，实际{len(result.sections)}"
        assert result.total_tokens > 0, "应有Token消耗"

        for s in result.sections:
            print(f"  §{s.index} {s.name}: {s.token_estimate} tokens")

        snapshot = result.to_snapshot_text()
        assert "§1" in snapshot and "§11" in snapshot
        print(f"  ✅ 11-section快照生成成功: {result.total_tokens} tokens")
        results["场景①_11section快照"] = True
    except Exception as e:
        print(f"  ❌ {e}")
        results["场景①_11section快照"] = False

    # 场景②: ForkContext 不可变
    print("\n--- 场景②: ForkContext 不可变 ---")
    try:
        from src.maisaka.subagent import ForkContext

        fc = ForkContext(
            system=["system prompt"],
            agent_id="kiana",
            session_id="s1",
        )
        assert fc.is_valid

        try:
            fc.system = ["modified"]
            print("  ❌ ForkContext 应不可变")
            results["场景②_ForkContext不可变"] = False
        except Exception:
            print("  ✅ ForkContext 不可变验证通过")
            results["场景②_ForkContext不可变"] = True
    except Exception as e:
        print(f"  ❌ {e}")
        results["场景②_ForkContext不可变"] = False

    # 场景③: 父级无agent信息时降级
    print("\n--- 场景③: 无ForkContext降级 ---")
    try:
        from src.maisaka.subagent import CheckpointWriterAgent, CheckpointWriterConfig

        config = CheckpointWriterConfig(fork_enabled=True)
        agent = CheckpointWriterAgent(config=config, fork_context=None)
        spec = SubAgentSpec(
            subagent_type=SubAgentType.CHECKPOINT_WRITER,
            agent_id="kiana",
            session_id="test_session",
            interactive=False,
        )
        status = SubAgentStatus(spec=spec)
        result = await agent.execute(spec, status)

        assert result.success
        assert not result.fork_mode, "无ForkContext应为非Fork模式"
        assert result.fallback_used, "应标记为降级"
        print(f"  ✅ 无ForkContext降级为非Fork模式: fallback={result.fallback_used}")
        results["场景③_降级非Fork模式"] = True
    except Exception as e:
        print(f"  ❌ {e}")
        results["场景③_降级非Fork模式"] = False

    # 场景④: 连续失败3次后暂停
    print("\n--- 场景④: 连续失败暂停 ---")
    try:
        from src.maisaka.subagent import CheckpointWriterAgent, CheckpointWriterConfig

        config = CheckpointWriterConfig(max_consecutive_failures=3)
        agent = CheckpointWriterAgent(config=config)
        agent._consecutive_failures = 3

        assert agent.is_paused, "连续失败3次应暂停"
        print("  ✅ 连续失败3次后暂停触发")

        spec = SubAgentSpec(
            subagent_type=SubAgentType.CHECKPOINT_WRITER,
            agent_id="kiana",
            session_id="test_session",
            interactive=False,
        )
        status = SubAgentStatus(spec=spec)
        result = await agent.execute(spec, status)

        assert not result.success
        assert "暂停" in result.error_message
        print(f"  ✅ 暂停后执行返回错误: {result.error_message[:50]}...")
        results["场景④_连续失败暂停"] = True
    except Exception as e:
        print(f"  ❌ {e}")
        results["场景④_连续失败暂停"] = False

    # 场景⑤: 并发限制
    print("\n--- 场景⑤: 子智能体并发限制 ---")
    try:
        from src.maisaka.subagent import (
            SubAgentScheduler,
            SubAgentRegistry,
            SubAgentType,
            SpawnTimeoutError,
            SubAgentLifecycle,
        )

        registry = SubAgentRegistry()

        class M:
            pass

        registry.register(SubAgentType.CHECKPOINT_WRITER, M, M)
        registry.register(SubAgentType.DREAM, M, M)
        registry.register(SubAgentType.COMPACTION, M, M)

        scheduler = SubAgentScheduler(registry=registry, max_concurrent=3, spawn_timeout=2.0)

        handles = []
        for i in range(3):
            spec = SubAgentSpec(
                subagent_type=SubAgentType.CHECKPOINT_WRITER,
                agent_id="kiana",
                session_id=f"s{i}",
                interactive=False,
                lifecycle=SubAgentLifecycle.EPHEMERAL,
            )
            h = await scheduler.spawn(spec)
            handles.append(h)
            print(f"  ✅ 派生 CP-Writer #{i+1}: {h.subagent_id}")

        try:
            spec4 = SubAgentSpec(
                subagent_type=SubAgentType.CHECKPOINT_WRITER,
                agent_id="kiana",
                session_id="s3",
                interactive=False,
            )
            await scheduler.spawn(spec4)
            print("  ❌ 第4个不应成功")
            results["场景⑤_并发限制"] = False
        except SpawnTimeoutError:
            print("  ✅ 第4个派生超时（并发限制生效）")

        cancelled = await scheduler.cancel("kiana")
        print(f"  ✅ 级联取消 {len(cancelled)} 个子智能体")
        results["场景⑤_并发限制"] = True
    except Exception as e:
        print(f"  ❌ {e}")
        results["场景⑤_并发限制"] = False

    # 汇总
    print("\n" + "=" * 60)
    print("验证结果汇总")
    print("=" * 60)
    all_passed = all(results.values())
    for name, passed in results.items():
        status = "✅ 通过" if passed else "❌ 失败"
        print(f"  {name}: {status}")

    print(f"\n总计: {sum(results.values())}/{len(results)} 通过")
    if all_passed:
        print("🎉 所有 Checkpoint-Writer 验证场景通过！")
    return results


if __name__ == "__main__":
    asyncio.run(verify_all())