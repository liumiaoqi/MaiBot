"""ZG-10 启动编排验证脚本 — 一键检查启动编排是否健康。

两种模式：
  静态（默认）：import main.py 收集 33 个 @startup_item 声明 → 仲裁 →
               验证波次/屏障/依赖/configure 位置（不需要真实启动）
  运行时（--runtime）：真实启动 MaiBot（--debug-startup）→ 解析逐项日志 →
               断言全部组件状态/波次顺序/摘要

用法（容器内）：
  cd /MaiMBot && uv run python scripts/zg10_startup_verify.py
  cd /MaiMBot && uv run python scripts/zg10_startup_verify.py --runtime [--skip a,b]
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path

# 脚本位于 scripts/ 下——项目根加入 sys.path（import src.main 需要）
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

EXPECTED_COUNT = 33
SUBSYSTEMS_WAVE0 = {"emoji_manager", "model_config_port_inject", "plugin_runtime", "plugin_runtime_v2"}
SUBSYSTEMS_WAVE1 = {"a_memorix", "ipc_bridge_port"}
BARRIER_CONTRIBUTORS = {"chat_manager_adapter", "agent_registry", "replyer_port"}

# ── 静态验证（默认）──────────────────────────────────────────────


def verify_static() -> int:
    """不启动系统：声明收集 + 仲裁 + 依赖断言。"""
    import src.main  # noqa: F401 — 触发 @startup_item 收集

    from src.core.startup.arbiter import CoreReadinessBarrier, StartupArbiter
    from src.core.startup.declaration import _registry
    from src.core.startup.types import StartupPhase

    checks: list[tuple[str, bool, str]] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        checks.append((name, ok, detail))

    items = _registry.drain()
    check("33 组件声明", len(items) == EXPECTED_COUNT,
          f"实际 {len(items)}")

    plan = StartupArbiter().arbitrate(items)
    subs = plan.phases.get(StartupPhase.SUBSYSTEMS, [])
    check("全局仲裁无环", plan.total_waves > 0)

    check("SUBSYSTEMS 2 波次", len(subs) == 2, f"实际 {len(subs)}")
    if len(subs) == 2:
        check("波次0 成员", set(subs[0]) == SUBSYSTEMS_WAVE0, str(subs[0]))
        check("波次1 成员", set(subs[1]) == SUBSYSTEMS_WAVE1, str(subs[1]))

    # 依赖顺序（波次索引）
    wave_index = {n: i for i, w in enumerate(subs) for n in w}
    check("ipc_bridge 在 plugin_runtime 后",
          wave_index.get("ipc_bridge_port", -1) > wave_index.get("plugin_runtime", 99))
    check("a_memorix 在 model_config_port_inject 后",
          wave_index.get("a_memorix", -1) > wave_index.get("model_config_port_inject", 99))

    # 屏障：READY 相位波次包含屏障且屏障在各项之前
    ready_waves = plan.phases.get(StartupPhase.READY, [])
    barrier_idx = plan.barrier_wave.get(StartupPhase.READY, -1)
    check("READY 屏障存在", barrier_idx >= 0)
    if barrier_idx >= 0:
        check("READY 项在屏障后",
              all(n != CoreReadinessBarrier.VIRTUAL_NODE_ID for w in ready_waves[:barrier_idx] for n in w))

    # 核心贡献组件声明 core_readiness_flag
    missing_flag = [
        n for n in BARRIER_CONTRIBUTORS
        if n not in items or not items[n].core_readiness_flag
    ]
    check("核心贡献组件 readiness_flag", not missing_flag, str(missing_flag))

    # configure 位置：event_bus_port init_fn 内含 configure，且不在 run() 之后
    main_src = open("src/main.py", encoding="utf-8").read()
    configure_lines = [i for i, line in enumerate(main_src.splitlines(), 1)
                       if "_core_event_bus.configure" in line]
    check("configure 唯一且在 event_bus_port 声明后",
          len(configure_lines) == 1, f"行号 {configure_lines}")
    if len(configure_lines) == 1:
        line_no = configure_lines[0]
        # event_bus_port 声明应在 configure 之前（configure 在 init_fn 内）
        event_bus_decl = next(
            (i for i, line in enumerate(main_src.splitlines(), 1)
             if 'name="event_bus_port"' in line), 0)
        check("configure 在 event_bus_port 声明内/后",
              event_bus_decl > 0 and line_no > event_bus_decl,
              f"event_bus_port@{event_bus_decl}, configure@{line_no}")

    # 汇总
    print("=" * 60)
    print("ZG-10 启动编排静态验证")
    print("=" * 60)
    failed = 0
    for name, ok, detail in checks:
        mark = "✅" if ok else "❌"
        print(f"  {mark} {name}" + (f"  [{detail}]" if detail and not ok else ""))
        if not ok:
            failed += 1
    print("-" * 60)
    print(f"结果: {len(checks) - failed}/{len(checks)} 通过")
    return 1 if failed else 0


# ── 运行时验证（--runtime）───────────────────────────────────────


def verify_runtime(skip: str = "") -> int:
    """真实启动 MaiBot（--debug-startup），解析日志断言。"""
    cmd = ["uv", "run", "python", "-m", "src.main", "--debug-startup"]
    if skip:
        cmd.append(f"--skip-startup-item={skip}")
    print(f"启动 MaiBot: {' '.join(cmd)}（30s 超时）")
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=45,
        )
    except subprocess.TimeoutExpired:
        print("❌ 启动超时（45s）——可能外部依赖未就绪，或启动编排卡住")
        return 1
    output = proc.stdout + proc.stderr

    # 解析逐项日志：启动项 {name} | 相位= | 波次= | 结果= | 耗时=
    item_re = re.compile(
        r"启动项 (\S+) \| 相位=(\S+) \| 波次=(\d+) \| 结果=(\S+) \| 耗时=(\d+)ms"
    )
    items = {}
    for m in item_re.finditer(output):
        items[m.group(1)] = {
            "phase": m.group(2), "wave": int(m.group(3)),
            "status": m.group(4), "ms": int(m.group(5)),
        }

    checks: list[tuple[str, bool, str]] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        checks.append((name, ok, detail))

    check("逐项日志 33 组件", len(items) == EXPECTED_COUNT, f"实际 {len(items)}")
    check("全部 SUCCESS", all(v["status"] == "SUCCESS" for v in items.values()),
          str({k: v["status"] for k, v in items.items() if v["status"] != "SUCCESS"}))
    if "ipc_bridge_port" in items and "plugin_runtime" in items:
        check("ipc_bridge 波次 > plugin_runtime 波次",
              items["ipc_bridge_port"]["wave"] > items["plugin_runtime"]["wave"])
    if "a_memorix" in items and "model_config_port_inject" in items:
        check("a_memorix 波次 > model_config_port_inject 波次",
              items["a_memorix"]["wave"] > items["model_config_port_inject"]["wave"])
    check("启动摘要 ready", "[启动摘要]" in output and "ready=True" in output)

    print("=" * 60)
    print("ZG-10 启动编排运行时验证")
    print("=" * 60)
    failed = 0
    for name, ok, detail in checks:
        mark = "✅" if ok else "❌"
        print(f"  {mark} {name}" + (f"  [{detail}]" if detail and not ok else ""))
        if not ok:
            failed += 1
    if failed:
        print("\n--- 启动输出尾部（供诊断）---")
        print("\n".join(output.splitlines()[-20:]))
    print("-" * 60)
    print(f"结果: {len(checks) - failed}/{len(checks)} 通过")
    return 1 if failed else 0


def main() -> int:
    parser = argparse.ArgumentParser(description="ZG-10 启动编排验证")
    parser.add_argument("--runtime", action="store_true",
                        help="真实启动验证（需完整外部环境）；默认静态验证")
    parser.add_argument("--skip", type=str, default="",
                        help="运行时模式：--skip-startup-item 值（逗号分隔）")
    args = parser.parse_args()
    if args.runtime:
        return verify_runtime(args.skip)
    return verify_static()


if __name__ == "__main__":
    sys.exit(main())
