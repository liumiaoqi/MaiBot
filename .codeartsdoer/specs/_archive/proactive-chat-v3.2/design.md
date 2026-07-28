# 1. 实现模型

## 1.1 上下文视图

当前插件架构（v3.1）的决策循环为 **ReAct 循环驱动的多轮推理 + 思考模式适配**：

```
perceive（+智能体记忆注入）
  → ReAct 循环（+1M 上下文溢出检测 + DeepSeek v4 思考模式 + reasoning_content 回传）
  → [反思子智能体]
  → act
  → reflect
```

v3.2 在此基础上新增两大方向优化，不改变核心决策循环流程：

```
perceive（+话题追踪 + 情感分析 + 参与者画像 + 记忆增强注入）
  → ReAct 循环（+步骤分类器 + 循环检测 + reasoning_effort 自适应 + strict 模式 + SSE 超时重试 + DeepSeek 专用 prompt + 上下文感知压缩 + 自适应步数）
  → [反思子智能体]（+多维度评估）
  → act
  → reflect（+决策质量统计）
```

核心变化：
- 新增 `step_classifier.py` 模块，实现 7 类步骤分类
- 新增 `loop_detector.py` 模块，实现重复步骤签名 + n-gram 文本循环检测
- 新增 `perception_enhancer.py` 模块，实现话题追踪 + 情感分析 + 参与者画像
- 新增 `quality_stats.py` 模块，实现决策质量统计
- 扩展 `deepseek_client.py`，新增 reasoning_effort 自适应调节、strict 模式集成、思考模式参数兼容、SSE 超时与指数退避重试
- 扩展 `agent_memory.py`，新增记忆分类、上下文关联、去重、容量动态调整
- 扩展 `overflow_manager.py`，新增上下文感知压缩
- 扩展 `agent.py`，集成步骤分类器、循环检测、感知增强、自适应步数、反思增强
- 扩展 `prompts.py`，新增 DeepSeek 专用 prompt、场景示例、决策边界条件
- 扩展 `config.py`，新增 2 个配置段
- 扩展 `webui.py`，新增决策质量统计面板

## 1.2 服务/组件总体架构

```
plugin.py (入口，不变)
  ├── AgentCore (agent.py，扩展 perceive + reason + _react_loop + reflect)
  │     ├── AgentToolRegistry (agent_tools.py，不变)
  │     ├── EventBus (event_bus.py，新增 decision_quality / step_classified / loop_detected 事件)
  │     ├── ContextCompressor (context_compressor.py，不变)
  │     ├── OverflowManager (overflow_manager.py，扩展上下文感知压缩)
  │     │     ├── 压力等级计算（v3.1 不变）
  │     │     ├── 软剪枝（v3.1 不变，v3.2 扩展相关性排序）
  │     │     ├── 硬剪枝（v3.1 不变，v3.2 扩展优先级标注）
  │     │     └── 上下文感知压缩（新增，基于感知信号保留相关内容）
  │     ├── AgentMemory (agent_memory.py，扩展增强注入)
  │     │     ├── DecisionRecord 摘要提取 + 衰减（v3.1 不变）
  │     │     ├── 记忆分类（已触发/未触发）
  │     │     ├── 上下文关联排序
  │     │     ├── 语义去重
  │     │     └── 容量动态调整
  │     ├── StepClassifier (step_classifier.py，新增)
  │     │     ├── 7 类步骤分类（final/continue/tool-call/filtered/think-only/invalid/failed）
  │     │     └── 分类驱动的处理策略
  │     ├── LoopDetector (loop_detector.py，新增)
  │     │     ├── 重复步骤签名检测
  │     │     └── n-gram 文本循环检测
  │     ├── PerceptionEnhancer (perception_enhancer.py，新增)
  │     │     ├── TopicTracker（话题追踪）
  │     │     ├── SentimentAnalyzer（情感分析）
  │     │     └── ParticipantProfiler（参与者画像）
  │     └── QualityStats (quality_stats.py，新增)
  │           ├── 滑动窗口统计
  │           ├── 触发准确率 / 误触发率 / 漏触发率估算
  │           └── ReAct 效率指标
  ├── CooldownManager (cooldown.py，不变)
  ├── DeepSeekClient (deepseek_client.py，扩展 v3.2 深度优化)
  │     ├── 思考模式（v3.1 不变）
  │     ├── reasoning_effort 自适应调节（新增）
  │     ├── strict 模式集成（从 v3.1 Beta 正式化）
  │     ├── 思考模式参数兼容（新增）
  │     ├── reasoning_content 回传健壮性增强（新增）
  │     └── SSE 超时检测 + 指数退避重试（新增）
  ├── PersistenceManager (persistence.py，不变)
  ├── WebUIServer (webui.py，扩展决策质量面板)
  ├── SmartCleaner (smart_cleanup.py，不变)
  └── 新增配置段：
        ├── DeepseekOptimizationConfig（DeepSeek 深度优化）
        └── AgentOptimizationConfig（智能体优化）
```

## 1.3 实现设计文档

### 1.3.1 步骤分类器（新文件 `step_classifier.py`）

**设计思路**：借鉴 MiMo-Code 的 `classifyAssistantStep()` 设计，将 ReAct 循环中 LLM 返回的助手步骤分为 7 类，替代 v3.1 的简单 `has_tool_calls` 判断，实现更精细的步骤处理。

**核心数据类**：

```python
from dataclasses import dataclass
from enum import Enum


class StepCategory(str, Enum):
    """步骤分类枚举。"""
    FINAL = "final"           # 最终决策（submit_decision 或无工具调用的决策结果）
    CONTINUE = "continue"     # 继续推理（工具调用 + 继续标志）
    TOOL_CALL = "tool-call"   # 有效工具调用
    FILTERED = "filtered"     # 被过滤的无效输出
    THINK_ONLY = "think-only" # 仅思考无输出（思考模式特有）
    INVALID = "invalid"       # 无效响应
    FAILED = "failed"         # 调用失败


@dataclass
class StepClassification:
    """步骤分类结果。"""
    category: StepCategory = StepCategory.INVALID
    tool_name: str = ""                    # 工具名称，无工具调用时为空
    has_reasoning_content: bool = False    # 是否包含 reasoning_content
    has_content: bool = False              # 是否包含 content
    signature: str = ""                    # 步骤签名（tool_name + 参数哈希）
```

**核心类**：

```python
class StepClassifier:
    def __init__(self, config_getter: Callable[[], ProactiveChatConfig] | None = None) -> None:
        self._config_getter = config_getter

    def classify(
        self,
        response: ThinkingResponse | ToolCallResponse,
        is_thinking_enabled: bool = False,
        error: str = "",
    ) -> StepClassification:
        """对 LLM 响应进行步骤分类。

        Args:
            response: LLM 响应对象（ThinkingResponse 或 ToolCallResponse）
            is_thinking_enabled: 是否启用思考模式
            error: 调用错误信息（非空表示 API 调用失败）
        """

    def _compute_signature(self, tool_name: str, arguments: dict) -> str:
        """计算步骤签名（tool_name + 参数哈希）。"""

    def get_handling_strategy(self, classification: StepClassification) -> str:
        """根据分类结果返回处理策略标识。"""
```

**分类逻辑**：

```python
def classify(self, response, is_thinking_enabled=False, error=""):
    # 1. API 调用失败 → failed
    if error:
        return StepClassification(category=StepCategory.FAILED)

    # 2. 思考模式特有：仅有 reasoning_content，无 content 和 tool_calls → think-only
    if is_thinking_enabled and response.reasoning_content and not response.content and not response.has_tool_calls:
        return StepClassification(
            category=StepCategory.THINK_ONLY,
            has_reasoning_content=True,
            has_content=False,
        )

    # 3. 无效响应：content 和 tool_calls 均为空 → invalid
    if not response.content and not response.has_tool_calls:
        return StepClassification(category=StepCategory.INVALID)

    # 4. 包含工具调用 → tool-call
    if response.has_tool_calls:
        tc = response.tool_calls[0]  # 主工具调用
        signature = self._compute_signature(tc.name, tc.arguments)
        return StepClassification(
            category=StepCategory.TOOL_CALL,
            tool_name=tc.name,
            has_reasoning_content=bool(response.reasoning_content) if isinstance(response, ThinkingResponse) else False,
            has_content=bool(response.content),
            signature=signature,
        )

    # 5. 包含 content 且无工具调用 → 检查是否为最终决策
    content = response.content.strip()
    if self._is_final_decision(content):
        return StepClassification(
            category=StepCategory.FINAL,
            has_content=True,
        )

    # 6. 有 content 但非最终决策 → filtered（格式异常但可恢复）
    return StepClassification(
        category=StepCategory.FILTERED,
        has_content=True,
    )
```

**处理策略映射**：

| 分类 | 处理策略 | 消耗步数 | 说明 |
|------|----------|----------|------|
| final | 结束循环，解析决策 | — | 正常结束 |
| tool-call | 执行工具，追加结果 | 是 | 继续循环 |
| think-only | 追加 reasoning_content，重新请求 | 是 | 思考模式特有 |
| filtered | 追加格式提示，重新请求 | 否 | 不消耗步数 |
| invalid | 重试（最多 2 次） | 否 | 不消耗步数 |
| failed | 按重试策略处理 | — | 视错误类型 |

**与现有模块的集成点**：

- `AgentCore._react_loop()` 中，当 `config.deepseek_optimization.step_classifier_enabled` 为 True 时，使用 `StepClassifier.classify()` 替代 `has_tool_calls` 判断
- 分类结果通过 `EventBus` 广播 `step_classified` 事件
- 步骤签名提供给 `LoopDetector` 用于循环检测

### 1.3.2 循环检测（新文件 `loop_detector.py`）

**设计思路**：在 ReAct 循环中检测 LLM 陷入重复行为的机制，包括重复步骤签名检测和 n-gram 文本循环检测。循环检测触发不消耗步数，仅记录警告或拒绝工具调用。

**核心数据类**：

```python
@dataclass
class LoopDetectionResult:
    """循环检测结果。"""
    is_loop: bool = False
    loop_type: str = ""            # "repeated_step" / "ngram_text" / ""
    repeated_signature: str = ""   # 重复的步骤签名
    repeat_count: int = 0          # 重复次数
    ngram_pattern: str = ""        # 重复的 n-gram 模式
```

**核心类**：

```python
class LoopDetector:
    def __init__(self, config_getter: Callable[[], ProactiveChatConfig] | None = None) -> None:
        self._config_getter = config_getter
        self._step_signatures: dict[str, int] = {}   # 签名 → 出现次数
        self._consecutive_detections: int = 0          # 连续循环检测次数

    def detect(
        self,
        classification: StepClassification,
        response_text: str,
    ) -> LoopDetectionResult:
        """检测当前步骤是否存在循环行为。

        Args:
            classification: 步骤分类结果
            response_text: LLM 响应文本
        """

    def _check_repeated_step(self, classification: StepClassification) -> LoopDetectionResult:
        """检查重复步骤签名。"""

    def _check_ngram_loop(self, text: str) -> LoopDetectionResult:
        """检查 n-gram 文本循环。"""

    def reset(self) -> None:
        """重置检测状态（每次决策循环开始时调用）。"""
```

**重复步骤签名检测**：

```python
def _check_repeated_step(self, classification):
    if not classification.signature:
        return LoopDetectionResult()

    # 更新签名计数
    sig = classification.signature
    self._step_signatures[sig] = self._step_signatures.get(sig, 0) + 1

    config = self._config_getter() if self._config_getter else None
    threshold = config.deepseek_optimization.repeated_step_threshold if config else 3

    if self._step_signatures[sig] >= threshold:
        self._consecutive_detections += 1
        return LoopDetectionResult(
            is_loop=True,
            loop_type="repeated_step",
            repeated_signature=sig,
            repeat_count=self._step_signatures[sig],
        )

    return LoopDetectionResult()
```

**n-gram 文本循环检测**：

```python
def _check_ngram_loop(self, text):
    if not text or len(text) < 20:
        return LoopDetectionResult()

    config = self._config_getter() if self._config_getter else None
    n = config.deepseek_optimization.ngram_window_size if config else 3
    threshold = config.deepseek_optimization.ngram_repeat_threshold if config else 3

    # 提取所有 n-gram
    ngrams: dict[str, int] = {}
    for i in range(len(text) - n + 1):
        gram = text[i:i + n]
        ngrams[gram] = ngrams.get(gram, 0) + 1

    # 检查是否有超过阈值的 n-gram
    for gram, count in ngrams.items():
        if count >= threshold and len(gram.strip()) >= n:  # 忽略纯空白
            return LoopDetectionResult(
                is_loop=True,
                loop_type="ngram_text",
                ngram_pattern=gram,
                repeat_count=count,
            )

    return LoopDetectionResult()
```

**循环中断策略**：

```python
def get_interruption_message(self, result: LoopDetectionResult) -> str:
    """根据循环类型返回中断提示消息。"""
    if result.loop_type == "repeated_step":
        return "错误：重复调用同一工具，请尝试其他工具或直接提交决策"
    if result.loop_type == "ngram_text":
        return "提示：你的输出中存在重复表述，请避免重复并直接给出决策"
    return ""
```

**与现有模块的集成点**：

- `AgentCore._react_loop()` 中，当 `config.deepseek_optimization.loop_detection_enabled` 为 True 时，在步骤分类后调用 `LoopDetector.detect()`
- 重复步骤签名循环：拒绝当前工具调用，返回错误信息给 LLM
- n-gram 文本循环：追加系统消息提示 LLM 避免重复
- 连续 3 次循环检测触发后，强制结束 ReAct 循环
- 每次决策循环开始时调用 `LoopDetector.reset()`

### 1.3.3 感知增强模块（新文件 `perception_enhancer.py`）

**设计思路**：将话题追踪、情感分析、参与者画像三个感知增强功能统一在一个模块中管理，通过 LLM 推理实现轻量级感知，结果注入到 perceive 阶段的用户提示词中。所有数据仅缓存在内存中，不持久化。

**核心数据类**：

```python
@dataclass
class TopicInfo:
    """话题追踪信息。"""
    topic: str = ""                  # 当前话题描述，最大 100 字符
    topic_relevance: float = 0.0     # 话题与 bot 角色/知识的关联度 0.0-1.0
    topic_changed: bool = False      # 是否检测到话题切换
    previous_topic: str = ""         # 切换前的话题
    confidence: float = 0.0          # 话题识别置信度


@dataclass
class SentimentInfo:
    """情感分析信息。"""
    polarity: str = "neutral"        # positive / neutral / negative
    confidence: float = 0.0          # 情感分析置信度
    sentiment_shift: bool = False    # 是否检测到情感转折
    shift_direction: str = ""        # 转折方向


@dataclass
class ParticipantProfile:
    """参与者画像。"""
    participant_id: str = ""         # 参与者标识
    message_frequency: int = 0       # 发言频率（最近 N 分钟消息数）
    last_active_at: float = 0.0      # 最近发言时间
    interaction_pattern: str = "unknown"  # frequent_asker / casual_talker / bot_interactor / unknown
    mention_bot: bool = False        # 是否最近 @过 bot
```

**核心类**：

```python
class PerceptionEnhancer:
    def __init__(
        self,
        deepseek_client: DeepSeekClient,
        event_bus: EventBus,
    ) -> None:
        self._deepseek = deepseek_client
        self._event_bus = event_bus
        # 参与者画像缓存：stream_id → {participant_id → ParticipantProfile}
        self._profile_cache: dict[str, dict[str, ParticipantProfile]] = {}
        self._profile_cache_time: dict[str, float] = {}

    async def analyze_topic(
        self,
        stream_id: str,
        recent_messages: list[dict],
        config: ProactiveChatConfig,
    ) -> TopicInfo | None:
        """分析当前话题。"""

    async def analyze_sentiment(
        self,
        stream_id: str,
        recent_messages: list[dict],
        config: ProactiveChatConfig,
    ) -> SentimentInfo | None:
        """分析对话情感。"""

    def build_participant_profiles(
        self,
        stream_id: str,
        recent_messages: list[dict],
        config: ProactiveChatConfig,
    ) -> list[ParticipantProfile]:
        """构建参与者画像（纯本地操作，不调用 LLM）。"""

    def format_topic_for_prompt(self, topic_info: TopicInfo | None) -> str:
        """将话题信息格式化为可注入提示词的文本。"""

    def format_sentiment_for_prompt(self, sentiment_info: SentimentInfo | None) -> str:
        """将情感信息格式化为可注入提示词的文本。"""

    def format_profiles_for_prompt(self, profiles: list[ParticipantProfile]) -> str:
        """将参与者画像格式化为可注入提示词的文本。"""
```

**话题追踪实现**：

话题追踪通过轻量级 LLM 调用实现，使用 JSON Output 模式确保结构化输出：

```python
async def analyze_topic(self, stream_id, recent_messages, config):
    if not config.agent_optimization.topic_tracking_enabled:
        return None

    # 消息不足 3 条时跳过
    if len(recent_messages) < 3:
        return None

    # 构建话题识别提示词
    messages_text = self._extract_messages_text(recent_messages, max_chars=2000)
    prompt = TOPIC_ANALYSIS_PROMPT.format(messages_text=messages_text)

    try:
        response = await self._deepseek.analyze_with_json_output(
            system_prompt=TOPIC_ANALYSIS_SYSTEM,
            user_prompt=prompt,
            config=config,
        )
        data = json.loads(response)
        return TopicInfo(
            topic=data.get("topic", "")[:100],
            topic_relevance=max(0.0, min(1.0, data.get("topic_relevance", 0.0))),
            topic_changed=data.get("topic_changed", False),
            previous_topic=data.get("previous_topic", "")[:100],
            confidence=max(0.0, min(1.0, data.get("confidence", 0.0))),
        )
    except (json.JSONDecodeError, KeyError, ValueError) as e:
        logger.warning("[proactive-chat] 话题追踪分析失败: %s", e)
        return None
```

**参与者画像实现**：

参与者画像为纯本地操作，从消息元数据中提取，不调用 LLM：

```python
def build_participant_profiles(self, stream_id, recent_messages, config):
    if not config.agent_optimization.participant_profile_enabled:
        return []

    # 检查缓存（5 分钟有效期）
    now = time.time()
    cache_time = self._profile_cache_time.get(stream_id, 0)
    if now - cache_time < 300 and stream_id in self._profile_cache:
        return list(self._profile_cache[stream_id].values())

    # 从消息中提取参与者信息
    profiles: dict[str, ParticipantProfile] = {}
    for msg in recent_messages:
        sender = msg.get("sender_id", msg.get("sender", ""))
        if not sender:
            continue
        if sender not in profiles:
            profiles[sender] = ParticipantProfile(participant_id=sender)
        p = profiles[sender]
        p.message_frequency += 1
        p.last_active_at = max(p.last_active_at, msg.get("timestamp", 0))
        # 检测 @bot
        content = msg.get("content", "")
        if "@" in content and "bot" in content.lower():
            p.mention_bot = True
            p.interaction_pattern = "bot_interactor"

    # 判断互动模式
    for p in profiles.values():
        if p.interaction_pattern == "unknown":
            if p.message_frequency >= 5:
                p.interaction_pattern = "frequent_asker"
            else:
                p.interaction_pattern = "casual_talker"

    # 容量限制
    max_entries = config.agent_optimization.participant_profile_max_entries
    sorted_profiles = sorted(profiles.values(), key=lambda x: x.message_frequency, reverse=True)
    result = sorted_profiles[:max_entries]

    # 更新缓存
    self._profile_cache[stream_id] = {p.participant_id: p for p in result}
    self._profile_cache_time[stream_id] = now

    return result
```

**与现有模块的集成点**：

- `AgentCore.perceive()` 中，在感知阶段调用 `PerceptionEnhancer` 的三个方法
- 话题/情感/画像信息格式化后注入到 `PerceptionData` 的新增字段
- 参与者画像缓存在内存中，5 分钟冷却期内复用
- 感知增强结果通过 `EventBus` 广播供 WebUI 展示

### 1.3.4 决策质量统计（新文件 `quality_stats.py`）

**设计思路**：通过滑动窗口统计决策质量指标，包括触发准确率、误触发率、漏触发率估算和 ReAct 效率指标。统计数据仅缓存在内存中，不持久化。

**核心数据类**：

```python
@dataclass
class DecisionQualityMetrics:
    """决策质量指标。"""
    trigger_accuracy: float = 0.0        # 触发准确率
    false_trigger_rate: float = 0.0      # 误触发率
    missed_trigger_rate: float = 0.0     # 漏触发率估算
    avg_react_steps: float = 0.0         # ReAct 平均步数
    avg_decision_duration_ms: float = 0.0 # 平均决策耗时
    tool_hit_rate: float = 0.0           # 工具调用命中率
    sample_size: int = 0                 # 统计样本量


@dataclass
class DecisionRecord:
    """单次决策记录（内存级，非持久化）。"""
    stream_id: str = ""
    triggered: bool = False              # 是否触发
    vetoed: bool = False                 # 是否被反思否决
    error: bool = False                  # 是否异常
    has_signal: bool = False             # 是否存在明确信号（@bot 等）
    react_steps: int = 0                 # ReAct 步数
    duration_ms: float = 0.0             # 决策耗时
    tool_calls: int = 0                  # 工具调用次数
    tool_hits: int = 0                   # 有效工具调用次数
```

**核心类**：

```python
class QualityStats:
    def __init__(self, event_bus: EventBus, config_getter: Callable[[], ProactiveChatConfig] | None = None) -> None:
        self._event_bus = event_bus
        self._config_getter = config_getter
        self._records: collections.deque[DecisionRecord] = collections.deque(maxlen=1000)

    def record_decision(self, record: DecisionRecord) -> None:
        """记录一次决策结果。"""

    def get_metrics(self) -> DecisionQualityMetrics:
        """计算当前决策质量指标。"""

    def _calc_trigger_accuracy(self, records: list[DecisionRecord]) -> float:
        """计算触发准确率。"""

    def _calc_false_trigger_rate(self, records: list[DecisionRecord]) -> float:
        """计算误触发率。"""

    def _calc_missed_trigger_rate(self, records: list[DecisionRecord]) -> float:
        """计算漏触发率估算。"""
```

**指标计算**：

```python
def get_metrics(self):
    config = self._config_getter() if self._config_getter else None
    window = config.agent_optimization.quality_stats_window_size if config else 100

    records = list(self._records)[-window:]
    if not records:
        return DecisionQualityMetrics()

    triggered = [r for r in records if r.triggered]
    not_triggered = [r for r in records if not r.triggered]

    # 触发准确率 = 正常触发 / 总触发
    accuracy = self._calc_trigger_accuracy(triggered)

    # 误触发率 = 被否决或异常的触发 / 总触发
    false_rate = self._calc_false_trigger_rate(triggered)

    # 漏触发率 = 未触发但存在明确信号 / 总未触发
    missed_rate = self._calc_missed_trigger_rate(not_triggered)

    # 效率指标
    avg_steps = sum(r.react_steps for r in records) / len(records) if records else 0
    avg_duration = sum(r.duration_ms for r in records) / len(records) if records else 0
    total_calls = sum(r.tool_calls for r in records)
    total_hits = sum(r.tool_hits for r in records)
    hit_rate = total_hits / total_calls if total_calls > 0 else 0

    return DecisionQualityMetrics(
        trigger_accuracy=accuracy,
        false_trigger_rate=false_rate,
        missed_trigger_rate=missed_rate,
        avg_react_steps=round(avg_steps, 1),
        avg_decision_duration_ms=round(avg_duration, 1),
        tool_hit_rate=round(hit_rate, 3),
        sample_size=len(records),
    )
```

**与现有模块的集成点**：

- `AgentCore.decision_loop()` 完成后调用 `QualityStats.record_decision()`
- 指标通过 `EventBus` 广播 `decision_quality` 事件
- WebUI 订阅 `decision_quality` 事件更新统计面板

### 1.3.5 DeepSeek 深度优化（扩展 `deepseek_client.py`）

**设计思路**：在 v3.1 的 `DeepSeekClient` 基础上，新增 reasoning_effort 自适应调节、reasoning_content 回传健壮性增强、思考模式参数兼容、strict 模式正式集成、SSE 超时检测和指数退避重试。

#### 1.3.5.1 reasoning_effort 自适应调节

**新增方法**：

```python
class DeepSeekClient:
    # ... 现有方法不变 ...

    def compute_adaptive_effort(
        self,
        perception_data: PerceptionData,
        step: int,
        has_tool_calls: bool,
        config: ProactiveChatConfig,
    ) -> str:
        """根据场景复杂度计算 reasoning_effort。

        Returns:
            "high" 或 "max"
        """
```

**复杂度评估与 effort 映射**：

```python
def compute_adaptive_effort(self, perception_data, step, has_tool_calls, config):
    ds_config = config.deepseek_optimization

    # 非思考模式不传递 reasoning_effort
    if not config.deepseek_v4.thinking_enabled:
        return ""

    # 自适应未启用，使用 v3.1 的固定逻辑
    if not ds_config.adaptive_effort_enabled:
        return "max" if has_tool_calls else config.deepseek_v4.reasoning_effort

    # 工具调用轮次强制 max
    if step > 1 or has_tool_calls:
        return "max"

    # 评估场景复杂度
    complexity = self._assess_complexity(perception_data)

    # 复杂度高 → max，否则 → high
    if complexity == "high":
        return "max"
    return "high"


def _assess_complexity(self, perception_data) -> str:
    """评估场景复杂度。"""
    signal_count = 0
    if perception_data.silence_signal:
        signal_count += 1
    if perception_data.missed_reply_signal:
        signal_count += 1
    if perception_data.topic_info and perception_data.topic_info.topic_relevance > 0.5:
        signal_count += 1

    msg_count = len(perception_data.recent_messages)
    has_sentiment_shift = (
        perception_data.sentiment_info and perception_data.sentiment_info.sentiment_shift
    )

    # 复杂场景：3+ 信号、15+ 条消息、多话题切换、情感复杂
    if signal_count >= 3 or msg_count >= 15 or has_sentiment_shift:
        return "high"
    # 普通场景
    if signal_count >= 1 or msg_count >= 5:
        return "medium"
    # 简单场景
    return "low"
```

#### 1.3.5.2 reasoning_content 回传健壮性

**增强 `analyze_with_thinking()` 方法**：

在 v3.1 的基础上，新增回传完整性验证和自动修复逻辑：

```python
async def analyze_with_thinking(self, system_prompt, messages, config, tools=None, is_tool_call_round=False):
    # ... 现有请求体构建逻辑 ...

    # v3.2 增强：回传完整性验证
    if config.deepseek_optimization.robust_reasoning_enabled:
        self._validate_reasoning_content(messages)

    # v3.2 增强：自适应 reasoning_effort
    if config.deepseek_optimization.adaptive_effort_enabled:
        step = sum(1 for m in messages if m.get("role") == "assistant")
        effort = self.compute_adaptive_effort(
            perception_data=None,  # 由调用方传入或从上下文推断
            step=step,
            has_tool_calls=any(m.get("tool_calls") for m in messages if m.get("role") == "assistant"),
            config=config,
        )
        if effort:
            body["extra_body"]["thinking"]["reasoning_effort"] = effort

    # v3.2 增强：思考模式参数兼容
    if config.deepseek_v4.thinking_enabled:
        # 移除互斥参数
        for param in ("temperature", "top_p", "presence_penalty", "frequency_penalty"):
            body.pop(param, None)

    # ... 发送请求 ...

    # v3.2 增强：400 错误自动修复
    try:
        response = await self._send_request(url, body, headers, config)
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 400 and config.deepseek_optimization.robust_reasoning_enabled:
            # 尝试补全 reasoning_content 后重试
            body = self._fix_reasoning_content(body, messages)
            response = await self._send_request(url, body, headers, config)
        else:
            raise

    # ... 解析响应 ...

    # v3.2 增强：简化写法追加消息
    # 调用方应使用 response.choices[0].message 的等效写法
    # DeepSeekClient 返回的 ThinkingResponse 已包含所有字段
```

**回传完整性验证**：

```python
def _validate_reasoning_content(self, messages: list[dict]) -> None:
    """验证所有包含工具调用的 assistant 消息均携带 reasoning_content。"""
    for msg in messages:
        if msg.get("role") == "assistant" and msg.get("tool_calls"):
            if not msg.get("reasoning_content"):
                logger.warning(
                    "[proactive-chat] 工具调用消息缺少 reasoning_content，"
                    "tool_calls 数量: %d",
                    len(msg.get("tool_calls", [])),
                )
```

**400 错误自动修复**：

```python
def _fix_reasoning_content(self, body: dict, messages: list[dict]) -> dict:
    """补全遗漏的 reasoning_content 后重新构建请求体。"""
    body_copy = dict(body)
    fixed_messages = []
    for msg in body_copy.get("messages", []):
        msg_copy = dict(msg)
        if msg_copy.get("role") == "assistant" and msg_copy.get("tool_calls"):
            if not msg_copy.get("reasoning_content"):
                # 从历史消息中查找对应的 reasoning_content
                msg_copy["reasoning_content"] = "[思维链已补全]"
                logger.warning("[proactive-chat] 已补全遗漏的 reasoning_content")
        fixed_messages.append(msg_copy)
    body_copy["messages"] = fixed_messages
    return body_copy
```

#### 1.3.5.3 strict 模式正式集成

v3.1 将 strict 模式列为 Beta 且默认关闭，v3.2 正式集成。配置项从 `deepseek_v4.strict_mode_enabled` 迁移到 `deepseek_optimization.strict_mode_enabled`（保持向后兼容）。

**strict 模式请求构建**：

```python
def _apply_strict_mode(self, body: dict, tools: list[dict] | None, config: ProactiveChatConfig) -> dict:
    """应用 strict 模式到请求体。"""
    # 检查 strict 模式是否启用（兼容 v3.1 和 v3.2 配置）
    strict_enabled = (
        config.deepseek_optimization.strict_mode_enabled
        or config.deepseek_v4.strict_mode_enabled  # v3.1 兼容
    )
    if not strict_enabled or not tools:
        return body

    body_copy = dict(body)
    body_copy["base_url"] = "https://api.deepseek.com/beta"

    # 为每个工具添加 strict: true + additionalProperties: false
    fixed_tools = []
    for tool in tools:
        tool_copy = dict(tool)
        func_def = dict(tool_copy.get("function", {}))
        func_def["strict"] = True
        params = dict(func_def.get("parameters", {}))
        params["additionalProperties"] = False
        func_def["parameters"] = params
        tool_copy["function"] = func_def
        fixed_tools.append(tool_copy)

    body_copy["tools"] = fixed_tools
    return body_copy
```

**strict 模式降级**：

```python
async def _send_with_strict_fallback(self, url, body, headers, config):
    """发送请求，strict 模式失败时自动降级。"""
    try:
        return await self._send_request(url, body, headers, config)
    except httpx.HTTPStatusError as e:
        if e.response.status_code in (404, 503) and "beta" in url:
            # beta 端点不可用，降级为标准端点
            logger.warning("[proactive-chat] strict 模式 beta 端点不可用，降级为标准模式")
            body_fallback = dict(body)
            body_fallback.pop("base_url", None)
            # 移除 strict 标记
            for tool in body_fallback.get("tools", []):
                func_def = tool.get("function", {})
                func_def.pop("strict", None)
                func_def.get("parameters", {}).pop("additionalProperties", None)
            return await self._send_request(
                "https://api.deepseek.com/v1/chat/completions",
                body_fallback, headers, config,
            )
        raise
```

#### 1.3.5.4 SSE 超时与指数退避重试

**新增方法**：

```python
async def _send_with_enhanced_retry(
    self,
    url: str,
    body: dict,
    headers: dict,
    config: ProactiveChatConfig,
) -> httpx.Response:
    """带 SSE 超时检测和指数退避重试的请求发送。"""
    if not config.deepseek_optimization.enhanced_retry_enabled:
        # 未启用增强重试，使用 v3.1 的固定重试逻辑
        return await self._send_request(url, body, headers, config)

    ds_config = config.deepseek_optimization
    base_delay = ds_config.retry_base_delay_ms / 1000.0
    max_retries = ds_config.retry_max_retries
    max_backoff = ds_config.retry_max_backoff_ms / 1000.0

    last_error: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            # SSE 超时检测
            timeout = ds_config.sse_chunk_timeout_seconds
            response = await self._send_request_with_sse_timeout(
                url, body, headers, config, timeout=timeout,
            )
            return response
        except (httpx.ReadTimeout, httpx.ConnectTimeout, asyncio.TimeoutError) as e:
            last_error = e
            if attempt < max_retries:
                # 指数退避
                delay = min(base_delay * (2 ** attempt), max_backoff)
                logger.warning(
                    "[proactive-chat] API 请求超时，第 %d 次重试（延迟 %.1fs）: %s",
                    attempt + 1, delay, e,
                )
                await asyncio.sleep(delay)

    # 重试耗尽，尝试非流式调用
    logger.warning("[proactive-chat] 指数退避重试耗尽，尝试非流式调用")
    try:
        body_no_stream = dict(body)
        body_no_stream.pop("stream", None)
        return await self._send_request(url, body_no_stream, headers, config)
    except Exception as e:
        logger.error("[proactive-chat] 非流式调用也失败: %s", e)
        raise last_error or e
```

**与现有模块的集成点**：

- `analyze_with_thinking()` 和 `analyze_with_tools()` 中，当 `config.deepseek_optimization.enhanced_retry_enabled` 为 True 时，使用 `_send_with_enhanced_retry()` 替代 `_send_request()`
- SSE 超时检测通过 `asyncio.wait_for()` 包装实现
- 指数退避参数通过 `DeepseekOptimizationConfig` 配置

### 1.3.6 记忆增强注入（扩展 `agent_memory.py`）

**设计思路**：在 v3.1 的 `AgentMemory` 基础上，新增记忆分类（已触发/未触发）、上下文关联排序、语义去重和容量动态调整。

**扩展数据类**：

```python
@dataclass
class AgentMemoryEntry:
    # ... v3.1 字段不变 ...
    category: str = "unknown"  # "triggered" / "not_triggered" / "unknown"
    context_relevance: float = 0.0  # 与当前感知的关联度 0.0-1.0
```

**扩展方法**：

```python
class AgentMemory:
    # ... 现有方法不变 ...

    async def get_enhanced_memories(
        self,
        stream_id: str,
        perception_context: PerceptionData,
        config: ProactiveChatConfig,
    ) -> list[AgentMemoryEntry]:
        """获取增强记忆列表（分类 + 关联排序 + 去重 + 动态容量）。"""

    def _classify_memory(self, entry: AgentMemoryEntry) -> str:
        """将记忆分类为已触发/未触发/未知。"""

    def _compute_context_relevance(
        self,
        entry: AgentMemoryEntry,
        perception_context: PerceptionData,
    ) -> float:
        """计算记忆与当前感知的关联度。"""

    def _deduplicate_memories(
        self,
        entries: list[AgentMemoryEntry],
    ) -> list[AgentMemoryEntry]:
        """语义去重：摘要高度相似的记忆仅保留权重最高的一条。"""

    def _adjust_capacity(
        self,
        entries: list[AgentMemoryEntry],
        token_budget: int,
        config: ProactiveChatConfig,
    ) -> list[AgentMemoryEntry]:
        """根据 token 预算动态调整记忆条数。"""

    def format_enhanced_memories_for_prompt(
        self,
        memories: list[AgentMemoryEntry],
    ) -> str:
        """将增强记忆列表格式化为可注入提示词的文本。"""
```

**记忆分类**：

```python
def _classify_memory(self, entry):
    if entry.action_taken and entry.action_taken not in ("skip", "no_action", ""):
        return "triggered"
    if entry.trigger_reason and "未触发" in entry.trigger_reason:
        return "not_triggered"
    return "unknown"
```

**上下文关联排序**：

```python
def _compute_context_relevance(self, entry, perception_context):
    score = 0.0
    # 冷场信号关联
    if perception_context.silence_signal and "冷场" in entry.summary:
        score += 0.5
    # 漏回信号关联
    if perception_context.missed_reply_signal and "漏回" in entry.summary:
        score += 0.5
    # 话题关联
    if perception_context.topic_info and perception_context.topic_info.topic in entry.summary:
        score += 0.3
    return min(1.0, score)
```

**语义去重**：

```python
def _deduplicate_memories(self, entries):
    """基于摘要文本相似度的去重。"""
    seen_summaries: dict[str, AgentMemoryEntry] = {}
    for entry in entries:
        # 简化的去重：提取摘要中的意图关键词
        key = entry.summary.split("，")[0] if "，" in entry.summary else entry.summary[:30]
        if key in seen_summaries:
            # 保留权重更高的
            if entry.weight > seen_summaries[key].weight:
                seen_summaries[key] = entry
        else:
            seen_summaries[key] = entry
    return list(seen_summaries.values())
```

**增强格式模板**：

```python
ENHANCED_MEMORY_HISTORY_TEMPLATE = """[历史决策记忆] 以下是该聊天流的历史决策记录摘要：

{memory_entries}

注意：这些是历史决策记录，仅作为上下文参考，不要被过去的决策过度影响当前判断。"""

ENHANCED_MEMORY_ENTRY_TEMPLATE = "- [{category}] {time}：{summary}（行动: {action_taken}，关联度: {context_relevance:.1f}）"
```

**与现有模块的集成点**：

- `AgentCore.perceive()` 中，当 `config.agent_optimization.enhanced_memory_enabled` 为 True 时，调用 `get_enhanced_memories()` 替代 `get_memories()`
- 未启用时保持 v3.1 的 `get_memories()` 行为不变

### 1.3.7 上下文感知压缩（扩展 `overflow_manager.py`）

**设计思路**：在 v3.1 的 `OverflowManager` 基础上，扩展软剪枝和硬剪枝策略，使其考虑内容与当前感知信号的相关性，而非仅按位置或字符长度操作。

**扩展方法**：

```python
class OverflowManager:
    # ... 现有方法不变 ...

    def soft_prune_with_relevance(
        self,
        messages: list[dict],
        threshold: int,
        perception_signals: list[str] | None = None,
    ) -> list[dict]:
        """上下文感知软剪枝：优先截断与感知信号无关的工具输出。"""

    def hard_prune_with_priority(
        self,
        messages: list[dict],
        usable_limit: int,
        config: ProactiveChatConfig,
        perception_signals: list[str] | None = None,
    ) -> list[dict]:
        """上下文感知硬剪枝：优先移除低优先级消息。"""

    def _compute_message_priority(
        self,
        msg: dict,
        perception_signals: list[str] | None,
    ) -> int:
        """计算消息优先级（0=低，1=中，2=高）。"""
```

**相关性排序软剪枝**：

```python
def soft_prune_with_relevance(self, messages, threshold, perception_signals=None):
    if not perception_signals:
        # 无感知信号时降级为 v3.1 的按位置剪枝
        return self.soft_prune(messages, threshold)

    result = []
    for msg in messages:
        msg_copy = dict(msg)
        if msg_copy.get("role") == "tool":
            content = msg_copy.get("content", "")
            if isinstance(content, str) and len(content) > threshold:
                # 检查内容是否与感知信号相关
                is_relevant = any(signal in content for signal in perception_signals)
                if is_relevant:
                    # 相关内容：放宽截断阈值（2 倍）
                    extended_threshold = threshold * 2
                    if len(content) > extended_threshold:
                        msg_copy["content"] = content[:extended_threshold] + "[已截断]"
                else:
                    # 无关内容：正常截断
                    msg_copy["content"] = content[:threshold] + "[已截断]"
        result.append(msg_copy)
    return result
```

**优先级标注硬剪枝**：

```python
def _compute_message_priority(self, msg, perception_signals):
    """计算消息优先级。"""
    if not perception_signals:
        return 1  # 中优先级

    content = msg.get("content", "")
    if not isinstance(content, str):
        return 1

    # 高优先级：包含 @bot 或感知信号关键词
    if any(signal in content for signal in perception_signals):
        return 2
    # 低优先级：工具输出且与信号无关
    if msg.get("role") == "tool":
        return 0
    return 1
```

**扩展 `get_managed_context()`**：

```python
async def get_managed_context(self, stream_id, messages, config, perception_signals=None):
    # ... 现有逻辑 ...

    # v3.2 增强：上下文感知压缩
    context_aware = config.agent_optimization.context_aware_compress_enabled

    if pressure == 2:
        if context_aware:
            pruned = self.soft_prune_with_relevance(messages, threshold, perception_signals)
        else:
            pruned = self.soft_prune(messages, threshold)
        # ... 其余逻辑不变 ...

    if pressure == 3:
        if context_aware:
            pruned = self.hard_prune_with_priority(messages, usable_limit, config, perception_signals)
        else:
            pruned = self.hard_prune(messages, usable_limit, config)
        # ... 其余逻辑不变 ...
```

**与现有模块的集成点**：

- `AgentCore._react_loop()` 中，调用 `get_managed_context()` 时传入感知信号列表
- 未启用上下文感知压缩时，行为与 v3.1 完全一致

### 1.3.8 配置扩展（修改 `config.py`）

**新增 2 个配置段**：

```python
class DeepseekOptimizationConfig(PluginConfigBase):
    """DeepSeek 深度优化配置。"""
    __ui_label__ = "DeepSeek 优化"
    __ui_icon__ = "rocket"
    __ui_order__ = 17

    robust_reasoning_enabled: bool = Field(
        default=True,
        description="是否启用 reasoning_content 回传健壮性增强",
    )
    adaptive_effort_enabled: bool = Field(
        default=True,
        description="是否启用 reasoning_effort 自适应调节",
    )
    step_classifier_enabled: bool = Field(
        default=True,
        description="是否启用步骤分类器",
    )
    loop_detection_enabled: bool = Field(
        default=True,
        description="是否启用循环检测",
    )
    repeated_step_threshold: int = Field(
        default=3, ge=2, le=10,
        description="重复步骤签名检测阈值",
    )
    ngram_window_size: int = Field(
        default=3, ge=2, le=5,
        description="n-gram 文本循环检测窗口大小",
    )
    ngram_repeat_threshold: int = Field(
        default=3, ge=2, le=10,
        description="n-gram 重复次数阈值",
    )
    strict_mode_enabled: bool = Field(
        default=False,
        description="是否启用 strict 模式（正式集成，默认关闭）",
    )
    deepseek_prompt_enabled: bool = Field(
        default=True,
        description="是否启用 DeepSeek 专用 prompt 优化",
    )
    enhanced_retry_enabled: bool = Field(
        default=True,
        description="是否启用 SSE 超时检测和指数退避重试",
    )
    sse_chunk_timeout_seconds: int = Field(
        default=480, ge=60, le=900,
        description="SSE chunk 超时时间（秒）",
    )
    retry_base_delay_ms: int = Field(
        default=500, ge=100, le=5000,
        description="重试基础延迟（毫秒）",
    )
    retry_max_retries: int = Field(
        default=10, ge=1, le=20,
        description="最大重试次数",
    )
    retry_max_backoff_ms: int = Field(
        default=60000, ge=1000, le=300000,
        description="最大退避时间（毫秒）",
    )


class AgentOptimizationConfig(PluginConfigBase):
    """智能体优化配置。"""
    __ui_label__ = "智能体优化"
    __ui_icon__ = "trending-up"
    __ui_order__ = 18

    topic_tracking_enabled: bool = Field(
        default=True,
        description="是否启用话题追踪",
    )
    sentiment_analysis_enabled: bool = Field(
        default=True,
        description="是否启用情感分析",
    )
    participant_profile_enabled: bool = Field(
        default=True,
        description="是否启用参与者画像",
    )
    participant_profile_max_entries: int = Field(
        default=5, ge=1, le=10,
        description="单次注入参与者数量上限",
    )
    adaptive_steps_enabled: bool = Field(
        default=True,
        description="是否启用自适应步数",
    )
    enhanced_memory_enabled: bool = Field(
        default=True,
        description="是否启用记忆增强注入",
    )
    enhanced_reflection_enabled: bool = Field(
        default=True,
        description="是否启用反思子智能体增强",
    )
    prompt_optimization_enabled: bool = Field(
        default=True,
        description="是否启用提示词优化",
    )
    context_aware_compress_enabled: bool = Field(
        default=True,
        description="是否启用上下文感知压缩",
    )
    quality_stats_window_size: int = Field(
        default=100, ge=10, le=1000,
        description="决策质量统计滑动窗口大小",
    )
```

**ProactiveChatConfig 新增字段**：

```python
class ProactiveChatConfig(PluginConfigBase):
    # ... 现有字段不变 ...
    deepseek_optimization: DeepseekOptimizationConfig = Field(default_factory=DeepseekOptimizationConfig)
    agent_optimization: AgentOptimizationConfig = Field(default_factory=AgentOptimizationConfig)
```

**config_version 升级**：`3.1.0` → `3.2.0`

### 1.3.9 提示词扩展（修改 `prompts.py`）

**新增 DeepSeek 专用 prompt 模板**：

```python
DEEPSEEK_WORKFLOW_PROMPT = """
## DeepSeek 工作流指导

请按以下步骤进行决策：
1. **Understand（理解场景）**：仔细阅读对话上下文，理解当前对话状态
2. **Explore（探索信息）**：使用可用工具获取必要信息
3. **Plan（制定计划）**：基于获取的信息制定决策方案
4. **Execute（执行决策）**：输出结构化的决策结果
5. **Verify（验证结果）**：确认决策符合场景要求
6. **Summarize（总结输出）**：以 JSON 格式输出最终决策
"""

DEEPSEEK_TOOL_PROTOCOL = """
## 工具使用协议

使用工具时请遵循以下步骤：
1. 确认你需要什么信息
2. 选择合适的工具
3. 构造正确的参数
4. 执行工具并分析结果
5. 基于结果做出决策

注意：不要重复调用同一工具获取相同信息。如果工具返回错误，请尝试其他策略或直接提交决策。
"""
```

**新增场景示例模板**：

```python
SCENARIO_EXAMPLES = {
    "silence_break": """
### 冷场打破示例
场景：群聊已沉默 10 分钟后有人发了一条消息
决策：{{"should_trigger": true, "intent": "silence_break", "reason": "冷场后新消息到达，适合介入", "confidence": 0.8, "timing_score": 0.9}}
""",
    "missed_reply": """
### 漏回补答示例
场景：有人 @了 bot 但未得到回应
决策：{{"should_trigger": true, "intent": "missed_reply", "reason": "用户 @bot 未获回应，需补答", "confidence": 0.9, "timing_score": 1.0}}
""",
    "topic_supplement": """
### 话题补充示例
场景：群聊正在讨论与 bot 专业领域相关的话题
决策：{{"should_trigger": true, "intent": "topic_supplement", "reason": "话题与 bot 领域相关，可补充信息", "confidence": 0.7, "timing_score": 0.6}}
""",
    "no_trigger": """
### 不触发示例
场景：对话节奏正常，bot 已参与讨论
决策：{{"should_trigger": false, "intent": "", "reason": "", "confidence": 0.0, "timing_score": 0.0}}
""",
}

DECISION_BOUNDARY = """
## 决策边界条件

以下情况不应触发主动发言：
- 对话节奏正常且 bot 已参与讨论
- 话题与 bot 无关且无冷场信号
- 冷却期内（最近已触发过）
- 用户正在互相讨论且未 @bot
- 消息内容为纯表情包或简短寒暄且无冷场信号
"""
```

**新增感知增强注入模板**：

```python
TOPIC_TRACKING_TEMPLATE = """
[话题追踪]
当前话题：{topic}
话题关联度：{relevance:.1f}
{topic_changed_section}
"""

SENTIMENT_ANALYSIS_TEMPLATE = """
[情感分析]
对话情感：{polarity}（置信度: {confidence:.1f}）
{sentiment_shift_section}
"""

PARTICIPANT_PROFILE_TEMPLATE = """
[参与者画像]
{profiles}
"""
```

**扩展 `build_system_prompt()`**：

```python
def build_system_prompt(
    bot_nickname: str = "",
    alias_names: list[str] | None = None,
    personality: str = "",
    reply_style: str = "",
    custom_prompt: str = "",
    react_enabled: bool = True,
    json_output_enabled: bool = False,
    # v3.2 新增参数
    deepseek_prompt_enabled: bool = False,
    scenario_signals: list[str] | None = None,
    prompt_optimization_enabled: bool = False,
) -> str:
    # ... 现有逻辑不变 ...

    # v3.2 新增：DeepSeek 专用 prompt
    if deepseek_prompt_enabled:
        prompt += DEEPSEEK_WORKFLOW_PROMPT
        if react_enabled:
            prompt += DEEPSEEK_TOOL_PROTOCOL

    # v3.2 新增：场景示例注入
    if prompt_optimization_enabled and scenario_signals:
        for signal in scenario_signals:
            if signal in SCENARIO_EXAMPLES:
                prompt += SCENARIO_EXAMPLES[signal]

    # v3.2 新增：决策边界条件
    if prompt_optimization_enabled:
        prompt += DECISION_BOUNDARY

    return prompt
```

### 1.3.10 AgentCore 集成变更（修改 `agent.py`）

#### perceive 阶段扩展

```python
async def perceive(self, stream_id, ctx, config):
    perception = PerceptionData()
    # ... 现有逻辑不变 ...

    # v3.2 新增：感知增强
    if self._perception_enhancer is not None:
        # 话题追踪
        if config.agent_optimization.topic_tracking_enabled:
            perception.topic_info = await self._perception_enhancer.analyze_topic(
                stream_id, perception.recent_messages, config,
            )

        # 情感分析
        if config.agent_optimization.sentiment_analysis_enabled:
            perception.sentiment_info = await self._perception_enhancer.analyze_sentiment(
                stream_id, perception.recent_messages, config,
            )

        # 参与者画像
        if config.agent_optimization.participant_profile_enabled:
            perception.participant_profiles = self._perception_enhancer.build_participant_profiles(
                stream_id, perception.recent_messages, config,
            )

    # 智能体记忆注入（v3.1 不变）
    if config.agent_memory.memory_enabled and self._agent_memory is not None:
        if config.agent_optimization.enhanced_memory_enabled:
            # v3.2 增强记忆
            memories = await self._agent_memory.get_enhanced_memories(
                stream_id, perception, config,
            )
            if memories:
                perception.memory_history = self._agent_memory.format_enhanced_memories_for_prompt(memories)
        else:
            # v3.1 原始记忆
            memories = await self._agent_memory.get_memories(stream_id, config)
            if memories:
                perception.memory_history = self._agent_memory.format_memories_for_prompt(memories)

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
    memory_history: str = ""          # v3.1
    topic_info: TopicInfo | None = None          # v3.2 新增
    sentiment_info: SentimentInfo | None = None  # v3.2 新增
    participant_profiles: list[ParticipantProfile] = field(default_factory=list)  # v3.2 新增
```

#### _react_loop 扩展

```python
async def _react_loop(self, stream_id, perception, config, ctx):
    # ... 现有初始化逻辑 ...

    # v3.2 新增：自适应步数
    max_steps = config.react.max_react_steps
    if config.agent_optimization.adaptive_steps_enabled:
        max_steps = self._compute_adaptive_steps(perception, config)

    # v3.2 新增：初始化循环检测
    if self._loop_detector is not None and config.deepseek_optimization.loop_detection_enabled:
        self._loop_detector.reset()

    # v3.2 新增：构建感知信号列表（用于上下文感知压缩）
    perception_signals = self._extract_perception_signals(perception)

    # 溢出管理（v3.1 扩展：传入感知信号）
    if self._overflow_manager is not None and config.deepseek_context.context_1m_enabled:
        messages, overflow_state = await self._overflow_manager.get_managed_context(
            stream_id, messages, config, perception_signals=perception_signals,
        )

    # v3.2 新增：构建系统提示词（含 DeepSeek 专用 prompt + 场景示例）
    scenario_signals = self._detect_scenario_signals(perception)
    system_prompt = build_system_prompt(
        # ... 现有参数 ...
        deepseek_prompt_enabled=config.deepseek_optimization.deepseek_prompt_enabled,
        scenario_signals=scenario_signals if config.agent_optimization.prompt_optimization_enabled else None,
        prompt_optimization_enabled=config.agent_optimization.prompt_optimization_enabled,
    )

    # v3.2 新增：感知增强信息注入到用户提示词
    user_prompt = self._build_enhanced_user_prompt(perception, config)

    invalid_retry_count = 0
    consecutive_think_only = 0

    for step in range(1, max_steps + 1):
        # 思考模式分支（v3.1 扩展）
        if config.deepseek_v4.thinking_enabled:
            # v3.2 增强：自适应 reasoning_effort
            response = await self._deepseek.analyze_with_thinking(
                system_prompt, messages, config, tools=tools,
                is_tool_call_round=(step > 1),
            )
        else:
            response = await self._deepseek.analyze_with_tools(
                system_prompt, messages, tools, config,
            )

        # v3.2 新增：步骤分类
        if self._step_classifier is not None and config.deepseek_optimization.step_classifier_enabled:
            classification = self._step_classifier.classify(
                response,
                is_thinking_enabled=config.deepseek_v4.thinking_enabled,
            )

            # 根据分类执行不同处理策略
            if classification.category == StepCategory.FINAL:
                result = self.parse_analysis_result(response.content)
                return result, react_steps

            if classification.category == StepCategory.THINK_ONLY:
                consecutive_think_only += 1
                if consecutive_think_only >= 3:
                    # 连续 3 次 think-only，结束循环
                    logger.warning("[proactive-chat] 连续 think-only 步骤过多，结束循环")
                    break
                # 追加 reasoning_content，重新请求
                messages.append({
                    "role": "assistant",
                    "content": "",
                    "reasoning_content": response.reasoning_content,
                })
                continue

            if classification.category == StepCategory.FILTERED:
                # 追加格式提示，不消耗步数
                messages.append({"role": "user", "content": "请调整输出格式，确保符合要求"})
                continue

            if classification.category == StepCategory.INVALID:
                invalid_retry_count += 1
                if invalid_retry_count > 2:
                    logger.warning("[proactive-chat] 连续 invalid 步骤过多，结束循环")
                    break
                messages.append({"role": "user", "content": "请重新输出有效的决策结果"})
                continue

            if classification.category == StepCategory.FAILED:
                # 按重试策略处理
                break

            # tool-call：继续执行
        else:
            # v3.1 的简单 has_tool_calls 判断
            if not response.has_tool_calls:
                result = self.parse_analysis_result(response.content)
                return result, react_steps

        # v3.2 新增：循环检测
        if self._loop_detector is not None and config.deepseek_optimization.loop_detection_enabled:
            loop_result = self._loop_detector.detect(classification, response.content if hasattr(response, 'content') else "")
            if loop_result.is_loop:
                interruption = self._loop_detector.get_interruption_message(loop_result)
                if loop_result.loop_type == "repeated_step":
                    # 拒绝工具调用，返回错误信息
                    messages.append({"role": "tool", "content": interruption, "tool_call_id": response.tool_calls[0].id if response.has_tool_calls else ""})
                    continue
                else:
                    # n-gram 文本循环：追加提示
                    messages.append({"role": "user", "content": interruption})
                    continue

        # ... 现有工具调用执行逻辑 ...

    # ... 其余逻辑不变 ...
```

#### 反思子智能体增强

```python
async def _reflect_with_subagent(self, stream_id, perception, analysis_result, config):
    # ... 现有逻辑 ...

    # v3.2 新增：增强反思输入
    if config.agent_optimization.enhanced_reflection_enabled:
        reflection_input = self._build_enhanced_reflection_input(
            perception, analysis_result,
        )
    else:
        reflection_input = self._build_reflection_input(perception, analysis_result)

    # ... 调用 LLM ...

    # v3.2 新增：多维度评估解析
    if config.agent_optimization.enhanced_reflection_enabled:
        result = self._parse_enhanced_reflection(raw_response)
    else:
        result = self._parse_reflection(raw_response)

    return result
```

**增强反思提示词**：

```python
ENHANCED_REFLECTION_USER_TEMPLATE = """请评估以下决策的质量：

## 感知数据
{perception_summary}

## 决策结果
{analysis_result}

## 话题信息
{topic_info}

## 情感信息
{sentiment_info}

请从以下维度评估：
1. consistency（决策与感知数据的一致性）：0.0-1.0
2. topic_relevance（话题相关性）：0.0-1.0
3. timing_rationality（时机合理性）：0.0-1.0
4. duplicate_risk（重复触发风险，1.0=高风险）：0.0-1.0

输出 JSON 格式：
{{"verdict": "confirmed/vetoed", "reason": "理由", "dimensions": {{"consistency": 0.0, "topic_relevance": 0.0, "timing_rationality": 0.0, "duplicate_risk": 0.0}}, "veto_dimension": ""}}"""
```

**增强反思结果**：

```python
@dataclass
class EnhancedReflectionResult(ReflectionResult):
    """v3.2 增强反思结果。"""
    dimensions: dict[str, float] = field(default_factory=lambda: {
        "consistency": 0.5,
        "topic_relevance": 0.5,
        "timing_rationality": 0.5,
        "duplicate_risk": 0.5,
    })
    veto_dimension: str = ""  # 否决的主要维度
```

#### AgentCore.__init__ 新增依赖注入

```python
class AgentCore:
    def __init__(self, deepseek_client, persistence_manager, cooldown_manager):
        # ... v3.1 字段不变 ...
        self._step_classifier: StepClassifier | None = None           # v3.2 新增
        self._loop_detector: LoopDetector | None = None               # v3.2 新增
        self._perception_enhancer: PerceptionEnhancer | None = None   # v3.2 新增
        self._quality_stats: QualityStats | None = None               # v3.2 新增
```

### 1.3.11 WebUI 扩展（修改 `webui.py`）

**新增决策质量统计面板**：

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/proactive-chat/quality` | GET | 获取决策质量指标 |
| `/api/proactive-chat/quality/details` | GET | 获取详细质量统计 |

**统计接口响应**：

```json
{
  "success": true,
  "metrics": {
    "trigger_accuracy": 0.933,
    "false_trigger_rate": 0.1,
    "missed_trigger_rate": 0.071,
    "avg_react_steps": 2.3,
    "avg_decision_duration_ms": 8500.0,
    "tool_hit_rate": 0.85,
    "sample_size": 100
  }
}
```

**stats 接口扩展**：

```json
{
  "quality_stats": {
    "trigger_accuracy": 0.933,
    "false_trigger_rate": 0.1,
    "missed_trigger_rate": 0.071,
    "sample_size": 100
  },
  "deepseek_optimization": {
    "step_classifier_enabled": true,
    "loop_detection_enabled": true,
    "strict_mode_enabled": false,
    "adaptive_effort_enabled": true
  },
  "agent_optimization": {
    "topic_tracking_enabled": true,
    "sentiment_analysis_enabled": true,
    "participant_profile_enabled": true,
    "enhanced_memory_enabled": true,
    "enhanced_reflection_enabled": true
  }
}
```

**WebSocket 新增事件类型**：

| 事件类型 | 数据字段 | 触发时机 |
|---------|---------|---------|
| `decision_quality` | `trigger_accuracy`, `false_trigger_rate`, `missed_trigger_rate`, `avg_react_steps`, `tool_hit_rate`, `sample_size` | 决策循环完成时 |
| `step_classified` | `category`, `tool_name`, `has_reasoning_content`, `signature` | 步骤分类完成时 |
| `loop_detected` | `loop_type`, `repeated_signature`, `repeat_count`, `ngram_pattern` | 循环检测触发时 |

### 1.3.12 EventBus 新增事件类型

| 事件类型 | 数据字段 | 触发时机 |
|---------|---------|---------|
| `decision_quality` | `trigger_accuracy`, `false_trigger_rate`, `missed_trigger_rate`, `avg_react_steps`, `avg_decision_duration_ms`, `tool_hit_rate`, `sample_size` | 决策循环完成时 |
| `step_classified` | `category`, `tool_name`, `has_reasoning_content`, `signature` | 步骤分类完成时 |
| `loop_detected` | `loop_type`, `repeated_signature`, `repeat_count`, `ngram_pattern` | 循环检测触发时 |
| `topic_analyzed` | `topic`, `topic_relevance`, `topic_changed` | 话题追踪完成时 |
| `sentiment_analyzed` | `polarity`, `confidence`, `sentiment_shift` | 情感分析完成时 |

# 2. 接口设计

## 2.1 总体设计

v3.2 新增决策质量统计 API 端点，其余变更在插件内部。所有新增功能默认开启（DeepSeek 深度优化和智能体优化配置段的布尔字段默认 True），但 strict 模式默认关闭。关闭任何 v3.2 功能时，行为与 v3.1 完全一致。

## 2.2 接口清单

| 接口 | 变更类型 | 说明 |
|------|----------|------|
| `GET /api/proactive-chat/quality` | 新增 | 获取决策质量指标 |
| `GET /api/proactive-chat/quality/details` | 新增 | 获取详细质量统计 |
| `GET /api/proactive-chat/stats` | 扩展响应 | 新增 `quality_stats`、`deepseek_optimization`、`agent_optimization` 字段 |
| `GET /api/proactive-chat/events` | 新增事件 | `decision_quality` / `step_classified` / `loop_detected` / `topic_analyzed` / `sentiment_analyzed` |
| WebSocket 推送 | 扩展事件 | 新增 `decision_quality` / `step_classified` / `loop_detected` 事件类型 |

### 2.2.1 决策质量指标

**请求**：`GET /api/proactive-chat/quality`

**响应**：

```json
{
  "success": true,
  "metrics": {
    "trigger_accuracy": 0.933,
    "false_trigger_rate": 0.1,
    "missed_trigger_rate": 0.071,
    "avg_react_steps": 2.3,
    "avg_decision_duration_ms": 8500.0,
    "tool_hit_rate": 0.85,
    "sample_size": 100
  }
}
```

### 2.2.2 统计接口扩展

**响应新增字段**：

```json
{
  "quality_stats": {
    "trigger_accuracy": 0.933,
    "false_trigger_rate": 0.1,
    "missed_trigger_rate": 0.071,
    "sample_size": 100
  },
  "deepseek_optimization": {
    "step_classifier_enabled": true,
    "loop_detection_enabled": true,
    "strict_mode_enabled": false,
    "adaptive_effort_enabled": true,
    "enhanced_retry_enabled": true
  },
  "agent_optimization": {
    "topic_tracking_enabled": true,
    "sentiment_analysis_enabled": true,
    "participant_profile_enabled": true,
    "enhanced_memory_enabled": true,
    "enhanced_reflection_enabled": true,
    "prompt_optimization_enabled": true,
    "context_aware_compress_enabled": true
  }
}
```

# 4. 数据模型

## 4.1 设计目标

1. 向后兼容 v3.1 的所有配置格式（新增配置段有默认值）
2. 向后兼容 v3.1 的 DecisionRecord 格式（不新增持久化字段）
3. 话题/情感/画像数据不持久化到磁盘，重启后重新构建
4. 步骤分类/循环检测数据通过事件总线广播或内存缓存
5. 决策质量统计数据仅缓存在内存中，重启后归零
6. 所有 v3.2 新增数据通过配置开关控制，关闭时行为与 v3.1 一致

## 4.2 模型实现

### StepClassification（step_classifier.py，新增）

```python
class StepCategory(str, Enum):
    FINAL = "final"
    CONTINUE = "continue"
    TOOL_CALL = "tool-call"
    FILTERED = "filtered"
    THINK_ONLY = "think-only"
    INVALID = "invalid"
    FAILED = "failed"

@dataclass
class StepClassification:
    category: StepCategory = StepCategory.INVALID
    tool_name: str = ""
    has_reasoning_content: bool = False
    has_content: bool = False
    signature: str = ""
```

### LoopDetectionResult（loop_detector.py，新增）

```python
@dataclass
class LoopDetectionResult:
    is_loop: bool = False
    loop_type: str = ""            # "repeated_step" / "ngram_text" / ""
    repeated_signature: str = ""
    repeat_count: int = 0
    ngram_pattern: str = ""
```

### TopicInfo（perception_enhancer.py，新增）

```python
@dataclass
class TopicInfo:
    topic: str = ""                  # 最大 100 字符
    topic_relevance: float = 0.0     # 0.0-1.0
    topic_changed: bool = False
    previous_topic: str = ""         # 最大 100 字符
    confidence: float = 0.0          # 0.0-1.0
```

### SentimentInfo（perception_enhancer.py，新增）

```python
@dataclass
class SentimentInfo:
    polarity: str = "neutral"        # positive / neutral / negative
    confidence: float = 0.0          # 0.0-1.0
    sentiment_shift: bool = False
    shift_direction: str = ""        # positive_to_negative / negative_to_positive / neutral_to_positive / neutral_to_negative
```

### ParticipantProfile（perception_enhancer.py，新增）

```python
@dataclass
class ParticipantProfile:
    participant_id: str = ""
    message_frequency: int = 0
    last_active_at: float = 0.0
    interaction_pattern: str = "unknown"  # frequent_asker / casual_talker / bot_interactor / unknown
    mention_bot: bool = False
```

### DecisionQualityMetrics（quality_stats.py，新增）

```python
@dataclass
class DecisionQualityMetrics:
    trigger_accuracy: float = 0.0
    false_trigger_rate: float = 0.0
    missed_trigger_rate: float = 0.0
    avg_react_steps: float = 0.0
    avg_decision_duration_ms: float = 0.0
    tool_hit_rate: float = 0.0
    sample_size: int = 0
```

### EnhancedReflectionResult（agent.py，扩展 ReflectionResult）

```python
@dataclass
class EnhancedReflectionResult(ReflectionResult):
    dimensions: dict[str, float] = field(default_factory=lambda: {
        "consistency": 0.5,
        "topic_relevance": 0.5,
        "timing_rationality": 0.5,
        "duplicate_risk": 0.5,
    })
    veto_dimension: str = ""
```

### PerceptionData（agent.py，扩展）

```python
@dataclass
class PerceptionData:
    recent_messages: list[dict] = field(default_factory=list)
    silence_signal: bool = False
    silence_seconds: int = 0
    missed_reply_signal: bool = False
    memory_result: str = ""
    message_summary: str = ""
    memory_history: str = ""                                # v3.1
    topic_info: TopicInfo | None = None                     # v3.2 新增
    sentiment_info: SentimentInfo | None = None             # v3.2 新增
    participant_profiles: list[ParticipantProfile] = field(default_factory=list)  # v3.2 新增
```

### AgentMemoryEntry（agent_memory.py，扩展）

```python
@dataclass
class AgentMemoryEntry:
    chat_stream_id: str = ""
    summary: str = ""
    timestamp: float = 0.0
    weight: float = 1.0
    trigger_reason: str = ""
    action_taken: str = ""
    category: str = "unknown"          # v3.2 新增："triggered" / "not_triggered" / "unknown"
    context_relevance: float = 0.0     # v3.2 新增：0.0-1.0
```

### DecisionRecord（persistence.py，不变）

v3.2 不新增 DecisionRecord 持久化字段。

### 新增配置段（config.py）

详见 1.3.8 节。

## 4.3 新增文件清单

| 文件 | 类型 | 说明 |
|------|------|------|
| `step_classifier.py` | 新增 | 步骤分类器，7 类步骤分类 + 分类驱动处理策略 |
| `loop_detector.py` | 新增 | 循环检测，重复步骤签名 + n-gram 文本循环检测 |
| `perception_enhancer.py` | 新增 | 感知增强，话题追踪 + 情感分析 + 参与者画像 |
| `quality_stats.py` | 新增 | 决策质量统计，滑动窗口 + 触发准确率/误触发率/漏触发率 |

## 4.4 修改文件清单

| 文件 | 变更类型 | 说明 |
|------|----------|------|
| `deepseek_client.py` | 扩展 | 新增 `compute_adaptive_effort()`、`_validate_reasoning_content()`、`_fix_reasoning_content()`、`_apply_strict_mode()`、`_send_with_strict_fallback()`、`_send_with_enhanced_retry()` |
| `agent.py` | 扩展 | perceive 集成感知增强、_react_loop 集成步骤分类器 + 循环检测 + 自适应步数、reflect 集成多维度评估、新增 `EnhancedReflectionResult`、`PerceptionData` 扩展 |
| `agent_memory.py` | 扩展 | 新增 `get_enhanced_memories()`、`_classify_memory()`、`_compute_context_relevance()`、`_deduplicate_memories()`、`_adjust_capacity()`、`format_enhanced_memories_for_prompt()` |
| `overflow_manager.py` | 扩展 | 新增 `soft_prune_with_relevance()`、`hard_prune_with_priority()`、`_compute_message_priority()`，`get_managed_context()` 新增 `perception_signals` 参数 |
| `config.py` | 扩展 | 新增 2 个配置段，config_version 升级 |
| `prompts.py` | 扩展 | 新增 `DEEPSEEK_WORKFLOW_PROMPT`、`DEEPSEEK_TOOL_PROTOCOL`、`SCENARIO_EXAMPLES`、`DECISION_BOUNDARY`、感知增强模板，`build_system_prompt()` 新增参数 |
| `webui.py` | 扩展 | 新增 2 个质量统计 API 端点，stats 扩展，WebSocket 新增事件类型 |
| `event_bus.py` | 不变 | 无需修改，事件类型由发布方定义 |
| `persistence.py` | 不变 | 不新增 DecisionRecord 字段 |
| `context_compressor.py` | 不变 | 1M 模式下由 OverflowManager 替代，非 1M 模式下行为不变 |
| `agent_tools.py` | 不变 | 现有工具定义和执行逻辑不变 |
| `cooldown.py` | 不变 | 不涉及 |
| `smart_cleanup.py` | 不变 | 不涉及 |
| `plugin.py` | 扩展 | 初始化新增模块实例 |

## 4.5 测试策略

### 单元测试

| 模块 | 测试重点 |
|------|---------|
| `step_classifier.py` | 7 类步骤分类正确性、分类驱动处理策略、think-only 步骤处理、filtered 步骤处理、invalid 步骤重试限制、签名计算 |
| `loop_detector.py` | 重复步骤签名检测、n-gram 文本循环检测、循环中断策略、连续检测强制结束、重置状态 |
| `perception_enhancer.py` | 话题识别和切换检测、情感极性和转折检测、参与者画像构建和缓存、LLM 调用失败降级 |
| `quality_stats.py` | 触发准确率计算、误触发率计算、漏触发率估算、滑动窗口、效率指标统计 |
| `deepseek_client.py` | reasoning_effort 自适应调节、reasoning_content 回传验证和修复、strict 模式集成和降级、思考模式参数兼容、SSE 超时检测、指数退避重试 |
| `agent_memory.py` | 记忆分类、上下文关联排序、语义去重、容量动态调整、增强格式模板 |
| `overflow_manager.py` | 上下文感知软剪枝、优先级标注硬剪枝、感知信号相关性排序 |
| `config.py` | 新增配置段默认值、向后兼容性 |

### 集成测试

| 场景 | 验证点 |
|------|--------|
| 步骤分类器 + ReAct 循环 | 步骤分类驱动不同的处理策略、think-only 步骤正确处理、invalid 步骤重试限制 |
| 循环检测 + ReAct 循环 | 重复步骤签名循环中断、n-gram 文本循环提示、连续检测强制结束 |
| 感知增强完整流程 | 话题追踪 → 情感分析 → 参与者画像 → 提示词注入 → 决策执行 |
| DeepSeek 深度优化完整流程 | reasoning_effort 自适应 → strict 模式 → SSE 超时重试 → reasoning_content 回传 |
| 记忆增强注入完整流程 | 记忆分类 → 上下文关联 → 去重 → 容量调整 → 格式化注入 |
| 反思子智能体增强 | 多维度评估 → 加权计算 → 否决维度和理由 |
| 上下文感知压缩 | 感知信号 → 相关性排序 → 优先级标注 → 剪枝 |
| 决策质量统计 | 决策记录 → 指标计算 → 事件广播 → WebUI 展示 |
| 向后兼容 | 所有 v3.2 新功能关闭时，行为与 v3.1 完全一致 |

### 性能测试

| 指标 | 目标 |
|------|------|
| 话题追踪分析耗时 | < 500ms |
| 情感分析耗时 | < 300ms |
| 参与者画像构建耗时 | < 200ms |
| 记忆增强注入格式化耗时 | < 50ms |
| 步骤分类器分类判定耗时 | < 10ms |
| 循环检测耗时 | < 50ms |
| reasoning_effort 自适应计算耗时 | < 10ms |
| SSE 超时检测额外延迟 | 0ms |