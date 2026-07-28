# proactive-chat v3.5 编码任务

> 任务编号从 336 开始（v3.4.1 最后一个任务是 #335，已完成）

---

## 1. 决策记录聊天流名称解析 + DeepSeek strict 修复

### #336 webui.py 新增 _resolve_stream_name 方法

- [ ] 在 `WebUIServer` 类中新增 `_resolve_stream_name()` 方法，复用 `_stream_display_cache` 将 stream_id 解析为可读名称
  - 方法签名：`def _resolve_stream_name(self, stream_id: str) -> str`
  - 逻辑：stream_id 为空返回空字符串；缓存命中返回 `[群聊] `/`[私聊] ` 前缀 + display_name；缓存未命中返回 `stream_id[:8] + "..."`
  - 不主动调用聊天流列表 API（避免额外延迟）
  - 重构 `_get_stream_display_name()` 使其委托给 `_resolve_stream_name()` 以消除重复
  - 涉及文件：`webui.py`
  - 依赖任务：无
  - 验收标准：`_resolve_stream_name()` 缓存命中时返回"[群聊] 测试群"格式；未命中时返回"a1b2c3d4..."格式；`_get_stream_display_name()` 行为不变

### #337 _handle_decisions 决策记录流名称填充

- [ ] 修改 `_handle_decisions()` 方法，将 `entry["stream_name"] = ""` 替换为调用 `_resolve_stream_name()`
  - 当前代码（第 216 行）：`entry["stream_name"] = ""`
  - 修改为：`entry["stream_name"] = self._resolve_stream_name(d.stream_id)`
  - 涉及文件：`webui.py`
  - 依赖任务：#336
  - 验收标准：决策记录列表 API 返回的 records 中 stream_name 字段不再为空字符串；缓存命中时显示聊天流名称

### #338 _handle_cooldown 冷却记录流名称填充

- [ ] 修改 `_handle_cooldown()` 方法，将 `stream_name` 从空字符串改为调用 `_resolve_stream_name()`
  - 当前代码（第 162 行）：`"stream_name": ""`
  - 修改为：`"stream_name": self._resolve_stream_name(rec.stream_id)`
  - 涉及文件：`webui.py`
  - 依赖任务：#336
  - 验收标准：冷却记录列表 API 返回的 records 中 stream_name 字段不再为空字符串；缓存命中时显示聊天流名称

### #339 DeepSeek strict 模式空参数工具 required 字段修复

- [ ] 修改 `_apply_strict_to_tools()` 方法，移除 `if prop_names:` 条件判断，始终设置 `required` 字段
  - 当前代码（第 459-460 行）：
    ```python
    prop_names = list(params.get("properties", {}).keys())
    if prop_names:
        params["required"] = prop_names
    ```
  - 修改为：
    ```python
    prop_names = list(params.get("properties", {}).keys())
    params["required"] = prop_names  # 空参数时 prop_names 为 []，符合 DeepSeek API 要求
    ```
  - 与主程序 bd077ae5 修复保持一致
  - 涉及文件：`deepseek_client.py`
  - 依赖任务：无
  - 验收标准：strict 模式下，空参数工具的 parameters 包含 `{"type": "object", "properties": {}, "required": []}`；非 strict 模式不受影响

### #340 决策记录流名称解析 + DeepSeek 修复验证

- [ ] 验证 #336-#339 的修复功能
  - 验证决策记录列表中 stream_name 字段正确显示聊天流名称（缓存命中时）
  - 验证冷却记录列表中 stream_name 字段正确显示聊天流名称
  - 验证缓存未命中时显示 stream_id 前 8 位加"..."
  - 验证空 stream_id 返回空字符串
  - 验证 DeepSeek strict 模式下空参数工具调用不返回 400 错误
  - 验证非 strict 模式下工具调用行为不变
  - 涉及文件：`webui.py`、`deepseek_client.py`
  - 依赖任务：#336、#337、#338、#339
  - 验收标准：所有验证项通过；git commit 后端修复

---

## 2. 决策调试服务（debug_service.py 重构）

### #341 DebugMessage 和 DebugSession 数据模型定义

- [ ] 在 `debug_service.py`（新建）中定义核心数据模型
  - `DebugMessage(dataclass)`：role（"system" | "debug_instruction" | "decision_result"）、content（str）、timestamp（float）、reasoning（str，仅 decision_result）、edit_performed（bool）
  - `DebugSession(dataclass)`：session_id（str）、stream_id（str，必填）、messages（list[DebugMessage]）、created_at（float）、last_active_at（float）、token_estimate（int）、is_responding（bool）、context_snapshot（dict）
  - 涉及文件：`debug_service.py`（新建）
  - 依赖任务：无
  - 验收标准：`DebugMessage` 和 `DebugSession` 可正常实例化，字段与设计文档一致

### #342 DebugService 初始化和会话管理方法

- [ ] 实现 `DebugService` 类的 `__init__`、`create_session`、`get_session`、`list_sessions`、`clear_session` 方法
  - `__init__` 参数：deepseek_client、event_bus、persistence_manager、message_api（与 AgentChatService 一致）
  - `__init__` 新增属性：`_sessions: dict[str, DebugSession]`、`_file_editor`、`_preference_cache`、持久化相关属性（保留 v3.4.1 机制）
  - `create_session(stream_id: str)`：stream_id 为必填参数（调试必须针对具体聊天流），空 stream_id 抛出 ValueError；创建后注入聊天流上下文、获取决策上下文快照、加载偏好缓存；淘汰旧会话逻辑与 AgentChatService 一致
  - `list_sessions()` 返回包含 stream_id 字段的会话列表
  - `clear_session()` 删除会话并清理持久化
  - 涉及文件：`debug_service.py`
  - 依赖任务：#341
  - 验收标准：`create_session("stream_123")` 成功创建会话；`create_session("")` 抛出 ValueError；会话包含 context_snapshot

### #343 DebugService 聊天流上下文注入和近期消息获取

- [ ] 实现 `_inject_stream_context`、`_get_recent_messages`、`_format_stream_context` 方法
  - 从 `AgentChatService` 迁移 `_inject_stream_context()`、`_get_recent_messages()`、`_format_stream_context()` 方法，适配 `DebugMessage` 和 `DebugSession` 数据模型
  - `_inject_stream_context()` 中系统消息使用 `DebugMessage(role="system", ...)`
  - 涉及文件：`debug_service.py`
  - 依赖任务：#341
  - 验收标准：创建会话时聊天流上下文正确注入为 system 角色的 DebugMessage

### #344 DebugService 决策上下文获取

- [ ] 实现 `get_decision_context(stream_id: str)` 方法
  - 返回 dict 包含：stream_id、recent_messages（近期消息列表）、cooldown_status（冷却状态）、activity_metrics（活跃度指标）、recent_decisions（近期决策记录摘要）
  - 获取近期消息：通过 `_get_recent_messages(stream_id, limit=10)` 获取，每条消息截取 content 前 100 字符
  - 获取冷却状态：通过 `_persistence.query_decisions(stream_id, limit=1)` 获取最近一条决策记录推断
  - 获取近期决策记录：通过 `_persistence.query_decisions(stream_id, limit=5)` 获取，提取 time、action_taken、intent、confidence、reason、react_steps
  - 各步骤独立 try/except，失败不阻塞其他数据获取
  - 涉及文件：`debug_service.py`
  - 依赖任务：#343
  - 验收标准：调用 `get_decision_context("stream_123")` 返回包含 recent_messages、cooldown_status、recent_decisions 的字典；数据获取失败时对应字段为空但不抛异常

### #345 DebugService 调试指令执行

- [ ] 实现 `execute_instruction()` 方法
  - 参数：session_id、instruction、config、bot_nickname、personality、alias_names、reply_style、custom_prompt
  - 记录调试指令为 `DebugMessage(role="debug_instruction", ...)`
  - 使用 `build_debug_system_prompt()` 构建系统提示词（从 prompts.py 导入）
  - 构建消息列表：system → debug_instruction（映射为 user）→ decision_result（映射为 assistant）
  - 调用 `_deepseek.analyze_with_messages()` 执行 LLM 推理
  - 解析编辑意图（`parse_edit_intent()`），执行偏好编辑
  - 记录决策结果为 `DebugMessage(role="decision_result", ...)`
  - 持久化集成：保存消息和更新会话元数据
  - 涉及文件：`debug_service.py`
  - 依赖任务：#341、#343、#375（build_debug_system_prompt）
  - 验收标准：发送调试指令后返回决策结果；编辑意图正确解析和执行；消息列表中角色为 debug_instruction/decision_result

### #346 DebugService 决策日志查询

- [ ] 实现 `get_decision_log(stream_id: str, limit: int = 20)` 方法
  - 通过 `_persistence.query_decisions(stream_id, limit)` 获取决策记录
  - 返回 list[dict]，每条包含：time、action_taken、intent、confidence、reason、react_steps
  - 涉及文件：`debug_service.py`
  - 依赖任务：#341
  - 验收标准：调用 `get_decision_log("stream_123")` 返回该聊天流的决策日志列表

### #347 DebugService 偏好管理和编辑意图执行

- [ ] 从 `AgentChatService` 迁移偏好管理相关方法
  - 迁移 `_load_preferences()`、`_update_preference_cache()`、`_build_preference_summary()`、`_execute_edit_intent()` 方法
  - 迁移 `set_file_editor()` 方法
  - 迁移 `parse_edit_intent()` 函数（从 agent_chat.py 导入或直接迁移）
  - 偏好摘要描述从"偏好识别"改为"决策调优"（`_build_preference_summary` 中 `[用户偏好]` 改为 `[决策调优依据]`）
  - 涉及文件：`debug_service.py`
  - 依赖任务：#341
  - 验收标准：偏好文件读取、缓存更新、编辑意图执行功能正常；偏好摘要前缀为"[决策调优依据]"

### #348 DebugService 会话自动清理和 token 估算

- [ ] 从 `AgentChatService` 迁移会话管理辅助方法
  - 迁移 `_auto_cleanup_if_needed()`、`_estimate_session_tokens()` 方法，适配 DebugSession/DebugMessage
  - 涉及文件：`debug_service.py`
  - 依赖任务：#341
  - 验收标准：会话 token 超限时自动清理；token 估算结果正确

### #349 DebugService 持久化集成

- [ ] 在 `DebugService` 中集成 SessionPersistence
  - 迁移 `set_session_persistence()`、`restore_sessions()` 方法
  - `restore_sessions()` 中加载消息时，将 v3.4.1 的 `role: "user"` 映射为 `role: "debug_instruction"`，`role: "assistant"` 映射为 `role: "decision_result"`
  - `restore_sessions()` 中 `stream_context_id` 映射为 `DebugSession.stream_id`
  - `create_session()`、`execute_instruction()`、`clear_session()` 中集成持久化写入
  - 涉及文件：`debug_service.py`
  - 依赖任务：#342、#345、#347、#348
  - 验收标准：持久化启用时，会话和消息正确保存到 JSONL 文件；恢复时角色映射正确；持久化未启用时行为与纯内存一致

### #350 AgentChatService 兼容包装

- [ ] 在 `agent_chat.py` 中将 `AgentChatService` 改造为委托给 `DebugService` 的兼容包装
  - 类文档字符串标记 `[deprecated] 请使用 DebugService 替代`
  - `__init__` 接收 `debug_service: DebugService` 参数
  - `create_session()` 委托给 `debug_service.create_session()`，将 `AgentChatSession` 转换返回
  - `send_message()` 委托给 `debug_service.execute_instruction()`，将 `DebugMessage` 转换为 `AgentChatMessage`
  - 其他方法（`clear_session`、`get_session`、`list_sessions`）委托给 DebugService
  - 保留 `AgentChatMessage` 和 `AgentChatSession` 数据类定义（标记 deprecated）
  - 保留 `parse_edit_intent()` 函数（从 debug_service.py 导入或保留原实现）
  - 涉及文件：`agent_chat.py`
  - 依赖任务：#345、#347
  - 验收标准：通过 `AgentChatService` 调用的原有功能正常工作；日志中出现 deprecated 警告

---

## 3. 决策调试 API（debug_api.py 新增）

### #351 DebugApiController 类定义和路由注册

- [ ] 新建 `debug_api.py`，定义 `DebugApiController` 类和 `register_routes()` 方法
  - `__init__` 参数：debug_service、webui_server、config_getter
  - `register_routes(app)` 注册以下路由：
    - `GET /api/proactive-chat/debug/context` → `_handle_context`
    - `GET /api/proactive-chat/debug/sessions` → `_handle_sessions`
    - `POST /api/proactive-chat/debug/sessions` → `_handle_create_session`
    - `GET /api/proactive-chat/debug/sessions/{id}` → `_handle_session_detail`
    - `POST /api/proactive-chat/debug/instruction` → `_handle_instruction`
    - `POST /api/proactive-chat/debug/sessions/{id}/clear` → `_handle_clear`
    - `GET /api/proactive-chat/debug/log` → `_handle_log`
  - 涉及文件：`debug_api.py`（新建）
  - 依赖任务：#342
  - 验收标准：路由注册后，各端点可访问（返回 400 或正确响应，而非 404）

### #352 _handle_context 决策上下文端点

- [ ] 实现 `GET /api/proactive-chat/debug/context` 端点
  - 请求参数：stream_id（必填）
  - 缺少 stream_id 返回 `{"success": False, "error": "缺少 stream_id"}`
  - 调用 `debug_service.get_decision_context(stream_id)` 获取上下文
  - 返回 `{"success": True, "context": {...}}`
  - 涉及文件：`debug_api.py`
  - 依赖任务：#351、#344
  - 验收标准：传入有效 stream_id 返回决策上下文数据；缺少 stream_id 返回错误

### #353 _handle_sessions 和 _handle_create_session 端点

- [ ] 实现调试会话列表和创建端点
  - `GET /api/proactive-chat/debug/sessions`：调用 `debug_service.list_sessions()`，返回 `{"success": True, "sessions": [...]}`；每个会话包含 stream_id、stream_display_name（通过 webui_server._resolve_stream_name 解析）、last_active_display、last_message_preview
  - `POST /api/proactive-chat/debug/sessions`：请求体 `{"stream_id": "xxx"}`（必填），调用 `debug_service.create_session(stream_id)`，返回 `{"success": True, "session_id": "..."}`
  - 缺少 stream_id 返回错误
  - 涉及文件：`debug_api.py`
  - 依赖任务：#351、#342
  - 验收标准：获取会话列表返回带 stream_display_name 的数据；创建会话必须指定 stream_id

### #354 _handle_session_detail 和 _handle_clear 端点

- [ ] 实现会话详情和清除端点
  - `GET /api/proactive-chat/debug/sessions/{id}`：调用 `debug_service.get_session(session_id)`，返回会话详情（包含 messages 列表，角色为 debug_instruction/decision_result）
  - `POST /api/proactive-chat/debug/sessions/{id}/clear`：调用 `debug_service.clear_session(session_id)`，返回 `{"success": True}`
  - 涉及文件：`debug_api.py`
  - 依赖任务：#351、#342
  - 验收标准：获取会话详情返回完整消息列表；清除会话后再次获取返回不存在

### #355 _handle_instruction 和 _handle_log 端点

- [ ] 实现调试指令发送和决策日志查询端点
  - `POST /api/proactive-chat/debug/instruction`：请求体 `{"session_id": "xxx", "instruction": "xxx"}`，调用 `debug_service.execute_instruction()`，返回 `{"success": True, "content": "...", "session_id": "...", "token_estimate": N, "edit_performed": bool}`
  - `GET /api/proactive-chat/debug/log`：请求参数 stream_id（必填）、limit（可选，默认 20，最大 100），调用 `debug_service.get_decision_log()`，返回 `{"success": True, "log": [...]}`
  - 涉及文件：`debug_api.py`
  - 依赖任务：#351、#345、#346
  - 验收标准：发送调试指令返回决策结果；查询决策日志返回该聊天流的决策记录

---

## 4. 决策调试系统提示词（prompts.py 修改）

### #356 DEBUG_SYSTEM_PROMPT 常量定义

- [ ] 在 `prompts.py` 中新增 `DEBUG_SYSTEM_PROMPT` 常量
  - 核心定位：智能体是"决策引擎"，管理员通过调试界面观察和干预其决策行为
  - 核心职责：解释决策依据、响应调试指令、展示推理过程、智能偏好提取
  - 调试指令类型：查看类、注入类、指导类
  - 决策调优指令规则：与 AGENT_CHAT_SYSTEM_PROMPT 的偏好识别规则一致，但描述改为"决策调优指令"
  - 文件编辑格式：保留 EDIT_INTENT 机制不变
  - 回复规则：以决策引擎身份回复，禁止闲聊和角色扮演
  - 包含 `{personality_section}` 和 `{custom_prompt_section}` 占位符
  - 涉及文件：`prompts.py`
  - 依赖任务：无
  - 验收标准：`DEBUG_SYSTEM_PROMPT` 包含核心职责、调试指令类型、决策调优指令、文件编辑格式、回复规则五个部分

### #357 build_debug_system_prompt 函数实现

- [ ] 在 `prompts.py` 中新增 `build_debug_system_prompt()` 函数
  - 函数签名：`def build_debug_system_prompt(bot_nickname, alias_names, personality, reply_style, custom_prompt, preference_summary) -> str`
  - 复用已有的 `PERSONALITY_TEMPLATE`、`ALIAS_TEMPLATE`、`PERSONALITY_DETAIL_TEMPLATE`、`REPLY_STYLE_TEMPLATE` 模板
  - 使用 `DEBUG_SYSTEM_PROMPT.format(personality_section=..., custom_prompt_section=...)` 构建基础提示词
  - 偏好摘要追加到末尾
  - 涉及文件：`prompts.py`
  - 依赖任务：#356
  - 验收标准：调用 `build_debug_system_prompt()` 返回完整的决策调试系统提示词；包含角色信息、偏好摘要

### #358 AGENT_CHAT_SYSTEM_PROMPT 保留并标记 deprecated

- [ ] 保留 `AGENT_CHAT_SYSTEM_PROMPT` 和 `build_chat_system_prompt()`，在文档字符串中标记 deprecated
  - `AGENT_CHAT_SYSTEM_PROMPT` 常量保留不变，上方添加注释 `# [deprecated] v3.5 起请使用 DEBUG_SYSTEM_PROMPT`
  - `build_chat_system_prompt()` 函数保留不变，文档字符串标记 `[deprecated]`
  - 涉及文件：`prompts.py`
  - 依赖任务：无
  - 验收标准：原有 `build_chat_system_prompt()` 功能不变；新增 `build_debug_system_prompt()` 可正常调用

### #359 prompts.py 同步英文和日文模板

- [ ] 如果 prompts.py 存在英文/日文模板文件，同步新增 `DEBUG_SYSTEM_PROMPT` 的英文和日文版本
  - 检查是否存在 `prompts_en.py`、`prompts_ja.py` 或类似文件
  - 若存在，新增对应语言的 `DEBUG_SYSTEM_PROMPT` 和 `build_debug_system_prompt()`
  - 若不存在，跳过此任务
  - 涉及文件：`prompts.py` 及相关语言文件
  - 依赖任务：#356、#357
  - 验收标准：英文/日文模板与中文模板对齐

---

## 5. 决策调试前端界面（webui_static/ 重构）

### #360 index.html 决策调试 Tab 替换智能体对话 Tab

- [ ] 修改 `index.html`，将"智能体对话"Tab 替换为"决策调试"Tab
  - Tab 标签从"智能体对话"改为"决策调试"
  - Tab 内容区替换为决策调试布局：提示横幅 + 左侧聊天流列表 + 右侧调试面板
  - 提示横幅文案："💡 注入 MaiBot 提示词是为了让智能体更好地理解上下文做出决策，而不是和智能体聊天。你可以通过调试指令观察和干预决策行为。"
  - 左侧聊天流列表容器：`<div id="debug-stream-list" class="debug-stream-list">`
  - 右侧调试面板包含三个区域：上下文区、日志区、指令区
  - 涉及文件：`webui_static/index.html`
  - 依赖任务：无
  - 验收标准：页面加载后显示"决策调试"Tab；点击后显示提示横幅、聊天流列表和调试面板

### #361 style.css 决策调试布局样式

- [ ] 新增决策调试界面相关的 CSS 样式
  - 主布局：`.debug-layout`（display:flex; height:100%）、`.debug-stream-list`（width:240px; border-right; overflow-y:auto）、`.debug-panel`（flex:1; display:flex; flex-direction:column; overflow:hidden）
  - 提示横幅：`.debug-hint-banner`（蓝色半透明背景、圆角、内边距、小字号）
  - 上下文区：`.debug-context-panel`（border-bottom; padding:12px; max-height:200px; overflow-y:auto）
  - 日志区：`.debug-log-panel`（flex:1; overflow-y:auto; padding:12px）
  - 指令区：`.debug-instruction-panel`（border-top; padding:12px）、`.instruction-buttons`（display:flex; gap:8px）
  - 调试按钮：`.btn-debug`（padding:6px 12px; border-radius:6px; border; cursor:pointer; hover 变色）
  - 聊天流类型徽标：`.stream-type-badge`（20×20px; border-radius:4px; text-align:center）、`.stream-type-badge.group`（绿色）、`.stream-type-badge.private`（蓝色）
  - 日志条目：`.log-entry`（margin-bottom:12px; padding:8px 12px; border-radius:8px）、`.log-entry.instruction`（紫色左边框）、`.log-entry.result`（普通边框）、`.log-entry.system`（蓝色居中）、`.log-entry.error`（红色左边框）
  - 调优徽标：`.edit-badge`（绿色小标签）
  - 上下文区子样式：`.context-section`、`.context-msg`、`.decision-item`、`.decision-item.triggered`/`.skipped`
  - 涉及文件：`webui_static/style.css`
  - 依赖任务：无
  - 验收标准：决策调试界面布局正确：左侧 240px 聊天流列表、右侧三段式调试面板；各区域样式与设计稿一致

### #362 app.js 聊天流列表加载和渲染

- [ ] 实现决策调试界面的聊天流列表功能
  - 新增状态变量：`debugStreams`、`currentDebugStreamId`、`currentDebugSessionId`、`debugContext`、`debugLog`
  - 新增 `loadDebugStreams()` 函数：调用 `GET /api/proactive-chat/streams` 获取聊天流列表
  - 新增 `renderDebugStreamList()` 函数：渲染聊天流列表，每项显示类型徽标（群/私）、显示名称、冷却状态；选中项高亮
  - 聊天流名称优先显示 `display_name` 字段（实际群名或"XX 的私聊"），而非 stream_id
  - 新增 `selectDebugStream(streamId)` 函数：选中聊天流后，依次刷新上下文、决策日志、创建/获取调试会话
  - 涉及文件：`webui_static/app.js`
  - 依赖任务：#360、#361
  - 验收标准：进入决策调试 Tab 后显示聊天流列表；点击聊天流后高亮选中并加载调试数据

### #363 app.js 决策上下文渲染

- [ ] 实现决策上下文面板的加载和渲染
  - 新增 `refreshContext()` 函数：调用 `GET /api/proactive-chat/debug/context?stream_id=xxx` 获取上下文
  - 新增 `renderDebugContext()` 函数：渲染上下文面板
    - 近期消息区：显示最近 10 条消息，格式 `[发送者] 内容`
    - 冷却状态区：显示上次触发时间和摘要
    - 近期决策区：显示最近 5 条决策记录，触发/跳过不同样式
    - 无数据时显示"暂无决策上下文"
  - 涉及文件：`webui_static/app.js`
  - 依赖任务：#362、#352
  - 验收标准：选择聊天流后，上下文面板显示近期消息、冷却状态、近期决策

### #364 app.js 调试会话管理

- [ ] 实现调试会话的创建和消息加载
  - 新增 `ensureDebugSession(streamId)` 函数：
    - 先调用 `GET /api/proactive-chat/debug/sessions` 查找该聊天流的已有会话
    - 已有会话：设置 `currentDebugSessionId`，加载消息
    - 无已有会话：调用 `POST /api/proactive-chat/debug/sessions` 创建新会话
  - 新增 `loadDebugMessages()` 函数：加载当前会话的消息并渲染到日志区
  - 涉及文件：`webui_static/app.js`
  - 依赖任务：#362、#353、#354
  - 验收标准：选择聊天流后自动创建或恢复调试会话；已有会话的消息正确加载到日志区

### #365 app.js 调试指令发送和日志渲染

- [ ] 实现调试指令发送和决策日志渲染
  - 新增 `sendDebugInstruction()` 函数：读取指令输入框内容，调用 `POST /api/proactive-chat/debug/instruction`，结果追加到日志区
  - 新增 `appendDebugLog(role, content, editPerformed)` 函数：在日志区追加一条日志条目
    - debug_instruction：紫色左边框，标签"调试指令"，纯文本
    - decision_result：普通边框，标签"决策引擎"，Markdown 渲染，可选"已调优"徽标
    - system：蓝色居中，标签"系统"
    - error：红色左边框，标签"错误"
  - 新增 `refreshDecisionLog()` 函数：调用 `GET /api/proactive-chat/debug/log` 获取决策日志
  - 日志区自动滚动到底部
  - 涉及文件：`webui_static/app.js`
  - 依赖任务：#362、#355
  - 验收标准：输入调试指令并发送后，日志区显示指令和决策结果；决策结果支持 Markdown 渲染

### #366 app.js UI 按钮操作实现

- [ ] 实现调试面板的 UI 按钮操作
  - `viewContext()`：调用 `refreshContext()` 刷新上下文区
  - `forceTrigger()`：调用 `POST /api/proactive-chat/trigger` 触发决策循环，结果追加到日志区
  - `resetCooldown()`：调用 `POST /api/proactive-chat/cooldown/reset` 重置冷却，结果追加到日志区，刷新上下文
  - 按钮操作不经过 LLM，直接调用对应 API 端点
  - 涉及文件：`webui_static/app.js`
  - 依赖任务：#362
  - 验收标准：点击"查看上下文"刷新上下文面板；点击"强制触发"触发决策循环；点击"重置冷却"重置冷却并刷新

### #367 app.js Tab 切换时初始化决策调试

- [ ] 修改 Tab 切换逻辑，在切换到"决策调试"Tab 时自动加载聊天流列表
  - 在 Tab 切换事件中，如果切换到决策调试 Tab 且 `debugStreams` 为空，调用 `loadDebugStreams()`
  - 涉及文件：`webui_static/app.js`
  - 依赖任务：#362
  - 验收标准：首次切换到决策调试 Tab 时自动加载聊天流列表

---

## 6. 配置调整 + 插件启动流程集成 + 向后兼容 + 测试

### #368 AgentChatConfig UI 标签和描述调整

- [ ] 修改 `AgentChatConfig` 类的 UI 标签和描述文案，从"智能体对话"改为"决策调试"
  - `__ui_label__` 从 `"智能体对话"` 改为 `"决策调试"`
  - `__ui_icon__` 从 `"message-circle"` 改为 `"bug"`
  - 各配置项的 `description` 文案调整：
    - `agent_chat_enabled`：`"是否启用 WebUI 决策调试功能"`
    - `chat_max_tokens`：`"调试指令 LLM 调用的最大 token 数"`
    - `chat_max_sessions`：`"最大同时活跃调试会话数"`
    - `chat_session_token_limit`：`"调试会话自动清除的 token 阈值"`
    - `chat_temperature`：`"调试指令的 LLM 温度"`
    - `file_edit_enabled`：`"是否启用决策调优指令的文件编辑能力"`
    - `auto_preference_enabled`：`"是否启用智能偏好提取（决策调优指令自动识别）"`
    - `session_persistence_enabled`：`"是否启用调试会话持久化（容器重启后保留会话数据）"`
    - `max_persisted_sessions`：`"最大持久化调试会话数"`
    - `max_persisted_messages_per_session`：`"每个调试会话最大持久化消息数"`
    - `session_retention_days`：`"调试会话保留天数，0 表示不清理"`
  - **注意**：配置项的 Python 字段名保持不变，仅修改 UI 标签和描述
  - 涉及文件：`config.py`
  - 依赖任务：无
  - 验收标准：WebUI 配置页面显示"决策调试"分组；各配置项描述体现调试语义；配置文件字段名不变

### #369 配置版本升级到 3.5

- [ ] 将 `PluginSectionConfig.config_version` 默认值从 `"3.4.1"` 升级到 `"3.5"`
  - 涉及文件：`config.py`
  - 依赖任务：#368
  - 验收标准：`PluginSectionConfig.config_version` 默认值为 `"3.5"`

### #370 plugin.py 启动流程集成 DebugService

- [ ] 修改 `plugin.py` 的 `on_load()` 中集成 `DebugService` 初始化
  - 导入 `from .debug_service import DebugService`
  - 创建 `DebugService` 实例（替代 `AgentChatService` 直接使用）
  - 注入 FileEditor（若 file_edit_enabled）
  - 持久化集成：创建 SessionPersistence，调用 `set_session_persistence()`，调用 `restore_sessions()`
  - 注入到 WebUIServer：`self._webui_server.set_debug_service(self._debug_service)`
  - 注册调试 API 路由：创建 `DebugApiController` 实例，调用 `register_routes()`
  - 创建 `AgentChatService` 兼容包装（委托给 DebugService），注入到 WebUIServer 的 `_agent_chat_service`
  - 涉及文件：`plugin.py`
  - 依赖任务：#349、#350、#351
  - 验收标准：插件启动后 DebugService 正确初始化；调试 API 路由可访问；原有 agent_chat API 仍可工作

### #371 webui.py 新增 set_debug_service 方法和 debug API 路由注册支持

- [ ] 在 `WebUIServer` 中新增 `set_debug_service()` 方法
  - `set_debug_service(self, debug_service: DebugService) -> None`：保存 debug_service 引用
  - 在 `start()` 方法中，如果有 debug_service，注册 debug API 路由（或由 plugin.py 外部注册）
  - 涉及文件：`webui.py`
  - 依赖任务：无
  - 验收标准：`set_debug_service()` 可正常调用；debug API 路由注册后可访问

### #372 原有 agent_chat API 端点标记 deprecated

- [ ] 在 `webui.py` 中为原有 agent_chat 端点添加 deprecated 标记
  - 在 `_handle_agent_chat_sessions`、`_handle_agent_chat_create`、`_handle_agent_chat_send`、`_handle_agent_chat_session_detail`、`_handle_agent_chat_clear` 方法的文档字符串中标记 `[deprecated] 请使用 /api/proactive-chat/debug/* 端点`
  - 功能保持不变，通过 AgentChatService 兼容包装继续工作
  - 涉及文件：`webui.py`
  - 依赖任务：#350
  - 验收标准：原有 agent_chat API 端点仍可正常工作；文档字符串标记 deprecated

### #373 决策记录聊天流名称解析验证

- [ ] 验证决策记录和冷却记录的 stream_name 字段正确显示
  - 验证决策记录列表 API 返回 stream_name 不为空字符串
  - 验证冷却记录列表 API 返回 stream_name 不为空字符串
  - 验证缓存命中时显示"[群聊] 测试群"或"[私聊] XX 的私聊"格式
  - 验证缓存未命中时显示 stream_id 前 8 位加"..."
  - 验证空 stream_id 返回空字符串
  - 涉及文件：`webui.py`
  - 依赖任务：#336、#337、#338
  - 验收标准：所有验证项通过

### #374 DeepSeek strict 模式修复验证

- [ ] 验证 DeepSeek strict 模式空参数工具修复
  - 验证 strict 模式下，空参数工具的 parameters 包含 `required: []`
  - 验证 strict 模式下，有参数工具的 parameters 包含 `required: [prop_names]`
  - 验证非 strict 模式下工具调用行为不变
  - 涉及文件：`deepseek_client.py`
  - 依赖任务：#339
  - 验收标准：所有验证项通过

### #375 决策调试服务功能验证

- [ ] 验证 DebugService 核心功能
  - 验证 `create_session("stream_123")` 成功创建调试会话
  - 验证 `create_session("")` 抛出 ValueError
  - 验证 `get_decision_context()` 返回近期消息、冷却状态、近期决策
  - 验证 `execute_instruction()` 正确执行调试指令并返回决策结果
  - 验证 `get_decision_log()` 返回决策日志
  - 验证偏好编辑功能正常
  - 验证持久化启用时会话和消息正确保存和恢复
  - 验证 v3.4.1 持久化数据可被 v3.5 正确恢复（角色映射 user→debug_instruction, assistant→decision_result）
  - 涉及文件：`debug_service.py`
  - 依赖任务：#349、#345
  - 验收标准：DebugService 所有核心功能正常；v3.4.1 数据兼容

### #376 决策调试 API 端点验证

- [ ] 验证所有调试 API 端点功能
  - 验证 `GET /debug/context` 返回决策上下文
  - 验证 `GET /debug/sessions` 返回会话列表（含 stream_display_name）
  - 验证 `POST /debug/sessions` 创建调试会话（必须指定 stream_id）
  - 验证 `GET /debug/sessions/{id}` 返回会话详情
  - 验证 `POST /debug/instruction` 发送调试指令并返回决策结果
  - 验证 `POST /debug/sessions/{id}/clear` 清除会话
  - 验证 `GET /debug/log` 返回决策日志
  - 涉及文件：`debug_api.py`
  - 依赖任务：#351-#355
  - 验收标准：所有调试 API 端点功能正常

### #377 决策调试前端界面验证

- [ ] 验证决策调试前端界面功能
  - 验证"决策调试"Tab 正确显示
  - 验证提示横幅文案正确
  - 验证聊天流列表加载和显示（优先显示聊天流名称而非 stream_id）
  - 验证选择聊天流后上下文面板显示近期消息、冷却状态、近期决策
  - 验证发送调试指令后日志区显示指令和决策结果
  - 验证"查看上下文"按钮刷新上下文面板
  - 验证"强制触发"按钮触发决策循环
  - 验证"重置冷却"按钮重置冷却
  - 验证界面中不出现"聊天"、"对话"等闲聊导向的文案
  - 涉及文件：`webui_static/index.html`、`webui_static/style.css`、`webui_static/app.js`
  - 依赖任务：#360-#367
  - 验收标准：决策调试界面功能完整；UI 文案体现"决策调试"定位

### #378 向后兼容验证

- [ ] 验证 v3.5 向后兼容 v3.4.1
  - 验证原有 `/api/proactive-chat/agent/chat/*` 端点仍可正常工作
  - 验证通过 `AgentChatService` 兼容包装调用的功能正常
  - 验证 v3.4.1 的配置文件可直接升级到 v3.5（字段名不变）
  - 验证 v3.4.1 的 JSONL 持久化数据可被 v3.5 正确恢复
  - 验证决策记录和冷却记录 API 返回数据新增 stream_name 字段不影响现有前端
  - 涉及文件：所有修改文件
  - 依赖任务：#370、#372
  - 验收标准：v3.4.1 的所有 API 端点契约保持兼容；配置文件无需迁移

### #379 系统提示词验证

- [ ] 验证决策调试系统提示词功能
  - 验证 `DEBUG_SYSTEM_PROMPT` 包含核心职责、调试指令类型、决策调优指令、文件编辑格式、回复规则
  - 验证 `build_debug_system_prompt()` 返回完整提示词
  - 验证智能体以"决策引擎"身份响应调试指令，而非"指令执行助手"
  - 验证 `AGENT_CHAT_SYSTEM_PROMPT` 和 `build_chat_system_prompt()` 仍可正常使用
  - 涉及文件：`prompts.py`
  - 依赖任务：#356、#357、#358
  - 验收标准：新提示词定位为"决策引擎"；旧提示词功能不变

### #380 端到端集成验证

- [ ] 验证 v3.5 完整功能链路
  - 验证完整流程：进入决策调试 Tab → 选择聊天流 → 查看决策上下文 → 发送调试指令 → 查看决策结果
  - 验证完整流程：发送调试指令 → LLM 调用 → 偏好编辑 → JSONL 持久化
  - 验证完整流程：创建调试会话 → 发送多条指令 → 容器重启 → 会话和消息恢复
  - 验证完整流程：决策记录列表显示聊天流名称 → 选择聊天流 → 调试界面显示对应上下文
  - 验证 DeepSeek strict 模式下空参数工具调用正常
  - 验证原有 agent_chat API 端点仍可正常工作
  - 验证配置页面显示"决策调试"分组
  - 涉及文件：所有修改文件
  - 依赖任务：#373-#379
  - 验收标准：端到端功能链路完整；向后兼容；git commit 最终版本