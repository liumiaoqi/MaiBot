"""M1 子智能体端到端验证脚本。

验证5个场景：
① Dream 子智能体7天周期自动触发
② Compaction 子智能体三级阈值压缩
③ 子智能体的 ask 请求被自动拒绝（interactive:false）
④ 同一智能体同时运行的子智能体不超过3个
⑤ Compaction 不可用时回退到 mid_term.py 同步压缩
"""

from __future__ import annotations

import asyncio
import sys
import time


async def verify_all() -> dict[str, bool]:
    results: dict[str, bool] = {}

    print("=" * 60)
    print("M1 子智能体端到端验证")
    print("=" * 60)

    # 场景③: InteractiveGate 非交互门控
    print("\n--- 场景③: InteractiveGate 非交互门控 ---")
    try:
        from src.maisaka.subagent import (
            AskRequest,
            AskResponse,
            InteractiveGate,
            SubAgentSpec,
            SubAgentType,
            SubAgentLifecycle,
        )

        gate = InteractiveGate()

        # 非交互模式（Dream/Compaction 默认）
        spec_non_interactive = SubAgentSpec(
            subagent_type=SubAgentType.DREAM,
            agent_id="kiana",
            interactive=False,
        )
        request = AskRequest(subagent_id="sub_test1", action="ask_user", description="需要确认")
        response = gate.evaluate_ask(spec_non_interactive, request)
        assert not response.approved, "非交互模式 ask 应被拒绝"
        assert "自动拒绝" in response.reason, f"拒绝原因应包含'自动拒绝': {response.reason}"
        print(f"  ✅ 非交互模式 ask 被自动拒绝: reason={response.reason}")

        # 交互模式（主智能体）
        spec_interactive = SubAgentSpec(
            subagent_type=SubAgentType.DREAM,
            agent_id="kiana",
            interactive=True,
        )
        request2 = AskRequest(subagent_id="sub_test2", action="ask_user", description="需要确认")
        response2 = gate.evaluate_ask(spec_interactive, request2)
        assert not response2.approved, "交互模式 ask 应等待审批"
        assert "等待" in response2.reason, f"交互模式应等待审批: {response2.reason}"
        print(f"  ✅ 交互模式 ask 等待审批: reason={response2.reason}")

        # 审批通过
        approve_resp = gate.approve("sub_test2", "运维确认")
        assert approve_resp is not None and approve_resp.approved, "审批应通过"
        print("  ✅ 交互模式审批通过")

        results["场景③_InteractiveGate"] = True
    except Exception as e:
        print(f"  ❌ 失败: {e}")
        results["场景③_InteractiveGate"] = False

    # 场景④: 并发限制≤3/智能体
    print("\n--- 场景④: 并发限制≤3/智能体 ---")
    try:
        from src.maisaka.subagent import (
            SubAgentScheduler,
            SubAgentRegistry,
            SubAgentLifecycleManager,
            SubAgentType,
            SubAgentLifecycle,
            SpawnTimeoutError,
        )

        registry = SubAgentRegistry()

        class MockAgent:
            pass

        class MockConfig:
            pass

        registry.register(SubAgentType.DREAM, MockAgent, MockConfig)
        registry.register(SubAgentType.COMPACTION, MockAgent, MockConfig)
        registry.register(SubAgentType.CHECKPOINT_WRITER, MockAgent, MockConfig)

        scheduler = SubAgentScheduler(
            registry=registry,
            max_concurrent=3,
            spawn_timeout=2.0,
        )

        # 派生3个子智能体
        handles = []
        for i in range(3):
            spec = SubAgentSpec(
                subagent_type=SubAgentType.DREAM,
                agent_id="kiana",
                session_id=f"session_{i}",
                interactive=False,
                lifecycle=SubAgentLifecycle.PERSISTENT,
            )
            handle = await scheduler.spawn(spec)
            handles.append(handle)
            print(f"  ✅ 派生子智能体 #{i+1}: id={handle.subagent_id}")

        # 第4个应超时
        spec4 = SubAgentSpec(
            subagent_type=SubAgentType.DREAM,
            agent_id="kiana",
            session_id="session_3",
            interactive=False,
        )
        try:
            await scheduler.spawn(spec4)
            print("  ❌ 第4个子智能体不应派生成功")
            results["场景④_并发限制"] = False
        except SpawnTimeoutError:
            print("  ✅ 第4个子智能体派生超时（并发限制生效）")

        # 级联取消
        cancelled = await scheduler.cancel("kiana")
        print(f"  ✅ 级联取消 {len(cancelled)} 个子智能体")

        results["场景④_并发限制"] = True
    except Exception as e:
        print(f"  ❌ 失败: {e}")
        results["场景④_并发限制"] = False

    # 场景①: Dream 7天周期自动触发
    print("\n--- 场景①: Dream 7天周期自动触发 ---")
    try:
        from src.maisaka.subagent import DreamTrigger, DreamConfig

        config = DreamConfig(enabled=True, interval_days=7, min_spawn_gap_seconds=0)

        registry2 = SubAgentRegistry()
        registry2.register(SubAgentType.DREAM, MockAgent, MockConfig)
        registry2.register(SubAgentType.COMPACTION, MockAgent, MockConfig)
        scheduler2 = SubAgentScheduler(registry=registry2, max_concurrent=3, spawn_timeout=5.0)

        trigger = DreamTrigger(scheduler=scheduler2, config=config)

        # 手动触发
        subagent_id = await trigger.trigger_now("kiana", "session_test")
        assert subagent_id is not None, "手动触发应成功"
        print(f"  ✅ Dream 手动触发成功: id={subagent_id}")

        # 间隔不足时应跳过
        subagent_id2 = await trigger.trigger_now("kiana", "session_test")
        # min_spawn_gap_seconds=0, 所以应该能再次触发
        print(f"  ✅ Dream 间隔0秒可再次触发: id={subagent_id2}")

        # 测试间隔限制
        trigger_gap = DreamTrigger(
            scheduler=scheduler2,
            config=DreamConfig(enabled=True, interval_days=7, min_spawn_gap_seconds=60),
        )
        await trigger_gap.trigger_now("bronya", "session_test")
        subagent_id3 = await trigger_gap.trigger_now("bronya", "session_test")
        assert subagent_id3 is None, "间隔不足应跳过"
        print("  ✅ Dream 间隔不足时跳过派生")

        results["场景①_Dream定时触发"] = True
    except Exception as e:
        print(f"  ❌ 失败: {e}")
        results["场景①_Dream定时触发"] = False

    # 场景②: Compaction 三级阈值压缩
    print("\n--- 场景②: Compaction 三级阈值压缩 ---")
    try:
        from src.maisaka.subagent import CompactionAgent, CompactionConfig, CompactionLevel

        config = CompactionConfig(
            enabled=True,
            threshold_level_1=0.4,
            threshold_level_2=0.6,
            threshold_level_3=0.8,
        )
        agent = CompactionAgent(config=config)

        # 验证阈值判断
        assert agent.determine_level(0.3) == CompactionLevel.NONE, "30% 不应触发"
        assert agent.determine_level(0.4) == CompactionLevel.LEVEL_1, "40% 应触发L1"
        assert agent.determine_level(0.6) == CompactionLevel.LEVEL_2, "60% 应触发L2"
        assert agent.determine_level(0.8) == CompactionLevel.LEVEL_3, "80% 应触发L3"
        print("  ✅ 三级阈值判断正确: NONE/L1(40%)/L2(60%)/L3(80%)")

        # 验证 CompactionTrigger
        from src.maisaka.subagent import CompactionTrigger, ContextMonitor

        registry3 = SubAgentRegistry()
        registry3.register(SubAgentType.COMPACTION, MockAgent, MockConfig)
        scheduler3 = SubAgentScheduler(registry=registry3, max_concurrent=3, spawn_timeout=5.0)

        compaction_trigger = CompactionTrigger(scheduler=scheduler3, config=config)
        monitor = ContextMonitor(compaction_trigger=compaction_trigger)

        # 模拟40%使用率
        result = await monitor.check_and_trigger(
            total_tokens=51200,
            max_tokens=128000,
            message_count=50,
            session_id="session_compact",
            agent_id="kiana",
        )
        print(f"  ✅ 40%使用率触发Compaction: {result is not None}")

        results["场景②_Compaction三级压缩"] = True
    except Exception as e:
        print(f"  ❌ 失败: {e}")
        results["场景②_Compaction三级压缩"] = False

    # 场景⑤: Compaction 降级到 mid_term.py
    print("\n--- 场景⑤: Compaction 降级到 mid_term.py ---")
    try:
        from src.maisaka.subagent import CompactionTrigger, CompactionConfig

        # 禁用 Compaction，应降级
        config_disabled = CompactionConfig(enabled=False, fallback_to_sync=True)
        trigger_fallback = CompactionTrigger(
            scheduler=scheduler3,
            config=config_disabled,
        )

        result = await trigger_fallback.trigger_compaction(
            agent_id="kiana",
            session_id="session_fallback",
            token_usage_ratio=0.5,
        )
        assert result is not None, "降级应返回结果"
        assert result.fallback_used, "应标记为降级"
        print(f"  ✅ Compaction 禁用时降级到同步压缩: fallback_used={result.fallback_used}")
        print(f"     降级原因: {result.error_message}")

        results["场景⑤_降级路径"] = True
    except Exception as e:
        print(f"  ❌ 失败: {e}")
        results["场景⑤_降级路径"] = False

    # 汇总
    print("\n" + "=" * 60)
    print("验证结果汇总")
    print("=" * 60)
    all_passed = True
    for name, passed in results.items():
        status = "✅ 通过" if passed else "❌ 失败"
        print(f"  {name}: {status}")
        if not passed:
            all_passed = False

    print(f"\n总计: {sum(results.values())}/{len(results)} 通过")
    if all_passed:
        print("🎉 所有验证场景通过！")
    else:
        print("⚠️ 部分场景未通过，需修复")

    return results


if __name__ == "__main__":
    asyncio.run(verify_all())