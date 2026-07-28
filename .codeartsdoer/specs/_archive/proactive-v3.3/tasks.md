# proactive-chat v3.3 编码任务

> 任务编号从 241 开始（v3.2 任务编号为 162-240，已完成）

---

## 1. 配置扩展

### #241 AgentOptimizationConfig 新增 4 个时间边界字段

- [ ] 在 `config.py` 的 `AgentOptimizationConfig` 类中新增 4 个时间边界配置项
  - `quiet_hours_start: int = Field(default=22, ge=0, le=23, description="安静时段开始时间（小时，0-23）")`
  - `quiet_hours_end: int = Field(default=6, ge=0, le=23, description="安静时段结束时间（小时，0-23）")`
  - `work_hours_start: int = Field(default=9, ge=0, le=23, description="工作时间开始时间（小时，0-23）")`
  - `work_hours_end: int = Field(default=18, ge=0, le=23, description="工作时间结束时间（小时，0-23）")`
  - 涉及文件：`config.py`
  - 依赖任务：无
  - 验收标准：4 个字段可正常实例化，默认值分别为 22、6、9、18；ge/le 约束生效

### #242 config_version 升级到 3.3.0，更新配置模板和 conftest.py

- [ ] 将 `PluginSectionConfig.config_version` 从 `"3.2.0"` 升级为 `"3.3.0"`
  - 更新 `config.toml` 配置模板，新增 `agent_optimization` 段的 4 个时间边界字段注释和默认值
  - 更新 `tests/conftest.py` 中的测试配置 fixture，确保包含新字段
  - 涉及文件：`config.py`、`config.toml`、`tests/conftest.py`
  - 依赖任务：#241
  - 验收标准：config_version 显示为 3.3.0；v3.2 配置文件加载后新字段使用默认值；模板文件包含 4 个新字段的注释和默认值

---

## 2. 时间感知模块

### #243 新增 time_awareness.py：TimePeriod 枚举 + TimeAwarenessInfo 数据类

- [ ] 在新文件 `time_awareness.py` 中定义 `TimePeriod` 枚举和 `TimeAwarenessInfo` 数据类
  - TimePeriod 枚举（继承 str, Enum）：LATE_NIGHT="深夜"、EARLY_MORNING="清晨"、MORNING_WORK="上午工作时间"、LUNCH_BREAK="午休时间"、AFTERNOON_WORK="下午工作时间"、EVENING_LEISURE="傍晚休闲"、NIGHT="夜间"
  - TimeAwarenessInfo 数据类：`current_time_str: str = ""`、`time_period: TimePeriod = TimePeriod.LATE_NIGHT`、`time_period_desc: str = ""`、`decision_tendency: str = ""`、`is_weekend: bool = False`、`interval_since_last_trigger: str = ""`、`interval_since_last_message: str = ""`
  - 涉及文件：`time_awareness.py`（新增）
  - 依赖任务：无
  - 验收标准：TimePeriod 枚举包含 7 个值；TimeAwarenessInfo 可正常实例化，字段类型和默认值符合预期

### #244 TimeAwareness 类：classify_time_period + get_decision_tendency

- [ ] 在 `time_awareness.py` 中实现 `TimeAwareness` 类的核心分类方法
  - 构造函数：`__init__(self, cooldown_manager, config_getter=None)`，存储 `_cooldown` 和 `_config_getter`
  - `classify_time_period(hour: int) -> TimePeriod`：根据配置的时间边界将小时映射到 7 个时间段分类。深夜(0~quiet_end)、清晨(quiet_end~work_start)、上午工作(work_start~12)、午休(12~14)、下午工作(14~work_end)、傍晚休闲(work_end~quiet_start)、夜间(quiet_start~24)
  - `get_decision_tendency(time_period, is_weekend) -> str`：根据时间段和是否周末生成决策倾向指导。周末的午休/傍晚/工作时间追加"（周末休闲时段，可适当更积极发言）"后缀
  - 定义模块级 `_TENDENCY_MAP` 字典和 `_WEEKEND_TENDENCY_SUFFIX` 常量
  - 涉及文件：`time_awareness.py`
  - 依赖任务：#243
  - 验收标准：hour=3 → LATE_NIGHT；hour=14 → AFTERNOON_WORK；hour=23 → NIGHT；周末 + LUNCH_BREAK → 包含"周末休闲时段"后缀

### #245 TimeAwareness 类：get_time_awareness_info + format_for_prompt + _format_interval

- [ ] 在 `TimeAwareness` 类中实现信息获取、格式化和间隔计算方法
  - `get_time_awareness_info(stream_id, recent_messages=None) -> TimeAwarenessInfo | None`：获取当前系统时间，计算时间段分类、决策倾向、时间间隔（距上次触发从 `_cooldown._records` 获取 `triggered_at`，距最后一条消息从 `recent_messages` 的时间戳计算）。系统时间不可用时返回 None 并记录警告日志。冷却记录不存在时 `interval_since_last_trigger="无记录"`。消息时间戳可能是秒或毫秒，需判断 `> 1e12` 时除以 1000
  - `format_for_prompt(info: TimeAwarenessInfo) -> str`：格式化为 `[时间感知] 当前时间：...，时间段：...\n[决策倾向] ...\n[时间间隔] ...` 格式。时间间隔部分用"；"连接
  - `_format_interval(seconds: float) -> str`：将秒数格式化为人类可读的间隔描述，如 "2小时15分钟"、"5分钟"、"30秒"
  - 涉及文件：`time_awareness.py`
  - 依赖任务：#244
  - 验收标准：当前时间 14:30 → 时间段"下午工作时间"；距上次触发 8100 秒 → "2小时15分钟"；冷却无记录 → "无记录"；format_for_prompt 输出包含 [时间感知]、[决策倾向]、[时间间隔] 三个段落

### #246 prompts.py 新增 TIME_AWARENESS_TEMPLATE

- [ ] 在 `prompts.py` 中新增 `TIME_AWARENESS_TEMPLATE` 常量
  - 模板内容：`"[时间感知] 当前时间：{current_time}，时间段：{time_period}\n[决策倾向] {decision_tendency}\n[时间间隔] {time_intervals}"`
  - 注意：此模板作为参考定义，实际格式化由 `TimeAwareness.format_for_prompt()` 完成
  - 涉及文件：`prompts.py`
  - 依赖任务：无
  - 验收标准：常量可正常使用 format() 填充；包含 current_time、time_period、decision_tendency、time_intervals 占位符

### #247 agent.py perceive 集成时间感知注入

- [ ] 在 `agent.py` 中集成时间感知到 perceive 阶段和提示词构建
  - `PerceptionData` 新增字段：`_time_awareness_text: str = ""`
  - `AgentCore.__init__` 新增字段：`self._time_awareness: Any = None`
  - `perceive()` 方法末尾新增时间感知调用：当 `self._time_awareness is not None` 时调用 `get_time_awareness_info(stream_id, recent_messages)`，结果格式化后存入 `perception._time_awareness_text`。异常时记录 debug 日志，不阻塞决策循环
  - `_react_loop()` 中构建 user_prompt 后，将 `perception._time_awareness_text` 注入到用户提示词最前面：`user_prompt = perception._time_awareness_text + "\n\n" + user_prompt`
  - `reason()` 方法中 `_build_prompts()` 调用后，同样注入时间感知文本到用户提示词最前面
  - 涉及文件：`agent.py`
  - 依赖任务：#245、#246
  - 验收标准：perceive 返回的 PerceptionData 包含 `_time_awareness_text`；`_react_loop` 和 `reason` 中用户提示词开头包含时间感知段落；时间感知异常时决策循环正常执行

### #248 plugin.py 初始化 TimeAwareness 并注入 AgentCore

- [ ] 在 `plugin.py` 的 `on_load` 方法中初始化时间感知模块并注入
  - 导入 `TimeAwareness`：`from .time_awareness import TimeAwareness`
  - 创建实例：`self._time_awareness = TimeAwareness(cooldown_manager=self._cooldown_manager, config_getter=lambda: self._config)`
  - 注入到 AgentCore：`self._agent._time_awareness = self._time_awareness`
  - 涉及文件：`plugin.py`
  - 依赖任务：#247
  - 验收标准：插件启动后 AgentCore 的 `_time_awareness` 不为 None；决策循环中时间感知信息正常注入到用户提示词

---

## 3. 聊天流上下文注入修复

### #249 agent_chat.py 修复 _inject_stream_context 空实现

- [ ] 修复 `AgentChatService._inject_stream_context()` 方法的空实现
  - 移除现有的 `hasattr(self._persistence, '_data_dir')` 检查和 `from .agent import AgentCore` 无用导入
  - 新逻辑：检查 `stream_id` 非空 → 调用 `_get_recent_messages(stream_id, limit=5)` 获取近期消息 → 消息非空时调用 `_format_stream_context()` 格式化 → 将格式化文本作为 `role="system"` 消息 `insert(0, ...)` 插入到会话消息列表开头
  - 注入成功时记录 debug 日志：`"已注入聊天流上下文，会话 %s，消息数: %d"`
  - 异常时记录 debug 日志并跳过，不阻塞会话创建
  - 涉及文件：`agent_chat.py`
  - 依赖任务：无
  - 验收标准：创建会话时指定 stream_context_id → `_inject_stream_context` 调用 `_get_recent_messages` → 返回消息被格式化注入到会话消息列表开头

### #250 agent_chat.py 新增 _get_recent_messages 和 _format_stream_context

- [ ] 在 `AgentChatService` 中新增 2 个辅助方法
  - `_get_recent_messages(stream_id: str, limit: int = 5) -> list[dict]`：封装 `self._message_api.get_recent(chat_id=stream_id, limit=limit)` 调用。`_message_api` 不可用时记录 debug 日志并返回空列表。调用异常时记录 debug 日志并返回空列表。返回值非 list 时返回空列表
  - `_format_stream_context(recent_messages: list[dict]) -> str`（静态方法）：格式化聊天流上下文消息。每条消息提取 `sender_name`（默认"未知"）和 `content`（截断至 100 字符），格式为 `[发送者名称] 消息内容摘要`。空内容的消息跳过。各条消息用换行符连接
  - 涉及文件：`agent_chat.py`
  - 依赖任务：#249
  - 验收标准：3 条近期消息 → 格式化为 3 行 `[发送者] 内容` 文本；消息缺少 sender_name → 显示"未知"；内容超过 100 字符 → 截断

### #251 AgentChatService 构造函数新增 message_api 参数

- [ ] 修改 `AgentChatService.__init__()` 新增 `message_api` 参数
  - 新增参数：`message_api: Any = None`
  - 存储：`self._message_api = message_api`
  - 涉及文件：`agent_chat.py`
  - 依赖任务：#250
  - 验收标准：构造函数接受 message_api 参数；`_get_recent_messages` 可通过 `self._message_api` 调用 `get_recent()`

### #252 plugin.py 传入 message_api 到 AgentChatService

- [ ] 在 `plugin.py` 的 `on_load` 方法中传入 `message_api` 到 `AgentChatService`
  - 在 AgentChatService 创建后（或通过属性注入），设置 `self._agent_chat_service._message_api = self.ctx.message if hasattr(self.ctx, 'message') else None`
  - 涉及文件：`plugin.py`
  - 依赖任务：#251
  - 验收标准：插件启动后 AgentChatService 的 `_message_api` 不为 None（当 ctx.message 可用时）；创建会话时聊天流上下文可正常注入

### #253 webui.py 4 个 Agent Chat API 新增 agent_chat_enabled 检查

- [ ] 在 `webui.py` 中新增 `_check_agent_chat_enabled()` 方法并在 4 个 Agent Chat API 处理方法中集成
  - 新增方法：`_check_agent_chat_enabled(self) -> web.Response | None`，检查 `config.agent_chat.agent_chat_enabled`，未启用时返回 `web.json_response({"success": False, "error": "智能体对话服务未启用"}, status=403)`
  - 在以下 4 个方法开头添加检查：
    - `_handle_agent_chat_sessions()`（GET /api/.../sessions）
    - `_handle_agent_chat_create()`（POST /api/.../sessions）
    - `_handle_agent_chat_send()`（POST /api/.../send）
    - `_handle_agent_chat_clear()`（POST /api/.../sessions/{id}/clear）
  - 使用 walrus 运算符：`if error_resp := self._check_agent_chat_enabled(): return error_resp`
  - 涉及文件：`webui.py`
  - 依赖任务：无
  - 验收标准：agent_chat_enabled=False → 4 个 API 均返回 403 + "智能体对话服务未启用"；agent_chat_enabled=True → 正常处理

---

## 4. WebUI 智能体对话 Tab

### #254 index.html 新增智能体对话 Tab 结构

- [ ] 在 `webui_static/index.html` 中新增智能体对话 Tab 的 HTML 结构
  - Tab 栏新增按钮：`<button class="tab-btn" onclick="switchTab('agent-chat')">智能体对话</button>`
  - 新增 `tab-agent-chat` 内容区，包含：
    - 未启用提示区（`#agent-chat-disabled`，默认隐藏）
    - 智能体对话主界面（`#agent-chat-main`，默认隐藏，flex 布局）
      - 左侧会话列表（`.chat-sidebar`）：标题栏 + 新建会话按钮 + 会话列表容器
      - 右侧对话区域（`.chat-main`）：空状态提示 + 对话界面（会话信息栏 + 消息列表 + 输入区域）
    - 新建会话对话框（`#new-session-dialog`，默认隐藏）：聊天流选择器 + 创建/取消按钮
  - 涉及文件：`webui_static/index.html`
  - 依赖任务：无
  - 验收标准：WebUI 加载后 Tab 栏显示三个 Tab；第三个为"智能体对话"；点击后显示对应内容区

### #255 style.css 新增智能体对话样式

- [ ] 在 `webui_static/style.css` 中新增智能体对话 Tab 相关样式
  - 主布局：`#tab-agent-chat #agent-chat-main` flex 布局，gap 16px，高度 calc(100vh - 140px)
  - 左侧会话列表：`.chat-sidebar` 宽 260px，flex-shrink: 0，圆角 12px，flex 列布局
  - 会话列表项：`.chat-session-item` 圆角 8px，hover 背景色变化，active 左边框 3px accent
  - 右侧对话区域：`.chat-main` flex: 1，flex 列布局
  - 聊天气泡：`.chat-bubble` max-width 75%，`.user-bubble` 靠右 accent 背景，`.assistant-bubble` 靠左 border 背景，`.system-bubble` 居中半透明背景
  - 输入区域：`.chat-input-area` flex 布局，textarea flex: 1，发送按钮 accent 背景
  - 响应式：768px 以下改为纵向布局
  - 涉及文件：`webui_static/style.css`
  - 依赖任务：无
  - 验收标准：智能体对话 Tab 布局正确；左右分栏显示；聊天气泡样式区分用户/助手/系统；响应式布局生效

### #256 app.js 新增智能体对话状态管理和 API 调用

- [ ] 在 `webui_static/app.js` 中新增智能体对话全局状态和核心 API 调用函数
  - 新增全局状态：`agentChatEnabled`、`agentChatSessions`、`currentChatSessionId`、`currentChatMessages`、`isChatResponding`
  - `loadAgentChat()`：检查 agent_chat_enabled 状态，未启用显示提示，已启用加载会话列表
  - `loadAgentChatSessions()`：GET /api/proactive-chat/agent/chat/sessions，更新 `agentChatSessions` 并调用 `renderSessionList()`
  - 扩展 `switchTab()` 函数：当 tab === 'agent-chat' 时调用 `loadAgentChat()`
  - 涉及文件：`webui_static/app.js`
  - 依赖任务：#254
  - 验收标准：点击"智能体对话"Tab → loadAgentChat 执行 → 未启用时显示提示；已启用时加载会话列表

### #257 app.js 新增聊天流选择器和会话管理

- [ ] 在 `app.js` 中新增会话列表渲染、会话选择、新建会话、清除会话相关函数
  - `renderSessionList()`：渲染会话列表，每个会话显示截断 ID、时间、消息数、关联聊天流
  - `selectChatSession(sessionId)`：设置当前会话 ID，更新列表高亮，显示对话区域，调用 `loadChatMessages()`
  - `loadChatMessages(sessionId)`：从会话列表数据初始化消息区域（会话列表不含消息内容，清空消息区域）
  - `createAgentChatSession()`：显示新建会话对话框，调用 `loadStreamListForNewSession()`
  - `loadStreamListForNewSession()`：GET /api/proactive-chat/streams，填充聊天流选择器，优先显示实际名称
  - `confirmCreateSession()`：POST /api/proactive-chat/agent/chat/sessions，创建成功后刷新列表并选中
  - `hideNewSessionDialog()`：隐藏新建会话对话框
  - `clearAgentChatSession()`：确认后 POST /api/proactive-chat/agent/chat/sessions/{id}/clear，清除成功后重置界面
  - 涉及文件：`webui_static/app.js`
  - 依赖任务：#256
  - 验收标准：会话列表正确渲染；选中会话显示对话区域；新建会话对话框可选择聊天流；清除会话后列表更新

### #258 app.js 新增消息发送和展示逻辑

- [ ] 在 `app.js` 中新增消息发送、消息渲染和 HTML 转义函数
  - `sendAgentChatMessage()`：获取输入内容 → 添加用户消息到界面 → 禁用输入框 + 显示"思考中..." → POST /api/proactive-chat/agent/chat/send → 移除思考状态 → 成功时添加助手回复 → 失败时显示错误 → finally 恢复输入框
  - `renderChatMessages()`：遍历 `currentChatMessages`，按 role 生成不同气泡（user 靠右、assistant 靠左、system 居中），每条显示时间，自动滚动到底部
  - `escapeHtml(text)`：HTML 转义，防止 XSS
  - Enter 键发送（textarea onkeydown 中 Shift+Enter 换行，Enter 发送）
  - 涉及文件：`webui_static/app.js`
  - 依赖任务：#257
  - 验收标准：输入消息 → 发送 → 显示用户气泡（右侧）+ 思考中 → 收到响应后显示助手气泡（左侧）；Enter 发送，Shift+Enter 换行；网络错误显示系统提示

---

## 5. 测试

### #259 时间感知模块单元测试

- [ ] 在 `tests/test_time_awareness.py` 中编写单元测试
  - 测试 `TimePeriod` 枚举 7 个值
  - 测试 `TimeAwarenessInfo` 数据类实例化和默认值
  - 测试 `classify_time_period()` 各时间段映射（0→LATE_NIGHT, 7→EARLY_MORNING, 10→MORNING_WORK, 13→LUNCH_BREAK, 15→AFTERNOON_WORK, 20→EVENING_LEISURE, 23→NIGHT）
  - 测试 `classify_time_period()` 使用自定义配置边界
  - 测试 `get_decision_tendency()` 各时间段倾向文本
  - 测试 `get_decision_tendency()` 周末追加后缀
  - 测试 `_format_interval()` 各时间间隔格式化（秒、分钟、小时+分钟）
  - 测试 `get_time_awareness_info()` 正常场景
  - 测试 `get_time_awareness_info()` 冷却无记录时 interval 为"无记录"
  - 测试 `get_time_awareness_info()` 消息时间戳为毫秒时正确转换
  - 测试 `format_for_prompt()` 输出格式
  - 测试系统时间不可用时返回 None
  - 涉及文件：`tests/test_time_awareness.py`（新增）
  - 依赖任务：#245
  - 验收标准：所有测试通过；覆盖 7 个时间段分类、决策倾向、间隔格式化、异常降级

### #260 聊天流上下文注入修复单元测试

- [ ] 在 `tests/test_agent_chat.py` 中扩展测试
  - 测试 `_inject_stream_context()` 正常注入：指定 stream_id → 调用 `_get_recent_messages` → 消息格式化后作为 system 消息 insert(0)
  - 测试 `_inject_stream_context()` stream_id 为空时跳过注入
  - 测试 `_inject_stream_context()` 近期消息为空列表时跳过注入
  - 测试 `_inject_stream_context()` 消息获取异常时跳过注入，不阻塞会话创建
  - 测试 `_get_recent_messages()` 正常返回消息列表
  - 测试 `_get_recent_messages()` message_api 不可用时返回空列表
  - 测试 `_get_recent_messages()` 调用异常时返回空列表
  - 测试 `_format_stream_context()` 正常格式化
  - 测试 `_format_stream_context()` 消息缺少 sender_name 时使用"未知"
  - 测试 `_format_stream_context()` 内容超过 100 字符时截断
  - 测试 `_format_stream_context()` 空内容消息跳过
  - 涉及文件：`tests/test_agent_chat.py`（扩展）
  - 依赖任务：#250
  - 验收标准：所有测试通过；覆盖正常注入、空消息、异常降级、格式化边界

### #261 WebUI Agent Chat API 开关检查单元测试

- [ ] 在 `tests/test_webui.py` 中扩展测试
  - 测试 `_check_agent_chat_enabled()` 未启用时返回 403 + "智能体对话服务未启用"
  - 测试 `_check_agent_chat_enabled()` 已启用时返回 None
  - 测试 GET /agent/chat/sessions 未启用时返回 403
  - 测试 POST /agent/chat/sessions 未启用时返回 403
  - 测试 POST /agent/chat/send 未启用时返回 403
  - 测试 POST /agent/chat/sessions/{id}/clear 未启用时返回 403
  - 测试已启用时 4 个 API 正常处理
  - 涉及文件：`tests/test_webui.py`（扩展）
  - 依赖任务：#253
  - 验收标准：所有测试通过；覆盖 4 个 API 的开关检查和正常处理

### #262 配置扩展单元测试

- [ ] 在 `tests/test_config.py` 中扩展测试
  - 测试 `AgentOptimizationConfig` 新增 4 个时间边界字段默认值
  - 测试 4 个字段的 ge/le 约束
  - 测试 `ProactiveChatConfig.agent_optimization` 包含新字段
  - 测试向后兼容性（v3.2 配置加载后新字段使用默认值）
  - 测试 config_version 升级到 3.3.0
  - 涉及文件：`tests/test_config.py`（扩展）
  - 依赖任务：#242
  - 验收标准：所有测试通过；新字段默认值正确；v3.2 配置向后兼容

### #263 prompts 扩展单元测试

- [ ] 在 `tests/test_prompts.py` 中扩展测试
  - 测试 `TIME_AWARENESS_TEMPLATE` 常量内容和占位符
  - 测试 `TIME_AWARENESS_TEMPLATE.format()` 填充
  - 涉及文件：`tests/test_prompts.py`（扩展）
  - 依赖任务：#246
  - 验收标准：所有测试通过；模板常量包含正确的占位符

### #264 AgentCore 集成单元测试

- [ ] 在 `tests/test_agent.py` 中扩展测试
  - 测试 `PerceptionData` 新增 `_time_awareness_text` 字段默认值
  - 测试 `AgentCore.__init__` 新增 `_time_awareness` 字段默认为 None
  - 测试 `perceive()` 时间感知集成：TimeAwareness 可用时 `_time_awareness_text` 非空
  - 测试 `perceive()` 时间感知异常时不阻塞决策循环
  - 测试 `_react_loop()` 用户提示词开头包含时间感知文本
  - 测试 `reason()` 用户提示词开头包含时间感知文本
  - 测试 TimeAwareness 为 None 时用户提示词无时间感知段落
  - 涉及文件：`tests/test_agent.py`（扩展）
  - 依赖任务：#247
  - 验收标准：所有测试通过；覆盖时间感知注入到 perceive、_react_loop、reason；异常降级正常

### #265 plugin.py 集成单元测试

- [ ] 在 `tests/test_plugin.py` 中扩展测试
  - 测试 `on_load` 中 TimeAwareness 初始化和注入到 AgentCore
  - 测试 `on_load` 中 message_api 传入到 AgentChatService
  - 测试 ctx.message 不可用时 message_api 为 None
  - 涉及文件：`tests/test_plugin.py`（扩展）
  - 依赖任务：#248、#252
  - 验收标准：所有测试通过；TimeAwareness 和 message_api 正确初始化和注入

### #266 WebUI 前端功能测试

- [ ] 手动验证 WebUI 智能体对话 Tab 的前端功能
  - 验证 Tab 栏显示三个 Tab，第三个为"智能体对话"
  - 验证 agent_chat_enabled=false 时点击 Tab 显示未启用提示
  - 验证 agent_chat_enabled=true 时显示智能体对话界面
  - 验证会话列表渲染和选中高亮
  - 验证新建会话对话框和聊天流选择器
  - 验证消息发送和助手回复展示
  - 验证思考中状态和输入框禁用
  - 验证清除会话功能
  - 验证响应式布局（窄屏纵向排列）
  - 验证错误提示显示（API 返回错误、网络错误）
  - 涉及文件：`webui_static/index.html`、`webui_static/app.js`、`webui_static/style.css`
  - 依赖任务：#258
  - 验收标准：所有前端功能正常；Tab 切换流畅；消息收发正确；错误提示友好

### #267 向后兼容集成测试

- [ ] 编写向后兼容集成测试，验证 v3.3 新功能不影响 v3.2 行为
  - 所有 v3.3 新功能关闭/默认配置时，决策循环行为与 v3.2 一致
  - TimeAwareness 为 None 时用户提示词无时间感知段落
  - agent_chat_enabled=False 时 Agent Chat API 返回 403
  - _inject_stream_context 在 message_api 不可用时跳过注入
  - 配置从 v3.2 升级到 v3.3 后新字段使用默认值
  - 涉及文件：`tests/test_integration_compat.py`（扩展）
  - 依赖任务：#262、#264、#265
  - 验收标准：所有测试通过；v3.3 默认配置下决策循环与 v3.2 行为一致