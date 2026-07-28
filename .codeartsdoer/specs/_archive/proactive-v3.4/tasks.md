# proactive-chat v3.4 编码任务

> 任务编号从 284 开始（v3.3.1 任务编号为 268-283，已完成）

---

## 1. 配置扩展

### #284 AgentChatConfig 新增 v3.4 配置项

- [ ] 在 `config.py` 的 `AgentChatConfig` 类中新增 5 个配置项
  - `file_edit_enabled: bool = Field(default=False, description="是否启用智能体文件编辑能力")`
  - `editable_files: list[str] = Field(default_factory=lambda: ["user_preferences.yaml"], description="可编辑文件白名单（相对于插件数据目录的文件路径）")`
  - `edit_backup_enabled: bool = Field(default=True, description="是否启用编辑前备份")`
  - `auto_preference_enabled: bool = Field(default=True, description="是否启用智能体主动偏好识别")`
  - `preference_summary_token_limit: int = Field(default=500, ge=100, le=2000, description="偏好摘要注入系统提示词的最大 Token 数")`
  - 涉及文件：`config.py`
  - 依赖任务：无
  - 验收标准：`AgentChatConfig` 包含上述 5 个新字段，默认值正确；WebUI 配置页面自动显示新字段

### #285 配置版本升级到 3.4.0

- [ ] 将 `PluginSectionConfig.config_version` 默认值从 `"3.3.0"` 升级到 `"3.4.0"`
  - 涉及文件：`config.py`
  - 依赖任务：#284
  - 验收标准：`PluginSectionConfig.config_version` 默认值为 `"3.4.0"`

---

## 2. 文件编辑器

### #286 FileEditor 数据类定义

- [ ] 在 `file_editor.py` 中定义核心数据类
  - `EditAction(str, Enum)`：ADD / REMOVE / UPDATE
  - `EditCategory(str, Enum)`：LIKES / DISLIKES / HABITS / RULES
  - `EditSource(str, Enum)`：EXPLICIT / AUTO
  - `EditIntent(dataclass)`：action, category, value, source, old_value
  - `EditResult(dataclass)`：success, message, category, value, action, is_duplicate
  - `AuditLogEntry(dataclass)`：timestamp, session_id, file_path, action, category, value, old_value, source
  - 涉及文件：`file_editor.py`（新建）
  - 依赖任务：无
  - 验收标准：所有数据类可正常实例化，Enum 值与设计文档一致

### #287 FileEditor 核心类实现

- [ ] 实现 `FileEditor` 类的核心方法
  - `__init__(self, data_dir: Path, editable_files: list[str] | None, backup_enabled: bool)`：初始化数据目录、白名单集合、备份开关
  - `validate_path(self, relative_path: str) -> bool`：路径守卫，标准化路径后校验是否在白名单中，防止 `..` 路径遍历
  - `read_file(self, relative_path: str) -> dict | None`：读取 YAML 文件，仅返回可编辑区域内的数据
  - `execute_edit(self, relative_path: str, intent: EditIntent, session_id: str) -> EditResult`：执行编辑操作（读取 → 去重检查 → 写入 → 审计日志）
  - 涉及文件：`file_editor.py`
  - 依赖任务：#286
  - 验收标准：`validate_path` 正确拦截非法路径；`read_file` 返回可编辑区域数据；`execute_edit` 完成完整的编辑流程

### #288 FileEditor 编辑区域标记处理

- [ ] 实现编辑区域标记的读取和写入方法
  - `_ensure_file_exists(self, relative_path: str) -> None`：文件不存在时创建默认内容（含 editable start/end 标记和空分类）
  - `_read_editable_region(self, relative_path: str) -> tuple[dict, str, str]`：解析文件中的标记区域，返回 (可编辑区域 YAML 数据, 标记前内容, 标记后内容)；标记缺失时将整个文件视为可编辑区域并记录警告日志
  - `_write_editable_region(self, relative_path: str, data: dict, pre_marker: str, post_marker: str) -> None`：原子写入（先写临时文件 `.tmp`，成功后 `replace` 替换原文件）；备份开关启用时先复制 `.bak` 备份
  - 涉及文件：`file_editor.py`
  - 依赖任务：#287
  - 验收标准：文件不存在时自动创建含标记的默认文件；标记区域内的内容可正确读写；标记区域外的内容不被修改；写入失败时原文件不损坏

### #289 FileEditor 去重检查与审计日志

- [ ] 实现去重检查和审计日志记录
  - `_check_duplicate(self, data: dict, intent: EditIntent) -> bool`：简单字符串精确匹配去重（忽略大小写和首尾空格）
  - `_record_audit(self, relative_path: str, intent: EditIntent, session_id: str) -> None`：将审计条目以 JSONL 格式追加到 `edit_audit.jsonl`，写入失败仅记录警告日志不抛异常
  - 涉及文件：`file_editor.py`
  - 依赖任务：#287
  - 验收标准：重复偏好不写入文件；审计日志正确记录每次编辑操作（含 source 字段区分显式/自动）

---

## 3. 提示词重写

### #290 重写 AGENT_CHAT_SYSTEM_PROMPT

- [ ] 将 `AGENT_CHAT_SYSTEM_PROMPT` 从"友好的聊天助手"重写为"指令执行助手"
  - 核心职责说明：执行指令 + 主动识别偏好 + 反馈结果
  - 指令类型说明：记忆指令、查询指令、行为指令、通用对话
  - 偏好识别说明：喜好表达 → likes、厌恶表达 → dislikes、习惯描述 → habits、行为倾向 → rules；排除临时性陈述、客观事实、他人偏好
  - 文件编辑说明：EDIT_INTENT JSON 格式及字段说明（action/category/value/source/old_value）
  - 回复规则：简洁反馈执行结果、角色信息仅影响语气、闲聊时引导指令模式、禁止无目的角色扮演闲聊
  - 保留 `{personality_section}` 和 `{custom_prompt_section}` 占位符
  - 涉及文件：`prompts.py`
  - 依赖任务：无
  - 验收标准：新系统提示词明确"指令执行助手"定位；包含 EDIT_INTENT 输出格式说明；包含偏好识别规则；保留角色信息占位符

### #291 扩展 build_chat_system_prompt() 支持偏好摘要注入

- [ ] 修改 `build_chat_system_prompt()` 函数，新增 `preference_summary` 参数
  - 函数签名新增 `preference_summary: str = ""`
  - 当 `preference_summary` 非空时，在系统提示词末尾追加 `f"\n\n{preference_summary}"`
  - 涉及文件：`prompts.py`
  - 依赖任务：#290
  - 验收标准：传入偏好摘要 → 系统提示词末尾包含偏好摘要段；不传入 → 系统提示词与无摘要时一致

---

## 4. 智能体对话服务扩展

### #292 编辑意图解析函数

- [ ] 在 `agent_chat.py` 中新增 `parse_edit_intent()` 函数
  - 使用 `re.compile(r'EDIT_INTENT:\s*(\{.*\})\s*$', re.MULTILINE)` 匹配 LLM 回复末尾的编辑意图行
  - 解析 JSON 并校验必填字段（action/category/value/source）
  - 校验 action ∈ {add, remove, update}、category ∈ {likes, dislikes, habits, rules}、source ∈ {explicit, auto}
  - 校验失败时记录警告日志，返回 `(None, 原回复文本)`
  - 从回复中移除 EDIT_INTENT 行，返回 `(编辑意图字典, 清理后的回复文本)`
  - 涉及文件：`agent_chat.py`
  - 依赖任务：#290
  - 验收标准：LLM 回复包含有效 EDIT_INTENT → 正确解析并移除意图行；JSON 格式错误 → 返回 None 不崩溃；字段不合法 → 返回 None 并记录警告

### #293 偏好自动读取与缓存

- [ ] 在 `AgentChatService` 中实现偏好自动读取和内存缓存
  - `__init__` 新增 `self._preference_cache: dict = {}` 和 `self._file_editor: FileEditor | None = None`
  - `_load_preferences(self) -> dict`：通过 `FileEditor.read_file()` 读取偏好文件，失败返回空字典
  - `_update_preference_cache(self, category: str, value: str, action: str) -> None`：写入偏好后即时更新内存缓存（add 追加、remove 移除、update 重新加载）
  - `_build_preference_summary(self, preferences: dict) -> str`：构建偏好摘要（`[用户偏好] 喜欢：X；习惯：Y` 格式），空偏好返回空字符串；超 Token 预算时按优先级截断（rules > habits > dislikes > likes）
  - 涉及文件：`agent_chat.py`
  - 依赖任务：#287
  - 验收标准：会话创建时读取偏好文件并缓存；写入偏好后缓存即时更新；偏好摘要格式正确；Token 超限时按优先级截断

### #294 会话创建时注入偏好

- [ ] 修改 `create_session()` 方法，在创建会话后读取偏好文件并缓存
  - 在 `self._sessions[session.session_id] = session` 之前，调用 `self._preference_cache = self._load_preferences()`
  - 涉及文件：`agent_chat.py`
  - 依赖任务：#293
  - 验收标准：创建新会话 → 偏好缓存已加载；偏好文件不存在 → 缓存为空字典，不崩溃

### #295 send_message() 重构：偏好摘要注入 + 编辑意图解析

- [ ] 重构 `send_message()` 方法，集成偏好摘要注入和编辑意图解析
  - 构建 `preference_summary`：从 `self._preference_cache` 调用 `_build_preference_summary()`
  - 调用 `build_chat_system_prompt()` 时传入 `preference_summary` 参数
  - LLM 回复后调用 `parse_edit_intent()` 解析编辑意图
  - 有编辑意图且 `file_edit_enabled` 为 True 时：调用 `_execute_edit_intent()` 执行编辑，成功则更新偏好缓存，失败则在回复中追加错误信息
  - 去重时（`is_duplicate`）保持 LLM 原回复
  - 无编辑意图时直接返回清理后的回复
  - 涉及文件：`agent_chat.py`
  - 依赖任务：#291、#292、#293
  - 验收标准：发送"记住我喜欢 Python" → 偏好摘要注入系统提示词 → LLM 回复含 EDIT_INTENT → 解析并执行编辑 → 返回清理后的回复；发送普通消息 → 无编辑意图 → 直接回复

### #296 编辑意图执行方法

- [ ] 在 `AgentChatService` 中实现 `_execute_edit_intent()` 方法
  - 校验 `self._file_editor` 是否可用，不可用返回 `EditResult(success=False)`
  - 将编辑意图字典转换为 `EditIntent` 数据类（含字段校验，ValueError 时返回失败）
  - 确定目标文件（当前固定为 `user_preferences.yaml`），调用 `validate_path()` 校验
  - 调用 `FileEditor.execute_edit()` 执行编辑
  - 返回 `EditResult`
  - 涉及文件：`agent_chat.py`
  - 依赖任务：#287、#292
  - 验收标准：有效编辑意图 → 执行成功返回 `EditResult(success=True)`；FileEditor 不可用 → 返回失败；目标文件不在白名单 → 返回失败

### #297 FileEditor 初始化注入

- [ ] 在 `plugin.py` 的 `on_load()` 中初始化 FileEditor 并注入到 AgentChatService
  - 导入 `from .file_editor import FileEditor`
  - 在 `AgentChatService` 实例化后，创建 `FileEditor` 实例：
    ```python
    file_editor = FileEditor(
        data_dir=_DATA_DIR,
        editable_files=config.agent_chat.editable_files,
        backup_enabled=config.agent_chat.edit_backup_enabled,
    )
    self._agent_chat_service._file_editor = file_editor
    ```
  - 涉及文件：`plugin.py`
  - 依赖任务：#287、#284
  - 验收标准：插件启动后 `AgentChatService._file_editor` 不为 None；FileEditor 使用配置中的白名单和备份设置

---

## 5. WebUI 后端扩展

### #298 send 端点返回值扩展

- [ ] 修改 `webui.py` 中 `_handle_agent_chat_send()` 的返回值，新增 `edit_performed` 字段
  - 在 `send_message()` 返回的 `AgentChatMessage` 上附加 `_edit_performed` 属性（在 `send_message()` 中设置）
  - 返回 JSON 中新增 `"edit_performed": getattr(result, '_edit_performed', False)`
  - 涉及文件：`webui.py`
  - 依赖任务：#295
  - 验收标准：触发文件编辑时 `edit_performed` 为 True；未触发时为 False

### #299 send_message() 中标记编辑执行状态

- [ ] 在 `send_message()` 中为返回的 `AgentChatMessage` 附加 `_edit_performed` 属性
  - 当编辑意图被成功执行时，设置 `assistant_msg._edit_performed = True`
  - 默认为 False
  - 涉及文件：`agent_chat.py`
  - 依赖任务：#295
  - 验收标准：编辑成功时 `_edit_performed` 为 True

---

## 6. 前端改进

### #300 输入区域固定底部

- [ ] 修改 `style.css` 中对话区域的布局，使输入区域固定在底部
  - `#agent-chat-main`：`display: flex; height: calc(100vh - 140px); min-height: 400px`
  - `#chat-area`：`display: flex; flex-direction: column; height: 100%; position: relative`
  - `.chat-messages`：`flex: 1; overflow-y: auto; padding: 16px; min-height: 0`
  - `.chat-input-area`：`flex-shrink: 0; padding: 12px 16px; border-top: 1px solid var(--border); background: var(--card)`
  - 涉及文件：`webui_static/style.css`
  - 依赖任务：无
  - 验收标准：50+ 条消息时输入区域始终固定在对话区域底部；滚动消息不影响输入区域位置

### #301 消息计数同步

- [ ] 修改 `app.js` 中消息计数逻辑，优先使用本地缓存数量
  - 修改 `updateChatSessionInfo(sid)`：消息数使用 `currentChatMessages.length` 替代后端返回的 `message_count`
  - 修改 `renderSessionList()`：当前活跃会话的消息数使用 `currentChatMessages.length`，非活跃会话使用后端 `message_count`
  - 每次消息发送/接收后调用 `updateChatSessionInfo()` 即时同步
  - 涉及文件：`webui_static/app.js`
  - 依赖任务：无
  - 验收标准：发送 4 条消息 → 会话信息栏显示"4条消息"；切换会话再切回 → 仍显示正确数量

### #302 清除按钮防误触

- [ ] 将"清除会话"按钮从直接按钮改为下拉菜单选项
  - 修改 `index.html` 中 `chat-header` 区域：替换原有清除按钮为 `⋮` 更多操作按钮 + 下拉菜单（含"清除会话"选项）
  - 在 `style.css` 中新增 `.chat-header-actions`、`.chat-more-btn`、`.chat-action-menu`、`.chat-menu-item` 样式
  - 在 `app.js` 中新增 `toggleChatMenu()` 函数：切换下拉菜单显示/隐藏
  - 在 `app.js` 中新增全局点击事件监听：点击菜单外区域关闭菜单
  - 涉及文件：`webui_static/index.html`、`webui_static/style.css`、`webui_static/app.js`
  - 依赖任务：无
  - 验收标准：点击 `⋮` 按钮 → 显示下拉菜单；点击"清除会话" → 执行清除；点击菜单外区域 → 菜单关闭

### #303 空会话提示和输入框占位符优化

- [ ] 修改空会话提示文案和输入框占位符，体现指令执行模式
  - 修改 `renderChatMessages()`：空会话提示从"开始与智能体对话 ✨"改为"输入指令开始，例如：记住我喜欢XX"
  - 修改 `index.html` 中 textarea 的 `placeholder`：从"输入消息..."改为"输入指令..."
  - 涉及文件：`webui_static/app.js`、`webui_static/index.html`
  - 依赖任务：无
  - 验收标准：空会话显示"输入指令开始，例如：记住我喜欢XX"；输入框显示"输入指令..."占位符

### #304 会话信息栏布局优化

- [ ] 优化会话信息栏布局，支持操作菜单
  - 确保 `.chat-header` 使用 `display: flex; justify-content: space-between; align-items: center; flex-shrink: 0`
  - 左侧显示会话信息（会话 ID + 关联聊天流 + 消息数量）
  - 右侧显示操作按钮区域
  - 涉及文件：`webui_static/style.css`
  - 依赖任务：#302
  - 验收标准：会话信息栏布局紧凑，左右分布合理

---

## 7. 验证

### #305 配置扩展验证

- [ ] 验证 v3.4 新增配置项功能正常
  - 验证 WebUI 配置页面显示 `agent_chat` 分组下的 5 个新字段
  - 验证 `file_edit_enabled` 默认为 False，`auto_preference_enabled` 默认为 True
  - 验证 `editable_files` 默认为 `["user_preferences.yaml"]`
  - 验证 `preference_summary_token_limit` 默认为 500
  - 验证配置版本号为 3.4.0
  - 验证配置保存后新字段值正确持久化
  - 涉及文件：`config.py`
  - 依赖任务：#284、#285
  - 验收标准：所有新增配置项在 WebUI 中可见、可编辑、可保存

### #306 文件编辑器功能验证

- [ ] 验证 FileEditor 核心功能
  - 验证 `validate_path()` 拒绝非法路径（含 `..`、不在白名单中的文件）
  - 验证 `_ensure_file_exists()` 创建含编辑区域标记的默认文件
  - 验证 `execute_edit()` 正确执行 add/remove/update 操作
  - 验证去重检查：重复偏好不写入
  - 验证原子写入：写入失败时原文件不损坏
  - 验证审计日志：`edit_audit.jsonl` 正确记录编辑操作
  - 验证编辑区域保护：标记区域外的内容不被修改
  - 涉及文件：`file_editor.py`
  - 依赖任务：#286、#287、#288、#289
  - 验收标准：FileEditor 所有核心功能正常，安全约束生效

### #307 智能体对话指令执行验证

- [ ] 验证智能体对话的指令执行模式
  - 验证"记住我喜欢 Python" → 智能体识别为记忆指令 → 写入偏好文件 → 回复包含确认
  - 验证"你还记得什么？" → 智能体读取偏好 → 汇总回复
  - 验证"下次遇到这种情况时XX" → 智能体识别为行为指令 → 写入 rules
  - 验证"你好" → 智能体简短回应 + 引导指令模式
  - 验证角色信息仅影响语气不影响指令执行
  - 验证 `file_edit_enabled=False` 时告知用户功能未启用
  - 涉及文件：`prompts.py`、`agent_chat.py`
  - 依赖任务：#290、#291、#292、#293、#294、#295、#296、#297
  - 验收标准：所有指令类型正确识别和执行；角色信息不影响核心职责

### #308 主动偏好识别验证

- [ ] 验证智能体主动偏好识别功能
  - 验证"我平时用 Python 写代码" → 智能体自动识别为偏好 → 写入 likes
  - 验证"我讨厌早起" → 识别为 dislikes
  - 验证"我习惯用 VSCode" → 识别为 habits
  - 验证"今天好累" → 不识别为偏好
  - 验证"他说他喜欢 Java" → 不识别为偏好
  - 验证 `auto_preference_enabled=False` 时仅响应显式记忆指令
  - 验证偏好去重：重复偏好不重复写入
  - 涉及文件：`prompts.py`、`agent_chat.py`、`file_editor.py`
  - 依赖任务：#307
  - 验收标准：偏好信号正确识别并记录；非偏好内容不被误记录；功能开关生效

### #309 偏好自动读取验证

- [ ] 验证偏好自动读取和注入功能
  - 验证创建新会话 → 系统提示词包含偏好摘要
  - 验证偏好摘要格式正确（`[用户偏好] 喜欢：X；习惯：Y`）
  - 验证空偏好时不注入摘要段
  - 验证会话中写入新偏好后，后续对话能感知到该偏好（内存缓存更新）
  - 验证偏好文件不存在时不影响对话
  - 验证偏好文件格式损坏时跳过注入，记录错误日志
  - 涉及文件：`agent_chat.py`
  - 依赖任务：#307
  - 验收标准：偏好自动读取和注入功能正常；异常情况不阻塞对话

### #310 前端布局改进验证

- [ ] 验证聊天界面布局改进
  - 验证输入区域固定在底部（50+ 条消息时不随滚动移动）
  - 验证消息计数与实际消息数量一致
  - 验证清除按钮在下拉菜单中，需点击 `⋮` 后选择
  - 验证点击菜单外区域关闭下拉菜单
  - 验证空会话提示为"输入指令开始，例如：记住我喜欢XX"
  - 验证输入框占位符为"输入指令..."
  - 验证浏览器窗口大小变化时布局自适应
  - 涉及文件：`webui_static/style.css`、`webui_static/app.js`、`webui_static/index.html`
  - 依赖任务：#300、#301、#302、#303、#304
  - 验收标准：所有前端布局改进项功能正常

### #311 端到端集成验证

- [ ] 验证 v3.4 完整功能链路
  - 验证完整流程：创建会话 → 发送"记住我喜欢 Python" → 偏好写入 → 发送"推荐语言" → 智能体基于偏好推荐 Python
  - 验证完整流程：发送"我平时用 VSCode" → 自动识别偏好 → 偏好写入 → 后续对话体现偏好
  - 验证 `file_edit_enabled=False` + `auto_preference_enabled=False` 时行为与 v3.3.1 一致
  - 验证 WebUI send 端点返回 `edit_performed` 字段
  - 验证审计日志正确记录编辑操作（含 source 字段）
  - 涉及文件：所有修改文件
  - 依赖任务：#305、#306、#307、#308、#309、#310
  - 验收标准：端到端功能链路完整；功能开关关闭时行为与 v3.3.1 一致