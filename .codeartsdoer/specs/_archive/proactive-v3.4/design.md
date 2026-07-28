# 1. 实现模型

## 1.1 上下文视图

v3.4 在 v3.3.1 基础上新增四大方向重构与改进：

```
智能体对话模式（聊天 → 指令执行）           ← 重构：系统提示词 + 消息处理流程
智能体主动偏好识别与记录                     ← 新增：LLM 输出编辑意图 → 后端执行文件写入
偏好自动读取（会话创建时注入 + 内存缓存）    ← 新增：偏好摘要注入系统提示词
聊天界面布局改进（输入固定 + 计数同步 + 防误触）← 修复：CSS/JS 布局调整
```

核心变化：
- 重写 `prompts.py` 中的 `AGENT_CHAT_SYSTEM_PROMPT` 和 `build_chat_system_prompt()`，从"聊天助手"改为"指令执行助手"
- 新增 `file_editor.py` 模块，实现文件编辑安全机制（白名单 + 编辑区域标记 + 路径守卫 + 原子写入 + 审计日志）
- 修改 `agent_chat.py`，新增偏好自动读取（会话创建时）、编辑意图解析与执行、偏好内存缓存
- 扩展 `config.py`，新增 `file_edit_enabled`、`editable_files`、`edit_backup_enabled`、`auto_preference_enabled`、`preference_summary_token_limit` 配置项
- 修改 `webui_static/app.js`，修复输入区域固定、消息计数同步、清除按钮防误触
- 修改 `webui_static/style.css`，新增固定布局样式
- 修改 `webui_static/index.html`，调整占位符文案和操作菜单
- 新增 `user_preferences.yaml` 偏好文件（插件数据目录下）

## 1.2 服务/组件总体架构

```
plugin.py (入口，不变)
  ├── AgentCore (agent.py，不变)
  ├── AgentChatService (agent_chat.py，扩展)
  │     ├── 会话管理（不变）
  │     ├── 消息收发（扩展：编辑意图解析 + 偏好缓存）
  │     ├── 聊天流上下文注入（不变）
  │     ├── 偏好自动读取（新增）     ← v3.4
  │     │     ├── 会话创建时读取偏好文件
  │     │     ├── 构建偏好摘要注入系统提示词
  │     │     └── 偏好内存缓存（写入后即时更新）
  │     └── 编辑意图执行（新增）     ← v3.4
  │           ├── 解析 LLM 输出中的编辑意图 JSON
  │           ├── 调用 FileEditor 执行文件编辑
  │           └── 将编辑结果反馈给 LLM 生成最终回复
  ├── FileEditor (file_editor.py，新增)  ← v3.4
  │     ├── 路径守卫（白名单校验）
  │     ├── 编辑区域标记校验
  │     ├── 原子写入（临时文件 + 替换）
  │     ├── 去重检查
  │     └── 审计日志记录
  ├── DeepSeekClient (deepseek_client.py，不变)
  ├── PersistenceManager (persistence.py，不变)
  ├── WebUIServer (webui.py，扩展 send 端点返回值)
  └── 新增配置项：
         └── agent_chat 分组扩展（file_edit_enabled, editable_files, edit_backup_enabled,
                                   auto_preference_enabled, preference_summary_token_limit）
```

## 1.3 实现设计文档

### 1.3.1 指令执行提示词设计（修改 `prompts.py`）

**设计思路**：将 `AGENT_CHAT_SYSTEM_PROMPT` 从"友好的聊天助手"重新定义为"指令执行助手"。核心变化是让 LLM 明确其职责是理解用户指令并执行操作，同时具备主动识别用户偏好的能力。LLM 通过输出结构化编辑意图（JSON）来触发文件编辑，而非直接操作文件系统。

**系统提示词重写**：

```python
AGENT_CHAT_SYSTEM_PROMPT = """你是一个指令执行助手，用户通过对话给你下达指令，你理解指令意图、执行操作并反馈结果。同时，你具备主动识别用户偏好的能力——当用户在对话中自然表达了偏好信息时，你会自动识别并记录。
{personality_section}
## 核心职责

1. **执行指令**：理解用户的指令意图并执行相应操作
2. **主动识别偏好**：在对话中自动识别用户自然表达的偏好信号
3. **反馈结果**：清晰反馈指令执行的结果

## 指令类型

- **记忆指令**：如"记住我喜欢XX"、"我讨厌XX" → 记录用户偏好
- **查询指令**：如"你还记得什么？" → 查询已记录的偏好
- **行为指令**：如"下次遇到这种情况时XX" → 记录行为规则
- **通用对话**：不属于上述类型的一般性问答 → 直接回答

## 偏好识别

当用户在对话中自然表达了偏好信号时，主动识别并记录：
- 喜好表达：如"我挺喜欢Python的" → 识别为 likes
- 厌恶表达：如"我讨厌早起" → 识别为 dislikes
- 习惯描述：如"我平时习惯用VSCode" → 识别为 habits
- 行为倾向：如"我总是先写测试再写代码" → 识别为 rules

**不要**从以下内容中提取偏好：临时性陈述（如"今天好累"）、客观事实（如"现在是下午三点"）、他人偏好（如"他说他喜欢Java"）。

## 文件编辑

当你需要记录偏好或行为规则时，在回复的**最后一行**输出编辑意图，格式如下：
```json
EDIT_INTENT: {"action": "add", "category": "likes", "value": "Python", "source": "explicit"}
```

字段说明：
- action：操作类型，add（新增）、remove（删除）、update（更新）
- category：分类，likes、dislikes、habits、rules
- value：条目值
- source：来源，explicit（用户显式指令）或 auto（主动识别）
- old_value：仅 update/remove 时需要，被替换/删除的旧值

**规则**：
- 只有需要文件编辑时才输出 EDIT_INTENT 行，否则正常回复即可
- EDIT_INTENT 行必须在回复的最末尾，单独一行
- 如果偏好已存在（去重），不要重复输出编辑意图，而是在回复中告知用户

## 回复规则

1. 简洁明了地反馈执行结果，如"已记住：你喜欢Python"
2. 角色信息仅影响回复语气，不影响核心职责（执行指令）
3. 当用户发送闲聊类消息时，简短回答后提示可用的指令类型
4. 不要进行无目的的角色扮演闲聊
5. 回复使用自然语言，不要在正文中输出 JSON（EDIT_INTENT 除外）
{custom_prompt_section}"""
```

**`build_chat_system_prompt()` 扩展**：

新增 `preference_summary` 参数，在系统提示词末尾注入偏好摘要：

```python
def build_chat_system_prompt(
    bot_nickname: str = "",
    alias_names: list[str] | None = None,
    personality: str = "",
    reply_style: str = "",
    custom_prompt: str = "",
    preference_summary: str = "",  # ← v3.4 新增
) -> str:
    # ... 现有 personality_section 构建逻辑不变 ...

    custom_prompt_section = ""
    if custom_prompt and custom_prompt.strip():
        custom_prompt_section = f"\n{custom_prompt.strip()}"

    prompt = AGENT_CHAT_SYSTEM_PROMPT.format(
        personality_section=personality_section,
        custom_prompt_section=custom_prompt_section,
    )

    # v3.4: 注入偏好摘要
    if preference_summary:
        prompt += f"\n\n{preference_summary}"

    return prompt
```

**编辑意图解析**：

在 `agent_chat.py` 中新增解析函数，从 LLM 回复中提取 `EDIT_INTENT:` 行：

```python
import json
import re

_EDIT_INTENT_PATTERN = re.compile(
    r'EDIT_INTENT:\s*(\{.*\})\s*$', re.MULTILINE,
)

def parse_edit_intent(response_text: str) -> tuple[dict | None, str]:
    """从 LLM 回复中解析编辑意图。

    Args:
        response_text: LLM 的完整回复文本

    Returns:
        (编辑意图字典 或 None, 清理后的回复文本)
    """
    match = _EDIT_INTENT_PATTERN.search(response_text)
    if not match:
        return None, response_text

    intent_json_str = match.group(1)
    try:
        intent = json.loads(intent_json_str)
    except json.JSONDecodeError:
        logger.warning("[proactive-chat] 编辑意图 JSON 解析失败: %s", intent_json_str)
        return None, response_text

    # 基础字段校验
    required_fields = {"action", "category", "value", "source"}
    if not required_fields.issubset(intent.keys()):
        logger.warning("[proactive-chat] 编辑意图缺少必填字段: %s", intent)
        return None, response_text

    valid_actions = {"add", "remove", "update"}
    valid_categories = {"likes", "dislikes", "habits", "rules"}
    valid_sources = {"explicit", "auto"}

    if intent["action"] not in valid_actions:
        logger.warning("[proactive-chat] 编辑意图 action 无效: %s", intent["action"])
        return None, response_text
    if intent["category"] not in valid_categories:
        logger.warning("[proactive-chat] 编辑意图 category 无效: %s", intent["category"])
        return None, response_text
    if intent["source"] not in valid_sources:
        logger.warning("[proactive-chat] 编辑意图 source 无效: %s", intent["source"])
        return None, response_text

    # 从回复中移除 EDIT_INTENT 行
    cleaned_text = _EDIT_INTENT_PATTERN.sub('', response_text).strip()

    return intent, cleaned_text
```

### 1.3.2 文件编辑器（新文件 `file_editor.py`）

**设计思路**：参考 MiMo-Code 的 memory-path-guard 模式，实现文件编辑安全机制。FileEditor 是一个独立的文件编辑服务，负责路径守卫、编辑区域校验、原子写入、去重检查和审计日志。AgentChatService 通过调用 FileEditor 执行实际的文件读写操作。

**核心数据类**：

```python
from dataclasses import dataclass
from enum import Enum


class EditAction(str, Enum):
    ADD = "add"
    REMOVE = "remove"
    UPDATE = "update"


class EditCategory(str, Enum):
    LIKES = "likes"
    DISLIKES = "dislikes"
    HABITS = "habits"
    RULES = "rules"


class EditSource(str, Enum):
    EXPLICIT = "explicit"
    AUTO = "auto"


@dataclass
class EditIntent:
    """编辑意图。"""
    action: EditAction
    category: EditCategory
    value: str
    source: EditSource
    old_value: str = ""


@dataclass
class EditResult:
    """编辑结果。"""
    success: bool
    message: str = ""
    category: str = ""
    value: str = ""
    action: str = ""
    is_duplicate: bool = False


@dataclass
class AuditLogEntry:
    """审计日志条目。"""
    timestamp: float = 0.0
    session_id: str = ""
    file_path: str = ""
    action: str = ""
    category: str = ""
    value: str = ""
    old_value: str = ""
    source: str = ""
```

**核心类**：

```python
class FileEditor:
    """文件编辑器，提供安全的文件编辑能力。"""

    EDITABLE_START_MARKER = "# --- editable start ---"
    EDITABLE_END_MARKER = "# --- editable end ---"

    def __init__(
        self,
        data_dir: Path,
        editable_files: list[str] | None = None,
        backup_enabled: bool = True,
    ) -> None:
        self._data_dir = data_dir
        self._editable_files = set(editable_files or ["user_preferences.yaml"])
        self._backup_enabled = backup_enabled

    def validate_path(self, relative_path: str) -> bool:
        """路径守卫：校验目标路径是否在白名单中。"""

    def read_file(self, relative_path: str) -> dict | None:
        """读取 YAML 文件内容，仅返回可编辑区域内的数据。"""

    def execute_edit(
        self,
        relative_path: str,
        intent: EditIntent,
        session_id: str = "",
    ) -> EditResult:
        """执行编辑操作。"""

    def _ensure_file_exists(self, relative_path: str) -> None:
        """确保文件存在，不存在则创建默认内容。"""

    def _read_editable_region(self, relative_path: str) -> tuple[dict, str, str]:
        """读取文件的可编辑区域内容。
        
        Returns:
            (可编辑区域的 YAML 数据, 标记前内容, 标记后内容)
        """

    def _write_editable_region(
        self,
        relative_path: str,
        data: dict,
        pre_marker: str,
        post_marker: str,
    ) -> None:
        """原子写入：先写临时文件，成功后替换原文件。"""

    def _check_duplicate(self, data: dict, intent: EditIntent) -> bool:
        """去重检查：判断新偏好是否与已有条目重复。"""

    def _record_audit(self, relative_path: str, intent: EditIntent, session_id: str) -> None:
        """记录审计日志。"""
```

**路径守卫实现**：

```python
def validate_path(self, relative_path: str) -> bool:
    """校验目标路径是否在白名单中。"""
    # 标准化路径，防止路径遍历攻击
    normalized = Path(relative_path).as_posix()
    if normalized.startswith("..") or "/" in normalized and normalized.split("/")[0] == "..":
        return False
    return normalized in self._editable_files
```

**编辑区域标记处理**：

```python
def _read_editable_region(self, relative_path: str) -> tuple[dict, str, str]:
    """读取文件的可编辑区域内容。"""
    file_path = self._data_dir / relative_path
    content = file_path.read_text(encoding="utf-8")

    start_idx = content.find(self.EDITABLE_START_MARKER)
    end_idx = content.find(self.EDITABLE_END_MARKER)

    if start_idx == -1 or end_idx == -1:
        # 标记缺失，将整个文件视为可编辑区域
        logger.warning("[proactive-chat] 文件 %s 缺少编辑区域标记，将整个文件视为可编辑", relative_path)
        data = yaml.safe_load(content) or {}
        return data, "", ""

    pre_marker = content[:start_idx]
    post_marker = content[end_idx + len(self.EDITABLE_END_MARKER):]
    editable_content = content[start_idx + len(self.EDITABLE_START_MARKER):end_idx]

    data = yaml.safe_load(editable_content) or {}
    return data, pre_marker, post_marker
```

**原子写入实现**：

```python
def _write_editable_region(
    self,
    relative_path: str,
    data: dict,
    pre_marker: str,
    post_marker: str,
) -> None:
    """原子写入：先写临时文件，成功后替换原文件。"""
    file_path = self._data_dir / relative_path

    # 构建完整文件内容
    editable_yaml = yaml.dump(data, allow_unicode=True, default_flow_style=False)
    full_content = (
        pre_marker
        + self.EDITABLE_START_MARKER + "\n"
        + editable_yaml
        + self.EDITABLE_END_MARKER + "\n"
        + post_marker
    )

    # 备份原文件
    if self._backup_enabled and file_path.exists():
        backup_path = file_path.with_suffix(file_path.suffix + ".bak")
        shutil.copy2(file_path, backup_path)

    # 原子写入：先写临时文件，再替换
    temp_path = file_path.with_suffix(file_path.suffix + ".tmp")
    try:
        temp_path.write_text(full_content, encoding="utf-8")
        temp_path.replace(file_path)
    except Exception:
        # 清理临时文件
        if temp_path.exists():
            temp_path.unlink()
        raise
```

**去重检查**：

```python
def _check_duplicate(self, data: dict, intent: EditIntent) -> bool:
    """去重检查：判断新偏好是否与已有条目重复。"""
    category_list = data.get(intent.category.value, [])
    if not isinstance(category_list, list):
        return False
    # 简单字符串匹配去重（精确匹配）
    normalized_value = intent.value.strip().lower()
    for item in category_list:
        if isinstance(item, str) and item.strip().lower() == normalized_value:
            return True
    return False
```

**审计日志**：

```python
def _record_audit(self, relative_path: str, intent: EditIntent, session_id: str) -> None:
    """记录审计日志到 JSONL 文件。"""
    audit_path = self._data_dir / "edit_audit.jsonl"
    entry = AuditLogEntry(
        timestamp=time.time() * 1000,
        session_id=session_id,
        file_path=relative_path,
        action=intent.action.value,
        category=intent.category.value,
        value=intent.value,
        old_value=intent.old_value,
        source=intent.source.value,
    )
    line = json.dumps(asdict(entry), ensure_ascii=False)
    try:
        with open(audit_path, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception as e:
        logger.warning("[proactive-chat] 审计日志写入失败(%s): %s", type(e).__name__, e)
```

**用户偏好文件默认内容**：

```yaml
# --- editable start ---
likes: []
dislikes: []
habits: []
rules: []
# --- editable end ---
```

### 1.3.3 偏好自动读取与注入（修改 `agent_chat.py`）

**设计思路**：在会话创建时自动读取用户偏好文件，构建偏好摘要注入系统提示词。写入新偏好后即时更新内存缓存，无需重新读取文件。偏好摘要使用简洁的结构化格式，不超过 500 Token。

**偏好摘要构建**：

```python
def _build_preference_summary(self, preferences: dict) -> str:
    """构建偏好摘要，注入系统提示词。

    Args:
        preferences: 偏好数据，如 {"likes": ["Python"], "dislikes": [], "habits": ["晚上写代码"], "rules": []}

    Returns:
        偏好摘要文本，如 "[用户偏好] 喜欢：Python；习惯：晚上写代码"
        空偏好返回空字符串
    """
    if not preferences:
        return ""

    parts = []
    category_labels = {
        "likes": "喜欢",
        "dislikes": "不喜欢",
        "habits": "习惯",
        "rules": "规则",
    }

    for key, label in category_labels.items():
        items = preferences.get(key, [])
        if items and isinstance(items, list):
            parts.append(f"{label}：{', '.join(str(i) for i in items)}")

    if not parts:
        return ""

    summary = "[用户偏好] " + "；".join(parts)

    # Token 预算截断（简单估算：1 中文字 ≈ 1.5 token）
    config = self._config_getter() if self._config_getter else None
    token_limit = config.agent_chat.preference_summary_token_limit if config else 500
    estimated_tokens = len(summary) * 1.2  # 粗略估算
    if estimated_tokens > token_limit:
        # 按优先级截断：rules > habits > dislikes > likes
        priority_order = ["rules", "habits", "dislikes", "likes"]
        while estimated_tokens > token_limit and parts:
            # 移除最低优先级的非空分类
            for cat in reversed(priority_order):
                cat_label = category_labels[cat]
                for i, p in enumerate(parts):
                    if p.startswith(cat_label):
                        parts.pop(i)
                        break
                else:
                    continue
                break
            summary = "[用户偏好] " + "；".join(parts)
            estimated_tokens = len(summary) * 1.2

    return summary
```

**会话创建时自动读取偏好**：

修改 `create_session()` 方法，在创建会话后读取偏好文件并缓存：

```python
async def create_session(
    self,
    stream_context_id: str = "",
) -> AgentChatSession:
    session = AgentChatSession(
        session_id=uuid.uuid4().hex[:16],
        created_at=time.time(),
        last_active_at=time.time(),
        stream_context_id=stream_context_id,
    )

    if len(self._sessions) >= 5:
        oldest_id = min(self._sessions, key=lambda k: self._sessions[k].last_active_at)
        del self._sessions[oldest_id]

    if stream_context_id:
        await self._inject_stream_context(session, stream_context_id)

    # v3.4: 读取偏好文件并缓存
    self._preference_cache = self._load_preferences()

    self._sessions[session.session_id] = session
    return session
```

**偏好内存缓存**：

```python
class AgentChatService:

    def __init__(self, ...) -> None:
        # ... 现有初始化 ...
        self._preference_cache: dict = {}  # v3.4: 偏好内存缓存
        self._file_editor: FileEditor | None = None  # v3.4

    def _load_preferences(self) -> dict:
        """从偏好文件加载偏好数据到内存缓存。"""
        if not self._file_editor:
            return {}
        data = self._file_editor.read_file("user_preferences.yaml")
        return data or {}

    def _update_preference_cache(self, category: str, value: str, action: str) -> None:
        """写入偏好后即时更新内存缓存。"""
        if not isinstance(self._preference_cache, dict):
            self._preference_cache = {}
        category_list = self._preference_cache.get(category, [])
        if not isinstance(category_list, list):
            category_list = []
        if action == "add" and value not in category_list:
            category_list.append(value)
        elif action == "remove" and value in category_list:
            category_list.remove(value)
        elif action == "update":
            # update 需要替换旧值
            pass  # 通过重新加载处理
        self._preference_cache[category] = category_list
```

### 1.3.4 消息处理流程重构（修改 `agent_chat.py`）

**设计思路**：修改 `send_message()` 方法，在构建系统提示词时注入偏好摘要，在 LLM 回复后解析编辑意图并执行文件编辑。如果编辑意图执行成功，将编辑结果反馈给 LLM 生成最终回复（二次 LLM 调用）；如果无需编辑，直接返回 LLM 回复。

**`send_message()` 重构**：

```python
async def send_message(
    self,
    session_id: str,
    user_content: str,
    config: ProactiveChatConfig,
    bot_nickname: str = "",
    personality: str = "",
    alias_names: list[str] | None = None,
    reply_style: str = "",
    custom_prompt: str = "",
) -> AgentChatMessage:
    session = self._sessions.get(session_id)
    if not session:
        session = await self.create_session()
        session_id = session.session_id

    if session.is_responding:
        raise RuntimeError("会话正在响应中，请等待完成")

    user_msg = AgentChatMessage(
        role="user",
        content=user_content[:4000],
        timestamp=time.time() * 1000,
    )
    session.messages.append(user_msg)

    self._auto_cleanup_if_needed(session, config)

    # v3.4: 构建偏好摘要
    preference_summary = ""
    if self._preference_cache:
        preference_summary = self._build_preference_summary(self._preference_cache)

    from .prompts import build_chat_system_prompt
    system_prompt = build_chat_system_prompt(
        bot_nickname=bot_nickname,
        alias_names=alias_names,
        personality=personality,
        reply_style=reply_style,
        custom_prompt=custom_prompt,
        preference_summary=preference_summary,  # v3.4
    )

    messages = [{"role": "system", "content": system_prompt}]
    for msg in session.messages:
        if msg.role in ("user", "assistant"):
            messages.append({"role": msg.role, "content": msg.content})

    session.is_responding = True
    try:
        response_text = await self._deepseek.analyze_with_messages(
            messages=messages,
            model=config.deepseek.deepseek_model,
            temperature=config.agent_chat.chat_temperature,
            max_tokens=config.agent_chat.chat_max_tokens,
        )
    except Exception as e:
        session.is_responding = False
        logger.warning("[proactive-chat] 智能体对话 LLM 调用失败(%s): %s", type(e).__name__, e)
        raise
    finally:
        session.is_responding = False

    # v3.4: 解析编辑意图
    edit_intent_dict, cleaned_response = parse_edit_intent(response_text)
    final_response = cleaned_response

    if edit_intent_dict and config.agent_chat.file_edit_enabled:
        edit_result = self._execute_edit_intent(edit_intent_dict, session_id, config)
        if edit_result.success:
            # 更新偏好缓存
            self._update_preference_cache(
                edit_intent_dict["category"],
                edit_intent_dict["value"],
                edit_intent_dict["action"],
            )
        elif edit_result.is_duplicate:
            # 去重：修改回复中的确认信息
            final_response = cleaned_response  # 保持原回复，LLM 应已处理去重
        else:
            # 编辑失败：在回复中追加失败信息
            final_response = cleaned_response + f"\n\n⚠ {edit_result.message}"

    assistant_msg = AgentChatMessage(
        role="assistant",
        content=final_response,
        timestamp=time.time() * 1000,
    )
    session.messages.append(assistant_msg)
    session.last_active_at = time.time()
    session.token_estimate = self._estimate_session_tokens(session)

    try:
        import asyncio
        asyncio.create_task(self._event_bus.publish("agent_chat_response", session_id, {
            "session_id": session_id,
            "content": final_response,
            "token_estimate": session.token_estimate,
            "edit_performed": edit_intent_dict is not None and config.agent_chat.file_edit_enabled,
        }))
    except Exception:
        pass

    return assistant_msg
```

**编辑意图执行**：

```python
def _execute_edit_intent(
    self,
    intent_dict: dict,
    session_id: str,
    config: ProactiveChatConfig,
) -> EditResult:
    """执行编辑意图。"""
    if not self._file_editor:
        return EditResult(success=False, message="文件编辑服务不可用")

    try:
        intent = EditIntent(
            action=EditAction(intent_dict["action"]),
            category=EditCategory(intent_dict["category"]),
            value=str(intent_dict["value"]),
            source=EditSource(intent_dict["source"]),
            old_value=str(intent_dict.get("old_value", "")),
        )
    except (ValueError, KeyError) as e:
        logger.warning("[proactive-chat] 编辑意图转换失败(%s): %s", type(e).__name__, e)
        return EditResult(success=False, message=f"编辑意图格式无效: {e}")

    # 确定目标文件（当前仅支持 user_preferences.yaml）
    target_file = "user_preferences.yaml"
    if not self._file_editor.validate_path(target_file):
        return EditResult(success=False, message="目标文件不在白名单中")

    result = self._file_editor.execute_edit(
        relative_path=target_file,
        intent=intent,
        session_id=session_id,
    )

    return result
```

### 1.3.5 配置扩展（修改 `config.py`）

**设计思路**：在 `AgentChatConfig` 中新增 5 个配置项，配置版本升级到 `3.4.0`。

```python
class AgentChatConfig(PluginConfigBase):
    __ui_label__ = "智能体对话"
    __ui_icon__ = "message-circle"
    __ui_order__ = 14

    agent_chat_enabled: bool = Field(
        default=False,
        description="是否启用 WebUI 智能体对话",
    )
    chat_max_tokens: int = Field(
        default=500, ge=100, le=2000,
        description="智能体对话 LLM 调用的最大 token 数",
    )
    chat_max_sessions: int = Field(
        default=5, ge=1, le=20,
        description="最大同时活跃会话数",
    )
    chat_session_token_limit: int = Field(
        default=800000, ge=100000, le=900000,
        description="会话自动清除的 token 阈值",
    )
    chat_temperature: float = Field(
        default=0.7, ge=0.0, le=2.0,
        description="智能体对话的 LLM 温度",
    )
    # v3.4 新增
    file_edit_enabled: bool = Field(
        default=False,
        description="是否启用智能体文件编辑能力",
    )
    editable_files: list[str] = Field(
        default_factory=lambda: ["user_preferences.yaml"],
        description="可编辑文件白名单（相对于插件数据目录的文件路径）",
    )
    edit_backup_enabled: bool = Field(
        default=True,
        description="是否启用编辑前备份",
    )
    auto_preference_enabled: bool = Field(
        default=True,
        description="是否启用智能体主动偏好识别",
    )
    preference_summary_token_limit: int = Field(
        default=500, ge=100, le=2000,
        description="偏好摘要注入系统提示词的最大 Token 数",
    )
```

**PluginSectionConfig 版本升级**：

```python
class PluginSectionConfig(PluginConfigBase):
    # ...
    config_version: str = Field(default="3.4.0", description="配置版本")
```

### 1.3.6 WebUI send 端点扩展（修改 `webui.py`）

**设计思路**：扩展 `POST /agent/chat/send` 端点的返回值，新增 `edit_performed` 字段，指示本次回复是否包含文件编辑操作。

**`_handle_agent_chat_send()` 修改**：

```python
async def _handle_agent_chat_send(self, request: web.Request) -> web.Response:
    if error_resp := self._check_agent_chat_enabled():
        return error_resp
    try:
        body = await request.json()
        session_id = body.get("session_id", "")
        content = body.get("content", "")
        if not session_id or not content:
            return web.json_response({"success": False, "error": "缺少 session_id 或 content"})

        config = self._config_getter() if self._config_getter else None
        if not config:
            return web.json_response({"success": False, "error": "配置不可用"})

        # 获取角色信息
        bot_nickname = ""
        personality = ""
        alias_names = []
        reply_style = ""
        custom_prompt = config.prompt.custom_prompt
        # ... 从配置中获取角色信息 ...

        result = await self._agent_chat_service.send_message(
            session_id=session_id,
            user_content=content,
            config=config,
            bot_nickname=bot_nickname,
            personality=personality,
            alias_names=alias_names,
            reply_style=reply_style,
            custom_prompt=custom_prompt,
        )

        return web.json_response({
            "success": True,
            "content": result.content,
            "timestamp": result.timestamp,
            "edit_performed": getattr(result, '_edit_performed', False),  # v3.4
        })
    except Exception as e:
        return web.json_response({"success": False, "error": str(e)})
```

### 1.3.7 聊天界面布局改进（修改前端文件）

**设计思路**：修复输入区域不固定、消息计数不同步、清除按钮易误触三个问题，同时优化空会话提示和输入框占位符。

#### 1.3.7.1 输入区域固定底部（修改 `style.css`）

**核心 CSS 变更**：

```css
/* 对话区域使用 flex 布局，填满可用空间 */
#agent-chat-main {
    display: flex;
    height: calc(100vh - 140px);
    min-height: 400px;
}

/* chat-area 使用 flex 列布局 */
#chat-area {
    display: flex;
    flex-direction: column;
    height: 100%;
    position: relative;
}

/* 消息区域：flex:1 填充剩余空间，可滚动 */
.chat-messages {
    flex: 1;
    overflow-y: auto;
    padding: 16px;
    min-height: 0; /* 关键：允许 flex 子元素收缩 */
}

/* 输入区域：固定在底部，不随消息滚动 */
.chat-input-area {
    flex-shrink: 0;
    padding: 12px 16px;
    border-top: 1px solid var(--border);
    background: var(--card);
}
```

#### 1.3.7.2 消息计数同步（修改 `app.js`）

**设计思路**：前端优先使用本地缓存的消息数量 `currentChatMessages.length`，而非后端返回的 `message_count`。

**`updateChatSessionInfo()` 修改**：

```javascript
function updateChatSessionInfo(sid) {
    const s = agentChatSessions.find(x => x.session_id === sid);
    if (!s) {
        document.getElementById('chat-session-info').textContent = '';
        return;
    }
    const parts = [s.session_id.substring(0, 8) + '...'];
    if (s.stream_context_id) {
        const name = getStreamDisplayName(s.stream_context_id);
        parts.push('关联: ' + name);
    }
    // v3.4: 优先使用本地缓存的消息数量
    const localCount = currentChatMessages.length;
    parts.push(localCount + '条消息');
    document.getElementById('chat-session-info').textContent = parts.join(' · ');
}
```

**`renderSessionList()` 中消息计数也使用本地缓存**：

```javascript
// 在 renderSessionList() 中，当前活跃会话的消息数使用缓存
function renderSessionList() {
    // ... 现有逻辑 ...
    el.innerHTML = sorted.map(s => {
        // ...
        // v3.4: 当前会话使用本地缓存数量
        const cnt = s.session_id === currentChatSessionId
            ? currentChatMessages.length
            : (s.message_count || 0);
        // ...
    }).join('');
}
```

#### 1.3.7.3 清除按钮防误触（修改 `index.html` + `app.js`）

**设计思路**：将会话信息栏的"清除会话"按钮改为下拉菜单中的选项，降低误触概率。

**HTML 结构调整**（`index.html` 中 `chat-header` 区域）：

```html
<div class="chat-header">
    <span id="chat-session-info">会话信息</span>
    <div class="chat-header-actions">
        <button class="chat-more-btn" onclick="toggleChatMenu()" title="更多操作">⋮</button>
        <div id="chat-action-menu" class="chat-action-menu" style="display:none">
            <button class="chat-menu-item" onclick="clearAgentChatSession()">清除会话</button>
        </div>
    </div>
</div>
```

**CSS 新增**：

```css
.chat-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 8px 16px;
    border-bottom: 1px solid var(--border);
    background: var(--card);
    flex-shrink: 0;
}
.chat-header-actions {
    position: relative;
}
.chat-more-btn {
    background: none;
    border: 1px solid var(--border);
    color: var(--text2);
    font-size: 1.1rem;
    padding: 2px 8px;
    border-radius: 4px;
    cursor: pointer;
}
.chat-more-btn:hover {
    background: var(--bg);
    color: var(--text);
}
.chat-action-menu {
    position: absolute;
    right: 0;
    top: 100%;
    margin-top: 4px;
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 6px;
    min-width: 120px;
    box-shadow: 0 4px 12px rgba(0,0,0,.3);
    z-index: 20;
}
.chat-menu-item {
    display: block;
    width: 100%;
    padding: 8px 12px;
    background: none;
    border: none;
    color: var(--red);
    font-size: .85rem;
    text-align: left;
    cursor: pointer;
}
.chat-menu-item:hover {
    background: rgba(225,112,85,.1);
}
```

**JS 新增**：

```javascript
function toggleChatMenu() {
    const menu = document.getElementById('chat-action-menu');
    if (!menu) return;
    menu.style.display = menu.style.display === 'none' ? 'block' : 'none';
}

// 点击页面其他区域关闭菜单
document.addEventListener('click', function(e) {
    const menu = document.getElementById('chat-action-menu');
    const btn = document.querySelector('.chat-more-btn');
    if (menu && menu.style.display !== 'none' && !menu.contains(e.target) && e.target !== btn) {
        menu.style.display = 'none';
    }
});
```

#### 1.3.7.4 空会话提示和输入框占位符优化

**`renderChatMessages()` 修改**：

```javascript
function renderChatMessages() {
    const el = document.getElementById('chat-messages');
    if (currentChatMessages.length === 0) {
        el.innerHTML = '<div class="chat-empty-hint">输入指令开始，例如：记住我喜欢XX</div>';
        return;
    }
    // ... 现有消息渲染逻辑 ...
}
```

**`index.html` 中 textarea 占位符修改**：

```html
<textarea id="chat-input" placeholder="输入指令... (Enter 发送, Shift+Enter 换行)" rows="2"
    onkeydown="handleChatKeydown(event)"></textarea>
```

### 1.3.8 FileEditor 初始化（修改 `plugin.py`）

**设计思路**：在插件 `on_load` 中初始化 FileEditor 并注入到 AgentChatService。

```python
# plugin.py on_load 中新增
from .file_editor import FileEditor

# 初始化 FileEditor
data_dir = Path(self._persistence._data_dir) if hasattr(self._persistence, '_data_dir') else Path("data")
file_editor = FileEditor(
    data_dir=data_dir,
    editable_files=config.agent_chat.editable_files,
    backup_enabled=config.agent_chat.edit_backup_enabled,
)

# 注入到 AgentChatService
self._agent_chat_service._file_editor = file_editor
```

# 2. 接口设计

## 2.1 总体设计

v3.4 扩展 1 个 API 端点的返回值，不新增端点。所有文件编辑操作在 `AgentChatService` 内部完成，通过 LLM 输出的编辑意图驱动，对外表现为 `send` 端点返回值的变化。

## 2.2 接口清单

| 接口 | 方法 | 路径 | 变更 |
|------|------|------|------|
| 发送消息 | POST | `/api/proactive-chat/agent/chat/send` | 返回值新增 `edit_performed` 字段 |
| 会话列表 | GET | `/api/proactive-chat/agent/chat/sessions` | 无变更 |
| 创建会话 | POST | `/api/proactive-chat/agent/chat/sessions` | 无变更 |
| 清除会话 | POST | `/api/proactive-chat/agent/chat/sessions/{id}/clear` | 无变更 |
| 配置读取 | GET | `/api/proactive-chat/config` | 返回值新增 5 个 `agent_chat` 字段 |
| 配置更新 | POST | `/api/proactive-chat/config` | 支持新增 5 个 `agent_chat` 字段的写入 |

### 2.2.1 send 端点返回值扩展

**v3.3.1 返回值**：
```json
{
    "success": true,
    "content": "已记住：你喜欢 Python",
    "timestamp": 1719561600000
}
```

**v3.4 返回值**：
```json
{
    "success": true,
    "content": "已记住：你喜欢 Python",
    "timestamp": 1719561600000,
    "edit_performed": true
}
```

`edit_performed`：布尔值，指示本次回复是否触发了文件编辑操作。前端可据此在消息气泡上显示编辑标识（可选，v3.4 不强制要求前端处理此字段）。

# 3. 数据模型

## 3.1 设计目标

1. 用户偏好文件使用 YAML 格式，结构清晰，人工可读可编辑
2. 编辑区域标记保护文件头部/尾部的非编辑内容
3. 审计日志使用 JSONL 格式，每行一条记录，便于追加和解析
4. 编辑意图使用 JSON 格式，LLM 输出 → 后端解析，结构严格校验

## 3.2 模型实现

### 3.2.1 用户偏好文件（`user_preferences.yaml`）

```yaml
# --- editable start ---
likes:
  - Python
  - VSCode
  - 深色主题
dislikes:
  - 早起
habits:
  - 晚上写代码
rules:
  - 总是先写测试再写代码
# --- editable end ---
```

**文件路径**：`{插件数据目录}/user_preferences.yaml`

**默认内容**（文件不存在时自动创建）：

```yaml
# --- editable start ---
likes: []
dislikes: []
habits: []
rules: []
# --- editable end ---
```

### 3.2.2 编辑审计日志（`edit_audit.jsonl`）

```json
{"timestamp": 1719561600000, "session_id": "a1b2c3d4e5f67890", "file_path": "user_preferences.yaml", "action": "add", "category": "likes", "value": "Python", "old_value": "", "source": "explicit"}
{"timestamp": 1719561610000, "session_id": "a1b2c3d4e5f67890", "file_path": "user_preferences.yaml", "action": "add", "category": "habits", "value": "晚上写代码", "old_value": "", "source": "auto"}
```

**文件路径**：`{插件数据目录}/edit_audit.jsonl`

### 3.2.3 编辑意图 JSON 结构

```json
{
    "action": "add",
    "category": "likes",
    "value": "Python",
    "source": "explicit",
    "old_value": ""
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| action | string | 是 | 操作类型：add / remove / update |
| category | string | 是 | 分类：likes / dislikes / habits / rules |
| value | string | 是 | 条目值 |
| source | string | 是 | 来源：explicit / auto |
| old_value | string | 否 | 被 replace/remove 的旧值 |