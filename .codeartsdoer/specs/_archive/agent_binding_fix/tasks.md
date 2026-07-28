# 智能体-会话绑定机制修复与多智能体共居对话 — 实现任务清单

## 1. 修复 AgentRouter 单例共享（Bug 1 核心）

**目标**：消除 WebUI API 与 ChatManager 使用不同 AgentRouter 实例导致的绑定隔离问题，确保所有操作通过 ChatManager 持有的唯一路由器单例执行。

### 1.1 删除 WebUI 独立路由器工厂函数

- [ ] 在 `src/webui/routers/agent.py` 中删除 `_get_router()` 函数（第 30-31 行），该函数每次创建新 `AgentRouter` 实例
- [ ] 在 `src/webui/routers/agent.py` 中删除 `_get_registry()` 函数（第 26-27 行），该函数每次创建新 `AgentConfigRegistry` 实例
- [ ] 在 `src/webui/routers/agent.py` 顶部添加导入：`from src.chat.message_receive.chat_manager import chat_manager`

### 1.2 暴露 ChatManager 路由器单例访问接口

- [ ] 在 `src/chat/message_receive/chat_manager.py` 的 `ChatManager` 类中，将 `_ensure_agent_router` 方法保持不变（已有延迟初始化逻辑），新增 `agent_router` 属性，直接返回 `self._ensure_agent_router()`，供外部模块访问路由器单例
- [ ] 确保 `agent_router` 属性的类型注解为 `AgentRouter`

### 1.3 重构 WebUI API 端点使用路由器单例

- [ ] 在 `src/webui/routers/agent.py` 中，将所有调用 `_get_router()` 的位置替换为 `chat_manager.agent_router`，涉及以下端点：
  - `get_session_binding`（第 284 行）
  - `bind_session_agent`（第 306 行）
  - `unbind_session_agent`（第 338 行）
  - `batch_bind_sessions`（第 350 行）
  - `list_group_bindings`（第 387 行）
  - `bind_group_agent`（第 401 行）
  - `unbind_group_agent`（第 426 行）
- [ ] 将所有调用 `_get_registry()` 的位置替换为 `chat_manager.agent_router._registry` 或通过 `AgentConfigRegistry()` 获取（保持现有行为，但避免每次创建新实例的冗余）
- [ ] 添加 `chat_manager` 未初始化的异常处理：当 `chat_manager.agent_router` 不可用时返回 503 错误

### 1.4 验证单例共享

- [ ] 验证：WebUI 绑定操作写入的绑定关系 → ChatManager 的路由器立即可见
- [ ] 验证：WebUI 绑定操作后，消息到达时 `chat_manager.agent_router.resolve_agent()` 返回正确的智能体
- [ ] 验证：`_get_router()` 和 `_get_registry()` 函数已完全移除，无残留引用

## 2. 实现 AgentRouter 多智能体共居数据结构

**目标**：将 AgentRouter 的会话绑定从一对一映射改造为一对多映射，支持同一会话绑定多个智能体。

### 2.1 改造 `_session_bindings` 数据结构

- [ ] 在 `src/maisaka/agent/router.py` 中，将 `_session_bindings` 类型从 `dict[str, str]` 改为 `dict[str, set[str]]`
- [ ] 新增 `_primary_order: dict[str, list[str]]` 字段，记录每个会话的智能体绑定顺序，第一个绑定的为主发言智能体

### 2.2 改造 `bind_session` 方法

- [ ] 修改 `bind_session(session_id, agent_id)` 方法：将 `self._session_bindings[session_id] = agent_id` 改为 `self._session_bindings.setdefault(session_id, set()).add(agent_id)`
- [ ] 在 `_primary_order` 中记录绑定顺序：若 `session_id` 不在 `_primary_order` 中，则 `agent_id` 为第一个（主发言）；否则追加到列表末尾
- [ ] 保持 `agent_id` 不存在时抛出 `ValueError` 的校验逻辑
- [ ] 幂等处理：若 `agent_id` 已在绑定集合中，不报错，仅记录 debug 日志

### 2.3 改造 `unbind_session` 方法

- [ ] 修改 `unbind_session(session_id, agent_id=None)` 方法签名，新增可选参数 `agent_id`
- [ ] 当 `agent_id=None` 时：清除该会话所有绑定（删除 `_session_bindings[session_id]` 和 `_primary_order[session_id]`）
- [ ] 当指定 `agent_id` 时：仅从集合中移除指定智能体，同时从 `_primary_order[session_id]` 中移除；若集合为空则清除整个条目
- [ ] 若移除的是主发言智能体（`_primary_order[session_id][0]`），自动将下一个智能体提升为主发言

### 2.4 新增路由器查询方法

- [ ] 新增 `get_session_primary_agent(session_id) -> str | None` 方法：返回 `_primary_order.get(session_id, [None])[0]`，即主发言智能体 ID
- [ ] 新增 `get_session_all_agents(session_id) -> set[str]` 方法：返回 `self._session_bindings.get(session_id, set())` 的副本
- [ ] 修改 `get_session_binding(session_id) -> str | None` 方法：保持返回主发言智能体 ID（向后兼容），内部调用 `get_session_primary_agent`

### 2.5 改造 `resolve_agent` 方法

- [ ] 修改 `resolve_agent(session_id, group_id=None)` 方法：将 `self._session_bindings.get(session_id)` 改为调用 `self.get_session_primary_agent(session_id)`
- [ ] 保持群绑定和默认智能体的 fallback 逻辑不变

### 2.6 改造 `list_session_bindings` 方法

- [ ] 修改 `list_session_bindings()` 返回类型从 `dict[str, str]` 改为 `dict[str, set[str]]`
- [ ] 返回 `_session_bindings` 的深拷贝（每个 set 也需拷贝）

### 2.7 验证多智能体数据结构

- [ ] 验证：同一会话绑定 2 个智能体 → `get_session_all_agents` 返回包含 2 个元素的集合
- [ ] 验证：`resolve_agent` 返回第一个绑定的智能体（主发言）
- [ ] 验证：解绑主发言后，`resolve_agent` 返回下一个智能体
- [ ] 验证：全部解绑后，`resolve_agent` 返回默认智能体
- [ ] 验证：`get_session_binding` 向后兼容，仍返回单个 agent_id 字符串

## 3. 实现绑定双写一致性（Bug 2 修复 — 绑定侧）

**目标**：绑定操作同时写入内存路由器和数据库 ChatSession.agent_id + AgentAutonomyActivity，确保三者一致。

### 3.1 重构绑定 API 端点实现双写

- [ ] 在 `src/webui/routers/agent.py` 的 `bind_session_agent` 端点中，重构绑定流程：
  1. 通过 `chat_manager.agent_router` 获取路由器单例
  2. 校验 `agent_id` 存在性
  3. 调用 `router.bind_session(session_id, agent_id)` 写入内存
  4. 更新 `ChatSession.agent_id` 为主发言智能体（通过 `router.get_session_primary_agent(session_id)` 获取）
  5. 若会话已有 Orchestrator（`AgentOrchestrator.get_by_session(session_id)`），调用 `orchestrator.activate_agent(agent_id, "manual_binding")`
  6. 若会话已有 Orchestrator，调用 `activity_store.save_activity(session_id, agent_id, is_primary, "manual_binding")`
- [ ] 添加数据库写入失败时的回滚逻辑：若数据库写入失败，回滚内存路由器的绑定，返回 500 错误
- [ ] 添加 `chat_manager` 未初始化的 503 错误处理

### 3.2 重构批量绑定 API 端点

- [ ] 在 `src/webui/routers/agent.py` 的 `batch_bind_sessions` 端点中，对每条绑定执行与 3.1 相同的双写流程
- [ ] 保持单条失败不影响其他绑定的行为

### 3.3 验证绑定双写

- [ ] 验证：执行 PUT /binding/session/{session_id} → 内存路由器有记录 且 数据库 ChatSession.agent_id 已更新
- [ ] 验证：绑定成功后重启 MaiBot → 路由器从数据库恢复后仍能正确路由
- [ ] 验证：数据库写入失败时，内存路由器的绑定被回滚

## 4. 实现解绑彻底清除（Bug 2 修复 — 解绑侧）

**目标**：解绑操作同时清除内存路由器、数据库 ChatSession.agent_id、Orchestrator 退场、Activity 记录关闭，四清一致。

### 4.1 重构解绑 API 端点实现四清

- [ ] 在 `src/webui/routers/agent.py` 的 `unbind_session_agent` 端点中，重构解绑流程：
  1. 通过 `chat_manager.agent_router` 获取路由器单例
  2. 获取该会话所有绑定的智能体列表（`router.get_session_all_agents(session_id)`）
  3. 对每个智能体：
     - 若在 Orchestrator 中活跃，调用 `orchestrator.deactivate_agent(agent_id, "manual_unbind")`
     - 调用 `activity_store.deactivate(session_id, agent_id, "manual_unbind")`
  4. 调用 `router.unbind_session(session_id)` 清除所有绑定
  5. 清除数据库 `ChatSession.agent_id` 为空
- [ ] 添加 Orchestrator 退场失败的容错：退场失败时继续完成内存和数据库清除，日志记录警告

### 4.2 新增指定智能体解绑端点

- [ ] 在 `src/webui/routers/agent.py` 中新增 `DELETE /binding/session/{session_id}/{agent_id}` 端点
- [ ] 实现多智能体场景下的精确解绑流程：
  1. 调用 `router.unbind_session(session_id, agent_id)` 仅移除指定智能体
  2. 若该智能体在 Orchestrator 中活跃，调用 `orchestrator.deactivate_agent(agent_id, "manual_unbind")`
  3. 调用 `activity_store.deactivate(session_id, agent_id, "manual_unbind")`
  4. 若该会话还有其他绑定智能体，保持 `ChatSession.agent_id` 为当前主发言；若为最后一个，清空 `ChatSession.agent_id`
- [ ] 添加对应的 Pydantic 响应模型（复用 `SessionBindingResponse`）

### 4.3 验证解绑彻底清除

- [ ] 验证：执行 DELETE /binding/session/{session_id} → 内存路由器无记录 且 数据库 ChatSession.agent_id 为空
- [ ] 验证：解绑后 Orchestrator 中所有智能体退场
- [ ] 验证：解绑后 Activity 记录 exited_at 不为空
- [ ] 验证：多智能体场景下解绑单个智能体不影响其他智能体
- [ ] 验证：解绑后重启 MaiBot → 该会话不再路由到已解绑的智能体

## 5. 实现绑定触发激活与解绑触发退场

**目标**：手动绑定智能体到会话时自动激活到 Orchestrator，手动解绑时自动退场。

### 5.1 绑定触发 Orchestrator 激活

- [ ] 在 `bind_session_agent` 端点中，绑定成功后检查会话是否已有 Orchestrator：
  - 调用 `AgentOrchestrator.get_by_session(session_id)` 获取编排器
  - 若存在，调用 `await orchestrator.activate_agent(agent_id, "manual_binding")`
  - 若不存在，仅记录绑定关系，不创建 Orchestrator（待会话有消息时自动激活）
- [ ] 在 `batch_bind_sessions` 端点中，每条绑定同样执行激活检查

### 5.2 解绑触发 Orchestrator 退场

- [ ] 在 `unbind_session_agent` 和新增的指定智能体解绑端点中，解绑时检查智能体是否在 Orchestrator 中活跃：
  - 调用 `AgentOrchestrator.get_by_session(session_id)` 获取编排器
  - 若存在且智能体在 `_active_agents` 中，调用 `await orchestrator.deactivate_agent(agent_id, "manual_unbind")`
  - 若 Orchestrator 不存在，跳过退场步骤

### 5.3 绑定触发 Activity 记录

- [ ] 在绑定成功且 Orchestrator 存在时，调用 `activity_store.save_activity(session_id, agent_id, is_primary, "manual_binding")` 记录活跃状态
- [ ] `is_primary` 由 `router.get_session_primary_agent(session_id) == agent_id` 判定

### 5.4 验证绑定/解绑触发

- [ ] 验证：会话已有 Orchestrator → 手动绑定新智能体 → 新智能体被 activate_agent 激活
- [ ] 验证：绑定后新智能体可以参与插话、交互信号等自主性活动
- [ ] 验证：解绑智能体 → Orchestrator 的 _active_agents 中不再包含该智能体
- [ ] 验证：解绑主发言智能体 → 自动切换到下一个活跃智能体为主发言

## 6. 实现活跃会话精确展示（Bug 3 修复）

**目标**：活跃会话查询联合 ChatSession + AgentAutonomyActivity，返回分类结果（活跃/已绑定未活跃）和共居智能体信息。

### 6.1 扩展 AgentActivityStore 查询方法

- [ ] 在 `src/maisaka/agent_autonomy/activity_store.py` 中新增 `get_sessions_by_agent(agent_id) -> list[AgentAutonomyActivity]` 方法：查询 `AgentAutonomyActivity` 表中 `agent_id` 匹配的所有记录（含活跃和已退出）
- [ ] 新增 `get_active_sessions_by_agent(agent_id) -> list[AgentAutonomyActivity]` 方法：查询 `AgentAutonomyActivity` 表中 `agent_id` 匹配且 `exited_at` 为空的记录

### 6.2 扩展后端 API 响应模型

- [ ] 在 `src/webui/routers/agent.py` 中扩展 `SessionAgentInfo` 模型，新增字段：
  - `status: str` — 会话状态（"active" 活跃 / "bound_inactive" 已绑定未活跃）
  - `is_primary: bool` — 是否为主发言智能体
  - `last_spoke_at: Optional[str]` — 最近发言时间（ISO 8601 格式）
  - `cohabitants: List[CohabitantInfo]` — 共居智能体列表
- [ ] 新增 `CohabitantInfo` 模型：
  - `agent_id: str`
  - `display_name: str`
  - `is_primary: bool`
  - `status: str`

### 6.3 重构活跃会话查询端点

- [ ] 在 `src/webui/routers/agent.py` 的 `get_sessions_by_agent` 端点中，重构查询逻辑：
  1. 通过 `chat_manager.agent_router` 获取路由器单例
  2. 查询 `ChatSession` 表中 `agent_id` 匹配的会话（绑定关系）
  3. 查询 `AgentActivityStore.get_active_sessions_by_agent(agent_id)` 获取活跃状态
  4. 对每个会话：
     - 判定状态：有未退出的 Activity → "active"；仅有 ChatSession 绑定 → "bound_inactive"
     - 获取共居智能体：通过 `router.get_session_all_agents(session_id)` 获取所有绑定智能体，排除当前智能体
     - 获取主发言标记：通过 `router.get_session_primary_agent(session_id)` 判定
     - 获取最近发言时间：从 Activity 记录的 `last_spoke_at` 字段
  5. 构建扩展后的 `SessionAgentInfo` 响应
- [ ] 保持向后兼容：新增字段均为可选或带有默认值，旧客户端不受影响

### 6.4 验证活跃会话精确展示

- [ ] 验证：智能体在会话中有未退出的 Activity 记录 → 会话出现在活跃会话列表，状态为 "active"
- [ ] 验证：智能体与会话仅有 ChatSession.agent_id 绑定但无 Activity 记录 → 状态为 "bound_inactive"
- [ ] 验证：多智能体共居的会话 → cohabitants 列表包含其他共居智能体
- [ ] 验证：主发言智能体 → is_primary 为 True

## 7. 实现启动恢复与一致性校验

**目标**：MaiBot 重启后从数据库恢复所有绑定关系到内存路由器和 Orchestrator，并进行一致性校验。

### 7.1 在 ChatManager.initialize 中恢复路由器绑定

- [ ] 在 `src/chat/message_receive/chat_manager.py` 的 `initialize` 方法中，在 `load_all_sessions_from_db` 之后添加绑定恢复逻辑：
  1. 遍历所有 `agent_id` 非空的 `ChatSession` 记录
  2. 对每条记录调用 `self._ensure_agent_router().bind_session(session_id, agent_id)`
  3. 若 `agent_id` 不在 `AgentConfigRegistry` 中，跳过并记录 WARNING 日志
- [ ] 记录恢复结果日志：恢复的绑定数量

### 7.2 在 ChatManager.initialize 中恢复 Orchestrator 活跃状态

- [ ] 在 `initialize` 方法中，路由器绑定恢复之后添加 Orchestrator 恢复逻辑：
  1. 调用 `AgentActivityStore().get_all_active_sessions()` 获取所有未退出的 Activity 记录
  2. 按 `session_id` 分组
  3. 对每个会话：
     - 获取或创建 Orchestrator（`AgentOrchestrator.get_by_session(session_id)`）
     - 若 Orchestrator 不存在，跳过（待会话有消息时自动创建）
     - 对每个活跃智能体调用 `orchestrator.restore_agent(agent_id, is_primary)`
  4. `restore_agent` 不触发任何事件（纯状态重建）

### 7.3 实现一致性校验

- [ ] 在 `initialize` 方法中，恢复完成后添加一致性校验逻辑：
  1. 比对路由器绑定与数据库 `ChatSession.agent_id`：
     - 内存有但数据库无 → WARNING 日志，以数据库为准（从内存移除）
     - 数据库有但内存无 → 补齐到内存（调用 `bind_session`）
  2. 比对 Activity 与绑定：
     - Activity 有活跃记录但路由器无绑定 → 以 Activity 为准恢复 Orchestrator
     - 路由器有绑定但 Activity 无活跃记录 → 标记为"已绑定未活跃"，不报错
- [ ] 所有不一致项输出 WARNING 级别日志，包含具体的不一致详情（session_id、agent_id、差异描述）

### 7.4 验证启动恢复

- [ ] 验证：重启前有 3 个会话绑定了不同智能体 → 重启后路由器能正确路由这 3 个会话
- [ ] 验证：重启后 WebUI 查询绑定 → 返回与重启前一致的结果
- [ ] 验证：重启前会话有 3 个智能体共居 → 重启后 3 个智能体均恢复到 Orchestrator
- [ ] 验证：重启后主发言智能体标记正确恢复
- [ ] 验证：恢复过程中不产生思考、表达、插话等事件
- [ ] 验证：绑定的智能体配置已删除 → 跳过恢复并记录 WARNING

## 8. 前端适配 — 扩展 SessionAgentInfo 类型与 API 层

**目标**：前端类型定义和 API 调用适配后端新增的 status/cohabitants/is_primary/last_spoke_at 字段。

### 8.1 扩展前端 SessionAgentInfo 类型

- [ ] 在 `dashboard/src/lib/agent-api.ts` 中扩展 `SessionAgentInfo` 接口，新增字段：
  - `status: 'active' | 'bound_inactive'` — 会话状态
  - `is_primary: boolean` — 是否为主发言智能体
  - `last_spoke_at: string | null` — 最近发言时间
  - `cohabitants: CohabitantInfo[]` — 共居智能体列表
- [ ] 新增 `CohabitantInfo` 接口：
  - `agent_id: string`
  - `display_name: string`
  - `is_primary: boolean`
  - `status: 'active' | 'bound_inactive'`

### 8.2 新增指定智能体解绑 API 调用

- [ ] 在 `dashboard/src/lib/agent-api.ts` 中新增 `unbindSessionSpecificAgent(sessionId: string, agentId: string)` 函数
- [ ] 调用 `DELETE /api/webui/agent/binding/session/{sessionId}/{agentId}`

### 8.3 验证前端类型适配

- [ ] 验证：TypeScript 编译无类型错误
- [ ] 验证：新增字段在未返回时不导致前端崩溃（可选字段有默认值处理）

## 9. 前端适配 — ActiveSessions 状态分类与共居展示

**目标**：ActiveSessions 组件展示活跃/已绑定未活跃状态分类、共居智能体标签、主发言标记。

### 9.1 改造 ActiveSessions 组件

- [ ] 在 `dashboard/src/routes/agent/components/inner-world/ActiveSessions.tsx` 中改造会话列表项：
  - 活跃会话显示绿色状态标记（如绿色圆点 + "活跃" 文字）
  - 已绑定未活跃显示灰色状态标记（如灰色圆点 + "已绑定" 文字）
  - 主发言智能体显示"主发言"标签或特殊图标（如皇冠图标）
  - 展示共居智能体标签（在会话项下方显示其他共居智能体的名称标签）
  - 显示最近发言时间（活跃会话显示 last_spoke_at）
- [ ] 使用 shadcn/ui 的 Badge 组件展示状态和共居标签

### 9.2 改造解绑交互

- [ ] 在 ActiveSessions 组件中，多智能体场景下：
  - 解绑按钮改为弹出下拉菜单，列出该会话所有绑定的智能体
  - 选择解绑特定智能体，调用 `unbindSessionSpecificAgent`
  - 保留"全部解绑"选项，调用 `unbindSessionAgent`
- [ ] 单智能体场景下保持原有解绑按钮行为

### 9.3 验证前端展示

- [ ] 验证：活跃会话显示绿色状态标记
- [ ] 验证：已绑定未活跃会话显示灰色状态标记
- [ ] 验证：主发言智能体显示"主发言"标签
- [ ] 验证：多智能体共居的会话显示共居智能体标签
- [ ] 验证：解绑特定智能体功能正常

## 10. 国际化适配

**目标**：新增的前端文案同步到中文、英文、日文三个语言文件。

### 10.1 更新 i18n 文件

- [ ] 在 `dashboard/src/i18n/locales/zh.json` 的 `agent.activeSessions` 下新增翻译键：
  - `active` — "活跃"
  - `boundInactive` — "已绑定"
  - `primary` — "主发言"
  - `cohabitants` — "共居智能体"
  - `unbindSpecific` — "解绑智能体"
  - `unbindAll` — "全部解绑"
  - `lastSpokeAt` — "最近发言"
- [ ] 在 `dashboard/src/i18n/locales/en.json` 中同步新增对应英文翻译
- [ ] 在 `dashboard/src/i18n/locales/ja.json` 中同步新增对应日文翻译

### 10.2 验证国际化

- [ ] 验证：三种语言下新增文案均正确显示
- [ ] 验证：无遗漏的硬编码文案

## 11. 集成验证与回归测试

**目标**：端到端验证所有修复和新功能，确保不破坏现有行为。

### 11.1 单智能体绑定回归测试

- [ ] 验证：单智能体绑定/解绑流程与修复前行为一致
- [ ] 验证：群绑定/解绑流程不受影响
- [ ] 验证：路由解析优先级（会话绑定→群绑定→默认）不变

### 11.2 多智能体共居端到端测试

- [ ] 验证：同一会话绑定 2+ 智能体 → 所有智能体均可在此会话中活跃
- [ ] 验证：多智能体场景下消息路由到主发言智能体
- [ ] 验证：主发言智能体解绑 → 自动切换到下一个智能体为主发言
- [ ] 验证：最后一个智能体解绑 → ChatSession.agent_id 清空

### 11.3 绑定一致性端到端测试

- [ ] 验证：绑定操作后内存路由器 + 数据库 + Activity 三者一致
- [ ] 验证：解绑操作后内存路由器 + 数据库 + Orchestrator + Activity 四者一致
- [ ] 验证：重启后绑定恢复正确
- [ ] 验证：一致性异常时日志有 WARNING 告警

### 11.4 活跃会话展示端到端测试

- [ ] 验证：WebUI 活跃会话列表正确展示状态分类
- [ ] 验证：共居智能体标签正确展示
- [ ] 验证：主发言标记正确展示

### 11.5 异常场景测试

- [ ] 验证：绑定不存在的智能体 → 返回 400 错误
- [ ] 验证：ChatManager 未初始化时绑定 → 返回 503 错误
- [ ] 验证：数据库写入失败 → 内存绑定回滚
- [ ] 验证：Orchestrator 退场失败 → 内存和数据库仍清除，日志有警告
- [ ] 验证：重复绑定同一智能体 → 幂等处理，不报错
- [ ] 验证：绑定的智能体配置已删除 → 启动恢复时跳过并记录 WARNING

## 12. 代码审查与收尾

**目标**：确保代码质量、日志规范、导入规范符合项目标准。

### 12.1 代码规范检查

- [ ] 检查所有修改文件的导入顺序是否符合 AGENTS.md 规范（标准库/第三方库在前，本地模块在后，按字母排序）
- [ ] 检查所有新增函数是否有类型注解
- [ ] 检查所有新增逻辑是否有中文注释
- [ ] 检查日志输出是否使用简体中文

### 12.2 日志规范检查

- [ ] 检查绑定操作日志是否包含 session_id、agent_id、操作类型（bind/unbind）、来源（manual/auto）
- [ ] 检查绑定不一致时是否输出 WARNING 级别日志，包含具体不一致详情
- [ ] 检查 WebUI API 中不再出现 `AgentRouter(...)` 构造调用

### 12.3 最终提交

- [ ] 确认所有修改文件已 git 提交
- [ ] 确认 pyproject.toml 和 requirements.txt 无需更新（无新依赖）
- [ ] 确认配置文件模板无变更（本功能不涉及配置变更）