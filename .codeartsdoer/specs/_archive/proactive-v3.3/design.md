# 1. 实现模型

## 1.1 上下文视图

v3.2 的决策循环为 **ReAct 循环驱动的多轮推理 + 感知增强 + 步骤分类/循环检测**：

```
perceive（+话题追踪 + 情感分析 + 参与者画像 + 记忆增强注入）
  → ReAct 循环（+步骤分类器 + 循环检测 + reasoning_effort 自适应 + strict 模式 + SSE 超时重试 + DeepSeek 专用 prompt + 上下文感知压缩 + 自适应步数）
  → [反思子智能体]（+多维度评估）
  → act
  → reflect（+决策质量统计）
```

v3.3 在此基础上新增三大方向增强与修复：

```
perceive（+时间感知注入）           ← 新增：直接集成到 perceive 流程
  → ReAct 循环（不变）
  → [反思子智能体]（不变）
  → act
  → reflect（不变）

WebUI（+智能体对话 Tab）            ← 新增
AgentChatService（+聊天流上下文注入修复 + agent_chat_enabled 开关检查）  ← 修复
```

核心变化：
- 新增 `time_awareness.py` 模块，实现时间感知注入（当前时间、时间段分类、决策倾向、时间间隔），**直接集成到 perceive 流程中，始终启用**
- 扩展 `agent.py`，在 perceive 阶段直接调用时间感知模块
- 扩展 `prompts.py`，新增时间感知提示词模板
- 扩展 `agent_chat.py`，修复 `_inject_stream_context` 空实现，新增 `agent_chat_enabled` 开关检查
- 扩展 `webui_static/index.html`、`app.js`、`style.css`，新增智能体对话 Tab
- 扩展 `config.py`，新增时间边界配置项，配置版本直接升级到 `3.3.0`
- 扩展 `plugin.py`，初始化时间感知模块

## 1.2 服务/组件总体架构

```
plugin.py (入口，扩展 on_load 初始化)
  ├── AgentCore (agent.py，扩展 perceive 阶段集成时间感知)
  │     ├── AgentToolRegistry (agent_tools.py，不变)
  │     ├── EventBus (event_bus.py，不变)
  │     ├── ContextCompressor (context_compressor.py，不变)
  │     ├── OverflowManager (overflow_manager.py，不变)
  │     ├── AgentMemory (agent_memory.py，不变)
  │     ├── StepClassifier (step_classifier.py，不变)
  │     ├── LoopDetector (loop_detector.py，不变)
  │     ├── PerceptionEnhancer (perception_enhancer.py，不变)
  │     ├── QualityStats (quality_stats.py，不变)
  │     └── TimeAwareness (time_awareness.py，新增)     ← v3.3
  │           ├── 当前时间获取与格式化
  │           ├── 时间段分类（7 段，基于配置边界）
  │           ├── 时间段决策倾向生成
  │           ├── 时间间隔计算（距上次触发/距最后一条消息）
  │           └── 星期感知（工作日/周末）
  ├── CooldownManager (cooldown.py，不变，提供 triggered_at 时间戳)
  ├── DeepSeekClient (deepseek_client.py，不变)
  ├── PersistenceManager (persistence.py，不变)
  ├── WebUIServer (webui.py，扩展 Agent Chat API 开关检查)
  │     └── Agent Chat API（4 个端点，新增 agent_chat_enabled 检查）
  ├── AgentChatService (agent_chat.py，修复 _inject_stream_context + 新增开关检查)
  │     ├── 会话管理（不变）
  │     ├── 消息收发（不变）
  │     └── 聊天流上下文注入（修复空实现）   ← v3.3
  ├── SmartCleaner (smart_cleanup.py，不变)
  └── 新增配置项：
         └── 时间边界配置（安静时段、工作时间边界）
```

## 1.3 实现设计文档

### 1.3.1 时间感知模块（新文件 `time_awareness.py`）

**设计思路**：将时间感知功能独立为 `TimeAwareness` 类，**直接集成到 perceive 阶段**，始终在决策循环启动时生成时间感知信息并注入到用户提示词中。纯本地操作，不调用 LLM，不增加 ReAct 循环的 LLM 调用次数。

时间感知是智能体决策的基础能力，无需开关控制——智能体始终需要知道"现在几点"才能做出合理的时机判断。

**核心数据类**：

```python
from dataclasses import dataclass
from enum import Enum


class TimePeriod(str, Enum):
    """时间段分类枚举。"""
    LATE_NIGHT = "深夜"           # 0:00-quiet_hours_end
    EARLY_MORNING = "清晨"       # quiet_hours_end-work_hours_start
    MORNING_WORK = "上午工作时间" # work_hours_start-12
    LUNCH_BREAK = "午休时间"     # 12-14
    AFTERNOON_WORK = "下午工作时间" # 14-work_hours_end
    EVENING_LEISURE = "傍晚休闲"  # work_hours_end-quiet_hours_start
    NIGHT = "夜间"               # quiet_hours_start-24


@dataclass
class TimeAwarenessInfo:
    """时间感知信息。"""
    current_time_str: str = ""        # 格式化当前时间，如 "2026-06-28 14:30:00（周日）"
    time_period: TimePeriod = TimePeriod.LATE_NIGHT  # 时间段分类
    time_period_desc: str = ""        # 时间段描述，如 "下午工作时间"
    decision_tendency: str = ""       # 时间段决策倾向指导
    is_weekend: bool = False          # 是否为周末
    interval_since_last_trigger: str = ""  # 距上次主动发言的时间间隔描述
    interval_since_last_message: str = ""  # 距最后一条消息的时间间隔描述
```

**核心类**：

```python
class TimeAwareness:
    def __init__(
        self,
        cooldown_manager: CooldownManager,
        config_getter: Callable[[], ProactiveChatConfig] | None = None,
    ) -> None:
        self._cooldown = cooldown_manager
        self._config_getter = config_getter

    def get_time_awareness_info(
        self,
        stream_id: str,
        recent_messages: list[dict] | None = None,
    ) -> TimeAwarenessInfo | None:
        """获取时间感知信息。

        Args:
            stream_id: 聊天流 ID，用于查询冷却记录
            recent_messages: 近期消息列表，用于计算消息时间间隔

        Returns:
            TimeAwarenessInfo 或 None（系统时间不可用时）
        """

    def classify_time_period(self, hour: int) -> TimePeriod:
        """将小时数映射到时间段分类。

        Args:
            hour: 当前小时（0-23）

        Returns:
            TimePeriod 枚举值
        """

    def get_decision_tendency(
        self,
        time_period: TimePeriod,
        is_weekend: bool,
    ) -> str:
        """根据时间段和是否周末生成决策倾向指导。

        Args:
            time_period: 时间段分类
            is_weekend: 是否为周末

        Returns:
            决策倾向指导文本
        """

    def format_for_prompt(self, info: TimeAwarenessInfo) -> str:
        """将时间感知信息格式化为可注入提示词的文本。

        Args:
            info: 时间感知信息

        Returns:
            格式化后的文本，如 "[时间感知] 当前时间：..."
        """

    def _format_interval(self, seconds: float) -> str:
        """将秒数格式化为人类可读的时间间隔描述。

        Args:
            seconds: 秒数

        Returns:
            如 "2小时15分钟"、"5分钟"、"30秒"
        """
```

**时间段分类算法**：

```python
def classify_time_period(self, hour: int) -> TimePeriod:
    config = self._config_getter() if self._config_getter else None

    # 使用配置项定义的时间边界
    quiet_start = config.agent_optimization.quiet_hours_start if config else 22
    quiet_end = config.agent_optimization.quiet_hours_end if config else 6
    work_start = config.agent_optimization.work_hours_start if config else 9
    work_end = config.agent_optimization.work_hours_end if config else 18

    # 深夜：0:00 到 quiet_hours_end
    if 0 <= hour < quiet_end:
        return TimePeriod.LATE_NIGHT
    # 清晨：quiet_hours_end 到 work_hours_start
    if quiet_end <= hour < work_start:
        return TimePeriod.EARLY_MORNING
    # 上午工作时间：work_hours_start 到 12
    if work_start <= hour < 12:
        return TimePeriod.MORNING_WORK
    # 午休时间：12 到 14
    if 12 <= hour < 14:
        return TimePeriod.LUNCH_BREAK
    # 下午工作时间：14 到 work_hours_end
    if 14 <= hour < work_end:
        return TimePeriod.AFTERNOON_WORK
    # 傍晚休闲：work_end 到 quiet_hours_start
    if work_end <= hour < quiet_start:
        return TimePeriod.EVENING_LEISURE
    # 夜间：quiet_hours_start 到 24
    return TimePeriod.NIGHT
```

**决策倾向映射**：

```python
_TENDENCY_MAP: dict[TimePeriod, str] = {
    TimePeriod.LATE_NIGHT: "当前是深夜时段，大多数人已休息，除非有紧急的漏回补答场景，否则不应主动发言",
    TimePeriod.EARLY_MORNING: "当前是清晨时段，人们可能刚开始一天，应避免主动发言打扰",
    TimePeriod.MORNING_WORK: "当前是工作时间，人们可能正在忙碌，发言应谨慎，优先处理漏回补答",
    TimePeriod.LUNCH_BREAK: "当前是午休休闲时段，人们可能更愿意聊天，可以更积极地参与对话",
    TimePeriod.AFTERNOON_WORK: "当前是工作时间，人们可能正在忙碌，发言应谨慎，优先处理漏回补答",
    TimePeriod.EVENING_LEISURE: "当前是休闲时段，人们可能更愿意聊天，可以更积极地参与对话",
    TimePeriod.NIGHT: "当前是夜间时段，人们可能准备休息，应逐渐减少发言",
}

_WEEKEND_TENDENCY_SUFFIX = "（周末休闲时段，可适当更积极发言）"

def get_decision_tendency(self, time_period: TimePeriod, is_weekend: bool) -> str:
    base = _TENDENCY_MAP.get(time_period, "")
    # 周末的休闲时段追加更积极的倾向
    if is_weekend and time_period in (
        TimePeriod.LUNCH_BREAK,
        TimePeriod.EVENING_LEISURE,
        TimePeriod.MORNING_WORK,
        TimePeriod.AFTERNOON_WORK,
    ):
        base += _WEEKEND_TENDENCY_SUFFIX
    return base
```

**时间间隔计算**：

```python
def get_time_awareness_info(self, stream_id, recent_messages=None):
    try:
        now = time.time()
        now_dt = datetime.now()
    except Exception:
        logger.warning("[proactive-chat] 系统时间不可用，跳过时间感知注入")
        return None

    hour = now_dt.hour
    weekday = now_dt.weekday()  # 0=周一, 6=周日
    is_weekend = weekday >= 5

    time_period = self.classify_time_period(hour)
    tendency = self.get_decision_tendency(time_period, is_weekend)

    # 当前时间格式化
    weekday_names = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    current_time_str = now_dt.strftime("%Y-%m-%d %H:%M:%S") + f"（{weekday_names[weekday]}）"

    # 距上次主动触发的时间间隔
    interval_trigger = ""
    record = self._cooldown._records.get(stream_id)
    if record and record.triggered_at > 0:
        elapsed = now - record.triggered_at
        interval_trigger = self._format_interval(elapsed)
    else:
        interval_trigger = "无记录"

    # 距最后一条消息的时间间隔
    interval_message = ""
    if recent_messages:
        last_ts = 0.0
        for msg in recent_messages:
            ts = msg.get("timestamp", 0)
            if isinstance(ts, (int, float)) and ts > last_ts:
                last_ts = ts
        if last_ts > 0:
            # timestamp 可能是秒或毫秒
            if last_ts > 1e12:
                last_ts = last_ts / 1000.0
            elapsed = now - last_ts
            if elapsed >= 0:
                interval_message = self._format_interval(elapsed)

    return TimeAwarenessInfo(
        current_time_str=current_time_str,
        time_period=time_period,
        time_period_desc=time_period.value,
        decision_tendency=tendency,
        is_weekend=is_weekend,
        interval_since_last_trigger=interval_trigger,
        interval_since_last_message=interval_message,
    )
```

**提示词格式化**：

```python
def format_for_prompt(self, info: TimeAwarenessInfo) -> str:
    parts = [
        f"[时间感知] 当前时间：{info.current_time_str}，时间段：{info.time_period_desc}",
        f"[决策倾向] {info.decision_tendency}",
    ]

    # 时间间隔信息
    interval_parts = []
    if info.interval_since_last_trigger:
        interval_parts.append(f"距上次主动发言：{info.interval_since_last_trigger}")
    if info.interval_since_last_message:
        interval_parts.append(f"距最后一条消息：{info.interval_since_last_message}")

    if interval_parts:
        parts.append("[时间间隔] " + "；".join(interval_parts))

    return "\n".join(parts)
```

**与现有模块的集成点**：

- `AgentCore.perceive()` 中，**直接调用** `TimeAwareness.get_time_awareness_info()`，将结果格式化后注入到用户提示词——时间感知是 perceive 阶段的标准步骤，无需开关控制
- 时间间隔中的"距上次主动发言"从 `CooldownManager._records` 获取 `triggered_at` 时间戳
- 时间间隔中的"距最后一条消息"从 `perception.recent_messages` 的时间戳计算
- 时间感知注入位置：用户提示词的开头，在感知增强（话题/情感/画像）信息之前

### 1.3.2 聊天流上下文注入修复（修改 `agent_chat.py`）

**设计思路**：修复 `_inject_stream_context` 的空实现，通过 `ctx.message.get_recent()` 获取聊天流近期消息并注入到会话中。同时新增 `agent_chat_enabled` 开关检查。

#### 1.3.2.1 `_inject_stream_context` 修复

**修复前（当前空实现）**：

```python
async def _inject_stream_context(self, session, stream_id):
    try:
        if not hasattr(self._persistence, '_data_dir'):
            return
        from .agent import AgentCore
        recent = []  # ← 空列表，永远不注入
        if recent:
            context_text = "\n".join(
                f"[{msg.get('sender_name', '未知')}] {msg.get('content', '')[:100]}"
                for msg in recent[:5]
            )
            session.messages.append(AgentChatMessage(
                role="system",
                content=f"[聊天流上下文] 以下是该聊天流的近期对话：\n{context_text}",
                timestamp=time.time() * 1000,
            ))
    except Exception as e:
        logger.debug("[proactive-chat] 聊天流上下文注入失败(%s): %s", type(e).__name__, e)
```

**修复后**：

```python
async def _inject_stream_context(
    self,
    session: AgentChatSession,
    stream_id: str,
) -> None:
    """注入聊天流上下文到会话中。

    通过 ctx.message.get_recent() 获取聊天流近期消息，
    格式化后作为 system 角色消息插入到会话消息列表开头。
    """
    if not stream_id:
        return

    try:
        recent = await self._get_recent_messages(stream_id, limit=5)
        if not recent:
            return

        context_text = self._format_stream_context(recent)
        if not context_text:
            return

        session.messages.insert(0, AgentChatMessage(
            role="system",
            content=f"[聊天流上下文] 以下是该聊天流的近期对话：\n{context_text}",
            timestamp=time.time() * 1000,
        ))
        logger.debug(
            "[proactive-chat] 已注入聊天流上下文，会话 %s，消息数: %d",
            session.session_id, len(recent),
        )
    except Exception as e:
        logger.debug("[proactive-chat] 聊天流上下文注入失败(%s): %s", type(e).__name__, e)


async def _get_recent_messages(
    self,
    stream_id: str,
    limit: int = 5,
) -> list[dict]:
    """获取聊天流近期消息。

    Args:
        stream_id: 聊天流 ID
        limit: 最大获取条数

    Returns:
        消息列表，每条消息包含 sender_name、content 等字段
    """
    if not self._message_api:
        logger.debug("[proactive-chat] ctx.message API 不可用，跳过上下文注入")
        return []

    try:
        messages = await self._message_api.get_recent(
            chat_id=stream_id, limit=limit,
        )
        if isinstance(messages, list):
            return messages
        return []
    except Exception as e:
        logger.debug(
            "[proactive-chat] 获取聊天流近期消息失败(%s): %s",
            type(e).__name__, e,
        )
        return []


@staticmethod
def _format_stream_context(recent_messages: list[dict]) -> str:
    """格式化聊天流上下文消息。

    Args:
        recent_messages: 近期消息列表

    Returns:
        格式化后的上下文文本，每条消息一行
    """
    lines = []
    for msg in recent_messages:
        sender_name = msg.get("sender_name", "未知")
        content = msg.get("content", "")
        # 内容截断至 100 字符
        content_summary = content[:100] if content else ""
        if content_summary:
            lines.append(f"[{sender_name}] {content_summary}")

    return "\n".join(lines)
```

**AgentChatService 构造函数变更**：

```python
class AgentChatService:
    def __init__(
        self,
        deepseek_client: DeepSeekClient,
        event_bus: EventBus,
        persistence_manager: PersistenceManager,
        message_api: Any = None,   # ← 新增：ctx.message API 实例
    ) -> None:
        self._deepseek = deepseek_client
        self._event_bus = event_bus
        self._persistence = persistence_manager
        self._message_api = message_api   # ← 新增
        self._sessions: dict[str, AgentChatSession] = {}
```

#### 1.3.2.2 `agent_chat_enabled` 开关检查

**在 WebUI 的 4 个 Agent Chat API 处理方法中新增开关检查**：

```python
def _check_agent_chat_enabled(self) -> web.Response | None:
    """检查智能体对话是否启用，未启用时返回错误响应。

    Returns:
        错误响应（未启用时）或 None（已启用时）
    """
    config = self._config_getter() if self._config_getter else None
    if not config or not config.agent_chat.agent_chat_enabled:
        return web.json_response(
            {"success": False, "error": "智能体对话服务未启用"},
            status=403,
        )
    return None
```

**各 API 端点集成**：

```python
async def _handle_agent_chat_sessions(self, request):
    if error_resp := self._check_agent_chat_enabled():
        return error_resp
    # ... 现有逻辑不变 ...

async def _handle_agent_chat_create(self, request):
    if error_resp := self._check_agent_chat_enabled():
        return error_resp
    # ... 现有逻辑不变 ...

async def _handle_agent_chat_send(self, request):
    if error_resp := self._check_agent_chat_enabled():
        return error_resp
    # ... 现有逻辑不变 ...

async def _handle_agent_chat_clear(self, request):
    if error_resp := self._check_agent_chat_enabled():
        return error_resp
    # ... 现有逻辑不变 ...
```

### 1.3.3 WebUI 智能体对话 Tab（修改前端文件）

**设计思路**：在现有 2 个 Tab（数据面板、配置）基础上，新增第 3 个"智能体对话"Tab。前端代码使用独立的 HTML/CSS/JS 文件，对接已有的 4 个后端 API 端点。

#### 1.3.3.1 HTML 结构（修改 `index.html`）

**Tab 栏扩展**：

```html
<!-- 现有 Tab 栏 -->
<div class="tabs">
  <button class="tab-btn active" onclick="switchTab('dashboard')">数据面板</button>
  <button class="tab-btn" onclick="switchTab('config')">配置</button>
  <!-- v3.3 新增 -->
  <button class="tab-btn" onclick="switchTab('agent-chat')">智能体对话</button>
</div>
```

**智能体对话 Tab 内容区**：

```html
<div class="tab-content" id="tab-agent-chat">
  <!-- 未启用提示（默认隐藏） -->
  <div id="agent-chat-disabled" class="empty-state" style="display:none">
    <p>🔒 智能体对话功能未启用，请在配置中开启 agent_chat.agent_chat_enabled</p>
  </div>

  <!-- 智能体对话主界面（默认隐藏） -->
  <div id="agent-chat-main" style="display:none">
    <!-- 左侧：会话列表 -->
    <div class="chat-sidebar">
      <div class="chat-sidebar-header">
        <h3>会话列表</h3>
        <button class="chat-new-btn" onclick="createAgentChatSession()">+ 新建会话</button>
      </div>
      <div id="agent-chat-sessions" class="chat-session-list">
        <!-- 动态填充 -->
      </div>
    </div>

    <!-- 右侧：对话区域 -->
    <div class="chat-main">
      <!-- 无会话选中时 -->
      <div id="chat-empty" class="empty-state">
        <p>请选择或新建一个会话开始对话</p>
      </div>

      <!-- 对话界面 -->
      <div id="chat-area" style="display:none">
        <!-- 会话信息栏 -->
        <div class="chat-header">
          <span id="chat-session-info">会话信息</span>
          <button class="chat-clear-btn" onclick="clearAgentChatSession()">清除会话</button>
        </div>

        <!-- 消息列表 -->
        <div id="chat-messages" class="chat-messages">
          <!-- 动态填充 -->
        </div>

        <!-- 输入区域 -->
        <div class="chat-input-area">
          <textarea id="chat-input" placeholder="输入消息..." rows="2"
            onkeydown="if(event.key==='Enter'&&!event.shiftKey){event.preventDefault();sendAgentChatMessage()}"></textarea>
          <button id="chat-send-btn" onclick="sendAgentChatMessage()">发送</button>
        </div>
      </div>
    </div>
  </div>

  <!-- 新建会话对话框 -->
  <div id="new-session-dialog" class="dialog-overlay" style="display:none" onclick="hideNewSessionDialog()">
    <div class="trigger-dialog" onclick="event.stopPropagation()">
      <h3>新建智能体会话</h3>
      <div style="margin-bottom:12px">
        <label style="display:block;margin-bottom:6px;color:var(--text2);font-size:.85rem">关联聊天流（可选）</label>
        <select id="new-session-stream" style="width:100%;padding:8px 12px;background:var(--bg);border:1px solid var(--border);color:var(--text);border-radius:6px">
          <option value="">不关联聊天流</option>
        </select>
      </div>
      <div class="actions">
        <button onclick="confirmCreateSession()">创建</button>
        <button onclick="hideNewSessionDialog()" style="background:var(--border)">取消</button>
      </div>
    </div>
  </div>
</div>
```

#### 1.3.3.2 JavaScript 逻辑（修改 `app.js`）

**新增全局状态**：

```javascript
// 智能体对话状态
let agentChatEnabled = false;
let agentChatSessions = [];
let currentChatSessionId = '';
let currentChatMessages = [];
let isChatResponding = false;
```

**核心函数**：

```javascript
/**
 * 加载智能体对话 Tab 内容
 * 检查 agent_chat_enabled 开关，加载会话列表
 */
async function loadAgentChat() {
    // 检查配置中 agent_chat_enabled 状态
    const config = await fetchJSON('/api/proactive-chat/config');
    agentChatEnabled = config.agent_chat?.agent_chat_enabled === true;

    if (!agentChatEnabled) {
        document.getElementById('agent-chat-disabled').style.display = 'block';
        document.getElementById('agent-chat-main').style.display = 'none';
        return;
    }

    document.getElementById('agent-chat-disabled').style.display = 'none';
    document.getElementById('agent-chat-main').style.display = 'flex';
    await loadAgentChatSessions();
}

/**
 * 加载会话列表
 * GET /api/proactive-chat/agent/chat/sessions
 */
async function loadAgentChatSessions() {
    const r = await fetchJSON('/api/proactive-chat/agent/chat/sessions');
    if (!r.success) {
        showToast('加载失败', r.error || '无法获取会话列表');
        return;
    }
    agentChatSessions = r.sessions || [];
    renderSessionList();
}

/**
 * 渲染会话列表
 */
function renderSessionList() {
    const el = document.getElementById('agent-chat-sessions');
    if (!agentChatSessions.length) {
        el.innerHTML = '<div class="empty-state" style="padding:12px;font-size:.8rem">暂无会话</div>';
        return;
    }
    let html = '';
    agentChatSessions.forEach(s => {
        const isActive = s.session_id === currentChatSessionId;
        const time = new Date(s.last_active_at * 1000).toLocaleString('zh-CN', {hour12: false, month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit'});
        const streamLabel = s.stream_context_id ? '🔗 ' + s.stream_context_id.slice(0, 8) + '...' : '';
        html += `<div class="chat-session-item${isActive ? ' active' : ''}" onclick="selectChatSession('${s.session_id}')">
            <div class="session-id">${s.session_id.slice(0, 8)}...</div>
            <div class="session-meta">${time} · ${s.message_count}条${streamLabel ? ' · ' + streamLabel : ''}</div>
        </div>`;
    });
    el.innerHTML = html;
}

/**
 * 选中会话
 */
async function selectChatSession(sessionId) {
    currentChatSessionId = sessionId;
    renderSessionList();
    // 显示对话区域
    document.getElementById('chat-empty').style.display = 'none';
    document.getElementById('chat-area').style.display = 'flex';
    // 加载会话消息
    await loadChatMessages(sessionId);
}

/**
 * 加载会话消息（从会话列表数据中获取）
 */
async function loadChatMessages(sessionId) {
    // 从 sessions API 获取的列表中没有消息内容，需要从 send API 的响应中累积
    // 此处从 session 列表数据中无法获取，清空消息区域
    currentChatMessages = [];
    renderChatMessages();
    // 更新会话信息栏
    const session = agentChatSessions.find(s => s.session_id === sessionId);
    if (session) {
        const info = `会话 ${sessionId.slice(0, 8)}...${session.stream_context_id ? ' · 关联聊天流: ' + session.stream_context_id.slice(0, 8) + '...' : ''}`;
        document.getElementById('chat-session-info').textContent = info;
    }
}

/**
 * 渲染聊天消息
 */
function renderChatMessages() {
    const el = document.getElementById('chat-messages');
    if (!currentChatMessages.length) {
        el.innerHTML = '<div class="empty-state" style="padding:24px;font-size:.85rem">开始对话吧</div>';
        return;
    }
    let html = '';
    currentChatMessages.forEach(msg => {
        const time = new Date(msg.timestamp).toLocaleTimeString('zh-CN', {hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit'});
        if (msg.role === 'user') {
            html += `<div class="chat-bubble user-bubble">
                <div class="bubble-content">${escapeHtml(msg.content)}</div>
                <div class="bubble-time">${time}</div>
            </div>`;
        } else if (msg.role === 'assistant') {
            html += `<div class="chat-bubble assistant-bubble">
                <div class="bubble-content">${escapeHtml(msg.content)}</div>
                <div class="bubble-time">${time}</div>
            </div>`;
        } else if (msg.role === 'system') {
            html += `<div class="chat-bubble system-bubble">
                <div class="bubble-content">${escapeHtml(msg.content)}</div>
            </div>`;
        }
    });
    el.innerHTML = html;
    el.scrollTop = el.scrollHeight;
}

/**
 * 发送消息
 * POST /api/proactive-chat/agent/chat/send
 */
async function sendAgentChatMessage() {
    const input = document.getElementById('chat-input');
    const content = input.value.trim();
    if (!content || isChatResponding) return;

    if (!currentChatSessionId) {
        showToast('提示', '请先选择或创建一个会话');
        return;
    }

    // 添加用户消息到界面
    currentChatMessages.push({
        role: 'user',
        content: content,
        timestamp: Date.now(),
    });
    renderChatMessages();
    input.value = '';

    // 禁用输入，显示思考状态
    isChatResponding = true;
    document.getElementById('chat-send-btn').disabled = true;
    input.disabled = true;
    currentChatMessages.push({role: 'assistant', content: '思考中...', timestamp: Date.now(), isThinking: true});
    renderChatMessages();

    try {
        const r = await postJSON('/api/proactive-chat/agent/chat/send', {
            session_id: currentChatSessionId,
            content: content,
        });

        // 移除思考状态
        currentChatMessages = currentChatMessages.filter(m => !m.isThinking);

        if (r.success) {
            currentChatMessages.push({
                role: 'assistant',
                content: r.content,
                timestamp: Date.now(),
            });
            // 如果会话 ID 变化（自动创建），更新
            if (r.session_id && r.session_id !== currentChatSessionId) {
                currentChatSessionId = r.session_id;
                await loadAgentChatSessions();
            }
        } else {
            currentChatMessages.push({
                role: 'system',
                content: '❌ 发送失败: ' + (r.error || '未知错误'),
                timestamp: Date.now(),
            });
        }
    } catch (e) {
        currentChatMessages = currentChatMessages.filter(m => !m.isThinking);
        currentChatMessages.push({
            role: 'system',
            content: '❌ 网络错误，请稍后重试',
            timestamp: Date.now(),
        });
    } finally {
        isChatResponding = false;
        document.getElementById('chat-send-btn').disabled = false;
        document.getElementById('chat-input').disabled = false;
        document.getElementById('chat-input').focus();
        renderChatMessages();
    }
}

/**
 * 创建新会话
 * POST /api/proactive-chat/agent/chat/sessions
 */
async function createAgentChatSession() {
    // 显示新建会话对话框，加载聊天流列表
    document.getElementById('new-session-dialog').style.display = 'flex';
    await loadStreamListForNewSession();
}

/**
 * 加载聊天流列表供新建会话选择
 * GET /api/proactive-chat/streams
 */
async function loadStreamListForNewSession() {
    const sel = document.getElementById('new-session-stream');
    sel.innerHTML = '<option value="">不关联聊天流</option>';
    try {
        const r = await fetchJSON('/api/proactive-chat/streams');
        if (r.success && r.streams) {
            r.streams.forEach(s => {
                const opt = document.createElement('option');
                opt.value = s.stream_id;
                opt.textContent = (s.chat_type === 'group' ? '[群聊] ' : '[私聊] ') + s.display_name;
                sel.appendChild(opt);
            });
        }
    } catch (e) {
        // 聊天流列表加载失败不影响创建会话
    }
}

/**
 * 确认创建会话
 */
async function confirmCreateSession() {
    const sel = document.getElementById('new-session-stream');
    const streamContextId = sel.value || '';

    const r = await postJSON('/api/proactive-chat/agent/chat/sessions', {
        stream_context_id: streamContextId,
    });

    if (r.success) {
        hideNewSessionDialog();
        await loadAgentChatSessions();
        await selectChatSession(r.session_id);
        showToast('创建成功', '新会话已创建');
    } else {
        showToast('创建失败', r.error || '未知错误');
    }
}

/**
 * 隐藏新建会话对话框
 */
function hideNewSessionDialog() {
    document.getElementById('new-session-dialog').style.display = 'none';
}

/**
 * 清除会话
 * POST /api/proactive-chat/agent/chat/sessions/{id}/clear
 */
async function clearAgentChatSession() {
    if (!currentChatSessionId) return;
    if (!confirm('确认清除该会话？')) return;

    const r = await postJSON(`/api/proactive-chat/agent/chat/sessions/${currentChatSessionId}/clear`, {});
    if (r.success) {
        currentChatSessionId = '';
        currentChatMessages = [];
        document.getElementById('chat-empty').style.display = 'block';
        document.getElementById('chat-area').style.display = 'none';
        await loadAgentChatSessions();
        showToast('已清除', '会话已删除');
    } else {
        showToast('清除失败', r.error || '未知错误');
    }
}

/**
 * HTML 转义
 */
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}
```

**`switchTab` 函数扩展**：

```javascript
function switchTab(tab) {
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
    document.querySelector('.tab-btn[onclick*="' + tab + '"]').classList.add('active');
    document.getElementById('tab-' + tab).classList.add('active');
    currentTab = tab;
    if (tab === 'config') loadConfig();
    if (tab === 'agent-chat') loadAgentChat();  // ← v3.3 新增
}
```

#### 1.3.3.3 CSS 样式（修改 `style.css`）

**新增智能体对话相关样式**：

```css
/* 智能体对话 Tab 布局 */
#tab-agent-chat #agent-chat-main {
    display: flex;
    gap: 16px;
    height: calc(100vh - 140px);
    min-height: 400px;
}

/* 左侧会话列表 */
.chat-sidebar {
    width: 260px;
    flex-shrink: 0;
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 12px;
    display: flex;
    flex-direction: column;
    overflow: hidden;
}

.chat-sidebar-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 12px 16px;
    border-bottom: 1px solid var(--border);
}

.chat-sidebar-header h3 {
    font-size: .9rem;
    font-weight: 600;
}

.chat-new-btn {
    background: var(--accent);
    color: #fff;
    border: none;
    padding: 4px 12px;
    border-radius: 6px;
    cursor: pointer;
    font-size: .8rem;
}

.chat-new-btn:hover {
    background: var(--accent2);
}

.chat-session-list {
    flex: 1;
    overflow-y: auto;
    padding: 8px;
}

.chat-session-item {
    padding: 10px 12px;
    border-radius: 8px;
    cursor: pointer;
    margin-bottom: 4px;
    transition: background .15s;
}

.chat-session-item:hover {
    background: rgba(108, 92, 231, .08);
}

.chat-session-item.active {
    background: rgba(108, 92, 231, .15);
    border-left: 3px solid var(--accent);
}

.chat-session-item .session-id {
    font-family: monospace;
    font-size: .8rem;
    font-weight: 600;
}

.chat-session-item .session-meta {
    font-size: .7rem;
    color: var(--text2);
    margin-top: 2px;
}

/* 右侧对话区域 */
.chat-main {
    flex: 1;
    display: flex;
    flex-direction: column;
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 12px;
    overflow: hidden;
}

.chat-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 10px 16px;
    border-bottom: 1px solid var(--border);
    font-size: .85rem;
}

.chat-clear-btn {
    background: none;
    border: 1px solid var(--red);
    color: var(--red);
    padding: 4px 12px;
    border-radius: 6px;
    cursor: pointer;
    font-size: .75rem;
}

.chat-clear-btn:hover {
    background: rgba(225, 112, 85, .1);
}

/* 消息列表 */
.chat-messages {
    flex: 1;
    overflow-y: auto;
    padding: 16px;
    display: flex;
    flex-direction: column;
    gap: 12px;
}

/* 聊天气泡 */
.chat-bubble {
    max-width: 75%;
    padding: 10px 14px;
    border-radius: 12px;
    font-size: .875rem;
    line-height: 1.5;
    word-break: break-word;
}

.user-bubble {
    align-self: flex-end;
    background: var(--accent);
    color: #fff;
    border-bottom-right-radius: 4px;
}

.assistant-bubble {
    align-self: flex-start;
    background: var(--border);
    color: var(--text);
    border-bottom-left-radius: 4px;
}

.system-bubble {
    align-self: center;
    background: rgba(108, 92, 231, .08);
    color: var(--text2);
    font-size: .8rem;
    border-radius: 8px;
    max-width: 90%;
    text-align: center;
}

.bubble-time {
    font-size: .65rem;
    opacity: .6;
    margin-top: 4px;
    text-align: right;
}

/* 输入区域 */
.chat-input-area {
    display: flex;
    gap: 8px;
    padding: 12px 16px;
    border-top: 1px solid var(--border);
    align-items: flex-end;
}

.chat-input-area textarea {
    flex: 1;
    background: var(--bg);
    border: 1px solid var(--border);
    color: var(--text);
    padding: 8px 12px;
    border-radius: 8px;
    font-size: .875rem;
    resize: none;
    font-family: inherit;
    line-height: 1.4;
}

.chat-input-area textarea:focus {
    border-color: var(--accent);
    outline: none;
}

.chat-input-area textarea:disabled {
    opacity: .5;
}

#chat-send-btn {
    background: var(--accent);
    color: #fff;
    border: none;
    padding: 8px 20px;
    border-radius: 8px;
    cursor: pointer;
    font-size: .875rem;
    white-space: nowrap;
}

#chat-send-btn:hover:not(:disabled) {
    background: var(--accent2);
}

#chat-send-btn:disabled {
    opacity: .5;
    cursor: not-allowed;
}

/* 响应式 */
@media (max-width: 768px) {
    #tab-agent-chat #agent-chat-main {
        flex-direction: column;
        height: auto;
    }
    .chat-sidebar {
        width: 100%;
        max-height: 200px;
    }
    .chat-main {
        min-height: 400px;
    }
}
```

### 1.3.4 提示词扩展（修改 `prompts.py`）

**新增时间感知提示词模板**：

```python
TIME_AWARENESS_TEMPLATE = "[时间感知] 当前时间：{current_time}，时间段：{time_period}\n[决策倾向] {decision_tendency}\n[时间间隔] {time_intervals}"
```

**时间感知注入位置**：在 `_react_loop()` 和 `reason()` 中构建用户提示词时，将时间感知信息注入到用户提示词的开头（感知增强信息之前）。

### 1.3.5 AgentCore 集成变更（修改 `agent.py`）

#### perceive 阶段扩展

时间感知直接集成到 perceive 流程中，始终执行：

```python
async def perceive(self, stream_id, ctx, config):
    perception = PerceptionData()
    # ... 现有逻辑不变 ...

    # v3.3 新增：时间感知注入（始终执行）
    time_awareness_text = ""
    if self._time_awareness is not None:
        try:
            time_info = self._time_awareness.get_time_awareness_info(
                stream_id=stream_id,
                recent_messages=perception.recent_messages,
            )
            if time_info is not None:
                time_awareness_text = self._time_awareness.format_for_prompt(time_info)
        except Exception as e:
            logger.debug("[proactive-chat] 时间感知注入失败(%s): %s", type(e).__name__, e)

    # 将时间感知文本暂存，供 _build_prompts / _react_loop 使用
    perception._time_awareness_text = time_awareness_text

    return perception
```

#### PerceptionData 扩展

```python
@dataclass
class PerceptionData:
    recent_messages: list[dict] = field(default_factory=list)
    silence_signal: bool = False
    silence_seconds: int = 0
    missed_reply_signal: bool = False
    memory_result: str = ""
    message_summary: str = ""
    memory_history: str = ""
    topic_info: Any = None
    sentiment_info: Any = None
    participant_profiles: list = field(default_factory=list)
    _time_awareness_text: str = ""  # v3.3 新增：时间感知文本
```

#### _react_loop 用户提示词构建扩展

在 `_react_loop()` 中构建用户提示词时，将时间感知信息注入到最前面：

```python
# 在 _react_loop 中，构建 user_prompt 后：
user_prompt = ANALYSIS_USER_TEMPLATE.format(...)

# v3.3 新增：时间感知注入（始终执行，无需开关）
if perception._time_awareness_text:
    user_prompt = perception._time_awareness_text + "\n\n" + user_prompt

# 感知增强注入（不变）
if self._perception_enhancer is not None:
    ...
```

#### reason 方法扩展

在 `reason()` 方法的 `_build_prompts()` 调用中，同样注入时间感知信息：

```python
async def reason(self, stream_id, perception, config):
    system_prompt, user_prompt = self._build_prompts(perception, config)

    # v3.3 新增：时间感知注入（始终执行，无需开关）
    if perception._time_awareness_text:
        user_prompt = perception._time_awareness_text + "\n\n" + user_prompt

    # ... 现有逻辑不变 ...
```

#### AgentCore 构造函数扩展

```python
class AgentCore:
    def __init__(self, deepseek_client, persistence_manager, cooldown_manager):
        # ... 现有字段不变 ...
        self._time_awareness: Any = None  # v3.3 新增
```

### 1.3.6 配置扩展（修改 `config.py`）

**新增时间边界配置项**：

```python
class AgentOptimizationConfig(PluginConfigBase):
    # ... 现有字段不变 ...

    # v3.3 新增：时间边界配置
    quiet_hours_start: int = Field(
        default=22, ge=0, le=23,
        description="安静时段开始时间（小时，0-23）",
    )
    quiet_hours_end: int = Field(
        default=6, ge=0, le=23,
        description="安静时段结束时间（小时，0-23）",
    )
    work_hours_start: int = Field(
        default=9, ge=0, le=23,
        description="工作时间开始时间（小时，0-23）",
    )
    work_hours_end: int = Field(
        default=18, ge=0, le=23,
        description="工作时间结束时间（小时，0-23）",
    )
```

**config_version 升级**：`3.2.0` → `3.3.0`

### 1.3.7 插件入口变更（修改 `plugin.py`）

**on_load 中初始化时间感知模块**：

```python
async def on_load(self):
    # ... 现有初始化逻辑不变 ...

    # v3.3 新增：时间感知模块初始化
    from .time_awareness import TimeAwareness
    self._time_awareness = TimeAwareness(
        cooldown_manager=self._cooldown_manager,
        config_getter=lambda: self._config,
    )
    self._agent._time_awareness = self._time_awareness

    # v3.3 新增：AgentChatService 传入 message_api
    # 通过 ctx.message 获取聊天流消息
    self._agent_chat_service._message_api = self.ctx.message if hasattr(self.ctx, 'message') else None

    # ... 其余初始化逻辑不变 ...
```

# 2. 接口设计

## 2.1 总体设计

v3.3 不新增后端 API 端点，仅修改已有 Agent Chat API 的行为（新增开关检查）和前端 UI。

## 2.2 接口清单

### 2.2.1 已有 API 变更

| 端点 | 方法 | v3.3 变更 |
|------|------|-----------|
| `/api/proactive-chat/agent/chat/sessions` | GET | 新增 `agent_chat_enabled` 检查，未启用返回 403 |
| `/api/proactive-chat/agent/chat/sessions` | POST | 新增 `agent_chat_enabled` 检查；`_inject_stream_context` 修复后实际注入聊天流上下文 |
| `/api/proactive-chat/agent/chat/send` | POST | 新增 `agent_chat_enabled` 检查 |
| `/api/proactive-chat/agent/chat/sessions/{id}/clear` | POST | 新增 `agent_chat_enabled` 检查 |

### 2.2.2 内部接口变更

| 接口 | 位置 | v3.3 变更 |
|------|------|-----------|
| `TimeAwareness.get_time_awareness_info()` | `time_awareness.py` | 新增，获取时间感知信息 |
| `TimeAwareness.format_for_prompt()` | `time_awareness.py` | 新增，格式化时间感知文本 |
| `AgentChatService._inject_stream_context()` | `agent_chat.py` | 修复空实现，通过 `ctx.message.get_recent()` 获取消息 |
| `AgentChatService._get_recent_messages()` | `agent_chat.py` | 新增，封装 `ctx.message.get_recent()` 调用 |
| `AgentChatService._format_stream_context()` | `agent_chat.py` | 新增，格式化聊天流上下文消息 |
| `WebUIServer._check_agent_chat_enabled()` | `webui.py` | 新增，检查 `agent_chat_enabled` 配置 |

# 4. 数据模型

## 4.1 设计目标

1. 新增 `TimeAwarenessInfo` 数据类，承载时间感知信息
2. 新增 `TimePeriod` 枚举，定义 7 个时间段分类
3. 扩展 `PerceptionData`，新增 `_time_awareness_text` 字段
4. 扩展 `AgentOptimizationConfig`，新增 4 个时间边界配置项
5. 不修改 `DecisionRecord` 格式，不新增持久化字段
6. 不修改 `AgentChatSession` 数据结构

## 4.2 模型实现

### 4.2.1 TimePeriod 枚举

```python
class TimePeriod(str, Enum):
    LATE_NIGHT = "深夜"           # 0:00-quiet_hours_end
    EARLY_MORNING = "清晨"       # quiet_hours_end-work_hours_start
    MORNING_WORK = "上午工作时间" # work_hours_start-12
    LUNCH_BREAK = "午休时间"     # 12-14
    AFTERNOON_WORK = "下午工作时间" # 14-work_hours_end
    EVENING_LEISURE = "傍晚休闲"  # work_hours_end-quiet_hours_start
    NIGHT = "夜间"               # quiet_hours_start-24
```

### 4.2.2 TimeAwarenessInfo 数据类

```python
@dataclass
class TimeAwarenessInfo:
    current_time_str: str = ""        # "2026-06-28 14:30:00（周日）"
    time_period: TimePeriod = TimePeriod.LATE_NIGHT
    time_period_desc: str = ""        # "下午工作时间"
    decision_tendency: str = ""       # 决策倾向指导文本
    is_weekend: bool = False
    interval_since_last_trigger: str = ""  # "2小时15分钟" 或 "无记录"
    interval_since_last_message: str = ""  # "5分钟"
```

### 4.2.3 PerceptionData 扩展

```python
@dataclass
class PerceptionData:
    # ... 现有字段不变 ...
    _time_awareness_text: str = ""  # v3.3 新增
```

### 4.2.4 AgentOptimizationConfig 扩展

```python
class AgentOptimizationConfig(PluginConfigBase):
    # ... 现有字段不变 ...

    # v3.3 新增：时间边界配置
    quiet_hours_start: int = Field(default=22, ge=0, le=23, description="安静时段开始时间（小时）")
    quiet_hours_end: int = Field(default=6, ge=0, le=23, description="安静时段结束时间（小时）")
    work_hours_start: int = Field(default=9, ge=0, le=23, description="工作时间开始时间（小时）")
    work_hours_end: int = Field(default=18, ge=0, le=23, description="工作时间结束时间（小时）")
```

### 4.2.5 AgentChatService 构造函数扩展

```python
class AgentChatService:
    def __init__(
        self,
        deepseek_client: DeepSeekClient,
        event_bus: EventBus,
        persistence_manager: PersistenceManager,
        message_api: Any = None,   # v3.3 新增
    ) -> None:
        # ...
        self._message_api = message_api
```

# 5. 文件变更清单

| 文件 | 变更类型 | 变更内容 |
|------|----------|----------|
| `time_awareness.py` | **新增** | TimePeriod 枚举、TimeAwarenessInfo 数据类、TimeAwareness 类 |
| `agent.py` | 修改 | perceive 阶段直接集成时间感知调用；PerceptionData 新增 `_time_awareness_text`；`_react_loop` 和 `reason` 中注入时间感知文本；构造函数新增 `_time_awareness` 字段 |
| `prompts.py` | 修改 | 新增 `TIME_AWARENESS_TEMPLATE` 常量 |
| `agent_chat.py` | 修改 | 修复 `_inject_stream_context`；新增 `_get_recent_messages`、`_format_stream_context` 方法；构造函数新增 `message_api` 参数 |
| `webui.py` | 修改 | 新增 `_check_agent_chat_enabled` 方法；4 个 Agent Chat API 处理方法新增开关检查 |
| `config.py` | 修改 | `AgentOptimizationConfig` 新增 4 个时间边界配置项；`PluginSectionConfig.config_version` 升级为 `3.3.0` |
| `plugin.py` | 修改 | `on_load` 中初始化 `TimeAwareness` 并注入到 `AgentCore`；`AgentChatService` 传入 `message_api` |
| `webui_static/index.html` | 修改 | Tab 栏新增"智能体对话"按钮；新增 `tab-agent-chat` 内容区（会话列表 + 对话区域 + 新建会话对话框） |
| `webui_static/app.js` | 修改 | 新增智能体对话相关全局状态和函数（`loadAgentChat`、`loadAgentChatSessions`、`renderSessionList`、`selectChatSession`、`sendAgentChatMessage`、`createAgentChatSession`、`clearAgentChatSession` 等）；扩展 `switchTab` |
| `webui_static/style.css` | 修改 | 新增智能体对话 Tab 相关样式（`.chat-sidebar`、`.chat-main`、`.chat-bubble`、`.chat-input-area` 等） |

# 6. 配置变更清单

| 配置段　　　　　　　 | 配置项　　　　　　　| 类型 | 默认值 | 说明　　　　　　　　　　　　　 |
| ----------------------| ---------------------| ------| --------| --------------------------------|
| `agent_optimization` | `quiet_hours_start` | int　| 22　　 | 安静时段开始时间（小时，0-23） |
| `agent_optimization` | `quiet_hours_end`　 | int　| 6　　　| 安静时段结束时间（小时，0-23） |
| `agent_optimization` | `work_hours_start`　| int　| 9　　　| 工作时间开始时间（小时，0-23） |
| `agent_optimization` | `work_hours_end`　　| int　| 18　　 | 工作时间结束时间（小时，0-23） |
| `plugin`　　　　　　 | `config_version`　　| str　| 3.3.0　| 配置版本号升级　　　　　　　　 |
