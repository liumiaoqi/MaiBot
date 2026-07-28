# Proactive Chat v2.1 — 编码任务规划

> 基于需求规格 `spec.md` 和实现方案 `design.md` 生成
> 插件目录：`data/MaiMBot/plugins/proactive-chat/`
> 修改模块：`config.py`、`persistence.py`、`prompts.py`、`agent.py`、`cooldown.py`、`webui.py`、`plugin.py`、`config.toml`
> 任务编号从 76 开始（原有任务 1-75 已完成）
> 前端约束：纯原生 HTML/CSS/JS，HTML 嵌入 Python 字符串 `_HTML_PAGE`，不引入外部 JS/CSS 库

---

## 76. 延迟触发配置段新增

- [ ] 在 `config.py` 中新增 `DelayedTriggerConfig(PluginConfigBase)` 配置段：
  - `delayed_trigger_enabled: bool = Field(default=True, description="是否启用延迟触发机制，禁用后所有触发即时执行")`
  - `timing_threshold: float = Field(default=0.7, ge=0.0, le=1.0, description="时机评估阈值，timing_score 低于此值时延迟触发")`
  - `max_delay_seconds: int = Field(default=600, ge=0, le=3600, description="延迟触发最大等待时长（秒），0 表示禁用延迟触发")`
  - 设置 `__ui_label__ = "延迟触发"`, `__ui_icon__ = "clock"`, `__ui_order__ = 10`
- [ ] 在 `ProactiveChatConfig` 中新增 `delayed_trigger: DelayedTriggerConfig = Field(default_factory=DelayedTriggerConfig)` 聚合字段
- [ ] 在 `config.toml` 中新增 `[delayed_trigger]` 段：
  - `delayed_trigger_enabled = true`
  - `timing_threshold = 0.7`
  - `max_delay_seconds = 600`
- [ ] 将 `PluginSectionConfig.config_version` 默认值从 `"2.0.0"` 更新为 `"2.1.0"`
- [ ] 同步更新 `config.toml` 中的 `config_version = "2.1.0"`
- 涉及文件：`plugins/proactive-chat/config.py`、`plugins/proactive-chat/config.toml`
- 验收标准：所有字段均有默认值；Pydantic 校验约束（ge/le）生效；WebUI 可展示新增的延迟触发配置段；`ProactiveChatConfig` 实例化不报错；config.toml 包含新增配置段且 config_version 为 2.1.0

**依赖**：无

---

## 77. DecisionRecord 扩展：新增 timing_score 字段

- [ ] 在 `persistence.py` 的 `DecisionRecord` dataclass 中新增 `timing_score: float = 1.0` 字段
- [ ] 在 `_fill_record_defaults()` 函数中新增 `data.setdefault("timing_score", 1.0)` 默认值填充
- [ ] 在 `_dict_to_record()` 函数中新增 `timing_score=data.get("timing_score", 1.0)` 字段映射
- 涉及文件：`plugins/proactive-chat/persistence.py`
- 验收标准：`DecisionRecord` 包含 `timing_score` 字段，默认值 1.0；旧版 JSONL 记录读取时自动填充默认值 1.0

**依赖**：无

---

## 78. AnalysisResult 扩展：新增 timing_score 字段

- [ ] 在 `agent.py` 的 `AnalysisResult` dataclass 中新增 `timing_score: float = 1.0` 字段
- [ ] 修改 `parse_analysis_result()` 方法，新增 `timing_score` 字段解析：
  - `timing_score = float(data.get("timing_score", 1.0))`
  - 解析失败时默认 1.0（与 v2.0 行为一致，即时触发）
  - 将 `timing_score` 值限制在 0.0-1.0 范围内（`max(0.0, min(1.0, timing_score))`）
  - 将 `timing_score` 加入返回的 `AnalysisResult` 构造
- [ ] 修改 `reflect()` 方法，在 `analysis_result` 字典中新增 `"timing_score": result.timing_score` 键
- [ ] 修改 `plugin.py` 的 `handle_trigger_proactive_chat` @Tool 方法，在 `analysis_result` 字典中新增 `"timing_score": 1.0`（@Tool 路径始终即时触发）
- 涉及文件：`plugins/proactive-chat/agent.py`、`plugins/proactive-chat/plugin.py`
- 验收标准：`AnalysisResult` 包含 `timing_score` 字段，默认值 1.0；`parse_analysis_result` 可正确解析 `timing_score`；解析失败时默认 1.0；`reflect` 持久化的 `analysis_result` 包含 `timing_score`

**依赖**：任务 77（DecisionRecord 已扩展 timing_score）

---

## 79. 提示词扩展：时机评估维度与 timing_score 输出格式

- [ ] 修改 `prompts.py` 的 `AGENT_SYSTEM_PROMPT`，在"输出格式"段落中扩展 JSON 格式定义：
  - 将 `{{"should_trigger": bool, "intent": "意图标签", "reason": "自然语言原因描述", "confidence": float}}` 改为 `{{"should_trigger": bool, "intent": "意图标签", "reason": "自然语言原因描述", "confidence": float, "timing_score": float}}`
  - 在字段说明中新增 `timing_score` 字段定义：`timing_score：触发时机评分，0.0-1.0 之间的浮点数，1.0 表示当前是绝佳时机应立即触发，0.0 表示当前完全不适合触发应延迟，中间值表示不同程度的适合性`
  - 修改不触发时的返回格式为 `{{"should_trigger": false, "intent": "", "reason": "", "confidence": 0.0, "timing_score": 0.0}}`
- [ ] 在 `AGENT_SYSTEM_PROMPT` 的"决策倾向"段落后新增"时机评估"段落：
  ```
  ## 时机评估

  当你判断 should_trigger=true 时，还需要评估当前是否是合适的触发时机。请基于以下维度评估 timing_score：

  1. **对话活跃度**：群聊正在热烈讨论时评分低（0.2-0.4），对话节奏平缓时评分中等（0.5-0.6），冷场后评分高（0.8-1.0）
  2. **话题连贯性**：话题刚切换时评分低（0.3-0.5），话题稳定讨论中评分中等（0.5-0.7），话题间隙评分高（0.7-0.9）
  3. **用户注意力**：刚有人提问时评分高（0.7-0.9），用户在闲聊时评分中等（0.4-0.6）
  4. **冷场信号**：有冷场信号时评分高（0.8-1.0），无冷场信号时按其他维度评估

  注意：
  - 如果对话节奏正常且 bot 有明确的介入理由（如漏回补答），timing_score 应较高
  - 如果只是话题相关但对话节奏正常，timing_score 应较低
  - missed_reply 场景通常 timing_score 较高，因为需要立即补答
  ```
- [ ] 同步修改英文和日文提示词文件（如有），对齐到中文
- 涉及文件：`plugins/proactive-chat/prompts.py`
- 验收标准：`AGENT_SYSTEM_PROMPT` 包含 `timing_score` 字段定义和评估维度；输出格式 JSON 包含 `timing_score`；时机评估段落包含四个维度和注意事项

**依赖**：无

---

## 80. 延迟触发队列实现

- [ ] 在 `agent.py` 中新增 `DelayedTriggerRequest` dataclass：
  ```python
  @dataclass
  class DelayedTriggerRequest:
      stream_id: str
      intent: str
      reason: str
      confidence: float
      timing_score: float
      created_at: float        # Unix 时间戳（秒）
      max_delay_seconds: int   # 最大延迟等待时长，默认 600
  ```
- [ ] 在 `agent.py` 中新增 `DelayedTriggerQueue` 类：
  - `__init__(self) -> None`：初始化 `self._queue: dict[str, DelayedTriggerRequest] = {}`
  - `enqueue(self, request: DelayedTriggerRequest) -> None`：入队，同一 stream_id 去重（替换旧请求）
  - `dequeue(self, stream_id: str) -> DelayedTriggerRequest | None`：出队指定聊天流的请求
  - `get_pending(self) -> list[DelayedTriggerRequest]`：获取所有待处理请求
  - `get_pending_for_stream(self, stream_id: str) -> DelayedTriggerRequest | None`：获取指定聊天流的待处理请求
  - `is_empty(self) -> bool`：队列是否为空
  - `clear(self) -> None`：清空队列
- [ ] 在 `AgentCore.__init__` 中新增 `self._delayed_queue = DelayedTriggerQueue()` 实例属性
- 涉及文件：`plugins/proactive-chat/agent.py`
- 验收标准：`DelayedTriggerQueue` 以 `dict[str, DelayedTriggerRequest]` 存储，以 `stream_id` 为键天然去重；入队时替换同 `stream_id` 的旧请求；`dequeue` 正确移除并返回请求；`is_empty` 和 `get_pending` 行为正确

**依赖**：任务 78（`AnalysisResult` 已扩展 `timing_score`）

---

## 81. 时机评估路由：decision_loop 行动阶段分支

- [ ] 修改 `agent.py` 的 `decision_loop()` 方法，在行动阶段（`should_trigger=True` 且 `confidence >= 0.5` 之后）插入时机评估路由逻辑：
  ```python
  # 原有：直接调用 act()
  # v2.1 新增：在 act 之前插入时机评估路由
  if result.should_trigger and result.confidence >= 0.5:
      if not config.delayed_trigger.delayed_trigger_enabled or config.delayed_trigger.max_delay_seconds == 0:
          # 延迟触发禁用，即时触发（v2.0 行为）
          action_taken, trigger_time = await self.act(stream_id, result, ctx, config)
      elif result.timing_score >= config.delayed_trigger.timing_threshold:
          # 时机合适，即时触发
          action_taken, trigger_time = await self.act(stream_id, result, ctx, config)
      else:
          # 时机不合适，延迟触发
          self._delayed_queue.enqueue(DelayedTriggerRequest(
              stream_id=stream_id,
              intent=result.intent,
              reason=result.reason,
              confidence=result.confidence,
              timing_score=result.timing_score,
              created_at=time.time(),
              max_delay_seconds=config.delayed_trigger.max_delay_seconds,
          ))
          action_taken = "delayed"
          trigger_time = 0.0
  ```
- [ ] 修改 `reflect()` 方法，在 `analysis_result` 字典中确保包含 `timing_score`
- [ ] 确保 `action_taken` 新增枚举值 `delayed` 和 `triggered_delayed` 在决策记录中正确持久化
- 涉及文件：`plugins/proactive-chat/agent.py`
- 验收标准：`delayed_trigger_enabled=False` 时所有触发即时执行（v2.0 行为）；`timing_score >= threshold` 时即时触发；`timing_score < threshold` 时入延迟队列，`action_taken` 为 `"delayed"`；`max_delay_seconds=0` 时禁用延迟触发

**依赖**：任务 76（`DelayedTriggerConfig` 已定义）、任务 78（`AnalysisResult` 含 `timing_score`）、任务 80（`DelayedTriggerQueue` 已实现）

---

## 82. 冷场信号查询方法：CooldownManager.get_cooled_down_streams

- [ ] 在 `cooldown.py` 的 `CooldownManager` 中新增 `get_cooled_down_streams(cooldown_seconds: int) -> list[str]` 方法：
  ```python
  def get_cooled_down_streams(self, cooldown_seconds: int) -> list[str]:
      """返回已过冷却期的聊天流 stream_id 列表。
      
      冷场信号的定义：聊天流在过去一段时间内无消息（已过冷却期），
      意味着该聊天流处于冷场状态，适合执行延迟触发。
      """
      now = time.time()
      return [
          sid for sid, rec in self._records.items()
          if (now - rec.triggered_at) >= cooldown_seconds
      ]
  ```
- 涉及文件：`plugins/proactive-chat/cooldown.py`
- 验收标准：`get_cooled_down_streams` 正确返回已过冷却期的 `stream_id` 列表；空记录时返回空列表

**依赖**：无

---

## 83. 延迟触发检查循环：plugin.py

- [ ] 在 `plugin.py` 中新增 `_delayed_trigger_check_loop` 异步方法：
  - 每 30 秒检查一次延迟触发队列
  - 获取冷场信号（`CooldownManager.get_cooled_down_streams()`）
  - 遍历队列中的待处理请求，判断是否应执行：
    - 请求超过最大等待时长（`now - req.created_at >= req.max_delay_seconds`）→ 应执行
    - 目标聊天流出现冷场信号（`req.stream_id in cooled_down_streams`）→ 应执行
  - 执行前校验冷却和白名单
  - 校验通过后调用 `AgentCore.act()` 执行延迟触发
  - 更新决策记录的 `action_taken` 为 `"triggered_delayed"`
  - 内部 try/except 包裹，确保异常不影响后续检查
- [ ] 在 `on_load()` 末尾，与 `_cooldown_expiry_loop` 同级启动延迟触发检查循环：
  ```python
  if config.delayed_trigger.delayed_trigger_enabled:
      self._delayed_check_task = asyncio.create_task(self._delayed_trigger_check_loop())
  ```
- [ ] 在 `on_unload()` 中取消延迟触发检查循环：
  ```python
  if hasattr(self, "_delayed_check_task") and self._delayed_check_task:
      self._delayed_check_task.cancel()
  ```
- [ ] 在 `on_config_update()` 中，如果延迟触发配置变更，重启检查循环
- [ ] 新增 `_delayed_check_task: asyncio.Task | None` 类属性声明
- 涉及文件：`plugins/proactive-chat/plugin.py`
- 验收标准：延迟触发检查循环每 30 秒执行一次；冷场信号驱动的延迟触发正确执行；最大等待超时的延迟触发正确执行；冷却中/不在白名单的请求被跳过并记录日志；循环异常不影响后续检查；插件卸载时循环被正确取消

**依赖**：任务 80（`DelayedTriggerQueue`）、任务 82（`get_cooled_down_streams`）、任务 81（时机评估路由）

---

## 84. 延迟触发恢复：从决策记录恢复队列

- [ ] 在 `plugin.py` 中新增 `_recover_delayed_triggers` 异步方法：
  ```python
  async def _recover_delayed_triggers(self) -> int:
      """从决策记录恢复延迟触发队列"""
      recovered = 0
      try:
          records, _ = await self._persistence_manager.query_decisions(
              action="delayed",
              limit=100,
          )
          for rec in records:
              ar = rec.analysis_result or {}
              # 检查是否已超过最大延迟时长，超时的不恢复
              max_delay = self._config.delayed_trigger.max_delay_seconds
              if time.time() - rec.ts >= max_delay:
                  continue
              self._agent._delayed_queue.enqueue(DelayedTriggerRequest(
                  stream_id=rec.stream_id,
                  intent=ar.get("intent", ""),
                  reason=ar.get("reason", ""),
                  confidence=ar.get("confidence", 0.0),
                  timing_score=ar.get("timing_score", 1.0),
                  created_at=rec.ts,
                  max_delay_seconds=max_delay,
              ))
              recovered += 1
          if recovered:
              logger.info("[proactive-chat] 恢复了 %d 条延迟触发请求", recovered)
      except Exception as e:
          logger.warning("[proactive-chat] 延迟触发恢复异常(%s): %s", type(e).__name__, e)
      return recovered
  ```
- [ ] 在 `on_load()` 中，AgentCore 初始化之后调用 `_recover_delayed_triggers()`：
  ```python
  if self._config.delayed_trigger.delayed_trigger_enabled:
      recovered = await self._recover_delayed_triggers()
  ```
- [ ] 在 `plugin.py` 顶部 import 中新增 `from .agent import DelayedTriggerRequest`
- 涉及文件：`plugins/proactive-chat/plugin.py`
- 验收标准：插件重启后可从决策记录恢复 `action_taken="delayed"` 的延迟触发请求；已超过最大延迟时长的请求不恢复；恢复的请求包含完整的 `timing_score` 等字段

**依赖**：任务 80（`DelayedTriggerQueue`、`DelayedTriggerRequest`）、任务 83（检查循环已启动）

---

## 85. 聊天流列表 API：GET /api/proactive-chat/streams

- [ ] 在 `webui.py` 的 `WebUIServer.__init__()` 中新增 `stream_fetcher: Callable | None = None` 参数，保存为 `self._stream_fetcher`
- [ ] 在 `webui.py` 中实现 `_handle_streams(request: web.Request)` 异步方法：
  - 调用 `self._stream_fetcher()` 获取聊天流列表
  - `stream_fetcher` 为 None 或调用失败时返回 `{"success": false, "error": "无法获取聊天流列表"}`
  - 构建返回数据：对每个聊天流调用 `_build_display_name()` 构建显示名称
  - 查询冷却状态：通过 `self._cooldown` 查询每个聊天流是否在冷却中及剩余时间
  - 查询白名单状态：通过 `ScopeMatcher` 或直接查询配置判断是否在白名单范围内
  - 排序：群聊在前，私聊在后，同类内按 `display_name` 排序
  - 返回 `{"success": true, "streams": [...]}`
- [ ] 实现 `_build_display_name(stream: dict) -> tuple[str, str]` 模块级函数：
  - 群聊：优先使用 `group_name`，无法获取时降级显示 `stream_id[:8] + "..."`
  - 私聊：优先使用 `user_nickname` 或 `user_cardname`，拼接"的私聊"，无法获取时降级显示 `stream_id[:8] + "..."`
  - 返回 `(display_name, chat_type)`
- [ ] 在 `start()` 方法中注册新路由：`self._app.router.add_get("/api/proactive-chat/streams", self._handle_streams)`
- 涉及文件：`plugins/proactive-chat/webui.py`
- 验收标准：`GET /api/proactive-chat/streams` 返回活跃聊天流列表；每条记录包含 `stream_id`、`display_name`、`chat_type`、`is_cooled_down`、`is_in_scope`、`remaining_cooldown_seconds`；群聊显示群名称，私聊显示"xxx 的私聊"；API 不可用时返回错误响应；排序规则正确

**依赖**：无

---

## 86. 聊天流获取回调：plugin.py 传入 stream_fetcher

- [ ] 在 `plugin.py` 中新增 `_fetch_streams()` 方法：
  ```python
  async def _fetch_streams(self) -> list[dict] | None:
      """获取活跃聊天流列表，供 WebUI streams API 使用"""
      try:
          if not hasattr(self.ctx, "chat"):
              return None
          result = await self.ctx.chat.get_all_streams()
          if isinstance(result, list):
              return result
          return None
      except Exception as e:
          logger.warning("[proactive-chat] 获取聊天流列表失败(%s): %s", type(e).__name__, e)
          return None
  ```
- [ ] 修改 `on_load()` 中 `WebUIServer` 初始化，新增 `stream_fetcher` 参数：
  ```python
  self._webui = WebUIServer(
      cooldown_manager=self._cooldown_manager,
      persistence_manager=self._persistence_manager,
      agent=self._agent,
      config_getter=lambda: self._config,
      config_updater=self._handle_webui_config_update,
      stream_fetcher=self._fetch_streams,
  )
  ```
- 涉及文件：`plugins/proactive-chat/plugin.py`
- 验收标准：`WebUIServer` 可通过 `stream_fetcher` 回调获取活跃聊天流列表；`ctx.chat` 不可用时返回 None

**依赖**：任务 85（`WebUIServer` 已支持 `stream_fetcher` 参数）

---

## 87. 聊天流选择器前端：手动触发对话框改造

- [ ] 修改 `_HTML_PAGE` 中 `showTriggerDialog()` 函数，将 `<input id="trigger-stream-id">` 替换为下拉选择器 + 降级输入框：
  - 新增 `<select id="trigger-stream-select">` 下拉选择器
  - 保留 `<input id="trigger-stream-id">` 作为降级输入框（默认隐藏）
  - 打开对话框时自动调用 `GET /api/proactive-chat/streams` 获取聊天流列表
  - 成功时：填充 `<select>` 选项
    - 每个选项 `value` = `stream_id`
    - 显示文本格式：`[群聊] 技术交流群` 或 `[私聊] 张三 的私聊`
    - 冷却中的选项：文本追加 `（冷却中 Xm Xs）`，设置 `disabled`
    - 不在白名单的选项：文本追加 `（不在白名单）`
    - 空状态：选项文本为"当前无活跃聊天流"，`disabled`
  - 失败时：隐藏 `<select>`，显示 `<input>` 文本输入框，提示"无法获取聊天流列表，请手动输入聊天流 ID"
  - 加载超时（>5s）时：显示"加载超时"，提供"重试"按钮和"手动输入"切换选项
- [ ] 修改 `triggerDecision()` 函数，优先从 `<select>` 获取 `stream_id`：
  - 如果 `<select>` 可见，从 `select.value` 获取
  - 如果 `<select>` 不可见，从 `input.value` 获取
- [ ] 新增 CSS 样式：选择器容器、加载状态、空状态提示
- 涉及文件：`plugins/proactive-chat/webui.py`（`_HTML_PAGE` 常量）
- 验收标准：点击"手动触发"弹出聊天流选择器；列表显示群名称/私聊名称而非哈希 ID；冷却中的聊天流不可选择；不在白名单的聊天流显示标签；API 不可用时降级为文本输入；空状态显示友好提示；加载超时提供重试和手动输入切换

**依赖**：任务 85（streams API 已实现）

---

## 88. 延迟触发状态展示：WebUI 决策记录增强

- [ ] 修改 `_HTML_PAGE` 中决策记录表格的"动作"列渲染，新增 `delayed` 和 `triggered_delayed` 的 badge 样式：
  - `delayed`：橙色 badge，显示"延迟中"
  - `triggered_delayed`：绿色 badge，显示"延迟触发"
- [ ] 修改决策记录详情面板，新增 `timing_score` 字段展示：
  - 在详情网格中新增一行：标签"时机评分"，值显示 `timing_score`（保留 2 位小数）
- [ ] 修改 `_handle_decisions` API 的 `action` 筛选参数，支持 `delayed` 和 `triggered_delayed` 可选值
- [ ] 修改决策记录筛选下拉框，新增"延迟中"和"延迟触发"选项
- 涉及文件：`plugins/proactive-chat/webui.py`（`_HTML_PAGE` 常量 + 后端方法）
- 验收标准：决策记录表格中 `delayed` 和 `triggered_delayed` 动作显示对应 badge；详情面板显示时机评分；筛选下拉框包含新增选项

**依赖**：任务 78（`AnalysisResult` 含 `timing_score`）、任务 81（`action_taken` 新增枚举值）

---

## 89. 延迟触发队列状态展示：WebUI 新增队列信息

- [ ] 在 `_HTML_PAGE` 统计概览卡片中新增延迟触发队列状态项：
  - "延迟队列"：显示当前队列中的待处理请求数量
- [ ] 新增 `GET /api/proactive-chat/delayed-queue` API 端点（或在 stats API 中新增字段）：
  - 返回延迟触发队列的待处理请求数量
  - 可选：返回队列中各请求的摘要信息（stream_id、intent、timing_score、等待时长）
- [ ] 修改 `_handle_stats()` 方法，在响应数据中新增 `delayed_queue_count` 字段
- 涉及文件：`plugins/proactive-chat/webui.py`（`_HTML_PAGE` 常量 + 后端方法）
- 验收标准：统计概览卡片显示延迟触发队列的待处理请求数量；stats API 包含 `delayed_queue_count` 字段

**依赖**：任务 80（`DelayedTriggerQueue` 已实现）、任务 83（检查循环已启动）

---

## 90. 降级与容错完善

- [ ] 确保 `timing_score` 缺失或解析失败时默认 1.0，行为与 v2.0 一致（即时触发）
- [ ] 确保延迟触发禁用（`delayed_trigger_enabled=False` 或 `max_delay_seconds=0`）时所有触发即时执行
- [ ] 确保延迟触发执行时仍校验冷却窗口：冷却中则跳过并记录日志
- [ ] 确保延迟触发执行时仍校验白名单：不在白名单则跳过并记录日志
- [ ] 确保延迟触发最大等待超时后自动执行（仍校验冷却+白名单）
- [ ] 确保 `ctx.chat.get_all_streams()` 不可用时 WebUI 降级为文本输入模式
- [ ] 确保聊天流名称获取失败时降级显示 `stream_id[:8] + "..."`
- [ ] 确保延迟触发检查循环异常不影响主流程
- [ ] 确保所有日志使用 `[proactive-chat]` 前缀，优先中文
- 涉及文件：`plugins/proactive-chat/agent.py`、`plugins/proactive-chat/plugin.py`、`plugins/proactive-chat/webui.py`
- 验收标准：各降级场景下插件不崩溃、不影响主流程；日志中可观察到降级记录；延迟触发禁用时行为与 v2.0 完全一致

**依赖**：任务 81（时机评估路由）、任务 83（检查循环）、任务 85（streams API）、任务 87（聊天流选择器）

---

## 91. 集成验证

- [ ] 验证延迟触发配置：通过 WebUI 修改 `delayed_trigger_enabled`、`timing_threshold`、`max_delay_seconds`，确认配置热更新生效
- [ ] 验证时机评估：在白名单群聊中发送消息，确认 DeepSeek 推理结果包含 `timing_score`
- [ ] 验证即时触发路径：`timing_score >= threshold` 时立即触发主动对话
- [ ] 验证延迟触发路径：`timing_score < threshold` 时不立即触发，请求进入延迟队列
- [ ] 验证冷场驱动触发：延迟队列中的请求在冷场信号出现后被执行
- [ ] 验证最大等待超时：延迟队列中的请求超过最大延迟时长后被执行
- [ ] 验证冷却校验：延迟触发执行时聊天流处于冷却期则跳过
- [ ] 验证白名单校验：延迟触发执行时聊天流不在白名单则跳过
- [ ] 验证延迟触发恢复：重启插件后，延迟队列中的请求从决策记录恢复
- [ ] 验证聊天流选择器：WebUI 手动触发对话框显示可选择的聊天流列表
- [ ] 验证聊天流选择器降级：`ctx.chat` 不可用时降级为文本输入模式
- [ ] 验证决策记录：`action_taken` 为 `delayed` 或 `triggered_delayed` 的记录正确持久化
- [ ] 验证禁用延迟触发：`delayed_trigger_enabled=False` 时所有触发即时执行
- [ ] Docker 部署验证：将插件目录挂载到容器内，确认容器化环境下正常运行
- 涉及文件：全部插件文件
- 验收标准：所有核心功能路径可走通；降级场景不崩溃；决策记录包含 `timing_score`；延迟队列状态可查询；聊天流选择器正常工作

**依赖**：任务 90（降级容错完善）

---

## 92. _manifest.json 更新与收尾

- [ ] 更新 `_manifest.json` 的 `version` 为 `"2.1.0"`
- [ ] 更新 `_manifest.json` 的 `description` 反映 v2.1 新增能力
- [ ] 确认所有文件无遗留的 v2.0 硬编码版本号引用
- [ ] 确认 `config.toml` 与 `ProactiveChatConfig` 模型字段完全对齐
- [ ] 确认所有新增日志使用 `[proactive-chat]` 前缀
- 涉及文件：`plugins/proactive-chat/_manifest.json`、`plugins/proactive-chat/config.toml`
- 验收标准：`_manifest.json` version 为 2.1.0；config.toml 与配置模型字段对齐；无遗留版本号引用

**依赖**：任务 91（集成验证通过）