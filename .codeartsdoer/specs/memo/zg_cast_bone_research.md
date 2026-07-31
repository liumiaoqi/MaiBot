# 铸骨（ZhuGu / ZG）— 研究备忘

> 2026-07-30，CA 整理，基于 Linux 内核源码分析 + MaiBot 现状评估 + 用户讨论

## 计划定义

**铸骨（ZhuGu）**：炉火纯青之后，为系统铸就骨架，让它像 OS 一样有自己的骨骼和节律。

两条主线交叉串行推进：
1. **OS 化** — 系统设计更靠近 Linux
2. **功能/组件审阅清理** — 随计划推进持续审阅，不是一轮定论

## 与上一代（CQ）的关系

CQ 收尾了 except 吞没、None 防御、启动崩溃、欲望驱动等"杂质尽除"工作。
ZG 在 CQ 基础上，从"能跑"走向"能可靠地跑、能优雅地降级、能精确地诊断"。

## Linux 内核借鉴价值分析

### 高价值（4 项）— 解决"全生命周期管理"

| Linux 机制 | 核心设计 | MaiBot 借鉴点 |
|------------|---------|--------------|
| **initcall 分级启动** | 8 级链接器段 + `_sync` 屏障 + `__init` 回收 | StartupOrchestrator 增加显式依赖声明 + 启动后一次性数据清理 |
| **watchdog/hung_task** | 双层检测（hard+soft） + buddy 互检 + touch 机制 | asyncio 心跳检测 + Runner 子进程健康检查 |
| **panic/oops** | notifier chain + tainted_mask + warn_limit | PanicNotifierChain + 系统污染标记 + 降级通知 |
| **notifier chain** | 4 种并发变体 + priority + STOP/BAD + robust 回滚 | EventBus 增加 BAD 否决语义 + 补偿回滚 |

### 中价值（3 项）— 解决"资源约束下运行时管理"

| Linux 机制　　　　　　| 核心设计　　　　　　　　　　　　　　　　　　　　　| MaiBot 借鉴点　　　　　　　　　　　　　　　　　　|
| -----------------------| ---------------------------------------------------| --------------------------------------------------|
| **cgroup/memcontrol** | 层级化计数 + 软/硬限制 + vmpressure + OOM kill　　| 每会话资源配额 + 内存压力分级 + 会话淘汰　　　　 |
| **printk**　　　　　　| 无锁环形缓冲区 + ratelimit + suppress + kmsg_dump | 结构化日志环形缓冲 + 日志频率限制 + 降级日志抑制 |
| **signal**　　　　　　| 同步/异步分类 + 屏蔽 + 不可捕获 + UNKILLABLE　　　| 控制消息优先级 + 不可屏蔽停止 + 主智能体保护　　 |

### 已排除的方向

- ~~声明式启动依赖（systemd After=/Requires=）~~ — 用户决定不需要
- ~~虚拟文件系统（/proc 化）~~ — SQLite + dict 够用
- ~~内核模块动态加载（modprobe 化）~~ — Python import 已是动态加载
- ~~进程调度器（CFS 化）~~ — asyncio 事件循环就是调度器
- ~~系统调用号表（syscall 化）~~ — Protocol 接口已是系统调用

## ZG 方向清单与优先级

### 🔴 P0 — 应该做

| 编号 | 方向 | 理由 | 复杂度 | 层级 |
|------|------|------|--------|------|
| **ZG-1** | 服务管理器（systemd 化） | 组件挂了没人知道，排障靠运气。"从能跑到能可靠地跑"的第一步 | 低 | 应用 |
| **ZG-2** | 统一日志管线（journald 化） | CQ-11 已在清理 45 处 `import logging` 残留，趁机加结构化+环形缓冲+ratelimit | 中 | 应用 |
| **ZG-3** | 看门狗（watchdog 化） | asyncio 事件循环阻塞 + Runner 子进程无响应，当前最痛的运行时风险 | 低 | 应用 |
| **ZG-9** | 极端环境加固 | 内核调参+OOM防护+I/O隔离，确保极端条件下不崩不卡死可预测降级 | 低 | 基础 |

### 🟡 P1 — 值得做但靠后

| 编号　　　　 | 方向　　　　　　　　　　　　　　　| 理由　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　| 层级 |
| --------------| -----------------------------------| -----------------------------------------------------------------------------| ------|
| **ZG-4**　　 | 事件总线增强（D-Bus 化）　　　　　| AutonomyEventBusPort 已有雏形，增加 BAD 否决语义+补偿回滚有价值，但当前够用 | 应用 |
| **ZG-5**　　 | 资源限制（cgroups 化）　　　　　　| 单进程下需求弱，会话/智能体数增长后价值上升。可先做每会话 LLM 配额　　　　　| 应用 |
| ~~**ZG-6**~~ | ~~系统状态机（system_state 化）~~ | ✅ **已完成**（2026-08-01，见已完成表）　　　　　　　　　　　　　　　　　　　| 应用 |

### 🔵 P2 — 打磨

| 编号 | 方向 | 理由 | 层级 |
|------|------|------|------|
| **ZG-7** | 污染标记（tainted_mask 化） | 一眼看出系统是否在"不干净"状态下运行，debug 利器 | 应用 |
| **ZG-8** | 控制消息优先级（signal 化） | 紧急消息优先于常规消息，主智能体不可淘汰 | 应用 |

## ZG-9 极端环境加固 — 子项详情

> 来源：`.shared/decisions/ubuntu2604_extreme_tuning.md`（2026-07-30）
> 核心哲学：不是给 MaiBot 提速，是确保它在极端条件下**不崩、不卡死、可预测地降级**。
> **WSL2 限制**：宿主内核 6.18.35.2（Microsoft WSL2），Kernel 7.0 特性不可用。EEVDF 调参、cgroup latency 隔离标记为待宿主升级。

| 子项　　　　　　　　　　　　　　　| 效果　　　　　　　　　　　　 | 风险　　　　　　　 | 建议　　　　　　　　　　　　　 |
| -----------------------------------| ------------------------------| --------------------| --------------------------------|
| EEVDF 调度器调参　　　　　　　　　| P99 延迟降 20-30%　　　　　　| 低　　　　　　　　 | ⚠️ 需 Kernel 7.0，WSL2 暂不可用 |
| cgroup latency 隔离　　　　　　　 | 容器独占低延迟域　　　　　　 | 低　　　　　　　　 | ⚠️ 需 Kernel 7.0，WSL2 暂不可用 |
| OOM score 分层　　　　　　　　　　| 关键进程豁免，非关键优先被杀 | 低　　　　　　　　 | ✅ 3 行代码　　　　　　　　　　 |
| PSI 压力监控　　　　　　　　　　　| 提前预警　　　　　　　　　　 | 无　　　　　　　　 | ✅　　　　　　　　　　　　　　　|
| /tmp tmpfs 挂载　　　　　　　　　 | 临时 I/O 降为 0　　　　　　　| RAM 占用　　　　　 | ✅ 内存>4G 时　　　　　　　　　 |
| swappiness=0　　　　　　　　　　　| 容器内 swap 禁用　　　　　　 | OOM 概率↑　　　　　| ✅ 有 GPU 时必选　　　　　　　　|
| I/O weight 隔离　　　　　　　　　 | 日志不阻塞数据写入　　　　　 | 低　　　　　　　　 | ⚠️ 仅争抢时生效　　　　　　　　 |
| io_uring（3.14 第三方→3.15 原生） | 网络 I/O↑50%　　　　　　　　 | 第三方稳定性待验证 | ⚠️ 3.15 GA 后零成本升级　　　　 |

ZG-9 与 ZG-5 互补：ZG-5 管理应用如何声明资源需求，ZG-9 管理基础设施如何兜底。

ZG-9 是 ZG-1/ZG-3 的前置条件：OS 层不稳定时，看门狗检测到的"超时"可能是调度器饿死协程的锅，不是代码的锅。ZG-9 先确保可预测的运行环境，ZG-1/ZG-3 才能可靠检测。

ZG-9 OOM 保护与 ZG-3 看门狗分工：OOM 保护管"死之前的优先级排序"（关键进程免杀），看门狗管"死之后的处理"（检测→重启→通知）。ZG-3 重启的进程应自动获得 OOM 保护优先级。

## 推进路线

```
批次1（P0 打底）
  ZG-9 极端环境加固（OS 层前置，确保可预测环境）──→ ZG-1 服务管理器 ──→ ZG-3 看门狗 ──→ 审阅清理

批次2（P0 收尾 + P1 启动）
  ZG-2 统一日志管线 ──→ 审阅清理 ──→ ZG-6 系统状态机

批次3（P1 深化）
  ZG-4 事件总线增强 ──→ ZG-5 资源限制 ──→ 审阅清理

批次4（P2 打磨）
  ZG-7 污染标记 ──→ ZG-8 控制消息优先级
```

每步前后都做功能/组件审阅。

## 已完成

| 日期 | 内容 | 提交 |
|------|------|------|
| 2026-07-30 | 扁平人格→四层模型迁移（6 调用方 + 30 测试） | 54514e7f8 |
| 2026-07-30 | send_service 废弃方法清理（7 方法 ~250 行） | 更早 |
| 2026-07-30 | ZG 研究备忘 + 废弃系统清单 | 文档 |
| 2026-08-01 | **ZG-6 系统状态机**（BOOTING→READY→DEGRADING→SHUTTING_DOWN + 通知链 + 崩溃导出 + WebUI /lifecycle + 信号退出联动，20 需求 48 验收全覆盖，38 测试） | c38dd6f1c |

## ZG-6 系统状态机遗留事项（2026-08-01）

> ZG-6 已编码完成并合并（c38dd6f1c）。CA 审查通过，CX 审查 2 bug 已修。
> 交接报告：`.shared/handoff/cc2ca_zg6_coding_0801.md`；审查报告：`.shared/handoff/ca2cc_zg6_review_0801.md`

| # | 项 | 内容 | 触发时机 |
|---|-----|------|---------|
| ZG-6-R1 | 全量既有回归确认 | 本批次修复了 pyproject pytest-asyncio 配置段（mode=STRICT→AUTO），历史 async 测试可能首次真正在 auto 模式运行，需全量 pytest 确认无潜伏失败 | 合并后（docker 恢复即跑） |
| ZG-6-R2 | 通知链 per-subscriber 超时 | 当前全局 5s 超时；design 已裁定不优先，订阅者超时记告警视为 DONE | 出现"单一慢订阅者拖累全局"实证时 |
| ZG-6-R3 | ServiceManager 自适应接入 | 适配器谓词已就绪，ServiceManager/消息管道按状态自适应（BOOTING 拒收等）尚未接线 | 后续系统审阅时评估 |

## 交叉的 CQ 债务

| 编号　　　　 | 内容　　　　　　　　　　　　　　　　　　　| 时机　　　　　　 |
| --------------| -------------------------------------------| ------------------|
| CQ-11　　　　| `import logging` 绕过统一日志　　　　　　 | ZG-2 时一并清理　|
| CQ-14/15/13　| Port 直接导入迁移　　　　　　　　　　　　 | ZG-1 时审阅　　　|
| 废弃系统清理 | 回复触发→vitality、行为学习→ThinkingOrgan | ZG-1/ZG-3 依赖时 |

## Docker 低资源测试

Docker 原生支持模拟低资源场景，可用于 ZG-3/ZG-5 验证：

```yaml
services:
  maim-bot-core:
    deploy:
      resources:
        limits:
          cpus: '0.5'
          memory: 512M
        reservations:
          memory: 256M
```

支持的约束：`cpus` / `memory` / `memswap_limit` / `oom_kill_disable` / `oom_score_adj` / `device_read_bps` / `device_write_bps`

## 功能/组件审阅（上一轮剖析结果）

### 🔴 已标记 DEPRECATED

1. `core/types.py` **ReplyTimingSnapshot** 整个类（10 字段）— vitality 系统已替代
2. `maisaka/agent/config.py` **personality 字段** — 已迁移到 layered_personality 四层模型
3. `services/send_service.py` **8 个 Deprecated 方法** — MessagePortV2 已替代
4. `config/official_configs.py` **18 处 DEPRECATED** — vitality/管家/ThinkingOrgan 替代

### 🟡 V1/V2 重叠

5. `chat/utils/typo_generator.py` vs `maisaka/context/typo_generator.py`（397 行重复）
6. `chat/utils/utils.py`（223 行）— V1 重导出层
7. `chat/replyer/` 4 个 5 行代理文件
8. `learners/learner_utils_old.py`（357 行，带 `_old` 后缀）

### 🟠 体积异常（>1000 行）

9. `official_configs.py` 6,189 行
10. `web_import_manager.py` 3,901 行
11. `statistic.py` 2,611 行（与 statistics_service.py 重叠）
12. `metadata_store.py` 2,626 行
13. `runtime.py` 1,945 行
14. `webui/routers/memory.py` 2,399 行

### ⚪ NotImplementedError/桩实现

- llm_models 9 处、plugin_runtime_v2/proto 8 处、common/data_models 4 处

## DEPRECATED 语义修正（2026-07-30）

### 认知修正

DEPRECATED 标记的含义**不是**"这个函数废弃了可以删"，而是"**这整个系统/功能废弃了，将由新系统替代**"。有活跃调用方是正常的——旧系统仍在运行，标记是说"整个系统要被新系统替换，替换完成后一起删"。

清理策略是**系统级替换**，不是逐个函数删。

### 废弃系统清单

| 废弃系统　　　　　　　　　 | 涉及代码　　　　　　　　　　　　　　　　　　　　　　　　　　　　| 替代系统　　　　　　　　　　 | 替代就绪？　　　　　　　　|
| ----------------------------| -----------------------------------------------------------------| ------------------------------| ---------------------------|
| **概率回复触发系统**　　　 | ReplyTimingSnapshot + ChatReplyTimingConfig 7 字段 + 6 个调用方 | vitality 系统　　　　　　　　| ❌ 未实现　　　　　　　　　|
| **扁平人格系统**　　　　　 | personality 字段 + 6 个调用方　　　　　　　　　　　　　　　　　 | layered_personality 四层模型 | ✅ 已迁移完成（54514e7f8） |
| **行为学习系统**　　　　　 | ExperimentalConfig 4 字段 + 12 个调用方　　　　　　　　　　　　 | ThinkingOrgan 思考-行动分离　| ⚠️ 部分替代　　　　　　　　|
| **启发式记忆召回系统**　　 | heuristic 4 字段 + 8 个调用方　　　　　　　　　　　　　　　　　 | IntuitionEngine　　　　　　　| ⚠️ 需确认覆盖度　　　　　　|
| **V1 发送 API**　　　　　　| send_service 旧方法　　　　　　　　　　　　　　　　　　　　　　 | MessagePortV2　　　　　　　　| ✅ 已替代，旧方法已删　　　|
| **A_memorix 迁移阶段控制** | phase 字段 + 6 个调用方　　　　　　　　　　　　　　　　　　　　 | 锁定为 new_independent　　　 | ⚠️ 需确认可锁定　　　　　　|

### 清理策略

1. **替代系统已就绪 + 调用方可迁移** → 迁移调用方 → 删旧系统（如：扁平人格 → 四层模型）
2. **替代系统未就绪** → 先实现替代系统 → 再迁移 → 再删（如：回复触发 → vitality）
3. **替代系统部分就绪** → 确认覆盖度 → 决定迁移范围（如：行为学习 → ThinkingOrgan）

### 与 ZG 的关系

系统级替换和 ZG OS 化特性是交叉的：
- ZG-1 服务管理器需要 vitality 系统 → vitality 就绪后替换回复触发系统 → 整块删
- ZG-3 看门狗需要 ThinkingOrgan 配置 → 替代 max_consecutive_wait_count 等 → 整块删
- 扁平人格迁移可独立进行（四层模型已就绪）

## DEPRECATED 引用分析（2026-07-30）

### 已完成清理

- ✅ 删除 `send_service.py` 6 个无调用方的废弃方法（`_text_to_stream`, `_text_to_stream_with_message`, `_emoji_to_stream`, `_emoji_to_stream_with_message`, `_image_to_stream`, `_custom_to_stream`, `_custom_reply_set_to_stream`）
- ✅ 移除 `_send_to_target_with_message` 的误标 Deprecated（它是 MessagePortV2 核心实现路径）

### 不可删除（有活跃调用方，需先完成替代系统）

| DEPRECATED 项 | 活跃引用数 | 迁移前置条件 |
|---------------|-----------|-------------|
| **ReplyTimingSnapshot** | 6（runtime/routes/utils_config/message_utils/mode_policy/chat_config_port） | 需先实现 vitality 系统并迁移全部调用方 |
| **ChatReplyTimingConfig 7 字段**（talk_value/private_talk_value/mentioned_bot_reply/inevitable_at_reply/reply_trigger_mode/enable_talk_value_rules/talk_value_rules） | 各 2-3 | 需 vitality 系统就绪 |
| **ExperimentalConfig 4 字段**（enable_behavior_learning/enable_rich_reply/behavior_learning_list/behavior_groups） | 2-12 | 需 ThinkingOrgan 思考-行动分离完全替代行为学习 |

### 需谨慎（有活跃调用方，可逐步迁移）

| DEPRECATED 项 | 活跃引用数 | 迁移前置条件 |
|---------------|-----------|-------------|
| **personality 字段** | 6 → 0（已迁移） | ✅ 已完成，fallback 路径保留 |
| **planner_interrupt_max_consecutive_count** | 2（chat_config_port/runtime） | 迁移到 ThinkingOrgan 配置 |
| **max_consecutive_wait_count** | 2（chat_config_port/runtime） | 迁移到 ThinkingOrgan 配置 |
| **heuristic 4 字段**（heuristic_memory_recall_enabled/cross_chat/group_to_private/private_to_group） | 各 2-3 | 需确认 IntuitionEngine 完全覆盖 |
| **AMemorixConnectionistConfig.phase** | 6（migration_router/memory_field/host_service） | 需确认迁移阶段锁定为 new_independent |

## 待讨论

- ~~ZG 方向优先级是否需要调整~~ → 已确定 4 批次路线
- ~~功能/组件清理的切入点和范围~~ → 随 ZG 批次推进审阅
- OS 化方向备忘录（`os_like_direction.md`）中是否有其他需要修正的幼稚想法

> 全项目债务全景和项目路线已迁入 `.shared/roadmap.md`，本文件只追踪与 ZG 直接相关的内容。

## ZG-3 看门狗编码遗留问题（2026-07-31）

| # | 严重度 | 位置 | 问题 | 当前影响 | 后续处理 |
|---|--------|------|------|---------|---------|
| 1 | 中 | `runner_health_bridge.py:50-80` | `register_v2_supervisor` 未将 `_on_v2_timeout` 注入到 `heartbeat_manager` 的 `timeout_callback` | V2 心跳超时回调桥接未连接，仅 V2 状态 diff 轮询工作 | 需了解 HeartbeatManager.start 的调用时机，在注册时注入包装回调 |
| 2 | 低 | `main.py:305` | `WatchdogConfig()` 使用默认配置，未从配置 Port 读取 | 无法通过配置文件自定义看门狗参数 | 在 AppConfigPort 新增配置项后接入 |
| 3 | 低 | `main.py` | Runner 注册（tasks 7.2）未实现 | 桥接部分空转，事件循环检测完整工作 | 需了解 V2 HostEndpoint 的 runner 列表访问方式 |
| 4 | 低 | `watchdog_adapter.py:85` | `_notify_subscribers` 在检测线程中调用 | 订阅者回调需线程安全 | 风险低，可改为 run_coroutine_threadsafe 提交 |

## ZG-2 统一日志管线遗留标记（2026-08-01，以后再改）

> ZG-2 已编码完成并合并（693b735f6）。printk 对照复盘见 `.shared/decisions/zg2_printk_review_0801.md`。
> 以下为"以后再改"的可改进项，不阻塞当前使用：

| # | 项 | 内容 | 触发时机 |
|---|-----|------|---------|
| ZG-2-L1 | 摘要输出完全异步化 | 当前事件循环不可用时同步 fallback；对标 printk deferred output，改为排队而非同步阻塞 | 日志风暴期间摘要输出阻塞写线程的实测证据出现时 |
| ZG-2-L2 | RingBuffer 无锁方案评估 | 当前 RLock 保护；printk 是 lockless ring buffer（写路径永不当机哲学）。Python 单线程场景收益待测 | 多线程日志并发成为瓶颈（基准实测 >1ms/条）时 |
| ZG-2-L3 | 按调用点 ratelimit | 当前按 logger_name+event 签名；printk 是每调用点（__ratelimit 宏）。粒度差异导致同 logger 不同调用点合并计数 | 误抑制日志（不同调用点被同源合并抑制）的实证出现时 |
