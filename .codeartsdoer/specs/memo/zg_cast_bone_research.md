# 铸骨（ZhuGu / ZG）— 研究备忘

> 2026-07-30 创建，CA 整理；2026-08-04 修订，全面刷新进度与路线；2026-08-06 修订，双内核认知；2026-08-07 修订，体积异常现状刷新（子代理调研）

## 计划定义

**铸骨（ZhuGu）**：炉火纯青之后，为系统铸就骨架，让它像 OS 一样有自己的骨骼和节律。

两条主线交叉串行推进：
1. **OS 化** — 系统设计更靠近 Linux
2. **功能/组件审阅清理** — 随计划推进持续审阅，不是一轮定论

## 双内核认知（2026-08-06，用户提出）

**MaiBot 有两个内核，职责不同、分层运行**：

| | 实际内核（运行层） | 理念内核（思考层） |
|---|---|---|
| 负责什么 | MaiBot 的**运行**——启动/生命周期/资源/故障/插件 | MaiBot 的**思考**——人格/记忆/欲望/情绪/决策 |
| 对应计划 | **铸骨（ZG）**，Linux 化系列 | **铸魂（Thinking Kernel）**，独立计划（见 `.shared/decisions/ZH_Plan/thinking_kernel_plan_0806.md`） |
| 现状 | 已系统化（ZG-1~19 对标 Linux 的骨架） | 散件就位（人格四层/记忆融合/vitality/thinking_organ），缺统一架构蓝图 |

**分层关系**：理念内核（"想干什么"）调实际内核（"可靠地做到"）——铸骨保证思考的底座不塌，铸魂决定思考本身的样子。两者正交：Linux 化与"更像人"无直接关系，但理念内核想好好思考，底下必须有不塌的骨架。

## 与上一代（CQ）的关系

CQ 收尾了 except 吞没、None 防御、启动崩溃、欲望驱动等"杂质尽除"工作。
ZG 在 CQ 基础上，从"能跑"走向"能可靠地跑、能优雅地降级、能精确地诊断"。

## Linux 内核借鉴价值分析

### 高价值（4 项）— 解决"全生命周期管理"

| Linux 机制　　　　　　 | 核心设计　　　　　　　　　　　　　　　　　　　　 | MaiBot 借鉴点　　　　　　　　　　　　　　　　　　　　　　　 |
| ------------------------| --------------------------------------------------| -------------------------------------------------------------|
| **initcall 分级启动**　| 8 级链接器段 + `_sync` 屏障 + `__init` 回收　　　| StartupOrchestrator 增加显式依赖声明 + 启动后一次性数据清理 |
| **watchdog/hung_task** | 双层检测（hard+soft） + buddy 互检 + touch 机制　| asyncio 心跳检测 + Runner 子进程健康检查　　　　　　　　　　|
| **panic/oops**　　　　 | notifier chain + tainted_mask + warn_limit　　　 | PanicNotifierChain + 系统污染标记 + 降级通知　　　　　　　　|
| **notifier chain**　　 | 4 种并发变体 + priority + STOP/BAD + robust 回滚 | EventBus 增加 BAD 否决语义 + 补偿回滚　　　　　　　　　　　 |

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

## ZG 方向清单与优先级（2026-08-04 刷新）

### ✅ 已完成（13/13）

| 编号 | 方向 | 完成日期 | 核心产出 |
|------|------|---------|---------|
| **ZG-1** | 服务管理器（systemd 化） | 2026-07-31 | 引擎层 dependency_graph/health_check/lifecycle/recovery + 适配器 + main.py 启动接管 |
| **ZG-2** | 统一日志管线（journald 化） | 2026-08-01 | 结构化日志 + RingBuffer + 按调用点 ratelimit + deferred output + 全 ERROR O(1) 快速判定 |
| **ZG-3** | 看门狗（watchdog 化） | 2026-08-02 | S1 延迟报告 + S2 检测线程健康 + S3 V2 注册验证 + S4 blocker 追踪 + 25 新测试 |
| **ZG-4** | 事件总线增强（D-Bus 化） | 2026-08-01 | Vote 统一投票 + BAD-only robust 回滚 + EventBus robust/nofail，78 测试全绿 |
| **ZG-5** | 资源限制（cgroups 化） | 2026-08-02 | ResourceCounter + FourTierLimit + PressureDetector + OOMHandler + 适配器全接线，75 测试 |
| **ZG-6** | 系统状态机（system_state 化） | 2026-08-01 | BOOTING→READY→DEGRADING→SHUTTING_DOWN + 通知链 + 崩溃导出 + WebUI /lifecycle，38 测试 |
| **ZG-7** | 污染标记（tainted_mask 化） | 2026-08-03 | 8 位 TaintFlag + 6 位运行时接线 + TaintActionMapper + CrashDump 内省，68 测试 |
| **ZG-8** | 控制消息优先级（signal 化） | 2026-08-07 | 9 引擎（kind_registry/mask/pending/priority/unkillable/force/fatal_diffuser）+ 11 测试文件 + 运行时接线（调研核实 2026-08-07） |
| **ZG-9** | 极端环境加固 | 2026-07-31 | mem_limit/swap=0/OOM保护/tmpfs，WSL2 内核 6.18 |
| **ZG-12** | 模型配置重写（alternative 化） | 2026-08-07 | @model_requirement 装饰器 + 三级索引 + fallback 链 + 16 组件声明 + DeclarationValidator（调研核实 2026-08-07） |
| **ZG-15** | 插件活体引用（try_module_get 化） | 2026-08-07 | 排空重写（mark_going→wait_drained→cancel→on_unload）+ 任务契约 + ServiceManager 集成 + 竞态集成测试，v2 186 passed |
| **ZG-21** | 事件回调预算（ksoftirqd 化） | 2026-08-07 | SoftirqBatcher（budget_ms=2/count=200）+ EventBus 批量化 + 日志广播批量，852 passed |
| **ZG-22** | 无锁读延迟回收（RCU 化） | 2026-08-07 | 索引热替换（IndexIDMap2 包装 + 原子替换），5 文件 68 行 |
| **ZG-23a** | 消息发送去重 + 发言节流 | 2026-08-07 | OutboundDedupWindow + MentionChainThrottle + 幂等键 metadata 通道 + FAILED 枚举，962 passed（CX 审查 3 P0 两轮修复定稿） |
| **ZG-10** | 启动编排演进（initcall→systemd 化） | 2026-08-04（基础设施）/ **2026-08-14 三项收尾** | src/core/startup/ 7 文件（declaration/arbiter/orchestrator/propagator/types/validator——分层仲裁 + 相位分波 + 失败传播 + 配置冻结 + CLI 观测 + StartupCompleteEvent）批 1-11 + CX 审核两轮；**2026-08-14 补完**：① `__init` 回收（orchestrator.reclaim_after_startup——释放 item 元数据/仲裁结构/波次计划）② watchdog/service_manager 移入启动编排（@startup_item CORE_SERVICES——"WatchdogPort 未注册"降级日志消除——真实启动验证）③ UDS 防御（探测活监听再报错——UDSSocketOccupiedError + 所有权标记）——**ZG-10 全部完成** |
| **ZG-14** | 错误升级梯（WARN→oops→panic 化） | Phase 1-3 08-05~06 / Phase 4 08-07 收口 / **Phase 5 08-14 完成** | error_escalation 包 10 文件（escalator/mapper/storm/counter/coverage/code_mapper）；Phase 4 except 改造覆盖 99.73%；**Phase 5 错误码→ErrorLevel 映射**（code_mapper.py——复用 ZG-12 定稿 PERMANENT/TRANSIENT_ERROR_CODES——永久→ERROR/暂时→WARN——LLM 重试终点接线——13 测试）——**ZG-14 全部完成** |

### 🔴 P0 — 剩余必做（2026-08-07 调研核实：**已空**——ZG-12 已完成）

| 编号 | 方向 | 理由 | 复杂度 | 层级 |
|------|------|------|--------|------|
| **ZG-12** | 模型配置重写（alternative 化） | V1 遗留命名+硬编码回退+embedding 静默失败+TaskConfig 无分化，**用户决定整体重写** | 高 | 应用 |

## ZG-24~31 调研驱动新批次（2026-08-17 立——44 份调研报告的落地编排）

> 2026-08-16 晚 44 任务调研队列全部完成（.shared/research/2026-08/），本批次为调研结论的正式 ZG 化。
> 优先级排序依据：P0 死代码/静默失效 > 用户疑问方向 > 性能 N+1 > 观测。

| 编号 | 任务 | 来源报告 | 优先级 | 核心内容 |
|------|------|---------|:---:|---------|
| **ZG-24** | 记忆写入链路接线（ZH1-1a 死代码修复） | memory_write_chain_0817 + compaction_sites_analysis_0817 | **P0** | `process_chat_history_after_cycle` 全库无调用者——裁切摘要入队/队列消费/insert 历史整条死链；修复后 mid_term_memory_summaries 表恢复增长，ZH1-1b recall 候选源复活。AGENTS.md 硬性规则违反项 |
| **ZG-25** | 会话压缩体系（B 层替换式 compaction） | compaction_sites_analysis_0817 + maiobot_vs_dsh_compression_0817 | **P1** | select 后对 selected_history 做摘要替换释放 token（对标 dsh compactSurfaceRegion），不污染共享历史；与 ZG16-2 软裁切正交叠加；组合方案：ZG16-2 选择→B 替换→G 持久化 |
| **ZG-26** | 缓存命中率提升（前缀稳定化） | cache_hit_improvement_0817 + cache_cold_start_analysis_0817 | **P1** | system prompt 4 个动态字段（emotion/relationship/favor/interaction_memory）后移/稳定化——b1 旁观者路径学习角色化路径（改动 1 文件、收益预估 30-50% 命中、低风险）——用户疑问③落地 |
| **ZG-27** | 记忆水位回收落地 | zg17_watermark_shrinker_survey_v2_0816 + memory_capacity_cleanup_0817 | **P1** | ZG-17 12 项落地清单：watermark/shrinker/ReclaimScheduler/kswapd/eviction_score + 6 机制直接注册 shrinker + 防误杀（核心记忆 priority_score=-1000） |
| **ZG-28** | 检索链路 N+1 与缓存治理 | memory_retrieval_chain_0817 | **P1** | 3 处 P0 N+1（关系检索/图后验竞争合并/图关系召回——循环内单条查询，批量 API 已存在可直接替换）+ embedding/BM25/profile 缓存覆盖不足 |
| **ZG-29** | 记忆容量清理治理 | memory_capacity_cleanup_0817 | **P1** | 3 个 P0 残留（deleted_relations 无自动清理/graph_edges 孤儿边/delete_entity 不级联）+ 7 个 P1 容量空缺（无水位/墓碑无 compaction/缓存无驱逐） |
| **ZG-30** | 社会关系记忆协调治理 | social_relation_memory_0817 | **P1** | 5 个 P0（profile 版本号竞态/relation RMW 非原子/跨存储无事务/person_profile 注入死代码/多写者无锁）+ 5 个 P1——灵魂理念（关系）实现层加固 |
| **ZG-31** | except 静默吞错清零 | except_audit_0816 | **P1** | 120 处 P0 静默吞错（pass_body 无日志，logger.py 4 处最优先）+ ZG-14 差额 74 处纳入改造（8-06 后新增代码） |

> 依赖关系：ZG-24 是 ZG-25（G 层）与 recall 能力的前置；ZG-27 依赖 ZG-29 的部分清理基线；其余独立。
> 排期：等用户拍板（试新模型队列排队中——新模型首次完整流程可能从 ZG-24 开始）。

### P2/P3 存量清单（不入 ZG 编号——主批次完成后按需取用）

| 级 | 内容 | 来源报告 |
|:---:|------|---------|
| P2 | ChatManager 死代码 + data_migration.py 独立脚本 + 概念命名分歧（多 ChatManager）+ 2 个孤岛死代码 | component_coordination |
| P2 | 记忆容量 4 项：串行无退避 / vacuum 未接线 / PPR O(n) 扫描 / 全图衰减无分批 | memory_capacity_cleanup |
| P2 | 社会关系 5 项：死锁清理 / 配置未用 / confidence 未作边权重 / 融合未用 confidence / Facade 废弃未迁移 | social_relation_memory |
| P2 | 压缩体系候选点 F（跨轮）/ C（注入前）/ D（注入后）/ E（prompt 前）——风险高暂缓，B 落地后再评估 | compaction_sites |
| P2 | 情绪跨会话持久化（c1——风险中，命中收益预估 +20%/+10%） | cache_hit_improvement |
| P2 | 前端错误告警面板缺失 + /reload-config 占位实现 | config_hotreload_escalation |
| P2 | 并行工具执行 + 工具调用限制（中价值） | agent_framework_tools |
| P3 | 渐进式工具暴露 + Handoff 路由模式（理论价值） | agent_framework_tools |
| P3 | 记忆注入标准化（c2——收益有限 +2%） | cache_hit_improvement |
| P3 | 测试债务（可疑测试分布——只测自己 init / 源码字符串断言）治理 | test_health_audit |

### P4/P5 明确不做/暂缓清单（记录在案——不占编号不排期，白纸黑字防重复问）

| 级 | 内容 | 理由 | 来源 |
|:---:|------|------|------|
| P4 | 压缩候选点 C/D/E（记忆注入前/后、prompt 构建前压缩） | 破坏记忆完整性/已合并难分离——报告明确不做 | compaction_sites |
| P4 | ZG-17 VectorShrinker 首版（向量回收） | 向量重建代价极高——降级为仅注册 count_objects 返回 0，留 V2 | zg17_survey_v2 |
| P4 | ZG-11 Phase 3 组件级进程隔离 | 架构变动大，当前规模不需要 | zg_cast_bone_research |
| P4 | ZG-13 角色语音 TTS | 用户拍板暂缓（2026-08-16） | zg_cast_bone_research |
| P5 | ZG-11 Phase 2 本地大模型 embedding worker | 等 bge 微调部署决策——倾向 Xinference 独立服务，大概率不需要 | zg_cast_bone_research |
| P5 | 组件级进程隔离（memory/embedding/LLM 各一进程 + Unix socket） | 同 P4 隔离项，更远期 | zg_cast_bone_research |

### 🟡 P1 — 值得做

| 编号 | 方向 | 理由 | 层级 |
|------|------|------|------|
| **ZG-8** | 控制消息优先级（signal 化） | 紧急消息优先于常规消息，主智能体不可淘汰 | 应用 |

### 🟢 P2 — 未来方向

| 编号 | 方向 | 理由 | 层级 |
|------|------|------|------|
| **ZG-11** | 多核利用（SMP 化） | 见下方 ZG-11 子项详情 | 基础 |
| **ZG-13** | 角色语音（TTS 输出） | ⏸️ **暂缓（2026-08-16 用户拍板）**——设计就绪未实现，见下方 ZG-13 子项详情 | 应用 |
| **ZG-17** | 记忆水位回收（watermark+shinker 化） | 📚 调研完成（zg17_watermark_shrinker_survey：水位分级 + 两相回收——**2026-08-14 代码核实：未实现**），见下方详情 | 基础 |
| **ZG-18** | 后台任务救援（workqueue rescuer 化） | 📚 调研完成（zg18_workqueue_rescuer_survey：并发上限 + 救援线程自死锁逃逸——**2026-08-14 代码核实：未实现**），见下方详情 | 基础 |
| **ZG-19** | 落盘背压（dirty 阈值化） | 📚 调研完成（zg19_dirty_threshold_survey：两级阈值写者节流 + 批量提交对齐——**2026-08-14 代码核实：未实现**），见下方详情 | 基础 |
| **ZG-23** | 剩余项综合（低价值合并） | 📚 调研完成（zg_remaining_items_survey：fsync 分层/OOM 评分/kswapd 等 9 项合并），见下方详情 | 基础 |

### 🧭 犄角旮旯对标（2026-08-07 调研：NATS/Zulip/Home Assistant，报告 `.shared/research/2026-08/`）

| 来源 | 可落地清单 | 挂靠 |
|------|-----------|------|
| **NATS**（事件总线对标，`nats_arch_0807.md`） | ① 事件名分层化（EventType 扁平 → 主题层级）② 通配订阅（`*`/`>`）③ **背压水位信号**（SoftirqBatcher 缺：积压时 emit 侧无感知）④ 队列组互斥分发（可选）⑤ vote history 按需落盘 | ZG-4 增强候选（背压信号 → ZG-21 增强） |
| **Zulip**（消息架构对标，`zulip_arch_0807.md`） | ① **事件 schema 测试制度**（事件结构变更走测试——防假改动）② client_capabilities 演进协议 ③ 心跳 + 队列 GC（45s/10min）④ 高频事件合并（virtual_events，与 ZG-21 同族）⑤ 事件 payload 预拼装（推送层零 DB） | ZG-4 增强候选；ws 部分归明堂 |
| **Home Assistant**（插件系统对标，`home_assistant_arch_0807.md`） | ① 集中 PluginCatalog 发现层 ② manifest 加 `requires_plugins` 拓扑加载 ③ @Command/@Tool 入参 schema 注册时校验 ④ `plugin_id.service` 命名空间互调 ⑤ 复用排空链做热重配（options_flow） | 插件域（ZG-15 后续） |

**共同洞察**：三份调研都指向"契约先行"——主题即契约（NATS）/ 事件 schema 测试（Zulip）/ manifest + service registry 校验（HA）——与明堂-1 的 extra='forbid' 同一道理（接口契约自动化杜绝假改动）。

### 🔧 已知遗留（从已完成项中拆出）

| 来源 | 遗留 | 严重度 | 触发时机 |
|------|------|--------|---------|
| ZG-7 | `degrade_on_taint_mask` 掩码级触发（对标 `panic_on_taint`） | P0 | 出现"污染后应自动降级但未降级"实证时 |
| ZG-7 | 3 个候选新标志（UNHANDLED_FATAL/EXTERNAL_FALLBACK/LOOP_STALL） | P2 | 对应场景出现时 |
| ZG-3 | V2 Runner 注册（register_v2_supervisor 方法已存在未调用） | 低 | V2 Runner 普及后 |
| ZG-5 | §11 WebUI 内省接口暂缓（适配器方法已实现，缺 WebUI 路由暴露） | 低 | 用户决定恢复 WebUI 资源监控时 |
| 防御扫描 2026-08-08 | **mcp SDK 2.0 迁移**（FastMCP→MCPServer/Client 重构/无握手协议纪元——mcp_module 三文件 + 插件生态，官方建议 pin `<2` 先迁移后升级；当前锁 mcp>=1.28.1,<2.0） | P2 | 协议新纪元收益明确时（stateless/负载均衡/新扩展 API）专项排期 |
| 2026-08-09 配置损坏事故 | **配置写入前校验**（configfs L5 提交式语义落地）：任何配置保存链路（前端/迁移/自动升级）写入前 tomlkit 校验 TOML 合法性——校验失败拒绝写入 + 清晰报错（含备份提示）。本次事故：bot_config.toml inner_voices 块被写坏（42 声音条目拍平）→ 容器启动崩溃——人肉对比 old/ 备份链修复。**配套**：启动编排配置加载阶段独立校验（ZG-10 方向——坏配置清晰报错而非裸崩溃） | P1 | ✅ **已完成**（38d3a0948 [dsh]：save_toml_with_format 三层防护——产物 TOML 校验 + .bak 备份 + 原子写——toml_utils.py:79，保存链路 12+ 调用点全覆盖） |
| ZG-2 | L1 deferred output 已实现；L2 锁已实测否决；L3 ratelimit 已完成 | — | 全部关闭 |

## ZG-10 启动编排演进 — 子项详情

> 当前 ZG-1 为 Windows SCM 式集中注册（main.py 内 30 个 `orchestrator.register()`），新增组件需改编排器。
> 演进目标：Linux 式**分层仲裁**——组件声明需求，编排器仲裁，组件无法绕过编排器。
>
> **2026-08-04 源码调研修正**（依据 `.shared/research/2026-08/zg10_initcall_source_0804.md`）：
> Linux initcall **无任何运行时依赖仲裁**（顺序=编译期等级+链接顺序，失败不阻断）。设计修正为**混合模式**：
> - **等级相位（Linux 式 fast path）**：粗粒度相位定大体顺序，相位内按声明序执行
> - **相位内拓扑仲裁（MaiBot 式 safety net）**：TopologicalSorter 只在相位内做仲裁 + 循环检测——第三方插件的环是真实输入风险
> - **核心就绪屏障**（对标 `_sync` 相位栅栏）：虚拟节点"入边=所有核心项、出边=后续项"，兜底未声明但隐含的先后关系
> - **失败标记降级**（超越 Linux）：失败项让依赖它的项标记"不可运行/降级"，不无声跳过（Linux 因无图只能失败继续跑）
> - **调试三件套**：`--debug-startup`（对标 initcall_debug，每项名称+耗时+相位）/ `--skip-startup-item`（对标 blacklist，运行时禁用）/ 启动完成回调在所有异步项 settle 后（对标 async_synchronize_full）
> - **`__init` 回收**：启动完成后释放一次性数据（item 元数据、仲裁中间结构）+ 启动配置冻结/只读化
>
> ### ZG-10 后续遗留（2026-08-04 运行验证期发现）
>
> 1. **watchdog/service_manager 移入启动编排**：watchdog 注册在 post-startup（run() 之后），SUBSYSTEMS 相位组件（V2 Runner 注册看门狗、_init_control_message）用不到 → 每次启动报"WatchdogPort 未注册"降级日志（servicer 有降级不阻断）。修复：watchdog 做成 @startup_item（CORE_SERVICES，depends_on app_config_port），post-startup 删除启动段（组件数 33→34）
> 2. **UDS 防御**：uds.py 无条件 unlink 活 socket（同路径碰撞时静默串线）——改为先探测活监听再报错（Runner 碰撞事故的架构级防御，子代理报告）

### 设计原则：分层仲裁（对标 Linux 内核/systemd）

| 层 | 负责什么 | 不负责什么 |
|---|---------|-----------|
| **编排器** | 依赖排序（Kahn/TopologicalSorter）、循环检测、phase 推导、管理员 override | 不实现业务逻辑、不决定组件内容 |
| **组件自身** | `@startup_item(depends_on=[...])` 声明依赖、实现 `init_fn` | 不决定启动顺序、不绕过编排器 |

对比当前模式：

| | 当前（Windows SCM 式） | 演进后（Linux systemd 式） |
|---|---|---|
| 组件能强制自己启动吗 | ✅ register() 直接生效 | ❌ 编排器仲裁后才生效 |
| 组件能绕过依赖检查吗 | ❌ 无依赖检查 | ❌ 循环依赖自动检测并拒绝 |
| 管理员能覆盖组件声明吗 | ❌ 无覆盖机制 | ✅ `phase_hint` / override 配置 |

### 技术方案

1. **组件自注册**：`@startup_item(name, depends_on=[...], critical=False, phase_hint=None)` 装饰器
2. **自动推导顺序**：`graphlib.TopologicalSorter`（Python 3.9+ 内置 Kahn 算法），天然产生"阶段"
3. **循环依赖检测**：Kahn 算法副产品，未剥离节点即为环上组件
4. **渐进迁移**：两种注册方式共存，新组件用装饰器，旧组件逐步迁移
5. **手动覆盖**：`phase_hint` 可选参数，不填则自动推导，填了则优先

### 开销评估

- 启动时拓扑排序：30 节点 ~50 依赖 → <0.1ms，可忽略
- 代码量：编排器 +50 行，main.py -30 行
- 运行时内存：+几 KB（依赖图）

## ZG-11 多核利用 — 子项详情

> 当前 MaiBot 单进程 asyncio，16 核/32 线程机器只用 1 核，大部分核空转。
> 对标 Linux SMP（对称多处理）：内核启动时检测 CPU 核数，per-CPU 数据结构，
> 中断亲和性绑定，工作队列多 worker 并行。
>
> **⚠️ 2026-08-03 调研修正**：用户已通过 WebUI 配置阿里 API embedding（`model_task_config.embedding.model_list` 运行时非空），模板默认 `model_list=[]` 不代表运行时状态。实际 CPU 瓶颈是 FAISS HNSW 向量搜索（同步阻塞）。

### Embedding 现状（2026-08-03 调研）

| 维度 | 现状 |
|------|------|
| embedding 模型 | **已配置**（用户通过 WebUI 配置阿里 API embedding，运行时 `model_list` 非空） |
| 阿里 API | 已接入（WebUI 配置生效） |
| 本地模型 | `E:\Users\lmq\all-MiniLM-L6-v2`（384 维，英文，~5-10ms/次，太快不需要 worker） |
| Fallback | embedding 不可用时回退 sparse BM25 搜索 + metadata-only 写入 + 向量回填队列 |
| 向量存储 | FAISS HNSW（IndexHNSWFlat + IndexIDMap2），M=32, efSearch=50 |
| 向量搜索阻塞 | FAISS search 同步执行（RLock），在调用线程阻塞 |

### 接入阿里 embedding 的配置步骤

```toml
# model_config.toml

# 1. 添加阿里百炼 API provider
[[api_providers]]
name = "AliBailian"
base_url = "https://{WorkspaceId}.cn-beijing.maas.aliyuncs.com/compatible-mode/v1"
api_key = "sk-xxx"
client_type = "openai"
auth_type = "bearer"

# 2. 添加 embedding 模型
[[models]]
model_identifier = "text-embedding-v4"
name = "ali-text-embedding-v4"
api_provider = "AliBailian"
visual = false

# 3. 配置 embedding 任务
[model_task_config.embedding]
model_list = ["ali-text-embedding-v4"]
```
> MaiBot 不需要内核级 SMP，但应利用多核做 CPU 密集型工作。

### 当前 CPU 密集型阻塞点（修正@2026-08-03）

| 阻塞点 | 频率 | 单次耗时 | 当前影响 | 是否真瓶颈 |
|--------|------|---------|---------|-----------|
| embedding.encode() API | 每次记忆写入/检索 | 100-500ms | ❌ I/O 等待，asyncio 不阻塞 | ❌ |
| embedding.encode() 本地大模型 | 每次记忆写入/检索 | 50-200ms | ✅ CPU 阻塞 | ⚠️ 当前未配置 |
| embedding.encode() 本地小模型(MiniLM) | 每次记忆写入/检索 | 5-10ms | ✅ CPU 阻塞但极快 | ❌ IPC 开销反超计算 |
| **FAISS HNSW 向量搜索** | **每次记忆检索** | **10-50ms** | **✅ 同步阻塞** | **✅ 真瓶颈** |
| 文本分块/摘要提取 | 每次记忆写入 | 5-20ms | 同上 | ⚠️ 中 |

### 技术方案（修正@2026-08-03）

**Phase 0（前置，接入阿里 embedding API）**：✅ **已完成**（2026-08-03 核实：用户已通过 WebUI 配置阿里 API embedding，运行时 `model_list` 非空，向量检索已恢复，非 sparse BM25 降级）
- 接入后 embedding 变为 I/O 密集型，asyncio 天然处理，无需 worker

**Phase 1（FAISS 搜索非阻塞化）**：✅ **已完成**（a55e279c3 [CC] 2026-08-04，2026-08-16 dsh 核实）
- VectorStore.search_async 原生 async（vector_store.py:193——`asyncio.to_thread(self.search, ...)`，FAISS C 扩展释放 GIL → 多核）
- async 上下文调用点全切 search_async（dual_path.py:1002/1081/1754）
- 同步方法链（_collect_mixed_candidates/_search_paragraphs/_search_relations，:1885/1983/2010 同步 search）由生产路径整体 `asyncio.to_thread` 包裹（_parallel_retrieve :1378 / _sequential_retrieve :1269）——worker 线程执行不阻塞事件循环，有意设计（同步链整体入池，避免逐点切换开销）
- 全库无遗漏同步调用点；dual_path 相关测试 43 passed（2026-08-16 验证）

**Phase 2（本地大模型 embedding worker，按需）**：
- 仅当使用本地大模型（如 bge-large-zh-v1.5，50-200ms/次）时启用
- `ProcessPoolExecutor(max_workers=physical_core_count)` 处理 embedding
- 小模型（MiniLM, 5-10ms）不需要 worker——IPC 开销反超计算
- **⚠️ 2026-08-03 定位待定**：用户已决定本地微调 bge-large-zh-v1.5（三元组构造完成，6 万+ 条）。微调产物的**部署方式决定本 Phase 是否需要**：
  - 走 Xinference/vLLM 本地服务（openai_client 指向 localhost）→ embedding 变 I/O 等待，**Phase 2 不需要**（服务进程自管并发）
  - 走 MaiBot 内嵌进程 → Phase 2 需要实现 + ZG-12 配置体系需加"本地模型"provider 类型（现仅 openai/gemini/plugin）
  - 倾向：Xinference 服务（MaiBot 侧零代码，ZG 计划不扩）——决策点待微调完成前确认

**Phase 2（精细调度）**：
- 按 CPU 亲和性分组 worker（embedding 独立池、search 独立池）
- 动态调整 pool 大小（负载低时缩减，高时扩容）
- 对标 Linux workqueue 的 WQ_UNBOUND / WQ_CPU_INTENSIVE 分级

**Phase 3（可选，架构变动大）**：
- 组件级进程隔离（memory worker / embedding worker / LLM worker）
- 进程间 Unix socket 通信
- 对标 Linux kthread per-CPU worker

### 收益估算（32 核，10 并发会话同时检索）

| | 当前（1 核串行） | Phase 1（N=4 worker） | Phase 1（N=8 worker） |
|---|---|---|---|
| 10 次检索耗时 | 10 × 50ms = 500ms | ceil(10/4) × 50ms = 150ms | ceil(10/8) × 50ms = 100ms |
| 事件循环阻塞 | 500ms | 0ms | 0ms |
| CPU 利用率 | 3%（1/32） | ~15% | ~28% |

### Python GIL 约束

- **线程**：无法用多核做 CPU 工作（GIL 互斥）
- **进程**：`ProcessPoolExecutor` 可用多核，但有进程启动开销和 IPC 序列化
- **C 扩展**：numpy/pytorch 已释放 GIL，`ThreadPoolExecutor` 即可用多核
- **建议**：embedding 若用 numpy 后端，可用线程池（零 IPC 开销）；纯 Python 实现用进程池

### 效率优化设计（对标 Linux 内存管理哲学）

> Linux 哲学：空闲 CPU 是浪费，空闲内存也是浪费（全用作 page cache）。
> 开销 = 消耗资源中不产生有用产出的部分；效率 = 有用产出 / 总资源消耗。
> 用满资源且每份资源都产出 = 高效率。

| 设计 | 对标 Linux | 减少的开销 | MaiBot 适用场景 | 实现方式 |
|------|-----------|-----------|----------------|---------|
| **mmap 共享索引** | page cache | 避免数据在 Python 堆和磁盘间复制两份 | 记忆向量索引（大数组） | `np.load(mmap_mode='r')`；SQLite WAL 已是 mmap |
| **共享内存 IPC** | shm/mmap | 避免 worker 进程间 pickle 序列化/反序列化 | embedding worker 返回 numpy 数组 | `multiprocessing.shared_memory.SharedMemory` + numpy |
| **对象池** | slab allocator | 减少 GC 压力和重复分配开销 | LLM 请求/响应对象、embedding 结果 | 预分配 + 循环复用 |
| **零拷贝传递** | splice/sendfile | 避免 CPU 做内存拷贝 | 大数据在组件间传递 | numpy 视图（view）而非 copy |
| **工作窃取** | workqueue | 避免 worker 闲置而其他 worker 排队 | 多 worker 负载不均 | `ProcessPoolExecutor` 已内置 |
| **惰性分配** | vmalloc | 只在首次访问时分配物理页 | 会话级数据结构 | Python `__slots__` + 延迟初始化 |

优先级：mmap 共享索引 > 共享内存 IPC > 对象池 > 零拷贝 > 工作窃取（已内置）> 惰性分配

## ZG-12 模型配置重写 — 子项详情

> 2026-08-03，CA 提议，基于模型配置系统深度调研。
> 2026-08-04，用户决定从"仲裁"升级为"整体重写"。
> 对标 Linux **alternative framework**（系统根据硬件能力选最优实现）+ **device model**（统一设备抽象）。
> 核心问题：V1 遗留命名不反映当前架构，回退链硬编码，TaskConfig 无分化，embedding 静默失败。
> **用户设计意图**：一次完整回复只调用一次 LLM，replyer 作为独立 task 应降级。

### 思考即回复 — reply 工具不调 LLM（2026-08-05，用户拍板记入）

**现状实锤**（2026-08-05 代码核查）：一次用户消息 → 回复 = 思考（thinking_organ 工具循环，1-10 轮，每轮 1 次 LLM）+ replyer 生成（1 次）+ 可选富回复检查（当前 `enable_rich_reply=false`，0 次）。典型 2 次，最多 12+。

reply 工具 schema（`builtin_tool/reply.py:43`）只有 `msg_id`/`set_quote`/`reply_guide`/`expression_intent`——**无 `text` 参数**。思考轮模型说"我要回复，指引如下" → reply 工具 → 内部再调一次 LLM（replyer，`generator_base.py:1059`，task_name="replyer"）按 `reply_guide` + `latest_thought` 重新生成正文。这是 V1 双阶段遗产（planner 决策 + replyer 生成）。

**科学依据**（用户提出，2026-08-05）：Vygotsky 内部言语理论——内部言语是压缩语义单位不是完整句子的预演，"想→说"是展开不是重新生成；Levelt 言语产出模型——"口是心非/润色"是同一大脑的输出前监控回路，不是第二个大脑重演。LLM 思考轮 content 本身就是完整句子，第二次调用是**同一生成器重复采样**：2 倍 token 成本 + 信息衰减（replyer 只拿到 `latest_thought`，上下文比思考轮更少，可能歪曲原意）。

**设计方向（革命而非改良）**：
- reply 工具 schema 加 `text` 参数（**required**，回复正文）——思考轮一次 LLM 直接生成正文放进参数，reply 工具只做校验/分段/发送，**零 LLM**
- 思考-行动分离保留：模型必须显式调 reply 工具才算"张嘴"（防止"只思考不回复"历史坑——`chat_loop_service.py:73` 注释：assistant pre-fill 强 bias 纯文本输出是"只思考不回复"核心成因，不能退回 content 直接发）
- 回复风格/表情习惯/内容过滤：注入思考轮 prompt 或做成无 LLM 的后处理
- `enable_rich_reply` 检查器保留为**可选**表达过滤器（正确的"表达过滤"形态，非每次必跑）
- **影响 ZG-12 子项范围**：replyer 不调 LLM 后 `chat_reply`（原 replyer）TaskConfig 是否还需要独立存在——归入子项 1 命名正名时一并裁定；Hook 系统（before_request/after_response）改为针对工具参数文本的无 LLM 后处理

### ComfyUI 借鉴（2026-08-04，用户提出）

模型注册层学 ComfyUI 的"资源池"哲学（Ollama / LM Studio 同惯例——目录即注册）：

| 借鉴 | 落地 | 对应子项 |
|------|------|---------|
| **目录即注册**：模型放 `models/` 约定目录自动发现，零配置 | 本地模型（bge 微调产物、TTS 等）放目录即自动注册，接入本地模型零配置 | 子项 3 分化 + "本地模型一等公民" |
| **模型是独立资产，任务只声明引用**：ComfyUI 的 checkpoint 是资源池，工作流只写"用哪个" | TaskConfig 只引用模型 id，模型实体（provider + 标识）独立声明，任务换模型不改结构 | 子项 3 + 单一路由 |
| **缺失可视化绝不静默**：ComfyUI 缺模型弹红标 | 启动校验**全部**被引用模型存在（不只 embedding），缺失显式告警/走声明式回退，不静默降级 | 子项 4 强化 |

**不学**：节点图工作流（MaiBot 是无人值守服务，声明式 toml 即可）、GUI 中心配置、运行时随意换模型（模型是角色身份，绑定要稳定）。

### 配置变更 → 组件单独重启（2026-08-04，用户提出）

改配置后**单独 restart 模型组件重载模型**（对标 systemd `systemctl reload`），不重启整个 MaiBot。能力基础已具备：

- **ZG-1 ServiceManager**：进程内组件 restart/recover 已实现（30s 限时、退避重试、重启风暴保护 → FAULT_MANUAL、AUTO/MANUAL_RESTART 状态）
- **V2 Runner**：子进程级隔离先例（subprocess.Popen，kill 重启不影响主进程）
- **接线**：`adopt_from_startup` 已纳入 main.py 全部组件 + `health_probe` + `set_service_manager_port`

**设计要点**：
- ZG-12 把"配置变更 → 组件重启"做成标准动作：配置加载成功后触发受影响组件 restart（模型组件 stop/start 钩子负责释放/重载模型资源）
- 边界：进程内重启非干净环境（全局单例/registry/事件循环共享状态不清理）；内存泄漏/死锁靠 ZG-5/ZG-9，非重启可救

### 命名正名方案

当前 `ModelTaskConfig` 字段名来自 V1 架构（单智能体+回复触发），与当前四主智能体+记忆融合架构不匹配：

| 当前名（V1 遗留） | 正名 | 语义 |
|-------------------|------|------|
| `replyer` | `chat_reply` | 聊天回复生成 |
| `planner` | `action_plan` | 行动规划（选工具/定策略） |
| `utils` | `light_task` | 轻量文本任务（摘要/整理/格式化） |
| `memory` | `memory_extract` | 记忆抽取（分段/关系/画像） |
| `mid_memory` | `context_recall` | 上下文回想 |
| `expression_use` | `style_apply` | 表达方式应用 |
| `learner` | `style_learn` | 表达方式学习 |
| `emoji` | `emoji_gen` | 表情包生成 |
| `vlm` | `vision` | 视觉理解 |
| `voice` | `asr` | 语音识别 |
| `embedding` | `embedding` | 文本向量化（无需改） |

**影响范围**：`ModelTaskConfig` 字段名 + `model_config.toml` 键名 + 所有 `LLMOrchestrator(task_name="...")` 调用点 + `EMPTY_TASK_FALLBACKS` + `EpisodeSegmentationService._resolve_model_config()` preferred 链 + WebUI schema + 配置升级钩子。**零逻辑变更，纯重命名**。

### 子项优先级

| # | 子项 | 优先级 | 对标 Linux | 内容 |
|---|------|--------|-----------|------|
| 1 | 命名正名 | P0 | — | 上述 10 个字段重命名 + 配置升级钩子自动迁移 |
| 2 | 回退链声明式 | P0 | alternative framework | `TaskConfig` 内声明 `fallback_to: str`，替代硬编码 `EMPTY_TASK_FALLBACKS`；空 model_list 时按声明链回退 |
| 3 | TaskConfig 分化 | P1 | device_class | 按 `task_category`（text_gen / embedding / vision / audio）分化 schema，不适用的字段标记 `x-hidden` |
| 4 | 启动自检 | P1 | device probe | embedding `model_list=[]` + fallback_enabled 时 WARNING；model_list 引用不存在的模型名时 ERROR |
| 5 | 生效配置预览 | P2 | sysfs | WebUI API 展示全局+智能体覆盖合并后的"生效配置" |
| 6 | extra_params schema | P2 | — | 按 provider_type 提供 `extra_params` 校验 schema |
| 7 | 升级钩子预埋 | P2 | — | `MODEL_CONFIG_UPGRADE_HOOKS` 框架对齐 bot_config（当前为空元组） |
| 8 | WebUI 连通性测试 | P3 | — | "测试连接"按钮，调 `/models` 端点或发最小请求验证 |

### 依赖关系

- **ZG-11 Phase 0 是 ZG-12 的前置**：先有正确的 embedding 配置（阿里 API 接入），才能验证配置仲裁系统的真实负载
- **子项 1（命名正名）是子项 2-4 的前置**：先正名，再在正确名字上建回退链和自检
- **子项 3（TaskConfig 分化）依赖子项 1**：分化 schema 需要正确的任务类别名

### 开销评估

- 子项 1（命名正名）：~30 个调用点 rename + 1 个升级钩子，纯机械操作
- 子项 2（回退链声明式）：`TaskConfig` +1 字段 + `LLMOrchestrator` 改回退逻辑，~20 行
- 子项 4（启动自检）：`kernel_initializer` +1 检查函数，~15 行
- 子项 3/5/6/7/8：各 ~50-100 行，可渐进

## ZG-16 方向修订（2026-08-14 用户拍板）

> **原方向（模型能力全景——OpenClaw/LiteLLM provider 适配层学习）暂停**——用户决定转向
> **学习 DeepSeek Harness 模式**：`decisions/dsh_ecosystem_observation_0814.md`——compaction/spill
> 上下文压缩、Trajectory 会话日志、goal/plan/todo 自主性骨架、Cordis 插件化、无 vision 看图技巧
> （ASCII 化表情包方案升级）。**2026-08-14 研究完成**：4 线源码深挖汇总——
> `research/2026-08/zg16_dsh_models_survey_0814.md`（12 项立项清单 P0-P2——token 感知窗口/
> 能力依赖声明/ASCII 看图 为 P0）——**待用户立项拍板**（专项报告：`zg16_dsh_autonomy_skeleton_survey_0814.md`）。
>
> **2026-08-14 用户拍板：Cordis 化与 Linux 化不冲突、甚至统一**——Linux 内核本身就是插件化的
> 鼻祖（模块=插件/try_module_get=可逆效应/modprobe 依赖=inject/bus-driver-device=三角色/
> systemd unit=依赖声明）——Cordis 是同一哲学在 agent 应用层的实现。**MaiBot 的 ZG 系列已在
> 系统层做了依赖仲裁（ZG-10 @startup_item + StartupArbiter）和生命周期管理（ZG-15 活体引用）——
> Cordis 化 = 把同一套机制铺到插件层——plugin_runtime_v2 的插件依赖激活应复用/对齐 ZG-10 模式，
> 不另起炉灶。**（ZG16-1 上下文供给链调研已派发 CA——dsh2ca_zg16_1_context_supply_0814.md）**

## ZG-16 模型能力全景 — 子项详情（2026-08-05 新立）

> 来源：ZG-12 设计讨论中用户提出"不同厂商不同模型的参数要求都不同，如何充分利用"（2026-08-05）。
> **用户决定独立立项**：ZG-12 管"组件自治 + 需求校验 + 适配器框架"（正确性），ZG-16 管"能力数据 + 适配器实现 + 动态最优"（充分利用）。
> **资料准备**：用户将收集市面上常见厂商/模型的 API 文档作为参考学习语料。
> **2026-08-05 策略转变（用户提出）**：厂商文档"复杂的要死"，自己啃边际收益低——**参考开源项目已整理的 provider 适配层**：OpenClaw（30+ 内置 provider、`<provider>/<model-id>` 扁平寻址、custom provider 声明带 contextWindow/maxTokens、fallback 链配置层）、LiteLLM / OneAPI 备选。用户已收集文档作对照，不再从零啃。
> **OpenClaw 源码位置**：`openclaw/`（工作区根目录，早期克隆，commit cb2965d；JS/TS 项目，provider 适配在 packages/ 下）——调研直接读本地，不用再克隆。

### 要解决的问题（ZG-12 保证边界中划出的结构性限制）

1. **厂商参数差异全景**：DeepSeek think 温度无效 / OpenAI 0-2 + top_p / Anthropic 0-1 + extended thinking / Gemini top_k / embedding 无温度——参数语义挂模型不挂任务
2. **厂商独有能力**：Gemini grounding（联网搜索）、Anthropic prompt caching、OpenAI 强制 JSON schema——统一语义表达不了
3. **动态最优**：静态声明 vs 时变最优（高峰用贵模型/低谷用便宜模型，对标 Linux cpufreq governor）
4. **能力实测**：capability 手写 vs 真实 API 行为漂移（Linux device probe 对标）
5. **效果评测**：哪个模型组合产出更好（A/B / 使用统计）

### 阶段划分

- **Phase 0（资料）**：开源 provider 适配层参考（OpenClaw 30+ provider 内置实现为主 + LiteLLM/OneAPI 备选 + 用户已收集文档作对照）→ 能力对比表（provider/参数范围/独有能力/窗口/价格档）。**不做**：从零啃厂商原始文档（策略转变 2026-08-05）
- **Phase 1（数据）**：能力全景数据模型（capability 字段集、参数 schema、vendor_only 扩展声明）——喂给 ZG-12 注册表
- **Phase 2（实现）**：provider 适配器族（每个厂商一个翻译层）+ 能力探测（启动实测 vs 声明校验）
- **Phase 3（策略）**：动态选择策略（价格/性能档切换）、效果评测（使用统计/A-B）

### DeepSeek 针对性优化（2026-08-05 用户提出）

生产环境实际只有 DeepSeek（主 LLM）+ 阿里（embedding/TTS/ASR）——**DeepSeek 域做深，其他厂商保持 OpenAI 兼容通用适配**（现有 `client_type` 机制已覆盖，不重复投入）：
- DeepSeek 深化项：think 模式参数语义（temperature 无效 → capability 翻译）、FLASH/PRO 分层（model_scheduler 现有物）、v4 系列 reasoning 参数、**错误码表**（404/401/402/400/422/429 等——错误码驱动验证的数据源，用户已收集链接：`docs/API 文档/`，含 api-docs.deepseek.com 页面清单）
- 通用层保持：OpenAI 兼容端点 + OpenClaw 参考适配（其他厂商仅骨架）
- 数据源：用户收集的 `docs/API 文档/`（30+ 链接，DeepSeek/阿里等）+ `openclaw/src/model-catalog/provider-index/openclaw-provider-index.ts`（含 deepseek 条目 reasoning/contextWindow 声明）

### 与 ZG-12 边界

- ZG-12 定义注册表/需求声明/适配器**框架与契约**（字段、校验、错误策略）
- ZG-16 提供**真实数据与实现**（各厂商能力表、适配器、探测、策略）
- 顺序：ZG-12 框架先行（P0），ZG-16 数据/实现跟进（P1）；Phase 0 资料收集可与 ZG-12 SSD 并行

## Linux 化扩展（ZG-14/15、17~19）— 子项详情（2026-08-06 规划）

> **定位（用户 2026-08-06）**：Linux 化与"角色更像人"没有直接关系，但计算机系统要**平稳运行和长久发展**不可少这一步——系统底座工程，与人格层并行。
> **调研全部完成**（2026-08-05，CA）：5 份源码级调研报告在 `.shared/research/2026-08/`，基准 Linux 7.2.0-rc6。
> **编号冲突记录**：CA 调研错误升级梯时自定 ZG-16，与用户已立项的"ZG-16 模型能力全景"撞号 → **改号 ZG-14**（空缺编号），调研文件同步改名。教训：调研派发须带 MaiBot 侧正式编号。

| 编号 | Linux 机制（调研文件） | MaiBot 借鉴设计 | 优先级 | 依赖/前置 |
|------|----------------------|----------------|--------|----------|
| **ZG-15** | try_module_get/put 原子活体引用（`zg15_try_module_get_survey_0805.md`） | 插件生命周期：四态机（LIVE/COMING/GOING/UNFORMED）+ 原子引用计数——插件被引用时禁止卸载，卸载中 acquire 原子失败（无 TOCTOU） | **P1** | 插件运行时（plugin_runtime_v2） |
| **ZG-14** | WARN→oops→panic 升级梯（`zg14_error_escalation_survey_0805.md`） | 错误分级处理：最小代价动作（记录/降级）为默认，配置开关逐级升级（→终止/重启组件），错误升级路径可配置 | **P1** | 现有 error_classifier 的 404/429 分类之上加"升级梯"语义 |
| **ZG-17** | watermark 水位 + 两相 shrinker（`zg17_watermark_shrinker_survey_0805.md`） | 记忆库内存管理：低/中/高水位分级，两级回收（可回收对象先回收、不可回收后处理），与 ZG-5 资源限制衔接 | P2 | ZG-5（ResourceCounter 已有四层限制） |
| **ZG-18** | workqueue rescuer 自死锁逃逸（`zg18_workqueue_rescuer_survey_0805.md`） | 后台任务并发上限 + 救援线程：任务依赖链形成死锁时逃逸（对标 asyncio 后台任务池） | P2 | — |
| **ZG-19** | 两级 dirty 阈值写者节流（`zg19_dirty_threshold_survey_0805.md`） | 落盘背压：DB 写入量超阈值时写者节流 + 批量提交时间对齐（round_jiffies_up） | P2 | 数据库写入管线（A_memorix/统计） |

## ZG-20 v2 插件 ToolRegistry 连通 — 子项详情（2026-08-06 正式立项）

> **2026-08-14 核心连通完成（dsh）**：ToolRegistry 加 shared 共享层 + 核心层全局单例
> `get_global_tool_registry()`——v2 bootstrap 挂全局（不再孤立实例）——会话 registry
> `shared=` 引用全局（本层工具优先）——invoke 回退 shared——close 只关本层。
> 7 新测试（pytests/core_test/test_tool_registry.py）+ core/plugin_runtime_v2 156 回归全绿。
> 方案 = 原候选 a+b 混合（全局共享层 + 会话转发）。

> 来源：ZG-15 补充调研发现（bootstrap.py:120-129 `_get_tool_registry` import 目标
> `src.maisaka.agent_autonomy.tool_registry` 全仓不存在 → ImportError 回退孤立实例）。
> 用户拍板：**不能不管**（v2 插件工具对 agent 不可见 = 插件功能失效）。
> 2026-08-06 用户表态：**不着急**——MaiBot 离发布到社区至少半年，
> 插件问题按发布节奏排（发布前完成即可），降为 P2 不阻塞近期主线。

**现状链路**：
- `runtime.py:220`：会话级自建 `ToolRegistry()`（每会话一个）；`:1437-1441` 注册
  PluginToolProvider + 传给 thinking_organ（v1 插件路径正常）；`:2242` 注册 MCPToolProvider
- `v2 bootstrap.py:45`：`_get_tool_registry()` → import 失败 → 孤立 `ToolRegistry()`
- `host_bridge.py:80`：v2 插件 provider 注册进**孤立实例**——thinking_organ（runtime 的
  registry）永远看不到 v2 插件工具

**本质**：全局 v2 工具 vs 会话级 registry 的生命周期架构问题——
"全局注册一次的工具，挂到哪个会话的 registry？"候选方案：
a) registry 全局共享（单例/共享层，agent 工具发现走全局）
b) v2 启动时挂到所有会话 registry（动态加入/移除）
c) 与 ZG-12 委派工具模式命名化合并设计（CA 裁决曾提及）

**优先级**：P1（插件功能可用性）；批次：随插件域推进（可与 ZG-15 编码同期设计）

### Linux 化扩展 2（ZG-21/22/23，2026-08-06 编排）

> 来源：Linux 全量清单调研（编号 3a/4b + 剩余项），源码基准 Linux 7.2.0-rc6。

| 编号 | Linux 机制（调研文件） | MaiBot 借鉴设计 | 优先级 | 依赖/前置 |
|------|----------------------|----------------|--------|----------|
| **ZG-21** | ksoftirqd 延迟处理 + 单次预算（`zg_ksoftirqd_budget_survey_0806.md`，2ms/10 次重启） | 事件回调批量处理：`EventBus._fire_and_forget`（每次 emit 创建 Task，无限制）改 pending 队列 + drainer Task 批量处理 + 单轮时间/次数预算；日志广播 call_soon_threadsafe 风暴同治理 | **P1** | EventBus（ZG-4 已增强） |
> 🔬 **SSD 前算法实验**：回调风暴基准——大量事件同时 emit，当前 create_task 实现 vs 批量 drainer 的调度延迟对比；预算参数（单轮时间/次数）以数据定（Linux 2ms 是内核值，MaiBot 需实测） |
| **ZG-22** | RCU 宽限期 + call_rcu + rcu_barrier（`zg_rcu_grace_period_survey_0806.md`） | 无锁读 + 延迟回收：VectorStore FAISS 索引（RLock 串行化读写 → search 无锁读旧快照 + add 原子替换 + 旧索引延迟释放）；VectorRebuildService 重建期间不降级；ModelRegistry/ConfigManager 热重载原子替换 | **P1** | VectorStore/A_memorix |
> 🔬 **SSD 前算法实验**：FAISS 读写互斥实测——并发 search+add 的真实阻塞延迟（当前 RLock 串行化），验证改造收益；索引原子替换可行性（替换瞬间并发读是否安全） |
| **ZG-23** | 剩余项综合（`zg_remaining_items_survey_0806.md`，1c/2c/2d/3b/4c/5b/6b/7a/8a） | 低价值项合并：fsync/fdatasync 分层 + sync_file_range、OOM 评分注册、kswapd 回收线程等——逐项按调研评估裁决（多数不落地，记录理由） | P3 | — |
| **ZG-23a** | 消息发送去重 + 发言节流（2026-08-07 事故） | 多角色在未白名单群刷屏（六分钟 20+ 条）：① **重复消息 bug**——同一条发送两遍（重试/并发未去重，发送幂等性）② **发言节流**——多角色轮流刷屏无频率限制（对标 ZG-21 预算思想：发言版风暴预算，每角色/每群单位时间发言上限）。运行层机制，与 ZH 的"角色社交智能"（谁该说话）互补 | P3 | 消息发送链路 + maisaka 发言调度 |

### 优先级逻辑（2026-08-06 用户拍板）

- **P1（ZG-15 插件活体引用 + ZG-14 错误升级梯）**：直接关系"平稳运行"——插件卸载竞态和错误升级是运行期最常踩的坑
- **P2（ZG-17/18/19）**：资源管理深化，依赖 ZG-5 底座，随主线推进

### 与既有 ZG 的关系

- ZG-15 插件活体引用 → ZG-1 ServiceManager 的组件 restart/recover 语义扩展（引用计数防"用中卸载"）
- ZG-14 错误升级梯 → ZG-6 状态机的 DEGRADING 触发语义细化（什么错误升到降级/终止）
- ZG-17 记忆水位回收 → ZG-5 资源限制的会话级配额衔接
- ZG-18/19 → 后台任务与写放大治理（审计清理主线的系统层配套）

## ZG-9 极端环境加固 — 子项详情

> 来源：`.shared/decisions/ubuntu2604_extreme_tuning.md`（2026-07-30）
> 核心哲学：不是给 MaiBot 提速，是确保它在极端条件下**不崩、不卡死、可预测地降级**。
> **WSL2 限制**：宿主内核 6.18.35.2（Microsoft WSL2），Kernel 7.0 特性不可用。EEVDF 调参、cgroup latency 隔离标记为待宿主升级。

| 子项　　　　　　　　　　　　　　　| 效果　　　　　　　　　　　　 | 风险　　　　　　　 | 建议　　　　　　　　　　　　　 |
| -----------------------------------| ------------------------------| --------------------| --------------------------------|
| EEVDF 调度器调参　　　　　　　　　| P99 延迟降 20-30%　　　　　　| 低　　　　　　　　 | ⚠️ 需 Kernel 7.0，WSL2 暂不可用 |
| cgroup latency 隔离　　　　　　　 | 容器独占低延迟域　　　　　　 | 低　　　　　　　　 | ⚠️ 需 Kernel 7.0，WSL2 暂不可用 |
| OOM score 分层　　　　　　　　　　| 关键进程豁免，非关键优先被杀 | 低　　　　　　　　 | ✅ 3 行代码　　　　　　　　　　 |
| PSI 压力监控　　　　　　　　　　　| 提前预警　　　　　　　　　　 | 无　　　　　　　　 | ⏳ **未实现（移交 ZG-5）**：ZG-9 只有 systemd slice 配置（50-psi.conf），无应用层读取；CA 已交 ZG-5 读 /proc/pressure/* |
| /tmp tmpfs 挂载　　　　　　　　　 | 临时 I/O 降为 0　　　　　　　| RAM 占用　　　　　 | ✅ 内存>4G 时　　　　　　　　　 |
| swappiness=0　　　　　　　　　　　| 容器内 swap 禁用　　　　　　 | OOM 概率↑　　　　　| ✅ 有 GPU 时必选　　　　　　　　|
| I/O weight 隔离　　　　　　　　　 | 日志不阻塞数据写入　　　　　 | 低　　　　　　　　 | ⚠️ 仅争抢时生效　　　　　　　　 |
| io_uring（3.14 第三方→3.15 原生） | 网络 I/O↑50%　　　　　　　　 | 第三方稳定性待验证 | ⚠️ 3.15 GA 后零成本升级　　　　 |

ZG-9 与 ZG-5 互补：ZG-5 管理应用如何声明资源需求，ZG-9 管理基础设施如何兜底。

ZG-9 是 ZG-1/ZG-3 的前置条件：OS 层不稳定时，看门狗检测到的"超时"可能是调度器饿死协程的锅，不是代码的锅。ZG-9 先确保可预测的运行环境，ZG-1/ZG-3 才能可靠检测。

ZG-9 OOM 保护与 ZG-3 看门狗分工：OOM 保护管"死之前的优先级排序"（关键进程免杀），看门狗管"死之后的处理"（检测→重启→通知）。ZG-3 重启的进程应自动获得 OOM 保护优先级。

## 推进路线（2026-08-04 刷新）

```
批次1（P0 打底）✅ 已完成
  ZG-9 极端环境加固 ✅ → ZG-1 服务管理器 ✅ → ZG-3 看门狗 ✅ → 审阅清理 ✅

批次2（P0 收尾 + P1 启动）✅ 已完成
  ZG-2 统一日志管线 ✅ → 审阅清理 ✅ → ZG-6 系统状态机 ✅

批次3（P1 深化）✅ 已完成
  ZG-4 事件总线增强 ✅ → ZG-5 资源限制 ✅ → 审阅清理 ✅

批次4（P2 打磨）✅ 已完成
  ZG-7 污染标记 ✅ → ZG-8 控制消息优先级 ⏳（唯一未编码的 P1+）

批次5（P1 配置重写）⏳ 待启动
  ZG-12 模型配置重写 → 审阅清理
  前置：ZG-11 Phase 0 ✅（embedding 阿里 API 已接入）+ embedding 微调 ✅（ONNX 量化完成）

批次6（Linux 化扩展）⏳ 调研完成待 SSD
  ZG-15 插件活体引用 → ZG-14 错误升级梯 → 审阅清理
  （ZG-17/18/19 为 P2，随主线推进）

批次7（Linux 化扩展 2）⏳ 调研完成待 SSD
  ZG-21 事件回调预算 → ZG-22 无锁读延迟回收 → 审阅清理
  （ZG-23 剩余项综合为 P3，裁决式处理）
```

### 当前优先级排序

1. **ZG-12 模型配置重写** — 唯一 P0 剩余，建议走 SDD 流程
2. **ZG-16 模型能力全景**（2026-08-05 新立）— "充分利用不同厂商模型能力"独立立项：厂商文档语料（用户收集）→ 能力全景 → provider 适配器体系 → 动态策略。与 ZG-12 边界：ZG-12 管"组件自治 + 需求校验 + 适配器框架"，ZG-16 管"能力数据 + 适配器实现 + 动态最优"
3. **ZG-15 插件活体引用**（2026-08-06 新排）— 插件卸载竞态治理，系统平稳运行底座，调研完成待 SSD
4. **ZG-14 错误升级梯**（2026-08-06 新排）— 错误分级处理升级语义，调研完成待 SSD
5. **ZG-8 控制消息优先级** — P1，独立可做
6. **ZG-21 事件回调预算**（2026-08-06 新排）— 回调风暴治理（EventBus 批量 drainer），调研完成待 SSD
7. **ZG-22 无锁读延迟回收**（2026-08-06 新排）— VectorStore 读写互斥/热重载原子替换，调研完成待 SSD
8. **ZG-7 P0 遗漏** — `degrade_on_taint_mask` 掩码级触发，小范围
9. **ZG-17/18/19** — P2 资源管理深化（记忆水位/任务救援/落盘背压），调研完成，随主线推进
10. **ZG-23 剩余项综合** — P3 低价值项裁决式处理
11. **ZG-10/ZG-11** — P2 未来方向，不急

### 附加成果（非 ZG 编号但随 ZG 推进完成）

- **记忆融合架构改造**：写入融合管线 + 检索融合（ScoreNormalizer + SpreadAnchorRetriever）+ 配置注册
- **Embedding 微调全流程**：数据提取 → 三元组构造 → GPU 微调 → ONNX INT8 量化 → embedding_server
- **审阅清理**：零引用死代码删除（37 文件 -5140 行）+ 人物画像死代码删除
- **消息发送失败修复**：T1/T2 编码完成
- **既有测试债务暴露**：601 passed / 195 failed / 77 errors（均为既有债务，非回归）

## 已完成

| 日期　　　 | 内容　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　 | 提交　　　|
| ------------| ----------------------------------------------------------------------------------------------------------------------------------------------------| -----------|
| 2026-07-30 | 扁平人格→四层模型迁移（6 调用方 + 30 测试）　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　| 54514e7f8 |
| 2026-07-30 | send_service 废弃方法清理（7 方法 ~250 行）　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　| 更早　　　|
| 2026-07-30 | ZG 研究备忘 + 废弃系统清单　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　 | 文档　　　|
| 2026-07-31 | **ZG-1 服务管理器**（systemd 化：引擎层 dependency_graph/health_check/lifecycle/recovery + 适配器 + main.py 启动接管 + E2E，84 测试）　　　　　　　| 86a1e91ff |
| 2026-07-31 | **ZG-9 极端环境加固**（mem_limit/swap=0/OOM 保护/tmpfs，WSL2 内核 6.18；Kernel7.0 特性待升级时补）　　　　　　　　　　　　　　　　　　　　　　　　 | 89ee8c815 |
| 2026-08-01 | **ZG-6 系统状态机**（BOOTING→READY→DEGRADING→SHUTTING_DOWN + 通知链 + 崩溃导出 + WebUI /lifecycle + 信号退出联动，20 需求 48 验收全覆盖，38 测试） | c38dd6f1c |
| 2026-08-01 | **ZG-4 事件总线增强**（统一 Vote 四值投票 + BAD-only robust 回滚 + EventBus robust/nofail + unique_priority + 内省，28 需求 39 验收，78 测试）　　 | 200dd93cf |
| 2026-08-01 | **ZG-2 统一日志管线**（结构化日志 + RingBuffer + 按调用点 ratelimit + deferred output + 全 ERROR O(1) 快速判定，31+33 测试）　　　　　　　　　　　　| 693b735f6+ |
| 2026-08-02 | **ZG-3 看门狗补强**（S1 延迟报告 + S2 检测线程健康检查 + S3 V2 注册验证 + S4 blocker 追踪，25 新测试全绿）　　　　　　　　　　　　　　　　　　　　　| c26e1ee4c+ |
| 2026-08-02 | **ZG-5 资源限制**（ResourceCounter + FourTierLimit + PressureDetector + OOMHandler + EventPropagator + 适配器全接线，75 测试全通过）　　　　　　　　　　| 16d53f284+ |
| 2026-08-02 | ZG-5 **§11 WebUI 内省接口暂缓**（适配器内省方法已实现，仅缺 WebUI 路由暴露）　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　 | 未做　　　 |
| 2026-08-02 | **审阅清理：零引用死代码删除**（subagent/18 + consolidation/4 + goal/5 + event_sensor/4 + message_port + embedding manager+presets + monologue 2文件 = 37文件 -5140行） | f63ca9bf1 |
| 2026-08-02 | **审阅清理：路线图标记** — cross_chat/ 待实现（社会关系功能）；deepseek 4文件 待评估（LLM优化适配）；learners/ expression+jargon 待独立 SSD 任务（21处活跃引用，与社会关系理念不合） | 文档　　　 |
| 2026-08-03 | **ZG-7 污染标记**（8 位 TaintFlag + 6 位运行时接线 + TaintActionMapper + CrashDump 内省 + 配置域扩展 + WebUI 展示，68 测试全绿）　　　　　　　　　　　| 7aa2d8c1f+ |
| 2026-08-03 | **人物画像死代码删除**（profile 相关废弃代码清理）　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　| 合并到 main |
| 2026-08-03 | **记忆融合架构改造**（写入融合管线 + 检索融合 ScoreNormalizer + SpreadAnchorRetriever + 配置注册 + 部署文档）　　　　　　　　　　　　　　　　　　　　　　| 多次提交　 |
| 2026-08-03 | **Embedding 微调全流程**（数据提取 60650→清洗 2291 条三元组 + GPU 微调 bge-large-zh-v1.5 + ONNX INT8 量化 312MB + embedding_server）　　　　　　　　　| ed53af9f6+ |
| 2026-08-03 | **消息发送失败修复**（T1/T2 编码完成）　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　| worktree　 |

## ZG-6 系统状态机遗留事项（2026-08-01）

> ZG-6 已编码完成并合并（c38dd6f1c）。CA 审查通过，CX 审查 2 bug 已修。
> 交接报告：`.shared/handoff/cc2ca_zg6_coding_0801.md`；审查报告：`.shared/handoff/ca2cc_zg6_review_0801.md`

| # | 项 | 内容 | 触发时机 |
|---|-----|------|---------|
| ZG-6-R1 | 全量既有回归确认 | ✅ 已完成（2026-08-01）：pyproject asyncio_mode 修复后全量 pytest 首次真正跑 auto 模式。结果：**601 passed（含 ZG-6 全部 38 测试）**；195 failed + 77 errors 均为**主仓库既有测试债务**（测试与代码不同步：引用已删模块 `behavior_pattern_store`/`expression._chat_manager`/`message.TextComponent`、config fixture 未初始化、lab/ 实验目录混入），无一由 ZG-6 或配置修复引入。需另立治理项 | ✅ 完成 |
| ZG-6-R2 | 通知链 per-subscriber 超时 | 当前全局 5s 超时；design 已裁定不优先，订阅者超时记告警视为 DONE | 出现"单一慢订阅者拖累全局"实证时 |
| ZG-6-R3 | ServiceManager 自适应接入 | 适配器谓词已就绪，ServiceManager/消息管道按状态自适应（BOOTING 拒收等）尚未接线 | 后续系统审阅时评估 |

## 全量回归暴露的既有测试债务（2026-08-01，ZG-6-R1 副产品）

> 主容器排除 lab/ 与 10 个已知行为学习遗留文件后：601 passed / 195 failed / 77 errors。
> 这些失败在 pytest-asyncio 配置修复前被 strict 模式掩盖（async 测试根本不跑），修复后暴露——**是长期债务，不是回归**。

| 类别 | 文件/范围 | 根因 |
|------|----------|------|
| 引用已删模块 | common_test behavior_*（4 文件，534b8890b 废弃后测试未同步清理） | 行为学习系统删除遗留 |
| 引用已删模块 | webui expression/jargon routes、session_message_test 等 | 路由/API 重构后测试未同步 |
| fixture 未初始化 | chat_config_utils 等（config_manager 未 init） | 测试环境依赖缺失 |
| 目录混入 | lab/exploratory/（8 文件） | 本地实验目录混入回归收集，AGENTS.md 默认原则应排除 |

**治理建议**：另立测试卫生批次（对齐"功能/组件审阅清理"主线）——同步/删除失效测试 + 全量回归加入 `--ignore=lab` 基线命令（建议写入 pyproject addopts）。

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

> 2026-08-07 子代理调研刷新：全部文件一年内 +9%~+18%（无瘦身趋势）；statistic.py 记录过时（已拆好）；拆分优先级见下表。

| # | 文件 | 现状行数（记录） | 判定 | 拆分建议 |
|---|------|----------------|------|---------|
| 9 | `src/config/official_configs.py` | 7,090（6,189） | 大但健康：82 个独立配置类，无相互依赖 | 不拆（零行为收益；测试 direct 依赖） |
| 10 | `src/A_memorix/core/utils/web_import_manager.py` | 4,487（3,901，**已移到 A_memorix**） | 该拆：单类 `ImportTaskManager`（157 方法）堆 7 套导入管道 | **中优先**：按管道拆策略类/mixin（共享实例状态多） |
| 11 | `src/webui/routers/statistic.py` | **已删除**（2,611） | 重叠问题已解决：拆成 `routers/statistics.py`（169 薄路由）+ `services/statistics_service.py`（525 重服务） | 无需动；**真正剩余大文件：`src/chat/utils/statistic.py`（2,929 行，`StatisticOutputTask` ~2,490 行 HTML 报告生成）**，低优先 |
| 12 | `src/A_memorix/core/storage/metadata_store.py` | 2,861（2,626） | god class：单类 `MetadataStore` 230 方法覆盖 8 领域 | 中优先但**高风险**：FTS 方法名是 `sparse_bm25.py` 硬契约（`fts_search_bm25` 等）；12+ 调用方依赖单类接口；先拆最孤立的 episode/vector 队列段试水 |
| 13 | `src/maisaka/runtime.py` | 2,298（1,945） | 大但内聚：对话循环主状态机（`MaisakaHeartFlowChatting` 125 方法） | 低优先：已有 mixin 先例（`focus/`、`display/`），可继续抽 monitor/proactive/deferred 为 mixin |
| 14 | `src/webui/routers/memory.py` | 2,720（2,399） | 该拆：一个文件聚合 10 个子系统（87 端点 + 1,800 行 helper，比例 1:4） | **高优先**：按端点前缀拆子 router（graph/import/tuning/timeline...）；无外部模块依赖（仅 routes.py 引 router/compat_router），风险最低 |

**共同风险**：metadata_store FTS 方法名 = sparse_bm25 硬契约；official_configs 有测试 direct 依赖；runtime/web_import_manager 是内核活跃调用点——拆分需保留公开接口或加兼容层。

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

- ~~ZG 方向优先级是否需要调整~~ → 已确定 5 批次路线，批次 1-4 已完成
- ~~功能/组件清理的切入点和范围~~ → 随 ZG 批次推进审阅，已完成两轮
- OS 化方向备忘录（`os_like_direction.md`）中是否有其他需要修正的幼稚想法
- **ZG-12 重写范围**：用户决定整体重写，需走 SDD 流程确定 spec/design
- **ZG-8 启动时机**：唯一未编码的 P1+ 方向，独立于 ZG-12
- **worktree 清理**：6 个 prunable 分支待清理
- **既有测试债务治理**：195 failed + 77 errors，需另立治理项

> 全项目债务全景和项目路线已迁入 `.shared/roadmap.md`，本文件只追踪与 ZG 直接相关的内容。

## ZG-3 看门狗编码遗留问题（2026-07-31）

> ✅ **Linux 源码研究已补**（2026-08-02）：`kernel/watchdog.c` / `kernel/hung_task.c` / `include/linux/nmi.h` / `watchdog_hld.c` / `workqueue.c` 调研完成，产出 `.codeartsdoer/specs/zg3_watchdog/linux_watchdog_research.md`（CA）。结论：现有实现对应良好，S1 延迟报告 / S2 检测线程健康 / S3 V2 注册 / S4 blocker 追踪已落地（ZG-3 补强，见已完成表）。

| # | 严重度 | 位置 | 问题 | 当前影响 | 后续处理 |
|---|--------|------|------|---------|---------|
| 1 | 中 | `runner_health_bridge.py:50-80` | `register_v2_supervisor` 未将 `_on_v2_timeout` 注入到 `heartbeat_manager` 的 `timeout_callback` | V2 心跳超时回调桥接未连接，仅 V2 状态 diff 轮询工作 | ✅ **已修复**（2026-08-02 核实：`:84` add_timeout_listener 已注入） |
| 2 | 低 | `main.py:305` | `WatchdogConfig()` 使用默认配置，未从配置 Port 读取 | 无法通过配置文件自定义看门狗参数 | ✅ **已修复**（2026-08-02 核实：`:339` get_app_config_port().get_watchdog_config()） |
| 3 | 低 | `main.py` | Runner 注册（tasks 7.2）未实现 | 桥接部分空转，事件循环检测完整工作 | V1 ✅ 已实现（`:351` 批量注册 plugin_runtime supervisors）；**V2 待补**（register_v2_supervisor 方法已存在未调用） |
| 4 | 低 | `watchdog_adapter.py:85` | `_notify_subscribers` 在检测线程中调用 | 订阅者回调需线程安全 | ✅ **已正确处理**（2026-08-02 核实：run_coroutine_threadsafe 调度到主循环） |

## ZG-2 统一日志管线遗留标记（2026-08-01，以后再改）

> ZG-2 已编码完成并合并（693b735f6）。printk 对照复盘见 `.shared/decisions/zg2_printk_review_0801.md`。
> ✅ **Linux 源码深入研究已完成**（2026-08-02）：详见 `.codeartsdoer/specs/zg2_log_pipeline/linux_printk_research.md`。覆盖无锁环形缓冲（prb 双层环设计）、cont 行续接（KERN_CONT）、console_lock handover（friendly handover + nbcon takeover）、kmsg_dump dispatcher（多 dumper RCU 分发）、deferred output（per-CPU 安全模式）、__ratelimit（每调用点 token 桶）。6 项未吸收精髓逐项裁决"不补"并写明理由。
> 以下为"以后再改"的可改进项，不阻塞当前使用：

| #       | 项　　　　　　　　　　　| 内容　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　 | 触发时机　　　　　　　　　　　　　　　　　　　　　 |
| ---------| -------------------------| --------------------------------------------------------------------------------------------------------------| ----------------------------------------------------|
| ZG-2-L1 | 摘要输出完全异步化　　　| 当前事件循环不可用时同步 fallback；对标 printk deferred output，改为排队而非同步阻塞　　　　　　　　　　　　 | 日志风暴期间摘要输出阻塞写线程的实测证据出现时　　 |
| ZG-2-L2 | RingBuffer 无锁方案评估 | ✅ **已完成**（2026-08-02）：实测完整 emit 单条 0.0094ms（触发线 1ms 的 106 倍余量），锁非瓶颈（占 2%），**维持 RLock 不改**。报告 `.shared/decisions/zg2_l2_lockfree_ringbuffer_0802.md`。**顺带发现真实缺陷**：全 ERROR 满缓冲 `_evict_oldest_non_error` O(capacity) 扫描 223µs/条（正常 127 倍，逼近触发线）——另立任务修复 | 已完成（实测否决）；新缺陷修复待排期 |
| ZG-2-L3 | 按调用点 ratelimit　　　| ✅ **已完成**（2026-08-02）：source_key 改调用点 (pathname, lineno) + call_site 摘要；合成 record（Runner 桥接占位符）回退 logger+event 键（CX P2）；31 passed | 已完成（主动修正，未等实证） |

## ZG-13 角色语音（TTS 输出）— 子项详情

> 2026-08-04 立项：给十三个角色接入本地 TTS 语音输出（每角色一音色）。
> 调研依据：`.shared/research/2026-08/voice_output_capability_0804.md`（Explore 全仓库调研）

### 现状（调研结论）

| 维度 | 现状 |
|------|------|
| TTS 输出 | **无**（全仓库零 synthesize 代码），但管道半成品在 |
| ASR 输入 | 有，默认关闭（`[voice] enable_asr = false`，链路完整） |
| 音色配置 | 无（14 个 agent_id 均无 voice 字段，需新建） |
| 现成管道 | `VoiceComponent`（message_component_data_model.py:128）+ napcat voice→record 编码器（segment_encoder.py:176） |

### 设计方向

```
本地 TTS 服务（候选：IndexTTS 2.0 / GPT-SoVITS / CosyVoice 2.0，zero-shot 克隆免微调）
→ 音色配置：每个 agent_id 一段参考音频（14 角色 14 音色）
→ maisaka 回复工具（reply.py:368 前）：按 agent_id 选音色 → 合成 → VoiceComponent
→ napcat 桥接：_handle_outbound_message 补 convert_segments 编码 → record 段
```

- **候选模型**：IndexTTS 2.0（中文天花板，2B 级，笔记本 8GB 勉强）；GPT-SoVITS（1B 级稳跑，中文接近）；CosyVoice 2.0（流式，轻量）。zero-shot 克隆 = 不用微调
- **关键坑**：napcat maim_message 桥接路径只特殊处理 text 段，voice 段透传 → 需补 convert_segments 编码（现成逻辑可复用）
- **策略**：管道优先模型次之——先跑通用语音输出口 + 音色配置，模型层留接口可换
- **硬件**：笔记本 5060 8GB 跑 IndexTTS 2.0 勉强 → 低频场景（角色主动说话/情绪高光）才发语音，文字为主体

## 部署形态设计方向（2026-08-04）

> 用户决策：**保留 Docker**（环境隔离 + 可重建，NapCatQQ 回退白版本改配置重建即可，不用操心依赖）。
> 与 Linux 化正交：Docker 管环境隔离层，ZG 系列管系统治理层——两者不冲突，容器还是 ZG-9 极端加固的天然沙箱。

### 三个工程化升级

1. **镜像版本标签化**：镜像打版本标签（如 `maibot:napcat-old` / `maibot:stable`），回退 = 改 tag 重建，连配置都不用动
2. **数据卷全分离（容器无状态化）**：记忆库（A_memorix）、向量库（FAISS）、日志、配置全部放 volumes——重建容器不丢数据；MaiBot 可随时重建
3. **模型服务独立常驻**：本地模型（bge 微调、TTS、未来 LLM）放宿主机或独立容器，MaiBot 容器通过 localhost 调——GPU 透传（Docker Desktop WSL2 nvidia-container-toolkit）搞不定的场景直接宿主机跑；架构上模型是资源池、MaiBot 是消费者（呼应 ZG-12 ComfyUI 资源池哲学）

### WSL2 注意

- `/mnt/e` 跨文件系统 IO 慢——容器的 volumes 别挂到 Windows 盘（数据目录放 Linux 侧或容器内），否则记忆写入拖慢

### 本地模型宿主机方案（2026-08-04，用户方向）

模型服务（embedding/TTS 等）跑 **Windows 宿主机**（GPU 在 Windows 侧，torch cu128 天然可用），MaiBot 容器通过 Docker Desktop 内置 `host.docker.internal` 连接：

```toml
# model_config.toml 本地模型 provider
base_url = "http://host.docker.internal:9997/v1"
```

**步骤**：① 服务监听 0.0.0.0（勿 127.0.0.1）② Windows 防火墙放行端口 ③ 容器内 base_url 指 host.docker.internal

**收益**：
- MaiBot 容器无状态重建不影响模型服务（模型加载一次几 GB）
- embedding 变 I/O 等待 → asyncio 天然处理，**ZG-11 Phase 2 worker 不需要实现**
- 配置层零敏感（OpenAI 兼容接口，换服务器只改 base_url）

**坑**：host.docker.internal 是 Docker Desktop 特有；迁原生 Linux Docker 时模型服务同机 localhost 直连或 `--add-host`。
