# 1. 实现模型

## 1.1 上下文视图

v3.4.1 在 v3.4 基础上新增两大方向改进：

```
即时通讯风格聊天界面（气泡+头像+时间分组+Markdown渲染）  ← 前端重构：CSS/JS 全面改造
会话持久化（内存 → JSONL 文件，容器重启不丢失）           ← 后端新增：持久化模块 + 恢复流程
```

核心变化：
- 新增 `session_persistence.py` 模块，实现会话和消息的 JSONL 文件持久化（参考已有 `persistence.py` 模式）
- 修改 `agent_chat.py`，在消息收发时同步写入 JSONL 文件，启动时从文件恢复会话
- 扩展 `config.py`，新增 `session_persistence_enabled`、`max_persisted_sessions`、`max_persisted_messages_per_session`、`session_retention_days` 配置项
- 修改 `webui_static/style.css`，新增即时通讯风格样式（头像、气泡、时间分组、Markdown 代码块）
- 修改 `webui_static/app.js`，重构消息渲染逻辑（头像生成、时间分组、Markdown 渲染、代码块复制、长消息折叠）
- 修改 `webui_static/index.html`，引入 marked.js CDN
- 修改 `webui.py`，扩展 sessions 端点返回最新消息预览和会话时间

## 1.2 服务/组件总体架构

```
plugin.py (入口，不变)
  ├── AgentCore (agent.py，不变)
  ├── AgentChatService (agent_chat.py，扩展)
  │     ├── 会话管理（扩展：持久化同步）
  │     ├── 消息收发（扩展：写入 JSONL + 更新元数据）
  │     ├── 聊天流上下文注入（不变）
  │     ├── 偏好自动读取（不变）
  │     ├── 编辑意图执行（不变）
  │     └── 持久化同步（新增）     ← v3.4.1
  │           ├── 消息追加写入 messages_*.jsonl
  │           ├── 元数据更新追加写入 sessions_index.jsonl
  │           ├── 启动时从 JSONL 恢复会话
  │           ├── 会话清除时删除持久化文件
  │           └── 过期数据定期清理
  ├── SessionPersistence (session_persistence.py，新增)  ← v3.4.1
  │     ├── JSONL 文件读写
  │     ├── 会话元数据管理
  │     ├── 消息记录管理
  │     ├── 数据恢复（去重+排序+截断）
  │     └── 过期数据清理
  ├── FileEditor (file_editor.py，不变)
  ├── DeepSeekClient (deepseek_client.py，不变)
  ├── PersistenceManager (persistence.py，不变)
  ├── WebUIServer (webui.py，扩展)
  │     └── sessions 端点扩展（返回最新消息预览+会话时间格式化）
  └── 新增配置项：
          └── agent_chat 分组扩展（session_persistence_enabled, max_persisted_sessions,
                                    max_persisted_messages_per_session, session_retention_days）
```

## 1.3 实现设计文档

### 1.3.1 会话持久化模块（新文件 `session_persistence.py`）

**设计思路**：参考已有的 `persistence.py` 模块的 JSONL 存储模式，实现会话和消息的持久化。核心原则是"追加写入、以末行为准"，避免频繁重写文件。SessionPersistence 负责 JSONL 文件的读写操作，AgentChatService 在消息收发时调用 SessionPersistence 进行同步写入。

**文件结构**：

```
{插件数据目录}/agent_chat_sessions/
  ├── sessions_index.jsonl       # 会话元数据，每行一个会话的最新状态
  ├── messages_{session_id}.jsonl # 每个会话一个消息文件
  └── ...
```

**核心数据类**：

```python
@dataclass
class SessionMetadata:
    """会话元数据，对应 sessions_index.jsonl 中的一行。"""
    session_id: str = ""
    created_at: float = 0.0
    last_active_at: float = 0.0
    stream_context_id: str = ""
    message_count: int = 0
```

**核心类**：

```python
class SessionPersistence:
    """会话 JSONL 持久化管理器。"""

    def __init__(self, data_dir: Path) -> None:
        self._sessions_dir = data_dir / "agent_chat_sessions"
        self._sessions_dir.mkdir(parents=True, exist_ok=True)

    # --- 写入操作 ---

    def save_session_metadata(self, metadata: SessionMetadata) -> None:
        """追加写入会话元数据到 sessions_index.jsonl。"""

    def save_message(self, session_id: str, role: str, content: str, timestamp: float) -> None:
        """追加写入一条消息到 messages_{session_id}.jsonl。"""

    def delete_session(self, session_id: str) -> None:
        """删除会话的消息文件，并重建 sessions_index.jsonl（移除该会话记录）。"""

    # --- 读取操作 ---

    def load_all_sessions(self) -> list[SessionMetadata]:
        """加载所有会话元数据，同一 session_id 以最后一行为准。"""

    def load_messages(
        self,
        session_id: str,
        max_messages: int = 200,
    ) -> list[dict]:
        """加载指定会话的消息，返回最近 max_messages 条。"""

    # --- 清理操作 ---

    def cleanup_expired(self, retention_days: int) -> int:
        """清理超过保留天数的会话及其消息文件。"""

    def cleanup_oldest_sessions(self, max_sessions: int) -> int:
        """淘汰最久未活跃的会话，保留最多 max_sessions 个。"""
```

**追加写入策略**：

- `sessions_index.jsonl`：每次会话状态变化（新消息、新会话）时追加一行。同一 `session_id` 可有多行记录，读取时以最后一行为准。此策略避免频繁重写整个文件，写入性能最优。
- `messages_{session_id}.jsonl`：每条消息追加一行，永不修改已有行。消息文件只增不减，除非会话被清除。

**数据恢复流程**：

```
1. 读取 sessions_index.jsonl → 按行解析 JSON
   - 跳过解析失败的行，记录警告日志
   - 同一 session_id 以最后一行为准（去重）
   - 按 last_active_at 降序排序
   - 截取最近 max_persisted_sessions 个会话

2. 对每个会话，按需加载 messages_{session_id}.jsonl
   - 跳过解析失败的行，记录警告日志
   - 按 timestamp 去重（同一 timestamp + role 只保留一条）
   - 截取最近 max_persisted_messages_per_session 条消息

3. 重建内存中的 _sessions 字典
   - 将恢复的元数据和消息填充到 AgentChatSession 对象
```

**会话清除时的文件处理**：

```python
def delete_session(self, session_id: str) -> None:
    """删除会话的消息文件，并重建 sessions_index.jsonl。"""
    # 1. 删除消息文件
    msg_file = self._sessions_dir / f"messages_{session_id}.jsonl"
    if msg_file.exists():
        msg_file.unlink()

    # 2. 重建 sessions_index.jsonl（排除该 session_id 的所有行）
    index_file = self._sessions_dir / "sessions_index.jsonl"
    if not index_file.exists():
        return
    kept_lines: list[str] = []
    with open(index_file, "r", encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if not stripped:
                continue
            try:
                data = json.loads(stripped)
                if data.get("session_id") != session_id:
                    kept_lines.append(line)
            except json.JSONDecodeError:
                kept_lines.append(line)  # 保留无法解析的行
    # 原子写入
    tmp_path = index_file.with_suffix(".jsonl.tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        f.writelines(kept_lines)
    tmp_path.replace(index_file)
```

**过期清理策略**：

- 触发时机：插件启动时执行一次
- 清理规则：删除 `last_active_at` 超过 `session_retention_days` 天的会话及其消息文件
- `session_retention_days` 为 0 时不清理
- 清理后重建 `sessions_index.jsonl`

### 1.3.2 AgentChatService 持久化集成（修改 `agent_chat.py`）

**设计思路**：在 AgentChatService 中集成 SessionPersistence，实现"内存为主、文件同步"的双写模式。所有操作先更新内存，再异步/同步写入文件。启动时从文件恢复到内存。

**初始化扩展**：

```python
class AgentChatService:

    def __init__(
        self,
        deepseek_client: DeepSeekClient,
        event_bus: EventBus,
        persistence_manager: PersistenceManager,
        message_api: Any = None,
    ) -> None:
        # ... 现有初始化 ...
        self._session_persistence: SessionPersistence | None = None  # v3.4.1
        self._persistence_enabled: bool = False  # v3.4.1

    def set_session_persistence(
        self,
        persistence: SessionPersistence,
        enabled: bool,
        max_sessions: int = 20,
        max_messages_per_session: int = 200,
        retention_days: int = 30,
    ) -> None:
        """设置会话持久化服务。"""
        self._session_persistence = persistence
        self._persistence_enabled = enabled
        self._max_persisted_sessions = max_sessions
        self._max_persisted_messages = max_messages_per_session
        self._retention_days = retention_days
```

**启动时数据恢复**：

```python
async def restore_sessions(self) -> None:
    """从 JSONL 文件恢复会话数据到内存。仅在持久化启用时调用。"""
    if not self._persistence_enabled or not self._session_persistence:
        return

    # 1. 过期清理
    if self._retention_days > 0:
        removed = self._session_persistence.cleanup_expired(self._retention_days)
        if removed > 0:
            logger.info("[proactive-chat] 已清理 %d 个过期会话", removed)

    # 2. 加载会话元数据
    metadata_list = self._session_persistence.load_all_sessions()

    # 3. 淘汰超出数量限制的旧会话
    if len(metadata_list) > self._max_persisted_sessions:
        excess = self._session_persistence.cleanup_oldest_sessions(
            self._max_persisted_sessions,
        )
        if excess > 0:
            logger.info("[proactive-chat] 已淘汰 %d 个旧会话", excess)
        metadata_list = metadata_list[:self._max_persisted_sessions]

    # 4. 重建内存中的 _sessions 字典
    for meta in metadata_list:
        messages_data = self._session_persistence.load_messages(
            meta.session_id,
            max_messages=self._max_persisted_messages_per_session,
        )
        messages = [
            AgentChatMessage(
                role=m.get("role", ""),
                content=m.get("content", ""),
                timestamp=m.get("timestamp", 0.0),
            )
            for m in messages_data
        ]
        session = AgentChatSession(
            session_id=meta.session_id,
            messages=messages,
            created_at=meta.created_at,
            last_active_at=meta.last_active_at,
            stream_context_id=meta.stream_context_id,
        )
        session.token_estimate = self._estimate_session_tokens(session)
        self._sessions[session.session_id] = session

    logger.info(
        "[proactive-chat] 已恢复 %d 个会话",
        len(self._sessions),
    )
```

**消息写入时机**：

在 `send_message()` 方法中，消息产生后立即写入 JSONL 文件：

```python
# 用户消息写入
if self._persistence_enabled and self._session_persistence:
    self._session_persistence.save_message(
        session_id=session.session_id,
        role="user",
        content=user_msg.content,
        timestamp=user_msg.timestamp,
    )

# ... LLM 调用 ...

# 智能体回复写入
if self._persistence_enabled and self._session_persistence:
    self._session_persistence.save_message(
        session_id=session.session_id,
        role="assistant",
        content=assistant_msg.content,
        timestamp=assistant_msg.timestamp,
    )

# 元数据更新
if self._persistence_enabled and self._session_persistence:
    self._session_persistence.save_session_metadata(SessionMetadata(
        session_id=session.session_id,
        created_at=session.created_at,
        last_active_at=session.last_active_at,
        stream_context_id=session.stream_context_id,
        message_count=len(session.messages),
    ))
```

**会话创建时持久化**：

```python
async def create_session(self, stream_context_id: str = "") -> AgentChatSession:
    # ... 现有创建逻辑 ...

    # 持久化：写入会话元数据
    if self._persistence_enabled and self._session_persistence:
        self._session_persistence.save_session_metadata(SessionMetadata(
            session_id=session.session_id,
            created_at=session.created_at,
            last_active_at=session.last_active_at,
            stream_context_id=session.stream_context_id,
            message_count=0,
        ))

    self._sessions[session.session_id] = session
    return session
```

**会话清除时删除持久化文件**：

```python
async def clear_session(self, session_id: str) -> bool:
    if session_id in self._sessions:
        del self._sessions[session_id]
        # 持久化：删除文件
        if self._persistence_enabled and self._session_persistence:
            self._session_persistence.delete_session(session_id)
        return True
    return False
```

**会话数量限制调整**：

持久化启用时，将内存中的最大会话数从 5 放宽到 `max_persisted_sessions`（默认 20）：

```python
async def create_session(self, stream_context_id: str = "") -> AgentChatSession:
    # ...
    max_sessions = (
        self._max_persisted_sessions
        if self._persistence_enabled
        else 5
    )
    if len(self._sessions) >= max_sessions:
        oldest_id = min(self._sessions, key=lambda k: self._sessions[k].last_active_at)
        await self.clear_session(oldest_id)  # 同时删除持久化文件
    # ...
```

**聊天流上下文注入消息的持久化**：

系统消息（聊天流上下文注入）也需要持久化，确保恢复后上下文不丢失：

```python
async def _inject_stream_context(self, session, stream_id):
    # ... 现有注入逻辑 ...
    # 注入后持久化系统消息
    if self._persistence_enabled and self._session_persistence:
        for msg in session.messages:
            if msg.role == "system" and msg.timestamp > 0:
                self._session_persistence.save_message(
                    session_id=session.session_id,
                    role="system",
                    content=msg.content,
                    timestamp=msg.timestamp,
                )
```

### 1.3.3 配置扩展（修改 `config.py`）

**新增配置项**：

在 `AgentChatConfig` 类中新增 4 个持久化相关配置项：

```python
class AgentChatConfig(PluginConfigBase):
    # ... 现有配置项不变 ...

    # v3.4.1: 会话持久化
    session_persistence_enabled: bool = Field(
        default=True,
        description="是否启用会话持久化（容器重启后保留会话数据）",
    )
    max_persisted_sessions: int = Field(
        default=20, ge=1, le=100,
        description="最大持久化会话数",
    )
    max_persisted_messages_per_session: int = Field(
        default=200, ge=10, le=1000,
        description="每个会话最大持久化消息数",
    )
    session_retention_days: int = Field(
        default=30, ge=0, le=365,
        description="会话保留天数，0 表示不清理",
    )
```

### 1.3.4 即时通讯风格聊天界面（修改前端文件）

**设计思路**：将当前的"技术面板风格"聊天界面改造为即时通讯风格，核心变化包括：消息气泡增加头像、时间分组显示、消息内时间戳、Markdown 渲染。改造策略是在现有 CSS 类基础上扩展，而非重写。

#### 1.3.4.1 消息气泡布局改造

**当前状态**：`.user-bubble` 和 `.assistant-bubble` 仅有简单的左右对齐和背景色区分。

**改造方案**：将每条消息从单个 `.chat-bubble` 改为 `.message-row` 容器 + 气泡 + 头像的三段式布局。

**HTML 结构**（由 JS 动态生成）：

```html
<!-- 用户消息 -->
<div class="message-row message-row-user">
  <div class="chat-bubble user-bubble">
    <div class="bubble-content">消息文本</div>
    <div class="bubble-time">14:30</div>
  </div>
  <div class="avatar avatar-user">U</div>
</div>

<!-- 智能体消息 -->
<div class="message-row message-row-assistant">
  <div class="avatar avatar-bot">🤖</div>
  <div class="chat-bubble assistant-bubble">
    <div class="bubble-content">消息文本（Markdown 渲染）</div>
    <div class="bubble-time">14:30</div>
  </div>
</div>

<!-- 系统消息 -->
<div class="message-row message-row-system">
  <div class="system-message">系统消息文本</div>
</div>

<!-- 时间分隔线 -->
<div class="time-divider">
  <span class="time-divider-text">14:30</span>
</div>
```

**头像生成规则**（CSS 生成，不依赖外部图片）：

- 用户头像：36×36px 圆形，紫色背景（`var(--accent)`），白色首字母文字
- 智能体头像：36×36px 圆形，深色背景（`var(--border)`），🤖 emoji
- 首字母提取逻辑：取用户名的第一个字符（支持中文、英文），空字符串时显示默认图标 "?"
- 头像位置：用户头像在气泡右侧，智能体头像在气泡左侧

**CSS 新增样式**：

```css
/* 消息行容器 */
.message-row {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  max-width: 85%;
}
.message-row-user {
  align-self: flex-end;
  flex-direction: row-reverse;  /* 头像在右 */
}
.message-row-assistant {
  align-self: flex-start;
}
.message-row-system {
  align-self: center;
  max-width: 90%;
}

/* 头像 */
.avatar {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 0.85rem;
  flex-shrink: 0;
}
.avatar-user {
  background: var(--accent);
  color: #fff;
  font-weight: 600;
}
.avatar-bot {
  background: var(--border);
  font-size: 1.1rem;
}

/* 气泡内容 */
.bubble-content {
  word-break: break-word;
  line-height: 1.6;
}
.bubble-time {
  font-size: 0.7rem;
  opacity: 0.5;
  margin-top: 4px;
  text-align: right;
}

/* 时间分隔线 */
.time-divider {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 8px 0;
}
.time-divider::before,
.time-divider::after {
  content: '';
  flex: 1;
  height: 1px;
  background: var(--border);
}
.time-divider-text {
  padding: 0 12px;
  font-size: 0.75rem;
  color: var(--text2);
  white-space: nowrap;
}

/* 系统消息 */
.system-message {
  font-size: 0.8rem;
  color: var(--text2);
  text-align: center;
  padding: 4px 12px;
}
```

**气泡样式优化**：

```css
/* 优化现有气泡样式 */
.user-bubble {
  background: var(--accent);
  color: #fff;
  border-bottom-right-radius: 4px;  /* 右下角小圆角 */
  padding: 10px 14px;
  border-radius: 12px;
}
.assistant-bubble {
  background: var(--bg);
  border: 1px solid var(--border);
  color: var(--text);
  border-bottom-left-radius: 4px;  /* 左下角小圆角 */
  padding: 10px 14px;
  border-radius: 12px;
}
```

#### 1.3.4.2 时间分组显示

**分组规则**（参照微信策略）：

- 5 分钟内的连续消息不重复显示时间分隔线
- 两条消息间隔超过 5 分钟时，在两条消息之间显示时间分隔线
- 时间格式：
  - 当天消息：仅显示 "HH:mm"
  - 昨天消息：显示 "昨天 HH:mm"
  - 更早消息：显示 "yyyy/MM/dd HH:mm"

**JS 实现**：

```javascript
function shouldShowTimeDivider(prevTimestamp, currentTimestamp) {
    if (!prevTimestamp) return true;  // 第一条消息显示时间
    const diffMs = currentTimestamp - prevTimestamp;
    return diffMs >= 5 * 60 * 1000;  // 5 分钟
}

function formatTimeDividerText(timestamp) {
    const date = new Date(timestamp);
    const now = new Date();
    const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    const yesterday = new Date(today.getTime() - 86400000);
    const msgDate = new Date(date.getFullYear(), date.getMonth(), date.getDate());

    const timeStr = date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });

    if (msgDate.getTime() === today.getTime()) {
        return timeStr;
    } else if (msgDate.getTime() === yesterday.getTime()) {
        return '昨天 ' + timeStr;
    } else {
        return date.getFullYear() + '/' +
            String(date.getMonth() + 1).padStart(2, '0') + '/' +
            String(date.getDate()).padStart(2, '0') + ' ' + timeStr;
    }
}

function formatBubbleTime(timestamp) {
    const date = new Date(timestamp);
    return date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
}
```

#### 1.3.4.3 Markdown 渲染

**库选择**：marked.js（轻量级，~40KB，CDN 引入）

**引入方式**：在 `index.html` 的 `<head>` 中添加 CDN 引用：

```html
<script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
```

**安全策略**：

1. 用户消息：不渲染 Markdown，使用 `escapeHtml()` 转义后以纯文本显示（防 XSS）
2. 智能体消息：使用 marked.js 渲染，配置 `sanitize` 选项禁止原始 HTML 标签
3. marked.js 配置：

```javascript
// marked 配置
marked.setOptions({
    breaks: true,        // 支持换行
    gfm: true,           // GitHub Flavored Markdown
    headerIds: false,    // 不生成 header id
    mangle: false,       // 不混淆邮箱链接
});
```

**代码块样式**：

```css
/* Markdown 渲染后的代码块样式 */
.bubble-content pre {
    background: #1e1e2e;
    border-radius: 8px;
    padding: 12px;
    overflow-x: auto;
    margin: 8px 0;
    position: relative;
}
.bubble-content code {
    font-family: 'Consolas', 'Monaco', monospace;
    font-size: 0.85rem;
}
.bubble-content :not(pre) > code {
    background: rgba(108, 92, 231, 0.15);
    padding: 2px 6px;
    border-radius: 4px;
    font-size: 0.85em;
}
.bubble-content pre code {
    color: #e0e0e0;
}

/* 代码块语言标签 */
.code-lang-label {
    position: absolute;
    top: 4px;
    left: 8px;
    font-size: 0.7rem;
    color: var(--text2);
    text-transform: uppercase;
}

/* 代码块复制按钮 */
.code-copy-btn {
    position: absolute;
    top: 4px;
    right: 8px;
    background: var(--border);
    border: none;
    color: var(--text2);
    padding: 2px 8px;
    border-radius: 4px;
    font-size: 0.7rem;
    cursor: pointer;
    opacity: 0;
    transition: opacity 0.2s;
}
pre:hover .code-copy-btn {
    opacity: 1;
}
.code-copy-btn:hover {
    background: var(--accent);
    color: #fff;
}

/* 链接样式 */
.bubble-content a {
    color: var(--accent2);
    text-decoration: none;
}
.bubble-content a:hover {
    text-decoration: underline;
}

/* 列表样式 */
.bubble-content ul,
.bubble-content ol {
    padding-left: 20px;
    margin: 4px 0;
}
.bubble-content li {
    margin: 2px 0;
}

/* 粗体/斜体 */
.bubble-content strong {
    font-weight: 600;
}
.bubble-content em {
    font-style: italic;
}
```

**代码块复制按钮实现**：

```javascript
function addCodeBlockFeatures(container) {
    const pres = container.querySelectorAll('pre');
    pres.forEach(pre => {
        // 语言标签
        const code = pre.querySelector('code');
        if (code) {
            const langMatch = code.className.match(/language-(\w+)/);
            if (langMatch) {
                const label = document.createElement('span');
                label.className = 'code-lang-label';
                label.textContent = langMatch[1];
                pre.appendChild(label);
            }
        }

        // 复制按钮
        const btn = document.createElement('button');
        btn.className = 'code-copy-btn';
        btn.textContent = '复制';
        btn.onclick = function() {
            const text = code ? code.textContent : pre.textContent;
            navigator.clipboard.writeText(text).then(() => {
                btn.textContent = '已复制';
                setTimeout(() => { btn.textContent = '复制'; }, 2000);
            }).catch(() => {
                // 降级方案
                const ta = document.createElement('textarea');
                ta.value = text;
                document.body.appendChild(ta);
                ta.select();
                document.execCommand('copy');
                document.body.removeChild(ta);
                btn.textContent = '已复制';
                setTimeout(() => { btn.textContent = '复制'; }, 2000);
            });
        };
        pre.appendChild(btn);
    });
}
```

**长消息折叠**：

```css
.bubble-content.collapsed {
    max-height: 300px;
    overflow: hidden;
    position: relative;
}
.bubble-content.collapsed::after {
    content: '';
    position: absolute;
    bottom: 0;
    left: 0;
    right: 0;
    height: 60px;
    background: linear-gradient(transparent, var(--bg));
    pointer-events: none;
}
.expand-btn {
    display: inline-block;
    margin-top: 4px;
    font-size: 0.8rem;
    color: var(--accent2);
    cursor: pointer;
}
.expand-btn:hover {
    text-decoration: underline;
}
```

```javascript
function applyMessageCollapse(bubbleContent) {
    if (bubbleContent.textContent.length > 500) {
        bubbleContent.classList.add('collapsed');
        const btn = document.createElement('span');
        btn.className = 'expand-btn';
        btn.textContent = '展开全文';
        btn.onclick = function() {
            if (bubbleContent.classList.contains('collapsed')) {
                bubbleContent.classList.remove('collapsed');
                btn.textContent = '收起';
            } else {
                bubbleContent.classList.add('collapsed');
                btn.textContent = '展开全文';
            }
        };
        bubbleContent.parentNode.appendChild(btn);
    }
}
```

#### 1.3.4.4 消息渲染重构（修改 `app.js`）

**核心函数 `renderChatMessages()` 重构**：

```javascript
function renderChatMessages() {
    const el = document.getElementById('chat-messages');
    if (currentChatMessages.length === 0) {
        el.innerHTML = '<div class="chat-empty-hint">输入指令开始，例如：记住我喜欢XX</div>';
        return;
    }

    let html = '';
    let prevTimestamp = null;

    currentChatMessages.forEach(m => {
        const ts = m.timestamp || 0;

        // 时间分组
        if (shouldShowTimeDivider(prevTimestamp, ts)) {
            html += '<div class="time-divider"><span class="time-divider-text">'
                + formatTimeDividerText(ts) + '</span></div>';
        }
        prevTimestamp = ts;

        if (m.role === 'system') {
            // 系统消息：居中灰色小字
            html += '<div class="message-row message-row-system">'
                + '<div class="system-message">' + escapeHtml(m.content) + '</div></div>';
        } else if (m.role === 'user') {
            // 用户消息：右侧气泡 + 首字母头像
            const initial = getUserInitial();
            html += '<div class="message-row message-row-user">'
                + '<div class="chat-bubble user-bubble">'
                + '<div class="bubble-content">' + escapeHtml(m.content) + '</div>'
                + '<div class="bubble-time">' + formatBubbleTime(ts) + '</div>'
                + '</div>'
                + '<div class="avatar avatar-user">' + initial + '</div></div>';
        } else {
            // 智能体消息：左侧气泡 + 机器人头像 + Markdown 渲染
            const rendered = renderMarkdown(m.content);
            html += '<div class="message-row message-row-assistant">'
                + '<div class="avatar avatar-bot">🤖</div>'
                + '<div class="chat-bubble assistant-bubble">'
                + '<div class="bubble-content">' + rendered + '</div>'
                + '<div class="bubble-time">' + formatBubbleTime(ts) + '</div>'
                + '</div></div>';
        }
    });

    el.innerHTML = html;

    // 后处理：代码块功能 + 长消息折叠
    el.querySelectorAll('.assistant-bubble .bubble-content').forEach(bc => {
        addCodeBlockFeatures(bc);
        applyMessageCollapse(bc);
    });

    el.scrollTop = el.scrollHeight;
}

function getUserInitial() {
    // 从配置或默认值获取用户名首字母
    return '我';  // 默认显示"我"
}

function renderMarkdown(text) {
    if (typeof marked === 'undefined') {
        return escapeHtml(text);  // marked.js 加载失败时降级为纯文本
    }
    try {
        return marked.parse(text);
    } catch (e) {
        return escapeHtml(text);  // 解析失败时降级为纯文本
    }
}
```

### 1.3.5 会话列表改进（修改前端 + 后端）

#### 1.3.5.1 后端 API 扩展（修改 `webui.py`）

**sessions 端点扩展**：在 `list_sessions()` 返回数据中增加最新消息预览和格式化时间。

```python
async def _handle_agent_chat_sessions(self, request: web.Request) -> web.Response:
    # ... 现有权限检查 ...
    sessions = self._agent_chat_service.list_sessions()
    now = time.time()

    # 为每个会话添加最新消息预览和格式化时间
    for s in sessions:
        session = self._agent_chat_service.get_session(s["session_id"])
        if session and session.messages:
            # 查找最新一条非系统消息
            latest_msg = None
            for msg in reversed(session.messages):
                if msg.role in ("user", "assistant"):
                    latest_msg = msg
                    break

            if latest_msg:
                prefix = "🤖: " if latest_msg.role == "assistant" else "我: "
                preview = prefix + latest_msg.content[:20]
                if len(latest_msg.content) > 20:
                    preview += "..."
                s["last_message_preview"] = preview
            else:
                s["last_message_preview"] = "暂无消息"
        else:
            s["last_message_preview"] = "暂无消息"

        # 格式化最后活跃时间
        s["last_active_display"] = self._format_session_time(
            s.get("last_active_at", 0), now,
        )

        # 关联聊天流名称
        if s.get("stream_context_id"):
            s["stream_display_name"] = self._get_stream_display_name(
                s["stream_context_id"],
            )
        else:
            s["stream_display_name"] = ""

    return web.json_response({"success": True, "sessions": sessions})
```

**会话时间格式化**：

```python
@staticmethod
def _format_session_time(last_active_at: float, now: float) -> str:
    """格式化会话最后活跃时间。"""
    if not last_active_at:
        return ""
    diff = now - last_active_at
    if diff < 0:
        return "刚刚"

    # 当天
    today_start = now - (now % 86400)
    if last_active_at >= today_start:
        return time.strftime("%H:%M", time.localtime(last_active_at))

    # 昨天
    yesterday_start = today_start - 86400
    if last_active_at >= yesterday_start:
        return "昨天"

    # 7 天内
    if diff < 7 * 86400:
        days = int(diff // 86400)
        return f"{days}天前"

    # 更早
    return time.strftime("%Y/%m/%d", time.localtime(last_active_at))
```

#### 1.3.5.2 前端会话列表改造（修改 `app.js`）

**两行布局**：

```javascript
function renderSessionList() {
    const el = document.getElementById('session-list');
    if (!agentChatSessions.length) {
        el.innerHTML = '<div style="padding:16px;color:var(--text-secondary);text-align:center;font-size:.85rem">暂无会话</div>';
        return;
    }

    const sorted = [...agentChatSessions].sort(
        (a, b) => (b.last_active_at || 0) - (a.last_active_at || 0)
    );

    el.innerHTML = sorted.map(s => {
        const name = s.stream_display_name || s.session_id.substring(0, 8) + '...';
        const time = s.last_active_display || '';
        const preview = s.last_message_preview || '暂无消息';
        const active = s.session_id === currentChatSessionId ? 'active' : '';

        return '<div class="chat-session-item ' + active + '" '
            + 'onclick="selectChatSession(\'' + s.session_id + '\')">'
            + '<div class="session-row-1">'
            + '<span class="session-name">' + escapeHtml(name) + '</span>'
            + '<span class="session-time">' + escapeHtml(time) + '</span>'
            + '</div>'
            + '<div class="session-row-2">' + escapeHtml(preview) + '</div>'
            + '</div>';
    }).join('');
}
```

**CSS 新增样式**：

```css
.chat-session-item .session-row-1 {
    display: flex;
    justify-content: space-between;
    align-items: center;
}
.chat-session-item .session-name {
    font-size: 0.85rem;
    color: var(--text);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    flex: 1;
    margin-right: 8px;
}
.chat-session-item .session-time {
    font-size: 0.7rem;
    color: var(--text2);
    flex-shrink: 0;
}
.chat-session-item .session-row-2 {
    font-size: 0.75rem;
    color: var(--text2);
    margin-top: 4px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}
```

### 1.3.6 插件启动流程集成（修改 `plugin.py`）

**设计思路**：在插件初始化时，根据配置创建 SessionPersistence 实例并注入 AgentChatService，然后触发数据恢复。

```python
# 在插件初始化逻辑中（伪代码）
async def _init_agent_chat(self):
    # ... 现有 AgentChatService 创建逻辑 ...

    # v3.4.1: 持久化集成
    config = self._config_getter()
    if config.agent_chat.session_persistence_enabled:
        from .session_persistence import SessionPersistence
        persistence = SessionPersistence(data_dir=self._data_dir)
        self._agent_chat_service.set_session_persistence(
            persistence=persistence,
            enabled=True,
            max_sessions=config.agent_chat.max_persisted_sessions,
            max_messages_per_session=config.agent_chat.max_persisted_messages_per_session,
            retention_days=config.agent_chat.session_retention_days,
        )
        await self._agent_chat_service.restore_sessions()
```

# 2. 接口设计

## 2.1 总体设计

v3.4.1 的接口变更集中在两个方面：
1. **后端 API 扩展**：sessions 端点返回数据增加最新消息预览和格式化时间
2. **前端渲染接口**：新增 JS 函数用于即时通讯风格渲染

不新增 API 端点，不修改现有端点的 URL 和请求格式。

## 2.2 接口清单

### 2.2.1 后端 API 变更

| 端点 | 方法 | 变更类型 | 变更内容 |
|------|------|----------|----------|
| `/api/proactive-chat/agent/chat/sessions` | GET | **响应扩展** | 返回数据新增 `last_message_preview`、`last_active_display`、`stream_display_name` 字段 |

**sessions 端点响应扩展**：

```json
{
  "success": true,
  "sessions": [
    {
      "session_id": "a1b2c3d4e5f6g7h8",
      "created_at": 1719561600.0,
      "last_active_at": 1719565200.0,
      "message_count": 5,
      "token_estimate": 1200,
      "stream_context_id": "stream_123",
      "last_message_preview": "🤖: 已记住你喜欢Python",
      "last_active_display": "14:30",
      "stream_display_name": "[群聊] 测试群"
    }
  ]
}
```

### 2.2.2 前端新增 JS 函数

| 函数名 | 用途 |
|--------|------|
| `shouldShowTimeDivider(prevTs, curTs)` | 判断是否需要显示时间分隔线 |
| `formatTimeDividerText(timestamp)` | 格式化时间分隔线文本 |
| `formatBubbleTime(timestamp)` | 格式化气泡内时间戳（HH:mm） |
| `renderMarkdown(text)` | 使用 marked.js 渲染 Markdown |
| `addCodeBlockFeatures(container)` | 为代码块添加语言标签和复制按钮 |
| `applyMessageCollapse(bubbleContent)` | 为长消息添加折叠/展开功能 |
| `getUserInitial()` | 获取用户名首字母用于头像 |

### 2.2.3 SessionPersistence 内部接口

| 方法 | 用途 |
|------|------|
| `save_session_metadata(metadata)` | 追加写入会话元数据 |
| `save_message(session_id, role, content, timestamp)` | 追加写入消息 |
| `delete_session(session_id)` | 删除会话的消息文件和索引记录 |
| `load_all_sessions()` | 加载所有会话元数据（去重） |
| `load_messages(session_id, max_messages)` | 加载指定会话的消息（截断） |
| `cleanup_expired(retention_days)` | 清理过期会话 |
| `cleanup_oldest_sessions(max_sessions)` | 淘汰最旧会话 |

# 4. 数据模型

## 4.1 设计目标

1. 与已有的 `persistence.py` 模块保持一致的 JSONL 存储模式
2. 支持追加写入，避免频繁重写文件
3. 支持容器重启后的数据恢复
4. 支持会话数量和消息数量的限制
5. 支持过期数据自动清理

## 4.2 模型实现

### 4.2.1 会话元数据（sessions_index.jsonl）

每行一条 JSON 记录，同一 session_id 可有多行（以最后一行为准）：

```json
{
  "session_id": "a1b2c3d4e5f6g7h8",
  "created_at": 1719561600.0,
  "last_active_at": 1719565200.0,
  "stream_context_id": "stream_123",
  "message_count": 5
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| session_id | string | 是 | 会话唯一标识，16 位十六进制 |
| created_at | float | 是 | 创建时间，Unix 时间戳（秒） |
| last_active_at | float | 是 | 最后活跃时间，Unix 时间戳（秒） |
| stream_context_id | string | 否 | 关联的聊天流 ID，默认空字符串 |
| message_count | int | 是 | 消息总数 |

### 4.2.2 消息记录（messages_{session_id}.jsonl）

每行一条 JSON 记录：

```json
{
  "role": "user",
  "content": "记住我喜欢Python",
  "timestamp": 1719565200000.0
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| role | string | 是 | 消息角色："user"、"assistant"、"system" |
| content | string | 是 | 消息内容，最大 4000 字符 |
| timestamp | float | 是 | 消息时间戳，Unix 时间戳（毫秒） |

### 4.2.3 AgentChatMessage 扩展

现有 `AgentChatMessage` 数据类无需修改，其字段与 JSONL 记录完全对应：

```python
@dataclass
class AgentChatMessage:
    role: str = ""       # 对应 JSONL 的 role
    content: str = ""    # 对应 JSONL 的 content
    timestamp: float = 0.0  # 对应 JSONL 的 timestamp
```

### 4.2.4 SessionMetadata 新增

```python
@dataclass
class SessionMetadata:
    """会话元数据，对应 sessions_index.jsonl 中的一行。"""
    session_id: str = ""
    created_at: float = 0.0
    last_active_at: float = 0.0
    stream_context_id: str = ""
    message_count: int = 0
```

### 4.2.5 配置数据模型扩展

在 `AgentChatConfig` 中新增 4 个字段：

| 配置项 | 类型 | 默认值 | 范围 | 说明 |
|--------|------|--------|------|------|
| session_persistence_enabled | bool | True | - | 是否启用会话持久化 |
| max_persisted_sessions | int | 20 | 1-100 | 最大持久化会话数 |
| max_persisted_messages_per_session | int | 200 | 10-1000 | 每个会话最大持久化消息数 |
| session_retention_days | int | 30 | 0-365 | 会话保留天数，0 不清理 |