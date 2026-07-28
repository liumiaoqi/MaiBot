# 规则性文件修订 — 实现方案

# 一、需求与存量功能关系分析

## 1.1 需求功能与存量功能对比

### 1.1.1 已实现功能

| 需求功能 | 存量功能 | 代码位置 | 匹配度 |
|---------|---------|---------|--------|
| 核心架构原则记录（9个Protocol） | 9个Protocol已在 `src/core/protocols.py` 中定义 | `src/core/protocols.py` | 100% |
| Agent-owns-Thinking 架构 | ThinkingOrgan + ThinkingOrganFactory + ParallelThinkScheduler 已实现 | `src/maisaka/agent_autonomy/thinking_organ.py`, `thinking_organ_factory.py`, `parallel_think.py` | 100% |
| 管家系统集成 | Butler 三层过滤 + 提醒 + 插话已在 Orchestrator 中集成 | `src/maisaka/agent_autonomy/orchestrator.py` | 100% |
| 内心世界系统 | InnerWorld + InnerWorldSnapshot 已实现 | `src/maisaka/agent_autonomy/inner_world.py` | 100% |
| 核心隔离（chat_manager 导入消除） | 核心模块已通过 Protocol 接口隔离，适配器层是唯一允许导入组件的地方 | `src/core/adapters/` | 100% |
| 通知分类统一（NoticeClassifier + NoticeKind） | 已消除 napcat_* 泄漏，统一通过 NoticeClassifier 分类 | `src/core/adapters/notice_classifier.py`, `src/core/types.py` | 100% |
| _KernelRuntimeFacade 删除 | 代码中 0 匹配，已完全删除 | `src/A_memorix/core/runtime/sdk_memory_kernel.py` | 100% |
| enqueue_proactive_task hack 消除 | 管家插话/提醒改为直接调用 ThinkingOrgan + MessagePort.send() | `src/maisaka/agent_autonomy/orchestrator.py` | 100% |
| A_memorix 隔离（person_profile） | person_profile 已通过 MemoryServicePort 调用 | `src/maisaka/memory/person_profile.py` | 100% |
| 阶段 7A 基础设施（config/ + admin/base + services/ 包） | config/、admin/base.py、services/ 包均已创建 | `src/A_memorix/core/runtime/config/`, `admin/base.py`, `services/__init__.py` | 100% |
| 阶段 7B 功能域服务提取 | 15 个服务文件已存在于 services/ 目录 | `src/A_memorix/core/runtime/services/` | 100% |
| 阶段 7C Admin Handler 提取 | 14 个 Admin Handler 文件已存在于 admin/ 目录 | `src/A_memorix/core/runtime/admin/` | 100% |
| 阶段 7D-01 删除 _KernelRuntimeFacade | 已完成（0 匹配） | `src/A_memorix/core/runtime/sdk_memory_kernel.py` | 100% |
| 阶段 7D-03 消除 or ""（目标 ≤150） | 当前 87 处，已低于 150 目标 | `src/A_memorix/core/runtime/sdk_memory_kernel.py` | 100% |

### 1.1.2 需要扩展的功能

| 需求功能 | 存量功能 | 差异说明 | 扩展方向 |
|---------|---------|---------|---------|
| AGENTS.md 智能体自主性架构原则完整性 | 当前仅3条原则（决策权、通知消息处理、规则引擎优先） | 缺少组件兼容核心原则、核心禁止项、内心状态三层、核心进化方向等已确立原则 | 补充会话级规则中已确立但未写入 AGENTS.md 的架构原则 |
| AGENTS.md 会话 ID 规范 | 当前要求"通过 chat_manager 的内部接口" | 与核心隔离原则矛盾：核心禁止项第1条禁止核心直接导入 chat_manager | 将"通过 chat_manager 的内部接口"改为"通过 SessionRepository Protocol 接口查询" |
| AGENTS.md A_memorix 修改规则 | 当前仅说"修改约束仅来自核心隔离和 Protocol 接口契约" | 未反映 SDKMemoryKernel 重构实际进展（services/ 和 admin/ 已提取、Facade 已删除、host_service 直接访问服务） | 补充 SDKMemoryKernel 重构进展说明和当前约束边界 |
| AGENTS.md or "" 兜底规范 | 当前禁止 or "" 兜底但无执行优先级和豁免条件 | SDKMemoryKernel 仍有 87 处 or ""，规则缺少量化目标和合理豁免场景 | 明确 or "" 的消除优先级、当前状态（87处）和合理豁免场景（如外部数据源返回值可能为 None） |
| AGENTS.md getattr 规范 | 当前要求减少 getattr 但无量化目标 | 当前 SDKMemoryKernel 有 8 处 getattr，规则无当前状态和目标值 | 补充当前 getattr 数量（8处）和目标（≤5处），以及保留场景的判定标准 |
| AGENTS.md debug 规范 | 当前要求"不要总是考虑 fallback" | 会话 ID 规范中"不要把自行计算的 fallback hash 写入数据库"本身是一种 fallback 策略，表述矛盾 | 消除矛盾表述，明确"不兜底"与"不写入脏数据"的区别 |
| tasks.md 阶段 7A-7C 任务状态 | 当前全部标记为未完成 `[ ]` | 实际已完成：15个服务文件、14个Admin Handler、config/ 包均已创建 | 将已完成的任务标记为 `[x]`，更新文件名和类名与实际代码一致 |
| tasks.md 阶段 7D 部分任务状态 | 当前全部标记为未完成 | TASK-7D-01 已完成（Facade 已删除）、TASK-7D-03 已完成（87处 < 150目标）、TASK-7D-02 部分完成（8处 > 5目标） | 更新各任务的实际完成状态和剩余目标 |
| tasks.md SDKMemoryKernel 行数描述 | 描述为 9650 行 | 实际当前为 2679 行（经多轮瘦身） | 更新为当前实际行数 2679 |
| tasks.md 阶段 7B/7C 文件名与类名 | 描述的文件名/类名与实际代码不一致 | 如 `graph_admin.py` → 实际 `graph.py`、`memory_maintenance.py` → 实际 `maintenance.py` 等 | 以实际代码为准更新 tasks.md 中的文件名和类名 |
| tasks.md 阶段 7E 验收标准 | 当前验收标准数值与实际进展不匹配 | getattr 目标 ≤5（当前8处）、行数目标 ≤800（当前2679行）差距过大 | 根据实际进展调整验收标准为可达成目标 |
| .codeartsdoer/AGENTS.md 工程上下文 | 当前仅包含 `Language Context: ["Python"]` | 缺少项目特定的工程上下文（核心架构约束、代码风格、技术栈） | 补充核心架构约束、代码风格关键规则、技术栈信息，明确与项目 AGENTS.md 的职责分工 |

### 1.1.3 需要新增的功能或接口

**AGENTS.md 新增条目**：
1. **核心架构原则补充**：组件兼容核心原则、核心禁止项（7条）、核心进化方向、内心状态三层
2. **已完成架构的规则说明**：内心世界系统（InnerWorld）、管家系统集成、Agent-owns-Thinking、并行思考
3. **架构债务追踪规则**：重大架构变更后同步更新规则性文件的要求

**tasks.md 新增记录**：
1. **host_service.py 直接访问服务的架构决策**：admin handler 改为直接访问服务而非通过 Kernel 委托
2. **额外存在的服务文件**：`search.py`、`ingest.py`、`delete.py`、`v5_memory.py`、`hit_filter.py`、`profile_evidence.py`、`types.py`
3. **额外存在的 Admin Handler**：`paragraph.py`（ParagraphAdminHandler）、`relation.py`（RelationAdminHandler）

**跨文件一致性**：
1. **AGENTS.md 与 tasks.md 量化目标统一**：getattr 目标、or "" 目标在两个文件中保持一致
2. **AGENTS.md 与 .codeartsdoer/AGENTS.md 职责边界明确**：项目级规则 vs CodeArts 工具链特定上下文

## 1.2 存量功能详细分析

### 1.2.1 AGENTS.md（项目级）— 当前结构与约束

**接口契约**：
- 108 行，包含 9 个章节：代码规范、运行/调试/构建/测试/依赖、语言规范、配置文件修改、Webui规范、会话 ID 规范、A_memorix 修改、prompt模板、智能体自主性架构原则
- 智能体自主性架构原则仅3条，缺少会话级规则中已确立的5条原则和7条核心禁止项

**业务规则**：
- 会话 ID 规范要求"通过 chat_manager 的内部接口"，与核心隔离原则直接矛盾
- 变量规范禁止 or "" 兜底，但无量化目标（当前 87 处）和豁免条件
- 类属性使用规范要求减少 getattr，但无当前状态（8处）和目标值
- debug 规范要求"不兜底"，但会话 ID 规范的"不写入 fallback hash"表述与之矛盾

**约束**：
- 不删除安全相关规则（核心禁止项、配置文件修改规范、A_memorix 修改约束）
- 修订后总行数应减少或持平
- 修订不得引入新的矛盾条目

### 1.2.2 tasks.md（核心革命任务文档）— 当前结构与约束

**接口契约**：
- 1070 行，包含阶段 1-7（含 7A-7E）+ 最终验证
- 阶段 1-6 全部标记为 `[x]` 已完成
- 阶段 7A-7C 全部标记为 `[ ]` 未完成（实际已完成）
- 阶段 7D-7E 全部标记为 `[ ]` 未完成（部分已完成）

**业务规则**：
- SDKMemoryKernel 行数描述为 9650 行（实际 2679 行），严重过时
- 阶段 7B 文件名与实际代码不一致（如 `graph_operations.py` → 实际 `graph_ops.py`、`memory_maintenance.py` → 实际 `maintenance.py`）
- 阶段 7C 文件名与实际代码不一致（如 `graph_admin.py` → 实际 `graph.py`、`import_admin.py` → 实际 `import_handler.py`）
- 缺少额外存在的服务文件和 Admin Handler 的记录

**约束**：
- 以实际代码为准更新 tasks.md
- 外部 API 签名不变的约束仍然有效
- 验收标准需根据实际进展调整

### 1.2.3 .codeartsdoer/AGENTS.md — 当前结构与约束

**接口契约**：
- 9 行，仅包含 `Language Context: ["Python"]`
- 无项目特定的工程上下文

**约束**：
- 仅保留 CodeArts 工具链特定的上下文
- 通用规则引用项目 AGENTS.md，避免内容重叠

### 1.2.4 CLAUDE.md（全局）— 当前结构与约束

**接口契约**：
- 113 行，包含行为准则（4条）+ Skill Auto-Trigger Rules（7条）
- Skill Auto-Trigger Rules 引用 `.codemate/specs/` 目录，实际目录为 `.codeartsdoer/specs/`

**约束**：
- 全局 CLAUDE.md 由工具链管理，项目无法直接修改
- 项目级 CLAUDE.md 仅为指针（内容为 "AGENTS.md"）
- Skill Auto-Trigger Rules 路径不一致需在工具链层面修改

# 二、增量设计方案

## 2.1 实现模型

### 2.1.1 上下文视图

```plantuml
@startuml
left to right direction

rectangle "规则性文件修订" as revision {
  usecase "AGENTS.md 修订" as agents
  usecase "tasks.md 修订" as tasks
  usecase ".codeartsdoer/AGENTS.md 修订" as codearts_agents
  usecase "CLAUDE.md 确认" as claude
}

database "代码库实际状态" as codebase {
  :SDKMemoryKernel 2679行;
  :getattr 8处;
  :or "" 87处;
  :9个Protocol;
  :15个服务文件;
  :14个Admin Handler;
}

database "会话级规则" as session_rules {
  :5条架构原则;
  :7条核心禁止项;
  :核心进化方向;
  :内心状态三层;
}

codebase --> agents : 验证描述准确性
codebase --> tasks : 验证任务完成状态
session_rules --> agents : 架构原则参考基准
agents --> tasks : 量化目标一致性
codearts_agents --> agents : 职责边界确认
claude --> revision : 只读参考

@enduml
```

### 2.1.2 修订总体架构

```plantuml
@startuml
package "修订优先级" {
  component [P0 阻塞性] as p0 {
    [AGENTS.md 会话ID规范矛盾]
    [tasks.md 7A-7C状态严重不符]
  }
  component [P1 高] as p1 {
    [AGENTS.md 架构原则补充]
    [tasks.md 行数描述过时]
    [AGENTS.md 已完成架构规则]
  }
  component [P2 中] as p2 {
    [AGENTS.md or ""/getattr量化]
    [.codeartsdoer/AGENTS.md补充]
    [tasks.md 7D-7E验收标准]
  }
  component [P3 低] as p3 {
    [CLAUDE.md定位确认]
    [Skill路径不一致]
    [debug规范表述优化]
  }
}

p0 --> p1 : 阻塞解除后
p1 --> p2 : 核心补充后
p2 --> p3 : 基础完善后

@enduml
```

### 2.1.3 修订执行顺序

修订按以下顺序执行，确保跨文件一致性：

**第一批（P0 阻塞性 + P1 高）**：
1. `AGENTS.md` — 修复会话 ID 规范矛盾（P0）
2. `tasks.md` — 更新阶段 7A-7C 任务状态（P0）
3. `AGENTS.md` — 补充智能体自主性架构原则（P1）
4. `tasks.md` — 更新 SDKMemoryKernel 行数描述（P1）
5. `AGENTS.md` — 补充已完成架构的规则说明（P1）

**第二批（P2 中）**：
6. `AGENTS.md` — 补充 or "" / getattr 量化目标（P2）
7. `tasks.md` — 更新阶段 7D-7E 验收标准（P2）
8. `.codeartsdoer/AGENTS.md` — 补充工程上下文（P2）

**第三批（P3 低）**：
9. `CLAUDE.md` — 定位确认（只读参考，一般不修改）
10. `AGENTS.md` — debug 规范与 fallback 表述优化（P3）

## 2.2 接口设计

### 2.2.1 总体设计

本修订不涉及代码接口变更，仅修改规则性文件的内容。修订的"接口"是各文件之间的引用关系和一致性约束。

| 文件 | 修订类型 | 稳定性 | 影响范围 |
|------|---------|--------|---------|
| `AGENTS.md` | 内容修订 + 新增章节 | 稳定 | AI Agent 行为规则 |
| `tasks.md` | 状态更新 + 描述修正 | 稳定 | 后续开发任务参考 |
| `.codeartsdoer/AGENTS.md` | 内容补充 | 稳定 | CodeArts Agent 上下文 |
| `CLAUDE.md`（全局） | 只读参考 | 工具链维护 | 不在本次修订范围 |

### 2.2.2 修订清单

#### 修订项 R-01：AGENTS.md 会话 ID 规范矛盾修复

- **文件**：`AGENTS.md`
- **优先级**：P0
- **原文**（第67行）：
  > 除聊天流创建/注册链路外，业务模块不应自行调用 `SessionUtils.calculate_session_id` 计算资源归属 ID。表达学习、黑话、记忆、WebUI、配置匹配等模块应通过 `chat_manager` 的内部接口，基于 platform、目标 ID 和聊天类型解析已存在的真实聊天流；如果解析不到真实 `ChatSession.session_id`，不要把自行计算的 fallback hash 写入数据库。
- **问题**：要求"通过 chat_manager 的内部接口"违反核心隔离原则（核心禁止项第1条：禁止核心直接导入 chat_manager）
- **修订方向**：
  - 将"应通过 `chat_manager` 的内部接口"改为"应通过 `SessionRepository` Protocol 接口查询"
  - 保留"不要把自行计算的 fallback hash 写入数据库"的约束，但明确这是"不写入脏数据"而非"fallback 兜底"
  - 消除与 debug 规范的表述矛盾

#### 修订项 R-02：AGENTS.md 智能体自主性架构原则补充

- **文件**：`AGENTS.md`
- **优先级**：P1
- **原文**（第94-103行）：仅包含3条原则
- **问题**：会话级规则中已确立5条原则和7条核心禁止项，AGENTS.md 仅包含3条
- **修订方向**：
  - 补充第4条：**组件兼容核心原则** — 核心定义接口契约，组件实现契约。核心不依赖组件的具体实现类，只依赖 Protocol。新增代码禁止引入对 chat_manager、send_service、HeartFlow 等组件具体实现的直接导入。
  - 补充第5条：**记忆是连接而非对象原则** — 记忆不是带标签的标本，而是概念之间的激活模式。新记忆 = 新连接，遗忘 = 连接衰减，回忆 = 重新激活模式。
  - 新增**核心禁止项**章节（7条）：禁止核心直接导入 chat_manager、禁止核心访问 chat_manager._agent_router、禁止核心持有 BotChatSession 可变引用、禁止核心硬编码 napcat_* 字段、禁止核心绕过 MessagePort 直接调用 send_service、禁止核心导入 A_memorix 内部模块、禁止 Orchestrator 通过 enqueue_proactive_task 模拟多智能体

#### 修订项 R-03：AGENTS.md 已完成架构规则说明补充

- **文件**：`AGENTS.md`
- **优先级**：P1
- **问题**：内心世界系统、管家系统集成、Agent-owns-Thinking、并行思考等已完成架构在 AGENTS.md 中无任何体现
- **修订方向**：
  - 新增**核心架构**章节，包含：
    - 微内核 + 接口契约架构说明
    - 核心接口层表格（9个Protocol + 实现者 + 状态）
    - 内心状态三层（情绪/欲望/记忆）及实现状态
    - Agent-owns-Thinking 架构说明
    - 管家系统（三层过滤 + 提醒流）架构说明
    - 目标核心管道流程图

#### 修订项 R-04：AGENTS.md A_memorix 修改规则更新

- **文件**：`AGENTS.md`
- **优先级**：P2
- **原文**（第69-70行）：
  > A_Memorix 是 MaiBot 的核心记忆子系统，可以自由修改。修改约束仅来自 MaiBot 自身架构原则（核心隔离、Protocol 接口契约），详见 `src/A_memorix/MODIFICATION_POLICY.md`。
- **问题**：未反映 SDKMemoryKernel 重构的实际进展
- **修订方向**：
  - 补充当前进展：SDKMemoryKernel 已从 9650 行瘦身至 2679 行；services/ 目录已提取 15 个服务文件；admin/ 目录已提取 14 个 Admin Handler；_KernelRuntimeFacade 已删除；host_service 直接访问服务
  - 补充当前约束：子模块不反向持有 SDKMemoryKernel 引用；外部 API 签名不变；不引入新的循环依赖

#### 修订项 R-05：AGENTS.md or "" / getattr 量化目标补充

- **文件**：`AGENTS.md`
- **优先级**：P2
- **原文**（第27-33行）：变量规范和类属性使用规范无量化目标
- **修订方向**：
  - 变量规范补充：当前 SDKMemoryKernel 中 or "" 数量为 87 处（已低于 tasks.md 目标 ≤150）。合理豁免场景：外部数据源返回值可能为 None（如 `dict.get(key, "") or ""` 中的 `or ""` 在 dict.get 已提供默认值时可删除；`str(x or "").strip()` 在 x 已知为 str 时可简化为 `x.strip()`）
  - 类属性使用规范补充：当前 SDKMemoryKernel 中 getattr 数量为 8 处（目标 ≤5）。保留场景判定标准：对动态能力检测的 getattr（如 `encode_batch`、`iter_vectors_by_ids`）通过 Protocol 接口统一后消除；对已知接口的 getattr 替换为直接属性访问

#### 修订项 R-06：AGENTS.md debug 规范与 fallback 表述优化

- **文件**：`AGENTS.md`
- **优先级**：P3
- **原文**（第35-37行）：
  > 不要总是想找兜底，一定要精准的找到问题的核心，然后提出建议，兜底是不合适，难以维护的。不要总是考虑fallback，如果哪里有错误，一定要让他及时完整的暴露，而不是用fall_back兜底掩盖过去
- **问题**：与修订项 R-01 中"不要把自行计算的 fallback hash 写入数据库"的表述矛盾
- **修订方向**：
  - 明确区分两种场景：
    - **不兜底**：当确定某个值应该存在时，直接使用，不用 `or ""` / `or None` 掩盖可能的错误。错误应完整暴露。
    - **不写入脏数据**：当某个值确实可能不存在（如外部数据源返回 None），不应强行计算一个 fallback 值写入数据库，而应跳过或报错。这不是"兜底"，而是"拒绝脏数据"。

#### 修订项 R-07：AGENTS.md 架构债务追踪规则新增

- **文件**：`AGENTS.md`
- **优先级**：P2
- **问题**：当前 AGENTS.md 无架构债务的记录和追踪机制，导致规则性文件与代码状态脱节
- **修订方向**：
  - 新增**架构债务追踪**规则：重大架构变更（新增/删除 Protocol、消除架构债务、核心模块迁移）完成后，应同步更新 AGENTS.md 和 tasks.md 中的相关描述，确保规则性文件与代码实际状态一致

#### 修订项 R-08：tasks.md 阶段 7A-7C 任务状态更新

- **文件**：`.codeartsdoer/specs/core_revolution/tasks.md`
- **优先级**：P0
- **问题**：阶段 7A-7C 全部标记为 `[ ]` 未完成，实际已完成
- **修订方向**：
  - TASK-7A-01 ~ 7A-06：标记为 `[x]` 已完成
  - TASK-7B-01 ~ 7B-10：标记为 `[x]` 已完成，更新文件名和类名与实际代码一致：
    - `paragraph_backfill.py` → 实际不存在（可能合并到 vector_pool.py），标注"已合并"
    - `vector_rebuild.py` → 实际不存在（可能仍在 Kernel 中），标注"待确认"
    - `memory_maintenance.py` → 实际为 `maintenance.py`
    - `graph_operations.py` → 实际为 `graph_ops.py`
    - 补充额外存在的服务：`search.py`、`ingest.py`、`delete.py`、`v5_memory.py`、`hit_filter.py`、`profile_evidence.py`、`types.py`
  - TASK-7C-01 ~ 7C-12：标记为 `[x]` 已完成，更新文件名和类名与实际代码一致：
    - `graph_admin.py` → 实际为 `graph.py`
    - `source_admin.py` → 实际为 `source.py`
    - `episode_admin.py` → 实际为 `episode.py`
    - `profile_admin.py` → 实际为 `profile.py`
    - `feedback_admin.py` → 实际为 `feedback.py`
    - `runtime_admin.py` → 实际为 `runtime.py`
    - `import_admin.py` → 实际为 `import_handler.py`
    - `tuning_admin.py` → 实际为 `tuning.py`
    - `v5_admin.py` → 实际为 `v5.py`
    - `delete_admin.py` → 实际为 `delete.py`
    - `correction_admin.py` → 实际为 `correction.py`
    - 补充额外存在的 Handler：`paragraph.py`（ParagraphAdminHandler）、`relation.py`（RelationAdminHandler）

#### 修订项 R-09：tasks.md 阶段 7D 任务状态更新

- **文件**：`.codeartsdoer/specs/core_revolution/tasks.md`
- **优先级**：P1
- **问题**：阶段 7D 部分任务已完成但未标记
- **修订方向**：
  - TASK-7D-01（删除 _KernelRuntimeFacade）：标记为 `[x]` 已完成（代码中 0 匹配）
  - TASK-7D-02（消除 getattr 52 → ≤5）：标记为 `[~]` 部分完成，标注当前 8 处，目标 ≤5 未达成
  - TASK-7D-03（消除 or "" 618 → ≤150）：标记为 `[x]` 已完成（当前 87 处，低于 150 目标）
  - TASK-7D-04（Kernel 公共方法改为委托）：标记为 `[~]` 部分完成，标注 6 个公共 API 仍有 await self.initialize()，23 个代理方法仍存在
  - TASK-7D-05（Kernel 行数 ≤ 800）：标记为 `[ ]` 未完成，标注当前 2679 行

#### 修订项 R-10：tasks.md SDKMemoryKernel 行数描述更新

- **文件**：`.codeartsdoer/specs/core_revolution/tasks.md`
- **优先级**：P1
- **问题**：描述 Kernel 为 9650 行，实际当前为 2679 行
- **修订方向**：
  - 更新阶段 7 开头的行数描述：`SDKMemoryKernel 从 9650 行 → 2679 行（持续瘦身中，目标 ≤800 行薄协调层）`
  - 更新 TASK-7D-05 验收标准中的行数目标：考虑到当前 2679 行与 800 行目标差距，建议调整目标为 ≤2000 行（7D 阶段），≤800 行作为最终目标

#### 修订项 R-11：tasks.md 阶段 7E 验收标准更新

- **文件**：`.codeartsdoer/specs/core_revolution/tasks.md`
- **优先级**：P2
- **问题**：验收标准中的数值与实际进展不匹配
- **修订方向**：
  - TASK-7E-02 代码质量验证：
    - getattr ≤5 → 当前 8 处，调整目标为 ≤8 处（7E 阶段），≤5 处作为后续目标
    - or "" ≤150 → 当前 87 处，已达标
    - 行数 ≤800 → 当前 2679 行，调整目标为 ≤2000 行（7E 阶段），≤800 行作为最终目标

#### 修订项 R-12：tasks.md 架构决策和额外记录补充

- **文件**：`.codeartsdoer/specs/core_revolution/tasks.md`
- **优先级**：P2
- **问题**：缺少 host_service 直接访问服务的架构决策记录和额外服务/Handler 的记录
- **修订方向**：
  - 在阶段 7D 开头补充架构决策说明：admin handler 改为通过 host_service 直接访问服务实例，而非通过 Kernel 委托。约束：host_service 是唯一允许持有 Kernel 实例引用的外部模块
  - 在阶段 7B 验证任务中补充额外存在的服务文件列表
  - 在阶段 7C 验证任务中补充额外存在的 Admin Handler 列表

#### 修订项 R-13：.codeartsdoer/AGENTS.md 工程上下文补充

- **文件**：`.codeartsdoer/AGENTS.md`
- **优先级**：P2
- **原文**（1-9行）：仅包含 `Language Context: ["Python"]`
- **问题**：缺少项目特定的工程上下文
- **修订方向**：
  - 补充以下工程上下文：
    - **核心架构**：微内核 + Protocol 接口契约，核心不依赖组件具体实现
    - **代码风格**：砍掉过度防御/兜底代码、减少 getattr/setattr、不用 or "" 兜底
    - **技术栈**：Python 3.14.6、uv 依赖管理、Docker 容器运行
    - **职责边界**：本文件仅提供 CodeArts 工具链特定的工程上下文，通用规则参见项目根目录 AGENTS.md

#### 修订项 R-14：CLAUDE.md 定位确认

- **文件**：`C:\Users\lmq\.claude\CLAUDE.md`（全局）
- **优先级**：P3
- **问题**：项目级 CLAUDE.md 仅为指针，全局 CLAUDE.md 由工具链管理
- **修订方向**：
  - 确认项目级 CLAUDE.md（`E:\Users\lmq\MaiBot\CLAUDE.md`）的定位：作为 AGENTS.md 的指针，不提供独立规则
  - 确认全局 CLAUDE.md（`C:\Users\lmq\.claude\CLAUDE.md`）的维护责任：行为准则和 Skill Auto-Trigger Rules 由工具链管理，项目无法直接修改
  - Skill Auto-Trigger Rules 路径不一致（`.codemate/specs/` vs `.codeartsdoer/specs/`）标注为"需工具链层面修改"

## 2.3 数据模型

### 2.3.1 设计目标

本修订的数据模型目标：
1. 确保规则性文件描述与代码实际状态一致
2. 消除跨文件矛盾（特别是 AGENTS.md 内部和 AGENTS.md ↔ tasks.md 之间）
3. 建立架构债务追踪机制，防止再次脱节

### 2.3.2 修订后的关键量化指标

以下指标将同步更新到 AGENTS.md 和 tasks.md：

| 指标 | 当前值 | 目标值 | 来源 |
|------|--------|--------|------|
| SDKMemoryKernel 行数 | 2679 | ≤2000（7E阶段）/ ≤800（最终） | 代码扫描 |
| getattr 数量 | 8 | ≤5 | 代码扫描 |
| or "" 数量 | 87 | ≤150（已达标） | 代码扫描 |
| _KernelRuntimeFacade | 0（已删除） | 0 | 代码扫描 |
| services/ 文件数 | 15（含 __init__.py） | — | 代码扫描 |
| admin/ 文件数 | 15（含 __init__.py） | — | 代码扫描 |
| 核心Protocol数 | 9 | — | 代码扫描 |
| 内心世界系统 | 已实现 | — | 代码扫描 |
| Agent-owns-Thinking | 已实现 | — | 代码扫描 |
| 管家系统 | 已实现 | — | 代码扫描 |
