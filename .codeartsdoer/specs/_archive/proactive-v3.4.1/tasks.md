# proactive-chat v3.4.1 编码任务

> 任务编号从 312 开始（v3.4 任务编号为 284-311，已完成）

---

## 1. 配置扩展

### #312 AgentChatConfig 新增 v3.4.1 持久化配置项

- [ ] 在 `config.py` 的 `AgentChatConfig` 类中新增 4 个持久化相关配置项
  - `session_persistence_enabled: bool = Field(default=True, description="是否启用会话持久化（容器重启后保留会话数据）")`
  - `max_persisted_sessions: int = Field(default=20, ge=1, le=100, description="最大持久化会话数")`
  - `max_persisted_messages_per_session: int = Field(default=200, ge=10, le=1000, description="每个会话最大持久化消息数")`
  - `session_retention_days: int = Field(default=30, ge=0, le=365, description="会话保留天数，0 表示不清理")`
  - 涉及文件：`config.py`
  - 依赖任务：无
  - 验收标准：`AgentChatConfig` 包含上述 4 个新字段，默认值和范围校验正确；WebUI 配置页面自动显示新字段

### #313 配置版本升级到 3.4.1

- [ ] 将 `PluginSectionConfig.config_version` 默认值从 `"3.4.0"` 升级到 `"3.4.1"`
  - 涉及文件：`config.py`
  - 依赖任务：#312
  - 验收标准：`PluginSectionConfig.config_version` 默认值为 `"3.4.1"`

---

## 2. 持久化模块

### #314 SessionMetadata 数据类定义

- [ ] 在 `session_persistence.py` 中定义核心数据类
  - `SessionMetadata(dataclass)`：session_id、created_at、last_active_at、stream_context_id、message_count
  - 字段默认值：session_id=""、created_at=0.0、last_active_at=0.0、stream_context_id=""、message_count=0
  - 涉及文件：`session_persistence.py`（新建）
  - 依赖任务：无
  - 验收标准：`SessionMetadata` 可正常实例化，字段与设计文档一致；可正确序列化为 JSON 和从 JSON 反序列化

### #315 SessionPersistence 写入操作

- [ ] 实现 `SessionPersistence` 类的初始化和写入方法
  - `__init__(self, data_dir: Path)`：创建 `{data_dir}/agent_chat_sessions/` 目录（`mkdir(parents=True, exist_ok=True)`）
  - `save_session_metadata(self, metadata: SessionMetadata) -> None`：将 `metadata` 序列化为 JSON 追加写入 `sessions_index.jsonl`，写入失败记录错误日志不抛异常
  - `save_message(self, session_id: str, role: str, content: str, timestamp: float) -> None`：将消息序列化为 JSON 追加写入 `messages_{session_id}.jsonl`，写入失败记录错误日志不抛异常
  - 涉及文件：`session_persistence.py`
  - 依赖任务：#314
  - 验收标准：调用 `save_session_metadata()` 后 `sessions_index.jsonl` 新增一行合法 JSON；调用 `save_message()` 后对应消息文件新增一行；写入失败不抛异常

### #316 SessionPersistence 读取操作

- [ ] 实现 `SessionPersistence` 类的读取方法
  - `load_all_sessions(self) -> list[SessionMetadata]`：逐行读取 `sessions_index.jsonl`，跳过解析失败的行并记录警告日志；同一 `session_id` 以最后一行为准（去重）；按 `last_active_at` 降序排序；返回 `SessionMetadata` 列表
  - `load_messages(self, session_id: str, max_messages: int = 200) -> list[dict]`：逐行读取 `messages_{session_id}.jsonl`，跳过解析失败的行并记录警告日志；按 `timestamp + role` 去重（同一组合只保留一条）；截取最近 `max_messages` 条；返回字典列表
  - 文件不存在时返回空列表，不抛异常
  - 涉及文件：`session_persistence.py`
  - 依赖任务：#314
  - 验收标准：`load_all_sessions()` 正确去重并按时间降序返回；`load_messages()` 正确截取最近 N 条；文件不存在时返回空列表；损坏行被跳过并记录警告

### #317 SessionPersistence 清理操作

- [ ] 实现 `SessionPersistence` 类的清理和删除方法
  - `delete_session(self, session_id: str) -> None`：删除 `messages_{session_id}.jsonl` 文件；重建 `sessions_index.jsonl`（排除该 session_id 的所有行），使用原子写入（先写 `.tmp` 再 `replace`）
  - `cleanup_expired(self, retention_days: int) -> int`：遍历所有会话元数据，删除 `last_active_at` 超过 `retention_days` 天的会话及其消息文件；重建 `sessions_index.jsonl`；返回清理数量；`retention_days` 为 0 时返回 0
  - `cleanup_oldest_sessions(self, max_sessions: int) -> int`：当会话数超过 `max_sessions` 时，删除最久未活跃的会话及其消息文件；重建 `sessions_index.jsonl`；返回淘汰数量
  - 涉及文件：`session_persistence.py`
  - 依赖任务：#316
  - 验收标准：`delete_session()` 后消息文件被删除、索引文件中无该会话记录；`cleanup_expired()` 正确清理过期会话；`cleanup_oldest_sessions()` 保留最近 N 个会话；原子写入确保数据安全

---

## 3. 后端集成

### #318 AgentChatService 持久化初始化

- [ ] 在 `AgentChatService` 中新增持久化相关属性和设置方法
  - `__init__` 新增属性：`self._session_persistence: SessionPersistence | None = None`、`self._persistence_enabled: bool = False`、`self._max_persisted_sessions: int = 20`、`self._max_persisted_messages: int = 200`、`self._retention_days: int = 30`
  - `set_session_persistence(self, persistence: SessionPersistence, enabled: bool, max_sessions: int = 20, max_messages_per_session: int = 200, retention_days: int = 30) -> None`：设置持久化服务实例和参数
  - 涉及文件：`agent_chat.py`
  - 依赖任务：#314
  - 验收标准：调用 `set_session_persistence()` 后，`_persistence_enabled` 为 True，持久化参数正确设置

### #319 AgentChatService 启动时数据恢复

- [ ] 实现 `AgentChatService.restore_sessions()` 方法
  - 仅在 `_persistence_enabled` 为 True 且 `_session_persistence` 不为 None 时执行
  - 步骤 1：若 `_retention_days > 0`，调用 `cleanup_expired()` 清理过期会话
  - 步骤 2：调用 `load_all_sessions()` 加载会话元数据
  - 步骤 3：若会话数超过 `_max_persisted_sessions`，调用 `cleanup_oldest_sessions()` 淘汰旧会话
  - 步骤 4：对每个会话调用 `load_messages()` 加载消息，重建 `AgentChatSession` 对象并填充到 `self._sessions`
  - 恢复后记录日志：`[proactive-chat] 已恢复 N 个会话`
  - 涉及文件：`agent_chat.py`
  - 依赖任务：#316、#318
  - 验收标准：持久化启用时，重启后之前的会话和消息全部恢复；过期会话被清理；超出数量限制的旧会话被淘汰

### #320 AgentChatService 消息写入持久化集成

- [ ] 在 `AgentChatService` 的消息收发流程中集成持久化写入
  - `create_session()`：会话创建后，若持久化启用，调用 `save_session_metadata()` 写入元数据；最大会话数根据持久化状态调整（启用时用 `_max_persisted_sessions`，否则用 5）
  - `send_message()`：用户消息发送后调用 `save_message()`；智能体回复后调用 `save_message()`；每次消息收发后调用 `save_session_metadata()` 更新元数据
  - `clear_session()`：会话清除后调用 `delete_session()` 删除持久化文件
  - `_inject_stream_context()`：系统消息注入后调用 `save_message()` 持久化系统消息
  - 所有持久化调用前检查 `self._persistence_enabled and self._session_persistence`
  - 涉及文件：`agent_chat.py`
  - 依赖任务：#315、#317、#318
  - 验收标准：发送消息后 JSONL 文件新增记录；清除会话后持久化文件被删除；持久化未启用时行为与 v3.4 一致

### #321 plugin.py 启动流程集成

- [ ] 在 `plugin.py` 的 `on_load()` 中集成 SessionPersistence 初始化和数据恢复
  - 导入 `from .session_persistence import SessionPersistence`
  - 在 `AgentChatService` 实例化后，读取配置 `config.agent_chat.session_persistence_enabled`
  - 若启用：创建 `SessionPersistence(data_dir=_DATA_DIR)` 实例，调用 `set_session_persistence()` 注入配置参数，调用 `await restore_sessions()` 恢复数据
  - 涉及文件：`plugin.py`
  - 依赖任务：#319、#320、#312
  - 验收标准：插件启动后，若持久化启用，历史会话从 JSONL 文件恢复；若未启用，行为与 v3.4 一致

### #322 webui.py sessions 端点扩展

- [ ] 扩展 sessions 端点返回数据，新增最新消息预览和格式化时间
  - 修改 `_handle_agent_chat_sessions()`：遍历每个会话，查找最新一条非系统消息（`role in ("user", "assistant")`），生成预览文本（智能体前缀"🤖: "，用户前缀"我: "，最多 20 字符超出截断加"..."，无消息显示"暂无消息"）
  - 新增 `_format_session_time(last_active_at: float, now: float) -> str` 静态方法：当天显示"HH:mm"，昨天显示"昨天"，7 天内显示"X天前"，更早显示"yyyy/MM/dd"
  - 新增 `_get_stream_display_name(stream_context_id: str) -> str` 方法：通过 chat_manager 解析聊天流名称
  - 返回数据新增字段：`last_message_preview`、`last_active_display`、`stream_display_name`
  - 涉及文件：`webui.py`
  - 依赖任务：无（可与持久化模块并行开发）
  - 验收标准：sessions 端点返回数据包含 `last_message_preview`、`last_active_display`、`stream_display_name` 字段；预览文本格式正确；时间显示规则符合设计

---

## 4. 前端UI改进

### #323 index.html 引入 marked.js CDN

- [ ] 在 `index.html` 的 `<head>` 中添加 marked.js CDN 引用
  - 添加 `<script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>`
  - 放在现有 `<style>` 标签之前
  - 涉及文件：`webui_static/index.html`
  - 依赖任务：无
  - 验收标准：页面加载后 `typeof marked !== 'undefined'`；CDN 加载失败时不影响页面其他功能

### #324 style.css 即时通讯风格样式

- [ ] 新增即时通讯风格相关的 CSS 样式
  - 消息行容器：`.message-row`（display:flex; align-items:flex-start; gap:8px; max-width:85%）、`.message-row-user`（align-self:flex-end; flex-direction:row-reverse）、`.message-row-assistant`（align-self:flex-start）、`.message-row-system`（align-self:center; max-width:90%）
  - 头像：`.avatar`（36×36px 圆形）、`.avatar-user`（紫色背景 var(--accent)、白色文字、font-weight:600）、`.avatar-bot`（深色背景 var(--border)、🤖 emoji）
  - 气泡内容：`.bubble-content`（word-break:break-word; line-height:1.6）、`.bubble-time`（font-size:0.7rem; opacity:0.5; margin-top:4px; text-align:right）
  - 时间分隔线：`.time-divider`（flex 居中）、`.time-divider-text`（font-size:0.75rem; color:var(--text2)）
  - 系统消息：`.system-message`（font-size:0.8rem; color:var(--text2); text-align:center）
  - 优化现有气泡样式：`.user-bubble` 增加右下角小圆角（border-bottom-right-radius:4px）、`.assistant-bubble` 增加左下角小圆角（border-bottom-left-radius:4px）
  - 涉及文件：`webui_static/style.css`
  - 依赖任务：无
  - 验收标准：新增样式类可被 JS 正确引用；头像 36×36px 圆形；气泡带时间戳；时间分隔线居中显示

### #325 app.js 消息渲染重构

- [ ] 重构 `renderChatMessages()` 函数为即时通讯风格渲染
  - 新增 `shouldShowTimeDivider(prevTimestamp, currentTimestamp)` 函数：5 分钟内不重复显示时间分隔线，第一条消息显示时间
  - 新增 `formatTimeDividerText(timestamp)` 函数：当天"HH:mm"、昨天"昨天 HH:mm"、更早"yyyy/MM/dd HH:mm"
  - 新增 `formatBubbleTime(timestamp)` 函数：返回"HH:mm"格式
  - 新增 `getUserInitial()` 函数：返回"我"作为默认用户首字母
  - 重构 `renderChatMessages()`：
    - 遍历消息时先判断是否需要时间分隔线
    - 系统消息：`.message-row-system` + `.system-message`（纯文本转义）
    - 用户消息：`.message-row-user` + `.user-bubble`（纯文本转义 + 时间戳）+ `.avatar-user`
    - 智能体消息：`.message-row-assistant` + `.avatar-bot` + `.assistant-bubble`（Markdown 渲染 + 时间戳）
  - 新增 `escapeHtml(text)` 函数：转义 `<>&"` 防止 XSS
  - 涉及文件：`webui_static/app.js`
  - 依赖任务：#324
  - 验收标准：用户消息靠右显示带首字母头像；智能体消息靠左显示带机器人头像；5 分钟间隔的消息之间显示时间分隔线；每条消息气泡底部显示"HH:mm"时间；系统消息居中灰色小字

### #326 style.css 会话列表两行布局样式

- [ ] 新增会话列表两行布局的 CSS 样式
  - `.chat-session-item .session-row-1`：display:flex; justify-content:space-between; align-items:center
  - `.chat-session-item .session-name`：font-size:0.85rem; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; flex:1; margin-right:8px
  - `.chat-session-item .session-time`：font-size:0.7rem; color:var(--text2); flex-shrink:0
  - `.chat-session-item .session-row-2`：font-size:0.75rem; color:var(--text2); margin-top:4px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap
  - 涉及文件：`webui_static/style.css`
  - 依赖任务：无
  - 验收标准：会话项显示为两行布局；第一行名称和时间左右对齐；第二行预览文本单行截断

### #327 app.js 会话列表渲染改造

- [ ] 改造 `renderSessionList()` 函数为两行布局
  - 修改 `renderSessionList()`：每个会话项使用 `.session-row-1`（名称 + 时间）和 `.session-row-2`（最新消息预览）两行布局
  - 名称来源：`s.stream_display_name || s.session_id.substring(0, 8) + '...'`
  - 时间来源：`s.last_active_display || ''`
  - 预览来源：`s.last_message_preview || '暂无消息'`
  - 涉及文件：`webui_static/app.js`
  - 依赖任务：#322、#326
  - 验收标准：会话列表项显示两行布局；第一行显示聊天流名称和格式化时间；第二行显示最新消息预览

---

## 5. 前端渲染增强

### #328 style.css Markdown 渲染与长消息折叠样式

- [ ] 新增 Markdown 渲染和长消息折叠的 CSS 样式
  - 代码块：`.bubble-content pre`（background:#1e1e2e; border-radius:8px; padding:12px; overflow-x:auto; position:relative）
  - 行内代码：`.bubble-content :not(pre) > code`（background:rgba(108,92,231,0.15); padding:2px 6px; border-radius:4px）
  - 代码块内代码：`.bubble-content pre code`（color:#e0e0e0; font-family:Consolas,Monaco,monospace）
  - 语言标签：`.code-lang-label`（position:absolute; top:4px; left:8px; font-size:0.7rem; color:var(--text2)）
  - 复制按钮：`.code-copy-btn`（position:absolute; top:4px; right:8px; opacity:0; transition:opacity 0.2s）、`pre:hover .code-copy-btn`（opacity:1）
  - 链接：`.bubble-content a`（color:var(--accent2); text-decoration:none）、`.bubble-content a:hover`（text-decoration:underline）
  - 列表：`.bubble-content ul, .bubble-content ol`（padding-left:20px; margin:4px 0）
  - 长消息折叠：`.bubble-content.collapsed`（max-height:300px; overflow:hidden; position:relative）、`.bubble-content.collapsed::after`（渐变遮罩）、`.expand-btn`（font-size:0.8rem; color:var(--accent2); cursor:pointer）
  - 涉及文件：`webui_static/style.css`
  - 依赖任务：无
  - 验收标准：代码块深色背景圆角；行内代码紫色背景；复制按钮悬停显示；链接紫色可点击；长消息默认折叠带渐变遮罩

### #329 app.js Markdown 渲染、代码块复制与长消息折叠

- [ ] 实现 Markdown 渲染、代码块复制和长消息折叠功能
  - 新增 `renderMarkdown(text)` 函数：使用 `marked.parse()` 渲染，marked 未加载或解析失败时降级为 `escapeHtml(text)`；配置 marked 选项（breaks:true, gfm:true, headerIds:false, mangle:false）
  - 新增 `addCodeBlockFeatures(container)` 函数：遍历 `container.querySelectorAll('pre')`，为每个代码块添加语言标签（从 `code.className` 提取 `language-xxx`）和复制按钮（点击复制代码内容，显示"已复制"2 秒后恢复，降级使用 `execCommand('copy')`）
  - 新增 `applyMessageCollapse(bubbleContent)` 函数：文本超过 500 字符时添加 `.collapsed` 类和"展开全文"/"收起"切换按钮
  - 修改 `renderChatMessages()` 后处理：对每个 `.assistant-bubble .bubble-content` 调用 `addCodeBlockFeatures()` 和 `applyMessageCollapse()`
  - 涉及文件：`webui_static/app.js`
  - 依赖任务：#323、#325、#328
  - 验收标准：智能体回复含代码块 → 正确渲染为深色背景代码块，右上角显示复制按钮；点击复制按钮 → 代码复制到剪贴板；回复含链接 → 可点击跳转新标签页；消息超过 500 字符 → 默认折叠，点击"展开全文"可展开

---

## 6. 验证

### #330 配置扩展验证

- [ ] 验证 v3.4.1 新增配置项功能正常
  - 验证 WebUI 配置页面显示 `agent_chat` 分组下的 4 个新字段
  - 验证 `session_persistence_enabled` 默认为 True
  - 验证 `max_persisted_sessions` 默认为 20，范围 1-100
  - 验证 `max_persisted_messages_per_session` 默认为 200，范围 10-1000
  - 验证 `session_retention_days` 默认为 30，范围 0-365
  - 验证配置版本号为 3.4.1
  - 验证配置保存后新字段值正确持久化
  - 涉及文件：`config.py`
  - 依赖任务：#312、#313
  - 验收标准：所有新增配置项在 WebUI 中可见、可编辑、可保存；范围校验生效

### #331 持久化模块功能验证

- [ ] 验证 SessionPersistence 核心功能
  - 验证 `save_session_metadata()` 追加写入 `sessions_index.jsonl`
  - 验证 `save_message()` 追加写入 `messages_*.jsonl`
  - 验证 `load_all_sessions()` 正确去重（同一 session_id 以最后一行为准）和排序
  - 验证 `load_messages()` 正确截取最近 N 条消息
  - 验证 `delete_session()` 删除消息文件并重建索引
  - 验证 `cleanup_expired()` 清理过期会话
  - 验证 `cleanup_oldest_sessions()` 淘汰最旧会话
  - 验证损坏行被跳过并记录警告日志
  - 验证文件不存在时返回空列表
  - 涉及文件：`session_persistence.py`
  - 依赖任务：#314、#315、#316、#317
  - 验收标准：SessionPersistence 所有核心功能正常；异常情况不崩溃

### #332 后端集成验证

- [ ] 验证 AgentChatService 持久化集成功能
  - 验证 `set_session_persistence()` 正确设置持久化参数
  - 验证 `restore_sessions()` 从 JSONL 文件恢复会话和消息
  - 验证 `create_session()` 创建会话后写入 `sessions_index.jsonl`
  - 验证 `send_message()` 发送消息后写入 `messages_*.jsonl` 并更新元数据
  - 验证 `clear_session()` 清除会话后删除持久化文件
  - 验证系统消息注入后持久化
  - 验证 `session_persistence_enabled=False` 时行为与 v3.4 一致（纯内存存储）
  - 验证会话数量限制：持久化启用时为 20，未启用时为 5
  - 涉及文件：`agent_chat.py`、`plugin.py`
  - 依赖任务：#318、#319、#320、#321
  - 验收标准：消息发送后 JSONL 文件有记录；容器重启后会话恢复；持久化未启用时行为与 v3.4 一致

### #333 前端UI改进验证

- [ ] 验证即时通讯风格聊天界面和会话列表改进
  - 验证消息气泡布局：用户消息靠右+首字母头像，智能体消息靠左+机器人头像
  - 验证时间分组：5 分钟间隔的消息之间显示时间分隔线；连续快速发送无时间分隔线
  - 验证消息内时间戳：每条消息气泡底部显示"HH:mm"格式时间
  - 验证系统消息居中灰色小字显示
  - 验证会话列表两行布局：名称+时间在第一行，预览在第二行
  - 验证最新消息预览格式（智能体前缀"🤖: "，用户前缀"我: "，20 字符截断）
  - 验证会话时间格式化（当天"HH:mm"、昨天"昨天"、7天内"X天前"、更早"yyyy/MM/dd"）
  - 验证空会话显示"暂无消息"
  - 涉及文件：`webui_static/style.css`、`webui_static/app.js`、`webui_static/index.html`、`webui.py`
  - 依赖任务：#324、#325、#326、#327
  - 验收标准：聊天界面呈现即时通讯风格；会话列表显示预览和格式化时间

### #334 前端渲染增强验证

- [ ] 验证 Markdown 渲染、代码块复制和长消息折叠功能
  - 验证智能体回复含代码块 → 正确渲染为深色背景代码块
  - 验证代码块左上角显示语言标签
  - 验证代码块复制按钮：悬停显示，点击复制，显示"已复制"
  - 验证智能体回复含链接 → 可点击跳转新标签页
  - 验证智能体回复含粗体/斜体/列表 → 正确渲染
  - 验证用户消息不渲染 Markdown（`**粗体**` 显示为纯文本）
  - 验证消息超过 500 字符 → 默认折叠，点击"展开全文"可展开，点击"收起"可折叠
  - 验证 XSS 防护：输入 `<script>alert(1)</script>` → 不执行脚本
  - 验证 marked.js 加载失败时降级为纯文本
  - 涉及文件：`webui_static/app.js`、`webui_static/style.css`、`webui_static/index.html`
  - 依赖任务：#323、#328、#329
  - 验收标准：Markdown 渲染正确；代码块复制功能正常；长消息折叠/展开正常；XSS 防护生效

### #335 端到端集成验证

- [ ] 验证 v3.4.1 完整功能链路
  - 验证完整流程：创建会话 → 发送消息 → JSONL 文件写入 → 清除会话 → 文件删除
  - 验证完整流程：创建会话 → 发送多条消息 → 容器重启 → 会话和消息恢复
  - 验证完整流程：发送消息 → 智能体回复含 Markdown → 即时通讯风格渲染（气泡+头像+时间+Markdown）
  - 验证完整流程：多个会话 → 会话列表显示预览和时间 → 切换会话 → 消息正确加载
  - 验证 `session_persistence_enabled=False` 时行为与 v3.4 一致
  - 验证过期会话清理：设置保留 1 天 → 2 天前的会话被清理
  - 验证会话数量限制：创建超过 20 个会话 → 最旧的被淘汰
  - 涉及文件：所有修改文件
  - 依赖任务：#330、#331、#332、#333、#334
  - 验收标准：端到端功能链路完整；持久化启用时数据不丢失；持久化未启用时行为与 v3.4 一致