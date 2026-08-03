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

## ZG 方向清单与优先级

### 🔴 P0 — 应该做

| 编号　　　　 | 方向　　　　　　　　　　　　 | 理由　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　 | 复杂度 | 层级 |
| --------------| ------------------------------| ------------------------------------------------------------------------------------------------------| --------| ------|
| ~~**ZG-1**~~ | ~~服务管理器（systemd 化）~~ | ✅ **已完成**（2026-07-31，引擎层+适配器+main.py 启动接管，见已完成表）　　　　　　　　　　　　　　　 | 低　　 | 应用 |
| **ZG-2**　　 | 统一日志管线（journald 化）　| CQ-11 已在清理 45 处 `import logging` 残留，趁机加结构化+环形缓冲+ratelimit　　　　　　　　　　　　　| 中　　 | 应用 |
| **ZG-3**　　 | 看门狗（watchdog 化）　　　　| asyncio 事件循环阻塞 + Runner 子进程无响应，当前最痛的运行时风险　　　　　　　　　　　　　　　　　　 | 低　　 | 应用 |
| ~~**ZG-9**~~ | ~~极端环境加固~~　　　　　　 | ✅ **已完成**（2026-07-31，mem_limit/swap=0/OOM保护/tmpfs，WSL2 内核 6.18；Kernel7.0 特性待升级时补） | 低　　 | 基础 |

### 🟡 P1 — 值得做但靠后

| 编号　　　　 | 方向　　　　　　　　　　　　　　　| 理由　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　 | 层级 |
| --------------| -----------------------------------| --------------------------------------------------------------------------------------------------------| ------|
| ~~**ZG-4**~~ | ~~事件总线增强（D-Bus 化）~~　　　| ✅ **已完成**（2026-08-01，Vote 统一投票 + BAD-only robust 回滚 + EventBus robust/nofail，78 测试全绿） | 应用 |
| **ZG-5**　　 | 资源限制（cgroups 化）　　　　　　| 单进程下需求弱，会话/智能体数增长后价值上升。可先做每会话 LLM 配额　　　　　　　　　　　　　　　　　　 | 应用 |
| ~~**ZG-6**~~ | ~~系统状态机（system_state 化）~~ | ✅ **已完成**（2026-08-01，见已完成表）　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　 | 应用 |
| **ZG-12**　 | 模型配置仲裁（alternative 化）　 | V1 遗留命名(replyer/planner/utils)+硬编码回退+embedding 静默失败+TaskConfig 无分化，见下方子项详情 | 应用 |

### 🔵 P2 — 打磨

| 编号　　 | 方向　　　　　　　　　　　　| 理由　　　　　　　　　　　　　　　　　　　　　　 | 层级 |
| ----------| -----------------------------| --------------------------------------------------| ------|
| **ZG-7** | 污染标记（tainted_mask 化） | ✅ **已完成**（2026-08-03，8 位 TaintFlag + 6 位运行时接线 + TaintActionMapper + CrashDump 内省，78 测试全绿）。**Linux 深度对标报告**：`.codeartsdoer/specs/zg7_tainted_mask/linux_taint_comparison_report.md`，核心发现：4/8 标志完全对齐 Linux，P0 遗漏为 `degrade_on_taint_mask` 掩码级触发（对标 `panic_on_taint`），P2 遗漏为 3 个候选新标志（UNHANDLED_FATAL/EXTERNAL_FALLBACK/LOOP_STALL） | 应用 |
| **ZG-8** | 控制消息优先级（signal 化） | 紧急消息优先于常规消息，主智能体不可淘汰　　　　 | 应用 |

### 🟢 P3 — 未来方向

| 编号 | 方向 | 理由 | 层级 |
|------|------|------|------|
| **ZG-10** | 启动编排演进（initcall→systemd 化） | 见下方 ZG-10 子项详情 | 应用 |
| **ZG-11** | 多核利用（SMP 化） | 见下方 ZG-11 子项详情 | 基础 |

## ZG-10 启动编排演进 — 子项详情

> 当前 ZG-1 为 Windows SCM 式集中注册（main.py 内 30 个 `orchestrator.register()`），新增组件需改编排器。
> 演进目标：Linux 式**分层仲裁**——组件声明需求，编排器仲裁，组件无法绕过编排器。

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

**Phase 1（FAISS 搜索非阻塞化）**：
- `await loop.run_in_executor(ThreadPoolExecutor, vector_store.search, query, k)`
- FAISS 是 C 扩展，释放 GIL → ThreadPoolExecutor 即可用多核
- 改动量：~3 行（search 调用点）

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

## ZG-12 模型配置仲裁 — 子项详情

> 2026-08-03，CA 提议，基于模型配置系统深度调研。
> 对标 Linux **alternative framework**（系统根据硬件能力选最优实现）+ **device model**（统一设备抽象）。
> 核心问题：V1 遗留命名不反映当前架构，回退链硬编码，TaskConfig 无分化，embedding 静默失败。

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

批次5（P1 配置仲裁）
  ZG-12 模型配置仲裁 ──→ 审阅清理
  前置：ZG-11 Phase 0（embedding 配置接入）确保配置系统有真实负载可验证
```

每步前后都做功能/组件审阅。

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
| 2026-08-02 | **ZG-5 资源限制**（cgroups 化：ResourceCounter 层级计数 + FourTierLimit 四档限制 + PressureDetector 压力分级 + OOMHandler OOM 处置 + EventPropagator 事件传播 + Adapter 适配器，§1-§10+§12 完成 75 测试全通过，worktree `zg5-resource-limit`） | 16d53f284+ |
| 2026-08-02 | ZG-5 **§11 WebUI 内省接口暂缓**（用户决定：和 WebUI 有关的暂时不做。适配器内省方法 `get_resource_tree_view`/`get_pressure_history`/`get_oom_history` 已实现，仅缺 WebUI 后端路由暴露） | 未做　　　 |
| 2026-08-02 | **审阅清理：零引用死代码删除**（subagent/18 + consolidation/4 + goal/5 + event_sensor/4 + message_port + embedding manager+presets + monologue 2文件 = 37文件 -5140行） | f63ca9bf1 |
| 2026-08-02 | **审阅清理：路线图标记** — cross_chat/ 待实现（社会关系功能）；deepseek 4文件 待评估（LLM优化适配）；learners/ expression+jargon 待独立 SSD 任务（21处活跃引用，与社会关系理念不合） | 文档　　　 |

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
