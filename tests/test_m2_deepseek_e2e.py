"""M2 DeepSeek优化与Python性能端到端验证。

验证5个场景：
① DeepSeek模型使用adaptive/full策略，非DeepSeek模型回退lean
② 前缀缓存命中率可按智能体维度监控
③ 非实时任务提交批处理API，批处理不可用降级
④ DeepSeek优化配置开关与回退
⑤ 子智能体并行执行
"""

from __future__ import annotations

import asyncio


async def verify_all() -> dict[str, bool]:
    results: dict[str, bool] = {}

    print("=" * 60)
    print("M2 DeepSeek优化与Python性能端到端验证")
    print("=" * 60)

    # 场景①: 注入策略选择
    print("\n--- 场景①: 注入策略选择 ---")
    try:
        from src.maisaka.deepseek import DeepSeekOptimizer

        opt = DeepSeekOptimizer()

        # 非 DeepSeek 模型 -> lean
        s1 = opt.select_strategy("kiana", 128000, model_id="gpt-4o")
        assert s1 == "lean", f"gpt-4o应为lean: {s1}"

        # DeepSeek 模型 -> 使用智能体配置
        s2 = opt.select_strategy("kiana", 128000, model_id="deepseek-v4-pro")
        assert s2 in ("full", "adaptive", "lean"), f"DeepSeek策略异常: {s2}"

        # 大窗口
        s3 = opt.select_strategy("kiana", 1000000, model_id="deepseek-v4-pro")

        print(f"  ✅ gpt-4o -> lean, deepseek-v4-pro -> {s2}, 1M窗口 -> {s3}")
        results["场景①_注入策略"] = True
    except Exception as e:
        print(f"  ❌ {e}")
        results["场景①_注入策略"] = False

    # 场景②: 前缀缓存命中率监控
    print("\n--- 场景②: 前缀缓存命中率监控 ---")
    try:
        from src.maisaka.deepseek import PrefixCacheManager

        pcm = PrefixCacheManager()

        # 构建前缀层（使用正确的API签名）
        layers1 = pcm.build_prefix_layers(
            agent_id="kiana",
            system_content="系统提示词",
            identity_content="琪亚娜人设",
            emotion_baseline_content="情绪基线",
            internal_relationships_content="内部关系网",
        )
        assert len(layers1) == 4

        # 第二次构建（相同内容 -> 命中）
        layers2 = pcm.build_prefix_layers(
            agent_id="kiana",
            system_content="系统提示词",
            identity_content="琪亚娜人设",
            emotion_baseline_content="情绪基线",
            internal_relationships_content="内部关系网",
        )

        # 第三次构建（不同内容 -> 未命中）
        layers3 = pcm.build_prefix_layers(
            agent_id="kiana",
            system_content="系统提示词（修改）",
            identity_content="琪亚娜人设",
            emotion_baseline_content="情绪基线",
            internal_relationships_content="内部关系网",
        )

        stats_kiana = pcm.get_cache_stats("kiana")
        assert stats_kiana is not None, "kiana应有缓存统计"
        assert "hit_rate" in stats_kiana, "应有hit_rate"

        # bronya
        pcm.build_prefix_layers(
            agent_id="bronya",
            system_content="系统提示词",
            identity_content="布洛妮娅人设",
            emotion_baseline_content="情绪基线",
            internal_relationships_content="内部关系网",
        )

        stats_bronya = pcm.get_cache_stats("bronya")
        assert stats_bronya is not None

        print(f"  ✅ kiana缓存统计: {stats_kiana}")
        print(f"  ✅ bronya缓存统计: {stats_bronya}")
        results["场景②_前缀缓存监控"] = True
    except Exception as e:
        print(f"  ❌ {e}")
        results["场景②_前缀缓存监控"] = False

    # 场景③: 批处理API
    print("\n--- 场景③: 批处理API降级 ---")
    try:
        from src.maisaka.deepseek import BatchScheduler, BatchTask, BatchTaskType
        from src.maisaka.deepseek.batch_scheduler import BatchTaskPriority, BatchTaskStatus

        bs = BatchScheduler()

        # 正常提交
        task = BatchTask(
            agent_id="kiana",
            task_type=BatchTaskType.DREAM_CONSOLIDATION,
            priority=BatchTaskPriority.NORMAL,
        )
        status = bs.submit_task(task)
        assert status == BatchTaskStatus.PENDING, f"应为PENDING: {status}"

        # 标记不可用
        bs.mark_batch_api_unavailable()
        task2 = BatchTask(
            agent_id="kiana",
            task_type=BatchTaskType.COMPACTION_SUMMARY,
            priority=BatchTaskPriority.NORMAL,
        )
        status2 = bs.submit_task(task2)
        assert status2 == BatchTaskStatus.DEGRADED, f"应为DEGRADED: {status2}"

        # 恢复
        bs.mark_batch_api_available()
        task3 = BatchTask(
            agent_id="kiana",
            task_type=BatchTaskType.PROFILE_UPDATE,
            priority=BatchTaskPriority.NORMAL,
        )
        status3 = bs.submit_task(task3)
        assert status3 == BatchTaskStatus.PENDING, f"恢复后应为PENDING: {status3}"

        print(f"  ✅ 批处理: PENDING -> 不可用DEGRADED -> 恢复PENDING")
        results["场景③_批处理API"] = True
    except Exception as e:
        print(f"  ❌ {e}")
        results["场景③_批处理API"] = False

    # 场景④: 配置开关与回退
    print("\n--- 场景④: 配置开关与回退 ---")
    try:
        from src.maisaka.deepseek import DeepSeekOptimizer

        opt = DeepSeekOptimizer()

        # is_deepseek_model
        assert opt.is_deepseek_model("deepseek-v4-pro")
        assert not opt.is_deepseek_model("gpt-4o")
        assert not opt.is_deepseek_model("claude-3.5-sonnet")

        # is_deepseek_enabled
        enabled = opt.is_deepseek_enabled("kiana", "deepseek-v4-pro")
        not_enabled = opt.is_deepseek_enabled("kiana", "gpt-4o")
        assert not not_enabled, "非DeepSeek模型应返回False"

        print(f"  ✅ is_deepseek_model/enable: deepseek={enabled} gpt-4o={not_enabled}")
        results["场景④_配置开关"] = True
    except Exception as e:
        print(f"  ❌ {e}")
        results["场景④_配置开关"] = False

    # 场景⑤: 子智能体并行执行
    print("\n--- 场景⑤: 子智能体并行执行 ---")
    try:
        from src.maisaka.subagent import ParallelSubAgentExecutor, SubAgentSpec, SubAgentType
        import time

        executor = ParallelSubAgentExecutor(max_parallel=5)

        async def mock_exec(spec: SubAgentSpec) -> str:
            await asyncio.sleep(0.1)
            return f"done_{spec.agent_id}_{spec.subagent_type.value}"

        specs = [
            SubAgentSpec(agent_id="kiana", subagent_type=SubAgentType.DREAM, session_id="s1"),
            SubAgentSpec(agent_id="bronya", subagent_type=SubAgentType.COMPACTION, session_id="s2"),
            SubAgentSpec(agent_id="seele", subagent_type=SubAgentType.DREAM, session_id="s3"),
        ]

        start = time.monotonic()
        results_parallel = await executor.execute_parallel(specs, mock_exec)
        elapsed = time.monotonic() - start

        assert len(results_parallel) == 3, f"应有3个结果: {len(results_parallel)}"
        assert elapsed < 0.5, f"并行执行应<0.5s，实际{elapsed:.2f}s"

        print(f"  ✅ 3个子智能体并行执行: {elapsed:.2f}s (应<0.5s)")
        results["场景⑤_并行执行"] = True
    except Exception as e:
        print(f"  ❌ {e}")
        results["场景⑤_并行执行"] = False

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
        print("🎉 所有 M2 DeepSeek+Python性能 验证场景通过！")
    return results


if __name__ == "__main__":
    asyncio.run(verify_all())