# 规则性文件修订 — 编码任务规划

> 基于 spec.md 需求规格和 design.md 实现方案生成
> 修订项编号 R-01 ~ R-14，按目标文件垂直分组，组内按优先级排序
> 代码扫描验证时间：2026-07-09

---

## 1. AGENTS.md 修订

> 修订项目级 Agent 规则文件，消除内部矛盾、补充缺失架构原则和量化指标。
> 涉及修订项：R-01（P0）、R-02（P1）、R-03（P1）、R-04（P2）、R-05（P2）、R-06（P3）、R-07（P2）

### 1.1 修复会话 ID 规范与核心隔离原则的矛盾（R-01，P0）

- [ ] 定位 `AGENTS.md` 会话 ID 规范段落（约第72行），将"应通过 `chat_manager` 的内部接口"改为"应通过 `SessionRepository` Protocol 接口查询"
- [ ] 保留"不应强行计算 fallback hash 写入数据库"的约束，明确表述为"拒绝脏数据"而非"fallback 兜底"
- [ ] 验证修订后与会话 ID 规范与核心禁止项第1条（禁止核心直接导入 chat_manager）无矛盾

### 1.2 补充智能体自主性架构原则（R-02，P1）

- [ ] 在现有3条原则后补充第4条：**组件兼容核心原则** — 核心定义接口契约，组件实现契约。核心不依赖组件的具体实现类，只依赖 Protocol。新增代码禁止引入对 chat_manager、send_service、HeartFlow 等组件具体实现的直接导入
- [ ] 补充第5条：**记忆是连接而非对象原则** — 记忆不是带标签的标本，而是概念之间的激活模式。新记忆 = 新连接，遗忘 = 连接衰减，回忆 = 重新激活模式
- [ ] 新增**核心禁止项**章节，包含7条：①禁止核心直接导入 chat_manager ②禁止核心访问 chat_manager._agent_router ③禁止核心持有 BotChatSession 可变引用 ④禁止核心硬编码 napcat_* 字段 ⑤禁止核心绕过 MessagePort 直接调用 send_service ⑥禁止核心导入 A_memorix 内部模块 ⑦禁止 Orchestrator 通过 enqueue_proactive_task 模拟多智能体
- [ ] 验证5条原则和7条禁止项与 `src/core/protocols.py` 中9个 Protocol 定义一致

### 1.3 补充已完成架构的规则说明（R-03，P1）

- [ ] 新增**核心架构**章节，包含微内核 + 接口契约架构说明
- [ ] 在核心架构章节中添加核心接口层表格，列出9个 Protocol 及其职责和实现者：SessionRepository、AgentRoutingService、ChatRuntime、ChatRuntimeRegistry、NoticeClassifier、MemoryServicePort、SessionInfoPort、ThinkingOrgan、ThinkingOrganFactory
- [ ] 添加内心状态三层说明（情绪层/欲望层/记忆层）及实现状态
- [ ] 添加 Agent-owns-Thinking 架构说明：每个智能体拥有自己的思维管道，Orchestrator 只协调"谁在思考"，共居智能体可并行思考（ParallelThinkScheduler）
- [ ] 添加管家系统架构说明：三层过滤（相关性→时机→价值）、提醒流（ThinkingOrgan.think_proactive()）、插话流（ThinkingOrgan.think() + MessagePort.send()）

### 1.4 更新 A_memorix 修改规则（R-04，P2）

- [ ] 在 A_memorix 修改段落补充当前重构进展：SDKMemoryKernel 已从 9650 行瘦身至 2679 行；`services/` 目录已提取 14 个服务文件；`admin/` 目录已提取 13 个 Admin Handler；`_KernelRuntimeFacade` 已删除；`host_service` 直接访问服务实例
- [ ] 补充当前约束：子模块不反向持有 SDKMemoryKernel 引用；外部 API 签名不变；不引入新的循环依赖
- [ ] 验证约束边界与 `src/A_memorix/MODIFICATION_POLICY.md` 一致

### 1.5 补充 or "" / getattr 量化目标（R-05，P2）

- [ ] 变量规范补充：当前 SDKMemoryKernel 中 or "" 数量为 87 处（已低于 ≤150 目标）。合理豁免场景：外部数据源返回值可能为 None（如 `dict.get(key, "") or ""` 中 dict.get 已提供默认值时可删除；`str(x or "").strip()` 在 x 已知为 str 时可简化为 `x.strip()`）
- [ ] 类属性使用规范补充：当前 SDKMemoryKernel 中 getattr 数量为 8 处（目标 ≤5）。保留场景判定标准：对动态能力检测的 getattr（如 `encode_batch`、`iter_vectors_by_ids`）通过 Protocol 接口统一后消除；对已知接口的 getattr 替换为直接属性访问

### 1.6 新增架构债务追踪规则（R-07，P2）

- [ ] 新增**架构债务追踪**规则：重大架构变更（新增/删除 Protocol、消除架构债务、核心模块迁移）完成后，应同步更新 AGENTS.md 和 tasks.md 中的相关描述，确保规则性文件与代码实际状态一致
- [ ] 明确触发条件和更新范围

### 1.7 优化 debug 规范与 fallback 表述（R-06，P3）

- [ ] 在 debug 规范中明确区分两种场景：**不兜底**（当确定某个值应该存在时，直接使用，不用 `or ""` / `or None` 掩盖可能的错误，错误应完整暴露）vs **不写入脏数据**（当某个值确实可能不存在时，不应强行计算 fallback 值写入数据库，而应跳过或报错——这不是"兜底"，而是"拒绝脏数据"）
- [ ] 验证修订后与会话 ID 规范（R-01 修订后）无矛盾

---

## 2. core_revolution/tasks.md 修订

> 更新 SDKMemoryKernel 革命任务文档的任务状态、文件名和验收标准，使其与代码实际状态一致。
> 涉及修订项：R-08（P0）、R-09（P1）、R-10（P1）、R-11（P2）、R-12（P2）
> 目标文件：`.codeartsdoer/specs/core_revolution/tasks.md`

### 2.1 更新阶段 7A-7C 任务状态（R-08，P0）

- [ ] TASK-7A-01 ~ 7A-06：全部标记为 `[x]` 已完成（config/ 包、admin/base.py、services/ 包均已创建）
- [ ] TASK-7B-01 ~ 7B-10：全部标记为 `[x]` 已完成，更新文件名和类名与实际代码一致：
  - `paragraph_backfill.py` → 标注"已合并到 vector_pool.py"
  - `vector_rebuild.py` → 标注"待提取，仍在 Kernel 中"
  - `memory_maintenance.py` → 实际为 `maintenance.py`
  - `graph_operations.py` → 实际为 `graph_ops.py`
- [ ] TASK-7B 验证任务中补充额外存在的服务文件列表：`search.py`、`ingest.py`、`delete.py`、`v5_memory.py`、`hit_filter.py`、`profile_evidence.py`、`types.py`
- [ ] TASK-7C-01 ~ 7C-12：全部标记为 `[x]` 已完成，更新文件名与实际代码一致：
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
- [ ] TASK-7C 验证任务中补充额外存在的 Admin Handler：`paragraph.py`（ParagraphAdminHandler）、`relation.py`（RelationAdminHandler）

### 2.2 更新阶段 7D 任务状态（R-09，P1）

- [ ] TASK-7D-01（删除 _KernelRuntimeFacade）：标记为 `[x]` 已完成（代码中 0 匹配）
- [ ] TASK-7D-02（消除 getattr 52 → ≤5）：标记为 `[~]` 部分完成，标注当前 8 处，目标 ≤5 未达成
- [ ] TASK-7D-03（消除 or "" 618 → ≤150）：标记为 `[x]` 已完成（当前 87 处，低于 150 目标）
- [ ] TASK-7D-04（Kernel 公共方法改为委托）：标记为 `[~]` 部分完成，标注 6 个公共 API 仍有 await self.initialize()，23 个代理方法仍存在
- [ ] TASK-7D-05（Kernel 行数 ≤ 800）：标记为 `[ ]` 未完成，标注当前 2679 行

### 2.3 更新 SDKMemoryKernel 行数描述（R-10，P1）

- [ ] 更新阶段 7 开头的行数描述：`SDKMemoryKernel 从 9650 行 → 2679 行（持续瘦身中，目标 ≤800 行薄协调层）`
- [ ] 更新 TASK-7D-05 验收标准中的行数目标：7D 阶段目标调整为 ≤2000 行，≤800 行作为最终目标

### 2.4 更新阶段 7E 验收标准（R-11，P2）

- [ ] TASK-7E-02 代码质量验证中 getattr 目标调整：当前 8 处，7E 阶段目标调整为 ≤8 处，≤5 处作为后续目标
- [ ] TASK-7E-02 代码质量验证中 or "" 目标确认：当前 87 处，已达标（≤150）
- [ ] TASK-7E-02 代码质量验证中行数目标调整：当前 2679 行，7E 阶段目标调整为 ≤2000 行，≤800 行作为最终目标
- [ ] 确保阶段性目标与最终目标区分明确

### 2.5 补充架构决策和额外记录（R-12，P2）

- [ ] 在阶段 7D 开头补充架构决策说明：admin handler 改为通过 host_service 直接访问服务实例，而非通过 Kernel 委托。约束：host_service 是唯一允许持有 Kernel 实例引用的外部模块
- [ ] 在阶段 7B 验证任务中补充额外存在的服务文件列表（7个）：`search.py`、`ingest.py`、`delete.py`、`v5_memory.py`、`hit_filter.py`、`profile_evidence.py`、`types.py`
- [ ] 在阶段 7C 验证任务中补充额外存在的 Admin Handler 列表（2个）：`paragraph.py`（ParagraphAdminHandler）、`relation.py`（RelationAdminHandler）

---

## 3. .codeartsdoer/AGENTS.md 修订

> 补充 CodeArts 工具链特定的工程上下文，明确与项目 AGENTS.md 的职责分工。
> 涉及修订项：R-13（P2）
> 目标文件：`.codeartsdoer/AGENTS.md`

### 3.1 补充工程上下文（R-13，P2）

- [ ] 补充**核心架构**约束：微内核 + Protocol 接口契约，核心不依赖组件具体实现
- [ ] 补充**代码风格**关键规则：砍掉过度防御/兜底代码、减少 getattr/setattr、不用 or "" 兜底
- [ ] 补充**技术栈**信息：Python 3.14.6、uv 依赖管理、Docker 容器运行
- [ ] 补充**职责边界**说明：本文件仅提供 CodeArts 工具链特定的工程上下文，通用规则参见项目根目录 AGENTS.md
- [ ] 验证补充内容与项目 AGENTS.md 无重复（仅保留摘要级描述，详细规则引用项目 AGENTS.md）

---

## 4. CLAUDE.md 定位确认

> 确认项目级和全局 CLAUDE.md 的维护责任和定位，不涉及代码修改。
> 涉及修订项：R-14（P3）
> 目标文件：`CLAUDE.md`（项目级，只读参考）、`C:\Users\lmq\.claude\CLAUDE.md`（全局，工具链维护）

### 4.1 确认 CLAUDE.md 定位和维护责任（R-14，P3）

- [ ] 确认项目级 CLAUDE.md（`E:\Users\lmq\MaiBot\CLAUDE.md`）的定位：作为 AGENTS.md 的指针，不提供独立规则
- [ ] 确认全局 CLAUDE.md（`C:\Users\lmq\.claude\CLAUDE.md`）的维护责任：行为准则和 Skill Auto-Trigger Rules 由工具链管理，项目无法直接修改
- [ ] Skill Auto-Trigger Rules 路径不一致（`.codemate/specs/` vs `.codeartsdoer/specs/`）标注为"需工具链层面修改"，记录在修订说明中

---

## 5. 跨文件一致性验证

> 确保修订后各规则性文件之间的量化指标、架构描述和引用关系一致。

### 5.1 量化指标一致性验证

- [ ] 验证 AGENTS.md 和 tasks.md 中 SDKMemoryKernel 行数描述一致（2911 行）
- [ ] 验证 AGENTS.md 和 tasks.md 中 getattr 数量和目标一致（当前 8 处，目标 ≤5）
- [ ] 验证 AGENTS.md 和 tasks.md 中 or "" 数量和目标一致（当前 87 处，目标 ≤150 已达标）
- [ ] 验证 AGENTS.md 和 tasks.md 中 services/ 文件数一致（14 个服务文件 + __init__.py）
- [ ] 验证 AGENTS.md 和 tasks.md 中 admin/ Handler 数一致（13 个 Handler + __init__.py + base.py）

### 5.2 架构描述一致性验证

- [ ] 验证 AGENTS.md 核心接口层表格与 `src/core/protocols.py` 中9个 Protocol 定义一致
- [ ] 验证 AGENTS.md 核心禁止项与会话级规则中的架构原则无矛盾
- [ ] 验证 AGENTS.md A_memorix 修改规则与 tasks.md 中的架构决策记录一致
- [ ] 验证 .codeartsdoer/AGENTS.md 与项目 AGENTS.md 职责边界清晰，无内容重叠

### 5.3 修订完整性验证

- [ ] 验证 spec.md 中5.1节（AGENTS.md）的8条业务规则全部有对应修订
- [ ] 验证 spec.md 中5.3节（tasks.md）的9条业务规则全部有对应修订
- [ ] 验证 spec.md 中5.4节（.codeartsdoer/AGENTS.md）的2条业务规则全部有对应修订
- [ ] 验证 design.md 中 R-01 ~ R-14 全部14个修订项有对应任务
- [ ] 验证修订后的规则性文件总行数未显著增加

---

## 量化指标基准（代码扫描验证时间：2026-07-09）

| 指标 | 当前值 | 目标值 | 来源 |
|------|--------|--------|------|
| SDKMemoryKernel 行数 | 2679 | ≤2000（7E阶段）/ ≤800（最终） | `sdk_memory_kernel.py` |
| getattr 数量 | 8 | ≤5 | `sdk_memory_kernel.py` |
| or "" 数量 | 87 | ≤150（已达标） | `sdk_memory_kernel.py` |
| _KernelRuntimeFacade | 0（已删除） | 0 | 全局搜索 |
| services/ 文件数 | 15（含 __init__.py） | — | `services/` 目录 |
| admin/ 文件数 | 15（含 __init__.py 和 base.py） | — | `admin/` 目录 |
| 核心 Protocol 数 | 9 | — | `src/core/protocols.py` |
