# Proactive Chat 插件 — 编码任务规划（v2）

> 基于需求规格 `spec.md` 和实现方案 `design.md` 生成
> 插件目录：`data/MaiMBot/plugins/proactive-chat/`
> 旧版模块（6个）：config.py, cooldown.py, scope.py, prompts.py, analyzer.py, plugin.py
> 新版模块（8个）：config.py, cooldown.py, scope.py, prompts.py, agent.py, deepseek_client.py, persistence.py, plugin.py

---

## 1. 配置模型扩展

- [ ] 在 `config.py` 的 `AnalysisConfig` 中新增 `decision_retention_days: int = Field(default=30, ge=1, le=365)` 字段，移除 `analysis_model` 字段（不再使用 ctx.llm.generate）
- [ ] 在 `config.py` 中新增 `DeepseekConfig(PluginConfigBase)` 配置段：
  - `deepseek_model: str = Field(default="deepseek-chat")`
  - `deepseek_temperature: float = Field(default=0.3, ge=0.0, le=2.0)`
  - `deepseek_api_key: str = Field(default="", json_schema_extra={"label": "DeepSeek API Key", "hidden": True})`
  - `deepseek_base_url: str = Field(default="https://api.deepseek.com")`
  - 设置 `__ui_label__ = "DeepSeek"`, `__ui_icon__ = "cpu"`, `__ui_order__ = 5`
- [ ] 在 `ProactiveChatConfig` 中新增 `deepseek: DeepseekConfig = Field(default_factory=DeepseekConfig)` 聚合字段
- [ ] 将 `PluginSectionConfig.config_version` 默认值更新为 `"2.0.0"`
- 涉及文件：`plugins/proactive-chat/config.py`
- 验收标准：所有字段均有默认值；WebUI 可展示新增的 DeepSeek 配置段；Pydantic 校验约束生效

**依赖**：无

---

## 2. Prompt 模板重写

- [ ] 将 `ANALYSIS_SYSTEM_PROMPT` 重命名为 `AGENT_SYSTEM_PROMPT`，重写为智能体系统提示词：
  - 角色定义：对话节奏感知智能体
  - 决策框架：感知信号 → 综合推理 → 判断输出
  - 场景定义：topic_supplement / silence_break / missed_reply / memory_recall
  - 输出格式：JSON `{should_trigger, intent, reason, confidence}`（新增 confidence 字段）
  - 约束条件：不强行介入、不重复触发、记忆关联需确实相关、confidence < 0.5 时不触发
  - 推理引导：先分析对话状态，再判断是否介入
- [ ] 更新 `ANALYSIS_USER_TEMPLATE`：在末尾增加推理引导语"请先分析当前对话的状态和节奏，然后给出你的判断结果（JSON 格式）。"
- [ ] 保留信号提示模板不变：`SILENCE_SIGNAL_TEMPLATE`、`MISSED_REPLY_SIGNAL_TEMPLATE`、`MEMORY_CONTEXT_TEMPLATE`
- [ ] 保留 `TOOL_GUIDANCE_TEXT` 和 `VALID_INTENTS` 不变
- 涉及文件：`plugins/proactive-chat/prompts.py`
- 验收标准：`AGENT_SYSTEM_PROMPT` 包含角色定义、决策框架、场景定义、输出格式（含 confidence）、约束条件、推理引导；`ANALYSIS_USER_TEMPLATE` 包含推理引导语

**依赖**：无

---

## 3. _manifest.json 更新

- [ ] 将 `version` 从 `"1.0.0"` 更新为 `"2.0.0"`
- [ ] 更新 `description` 为智能体模式描述："以独立智能体模式运行，基于对话上下文自主判断并触发 MaiBot 主动发言，支持话题补充、冷场打破、漏回补答、记忆关联四种触发场景"
- [ ] 从 `capabilities` 中移除 `"llm.generate"` 和 `"knowledge.search"`
- [ ] 在 `capabilities` 中新增 `"config.get"`
- 涉及文件：`plugins/proactive-chat/_manifest.json`
- 验收标准：capabilities 不包含 `llm.generate` 和 `knowledge.search`；包含 `config.get`；version 为 2.0.0

**依赖**：无

---

## 4. DeepSeek 客户端模块实现

- [ ] 创建 `deepseek_client.py`，实现 `DeepSeekClient` 类
- [ ] 实现 `__init__(self)` 构造函数：初始化 `_api_key: str = ""`、`_api_key_available: bool = False`、`_client: httpx.AsyncClient | None = None`
- [ ] 实现 `async initialize(self, ctx, config: ProactiveChatConfig)` 方法：
  - 按优先级获取 API Key：
    1. `await ctx.config.get("api_providers")` → 遍历 provider 列表找 name 含 "deepseek" 的 → 提取 api_key
    2. 从 `config.deepseek.deepseek_api_key` 读取
    3. 从 `os.environ.get("DEEPSEEK_API_KEY")` 读取
  - 获取成功后缓存至 `_api_key`，设置 `_api_key_available = True`
  - 创建 `httpx.AsyncClient(timeout=30.0)`
  - 全部失败时记录错误日志，设置 `_api_key_available = False`
- [ ] 实现 `async analyze(self, system_prompt: str, user_prompt: str, config: ProactiveChatConfig) -> str` 方法：
  - 检查 `_api_key_available`，不可用则抛出 `RuntimeError`
  - 构建 OpenAI 兼容格式请求体（model、messages、temperature、max_tokens）
  - 使用 `self._client.post()` 发送 POST 请求到 `{base_url}/v1/chat/completions`
  - 处理 HTTP 错误：
    - 429：记录警告，放弃本次，不重试
    - 401/403：标记 `_api_key_available = False`，记录错误，后续不再尝试
    - 5xx：记录警告，放弃本次，下次仍可尝试
  - 解析响应 JSON，返回 `choices[0].message.content`
  - 超时（30s）和网络错误：记录警告，抛出异常
- [ ] 实现 `is_available(self) -> bool` 方法：返回 `_api_key_available`
- [ ] 实现 `async close(self)` 方法：关闭 httpx.AsyncClient
- [ ] 实现 `_mask_api_key(key: str) -> str` 静态方法：脱敏为 `sk-***...***` 格式
- 涉及文件：`plugins/proactive-chat/deepseek_client.py`（新建）
- 验收标准：API Key 按三级优先级正确获取；HTTP 请求格式符合 OpenAI Chat Completions API 规范；429/401/403/5xx 错误分别正确处理；API Key 不出现在日志中

**依赖**：任务 1（DeepseekConfig 已定义）

---

## 5. 持久化管理模块实现

- [ ] 创建 `persistence.py`，定义 `DecisionRecord` dataclass：
  - `ts: float`、`time: str`、`stream_id: str`、`input_summary: str`、`analysis_result: dict`、`action_taken: str`、`error: str = ""`
- [ ] 实现 `PersistenceManager` 类，构造函数接收 `data_dir: Path` 和 `retention_days: int = 30`
- [ ] 实现 `async save_decision(self, decision: DecisionRecord) -> None` 方法：
  - 写入 JSONL 文件 `data_dir / "decisions" / "decisions_YYYY-MM-DD.jsonl"`
  - 使用 `asyncio.to_thread` 避免阻塞事件循环
  - 写入失败时记录警告日志，功能不中断
- [ ] 实现 `async query_decisions(self, stream_id="", start_time=0.0, end_time=0.0, intent="", limit=100) -> list[DecisionRecord]` 方法：
  - 从 JSONL 文件中读取并过滤记录
  - 使用 `asyncio.to_thread` 避免阻塞
- [ ] 实现 `async cleanup_expired(self, retention_days: int = 0) -> int` 方法：
  - 删除超过 retention_days 天的决策文件
  - 默认使用构造函数传入的 retention_days
- 涉及文件：`plugins/proactive-chat/persistence.py`（新建）
- 验收标准：`save_decision` 可正确写入 JSONL 文件；`query_decisions` 可按条件过滤记录；`cleanup_expired` 可删除过期文件；文件写入失败时静默降级

**依赖**：无

---

## 6. 冷却管理模块重构

- [ ] 在 `cooldown.py` 中为 `CooldownManager` 新增文件持久化支持：
  - 构造函数新增 `data_dir: Path | None = None` 参数
  - 新增 `_data_dir` 和 `_file_path` 属性（`data_dir / "cooldown_state.json"`）
- [ ] 实现 `async restore_from_storage(self) -> None` 方法：
  - 从 JSON 文件读取冷却记录，仅恢复未过期的记录
  - 文件不存在或读取失败时静默跳过
  - JSON 格式：`{"version": 1, "records": {"stream_id": {"stream_id": "...", "triggered_at": ..., "intent": "..."}}}`
- [ ] 修改 `mark_triggered` 为异步方法 `async mark_triggered(self, stream_id: str, intent: str = "") -> None`：
  - 原有内存更新逻辑不变
  - 新增：同时持久化至 JSON 文件（使用 `asyncio.to_thread`）
  - 文件写入失败时记录降级日志，不影响内存状态
- [ ] 修改 `cleanup_expired` 方法：清理时同步清理文件中的过期记录
- [ ] 修改 `clear_all` 方法：清空时同步删除持久化文件
- 涉及文件：`plugins/proactive-chat/cooldown.py`
- 验收标准：`restore_from_storage` 可从文件恢复未过期的冷却记录；`mark_triggered` 同时写入内存和文件；文件读写失败时静默降级至内存模式

**依赖**：任务 5（PersistenceManager 的 data_dir 路径约定）

---

## 7. 智能体核心模块实现

- [ ] 创建 `agent.py`，定义 `PerceptionData` dataclass：
  - `recent_messages: list[dict]`、`silence_signal: bool`、`silence_seconds: int`、`missed_reply_signal: bool`、`memory_result: str`、`message_summary: str`
- [ ] 定义 `AnalysisResult` dataclass（从 analyzer.py 迁移并扩展）：
  - `should_trigger: bool = False`、`intent: str = ""`、`reason: str = ""`、`confidence: float = 0.0`
  - 新增 `confidence` 字段
- [ ] 实现 `AgentCore` 类，构造函数接收 `deepseek_client: DeepSeekClient`、`persistence_manager: PersistenceManager`、`cooldown_manager: CooldownManager` 的引用
- [ ] 实现 `async perceive(self, stream_id: str, ctx, config: ProactiveChatConfig) -> PerceptionData` 方法：
  - 获取近期消息（`ctx.message.get_recent()`）
  - 检测冷场信号（时间间隔分析，仅在 `enable_silence_break` 启用时）
  - 检测漏回信号（@bot 检测，仅在 `enable_missed_reply` 启用时）
  - 可选：检索 A_Memorix 记忆（`ctx.api.call("a_memorix.search_memory")`，失败时静默跳过）
  - 格式化消息摘要文本
- [ ] 实现 `async reason(self, stream_id: str, perception: PerceptionData, config: ProactiveChatConfig) -> AnalysisResult` 方法：
  - 从 `prompts.py` 获取 `AGENT_SYSTEM_PROMPT` 和 `ANALYSIS_USER_TEMPLATE`
  - 构建用户 Prompt（填充对话摘要、信号提示、记忆结果）
  - 调用 `self._deepseek_client.analyze()` 进行上下文分析
  - 解析分析结果（复用现有 `parse_analysis_result` 逻辑，新增 confidence 字段解析）
  - 解析失败时安全降级返回 `AnalysisResult(should_trigger=False)`
- [ ] 实现 `async act(self, stream_id: str, result: AnalysisResult, ctx, config: ProactiveChatConfig) -> None` 方法：
  - 调用 `ctx.maisaka.context.append()` 注入判断依据
  - 调用 `ctx.maisaka.trigger_proactive()` 触发主动对话
  - 调用 `self._cooldown_manager.mark_triggered()` 启动冷却
  - `context.append` 失败时记录警告，继续执行 trigger
  - `trigger_proactive` 失败时记录错误，不启动冷却
- [ ] 实现 `async reflect(self, stream_id: str, perception: PerceptionData, result: AnalysisResult, action_taken: str, error: str = "") -> None` 方法：
  - 构建 `DecisionRecord`
  - 调用 `self._persistence_manager.save_decision()` 持久化
- [ ] 实现 `async decision_loop(self, stream_id: str, ctx, config: ProactiveChatConfig) -> None` 方法：
  - 编排完整的感知→推理→行动→反思流程
  - 感知异常时记录日志并返回
  - 推理异常时记录日志，action_taken 设为 `error_api`/`error_timeout`/`error_parse`
  - 行动异常时记录日志，action_taken 设为 `error_trigger`
  - 反思异常时记录日志（反思失败不影响主流程）
  - 所有异常在内部捕获，不向外传播
- [ ] 将 `analyzer.py` 中的 `parse_analysis_result`、`_format_message_summary`、`_infer_message_role`、`_extract_query_text` 工具方法迁移至 `agent.py` 作为 `AgentCore` 的静态方法
  - 更新 `parse_analysis_result` 以支持 `confidence` 字段解析
- 涉及文件：`plugins/proactive-chat/agent.py`（新建）
- 验收标准：`decision_loop` 编排完整的四阶段流程；`perceive` 收集所有决策输入；`reason` 通过 DeepSeekClient 独立调用 API；`act` 正确注入上下文和触发；`reflect` 持久化决策记录；所有异常被捕获不向外传播

**依赖**：任务 2（Prompt 模板）、任务 4（DeepSeekClient）、任务 5（PersistenceManager）、任务 6（CooldownManager）

---

## 8. 插件入口重构

- [ ] 更新 `plugin.py` 的 import：移除 `from .analyzer import ...`，新增 `from .agent import AgentCore, AnalysisResult`、`from .deepseek_client import DeepSeekClient`、`from .persistence import PersistenceManager`
- [ ] 重构 `on_load()` 方法：
  - 初始化 `DeepSeekClient` 并调用 `await self._deepseek_client.initialize(self.ctx, config)`
  - 初始化 `PersistenceManager(data_dir=...)`，使用 `ctx.paths.data_dir` 或 fallback 至 `_PLUGIN_DIR / "data"`
  - 初始化 `CooldownManager(data_dir=...)` 并调用 `await self._cooldown_manager.restore_from_storage()`
  - 初始化 `AgentCore(deepseek_client, persistence_manager, cooldown_manager)`
  - 保留现有的 `ScopeMatcher` 初始化逻辑
- [ ] 重构 `on_unload()` 方法：
  - 新增 `await self._deepseek_client.close()`
  - 保留 `self._cooldown_manager.clear_all()`
- [ ] 重构 `on_message` HookHandler（`maisaka.planner.after_response`）：
  - 新增 `is_notify` 过滤：检查 `message.get("is_notify")`，为 True 则跳过
  - 保留现有的白名单检查、冷却检查、场景开关检查
  - 将 `asyncio.create_task(self._analyze_and_trigger(...))` 替换为 `asyncio.create_task(self._agent_core.decision_loop(stream_id=session_id, ctx=self.ctx, config=config))`
  - 移除信号检测逻辑（已迁移至 AgentCore.perceive）
- [ ] 移除 `_analyze_and_trigger` 方法（逻辑已迁移至 AgentCore.decision_loop）
- [ ] 移除 `_detect_silence_signal` 方法（已迁移至 AgentCore.perceive）
- [ ] 移除 `_detect_missed_reply_signal` 方法（已迁移至 AgentCore.perceive）
- [ ] 移除 `_get_recent_messages` 方法（已迁移至 AgentCore.perceive）
- [ ] 移除 `_inject_context_and_trigger` 方法（已迁移至 AgentCore.act）
- [ ] 保留 `_startup_catchup` 方法，但重构为使用 `AgentCore.decision_loop`
- [ ] 保留 `on_planner_before_request` HookHandler（逻辑不变）
- [ ] 保留 `handle_trigger_proactive_chat` @Tool，但更新为使用 `AgentCore.act` 替代 `_inject_context_and_trigger`
- [ ] 移除 `_write_audit` 全局函数和 `_AUDIT_LOG_DIR` 常量（决策记录持久化已迁移至 PersistenceManager）
- [ ] 确保所有日志使用 `[proactive-chat]` 前缀，优先中文
- 涉及文件：`plugins/proactive-chat/plugin.py`
- 验收标准：插件可正常加载和卸载；HookHandler 正确过滤 is_notify 消息；异步决策循环不阻塞消息主流程；@Tool 路径正常工作；所有旧方法已移除

**依赖**：任务 1（配置模型）、任务 4（DeepSeekClient）、任务 5（PersistenceManager）、任务 6（CooldownManager）、任务 7（AgentCore）

---

## 9. 旧模块清理

- [ ] 删除 `analyzer.py` 文件（所有逻辑已迁移至 agent.py）
- [ ] 更新 `__init__.py` 的导出（如有引用 analyzer 模块则移除）
- [ ] 确认 `prompts.py` 中不再有 `ANALYSIS_SYSTEM_PROMPT` 名称（已重命名为 `AGENT_SYSTEM_PROMPT`），更新所有引用
- [ ] 更新 `config.toml` 配置文件：
  - 移除 `[analysis]` 中的 `analysis_model` 字段
  - 新增 `[analysis]` 中的 `decision_retention_days = 30`
  - 新增 `[deepseek]` 段：`deepseek_model = "deepseek-chat"`, `deepseek_temperature = 0.3`, `deepseek_api_key = ""`, `deepseek_base_url = "https://api.deepseek.com"`
  - 更新 `config_version = "2.0.0"`
- 涉及文件：`plugins/proactive-chat/analyzer.py`（删除）、`plugins/proactive-chat/__init__.py`、`plugins/proactive-chat/prompts.py`、`plugins/proactive-chat/config.toml`
- 验收标准：`analyzer.py` 已删除；所有模块可正常 import；config.toml 包含新增配置段

**依赖**：任务 7（agent.py 已实现）、任务 8（plugin.py 已更新 import）

---

## 10. 降级与容错完善

- [ ] 确保 DeepSeek API 不可用时自动路径静默降级：`_api_key_available = False` 时 `decision_loop` 跳过推理阶段，action_taken 设为 `error_api`
- [ ] 确保 A_Memorix 不可用时跳过记忆检索：`perceive` 中 `ctx.api.call("a_memorix.search_memory")` 异常时 `memory_result = ""`，记录降级日志
- [ ] 确保 `maisaka.trigger_proactive` 失败时不启动冷却窗口，允许后续重试
- [ ] 确保 `maisaka.context.append` 失败时继续执行 trigger（非关键路径）
- [ ] 确保冷却状态文件读写失败时 fallback 至纯内存模式，记录降级日志
- [ ] 确保决策记录文件写入失败时记录警告日志，功能不中断
- [ ] 确保 `decision_loop` 内部所有异常被捕获，不影响消息主流程
- [ ] 确保 API Key 脱敏：日志中 API Key 显示为 `sk-***...***` 格式
- 涉及文件：`plugins/proactive-chat/agent.py`、`plugins/proactive-chat/deepseek_client.py`、`plugins/proactive-chat/persistence.py`、`plugins/proactive-chat/cooldown.py`
- 验收标准：各降级场景下插件不崩溃、不影响主流程；日志中可观察到降级记录；API Key 不出现在日志中

**依赖**：任务 7（AgentCore）、任务 4（DeepSeekClient）、任务 5（PersistenceManager）、任务 6（CooldownManager）

---

## 11. SDK 版本与 Docker 兼容性验证

- [ ] 确认 Docker 容器内 SDK 版本 ≥ 2.5.4，如需升级至 2.6.0 则更新容器镜像或 requirements
- [ ] 验证 `ctx.config.get("api_providers")` API 在当前 SDK 版本中可用（DeepSeekClient 依赖此 API 获取 API Key）
- [ ] 验证 `ctx.paths.data_dir` 属性在当前 SDK 版本中可用（PersistenceManager 和 CooldownManager 依赖此路径）
- [ ] 验证 `ctx.maisaka.trigger_proactive` 和 `ctx.maisaka.context.append` API 签名与当前版本兼容
- [ ] 验证插件代码通过卷挂载可正常同步到容器内 `data/MaiMBot/plugins/proactive-chat/`
- [ ] 确认 `httpx` 依赖已包含在项目依赖中（`deepseek_client.py` 依赖 httpx）
- 涉及文件：`pyproject.toml`（可能需要新增 httpx 依赖）、Docker 配置
- 验收标准：插件在 Docker 容器内可正常加载；所有 SDK API 调用可用；httpx 依赖已安装

**依赖**：任务 4（DeepSeekClient 使用 httpx）

---

## 12. 集成验证

- [ ] 在本地开发环境验证插件加载：启动 MaiBot，确认插件被正确加载，日志显示初始化成功（包括 DeepSeek API Key 获取结果）
- [ ] 验证 WebUI 配置页面：确认新增的 DeepSeek 配置段正确展示，API Key 字段隐藏
- [ ] 验证白名单机制：配置群聊/私聊白名单，确认仅白名单内聊天流触发分析
- [ ] 验证冷却窗口持久化：触发主动对话后重启插件，确认冷却状态从文件恢复
- [ ] 验证自动路径（after_response Hook）：在白名单群聊中发送消息，确认智能体决策循环被触发
- [ ] 验证 DeepSeek API 独立调用：确认上下文分析通过 DeepSeek API 完成，而非 ctx.llm.generate()
- [ ] 验证 @Tool 路径：确认 LLM 可调用 `trigger_proactive_chat` 工具
- [ ] 验证 before_request Hook 路径：确认 Planner 请求前注入工具引导文本
- [ ] 验证决策记录持久化：触发/跳过后检查 JSONL 文件中是否有对应记录
- [ ] 验证降级场景：
  - DeepSeek API Key 不可用 → 自动路径禁用，@Tool 路径仍可用
  - DeepSeek API 超时 → 放弃本次分析，记录决策
  - A_Memorix 不可用 → 跳过记忆检索
  - 冷却状态文件写入失败 → 纯内存模式
- [ ] Docker 部署验证：将插件目录挂载到容器内，确认容器化环境下正常运行
- 涉及文件：全部插件文件
- 验收标准：所有核心功能路径可走通；降级场景不崩溃；决策记录可查询；冷却状态可恢复

**依赖**：任务 8、9、10、11（所有功能模块已完成）

---

## 13. Git 提交与收尾

- [ ] 在任务 1-3 完成后提交：`feat(proactive-chat): 扩展配置模型、重写 Prompt 模板、更新 manifest`
- [ ] 在任务 4-6 完成后提交：`feat(proactive-chat): 新增 DeepSeek 客户端、持久化管理、冷却持久化`
- [ ] 在任务 7-8 完成后提交：`feat(proactive-chat): 实现智能体决策循环，重构插件入口`
- [ ] 在任务 9 完成后提交：`refactor(proactive-chat): 移除旧 analyzer 模块，清理配置文件`
- [ ] 在任务 10-12 完成后提交：`fix(proactive-chat): 完善降级容错，验证集成`
- [ ] 确认所有文件无遗留的 `analyzer.py` 引用
- [ ] 确认 `config.toml` 与 `ProactiveChatConfig` 模型字段完全对齐
- 涉及文件：全部插件文件
- 验收标准：Git 历史清晰，每次提交粒度合理；无遗留旧代码引用

**依赖**：任务 12（所有验证通过）

---

## 14. 人格注入与自定义提示词

- [x] 在 `config.py` 中新增 `PromptConfig(PluginConfigBase)` 配置段：
  - `custom_prompt: str = Field(default="", ...)` 字段
  - 设置 `__ui_label__ = "提示词"`, `__ui_icon__ = "message-square"`, `__ui_order__ = 6`
- [x] 在 `ProactiveChatConfig` 中新增 `prompt: PromptConfig = Field(default_factory=PromptConfig)` 聚合字段
- [x] 在 `prompts.py` 的 `AGENT_SYSTEM_PROMPT` 中新增 `{personality_section}` 和 `{custom_prompt_section}` 占位符
- [x] 在 `prompts.py` 中新增子模板常量：`PERSONALITY_TEMPLATE`、`ALIAS_TEMPLATE`、`PERSONALITY_DETAIL_TEMPLATE`、`REPLY_STYLE_TEMPLATE`
- [x] 在 `prompts.py` 中新增 `build_system_prompt()` 函数，组装人格段落和自定义提示词段落
- [x] 在 `agent.py` 的 `AgentCore.__init__` 中新增缓存属性：`_bot_nickname`、`_alias_names`、`_personality`、`_reply_style`
- [x] 在 `agent.py` 中新增 `update_personality()` 方法，更新人格缓存属性
- [x] 将 `agent.py` 的 `_build_prompts` 从静态方法改为实例方法，调用 `build_system_prompt()` 传入人格缓存和 `config.prompt.custom_prompt`
- [x] 在 `plugin.py` 中新增 `_load_personality_config()` 方法，从主程序配置读取 `bot.nickname`、`bot.alias_names`、`personality.personality`、`personality.reply_style` 并缓存到 AgentCore
- [x] 在 `plugin.py` 的 `on_load()` 中调用 `_load_personality_config()`（AgentCore 初始化之后）
- [x] 在 `plugin.py` 的 `on_config_update()` 中调用 `_load_personality_config()`（配置热更新时刷新人格缓存）
- [x] 在 `config.toml` 中新增 `[prompt]` 段：`custom_prompt = ""`
- 涉及文件：`plugins/proactive-chat/config.py`、`plugins/proactive-chat/prompts.py`、`plugins/proactive-chat/agent.py`、`plugins/proactive-chat/plugin.py`、`plugins/proactive-chat/config.toml`
- 验收标准：`build_system_prompt()` 可正确组装含人格信息的系统提示词；人格配置为空时提示词无多余段落；`custom_prompt` 非空时注入到系统提示词末尾；`_load_personality_config()` 在 on_load 和 on_config_update 时正确缓存人格信息；Docker 环境下可成功读取主程序的 bot 配置

**依赖**：任务 7（AgentCore 已实现）、任务 8（plugin.py 已重构）

---

## 决策记录智能清理编码任务

> 基于 spec.md 5.9 节"决策记录智能清理"和 design.md 末尾"决策记录智能清理"章节生成
> 新增模块：`smart_cleanup.py`
> 修改模块：`config.py`、`persistence.py`、`deepseek_client.py`、`prompts.py`、`plugin.py`、`config.toml`

---

## 15. 智能清理配置段新增

- [ ] 在 `config.py` 中新增 `SmartCleanupConfig(PluginConfigBase)` 配置段：
  - `smart_cleanup_enabled: bool = Field(default=False, description="是否启用决策记录智能清理")`
  - `smart_cleanup_interval_hours: int = Field(default=6, description="智能清理执行间隔（小时）", ge=1, le=72)`
  - `smart_cleanup_batch_size: int = Field(default=20, description="单次智能清理批量处理的记录数", ge=5, le=100)`
  - `smart_cleanup_min_age_hours: int = Field(default=24, description="决策记录参与智能清理的最小年龄（小时）", ge=1, le=168)`
  - `smart_cleanup_model: str = Field(default="deepseek-chat", description="智能清理使用的 DeepSeek 模型名称")`
  - `smart_cleanup_max_tokens: int = Field(default=500, description="智能清理单次 LLM 调用的最大 token 数", ge=100, le=2000)`
  - 设置 `__ui_label__ = "智能清理"`, `__ui_icon__ = "trash-2"`, `__ui_order__ = 8`
- [ ] 在 `ProactiveChatConfig` 中新增 `smart_cleanup: SmartCleanupConfig = Field(default_factory=SmartCleanupConfig)` 聚合字段
- [ ] 在 `config.toml` 中新增 `[smart_cleanup]` 段，包含上述所有字段的默认值
- 涉及文件：`plugins/proactive-chat/config.py`、`plugins/proactive-chat/config.toml`
- 验证方式：所有字段均有默认值；Pydantic 校验约束（ge/le）生效；WebUI 可展示新增的智能清理配置段；`ProactiveChatConfig` 实例化不报错

**依赖**：无（独立配置变更）

---

## 16. 智能清理 Prompt 模板新增

- [ ] 在 `prompts.py` 中新增 `CLEANUP_SYSTEM_PROMPT` 常量：
  - 角色定义：决策记录完结判定助手
  - 判定标准：一次性问答、话题转移、持续讨论、重复触发、低置信度跳过
  - 输出格式：JSON `{"results": [{"key": "记录标识", "verdict": "completed" | "relevant", "reason": "判定理由"}]}`
  - verdict 为 "completed" 表示已完结可清理，"relevant" 表示仍相关应保留
  - reason 不超过 50 字符
- [ ] 在 `prompts.py` 中新增 `CLEANUP_USER_TEMPLATE` 常量：
  - 包含 `{records_summary}` 占位符
  - 引导语"请逐条判定并返回 JSON 格式结果"
- [ ] 在 `prompts.py` 中新增 `format_cleanup_records()` 辅助函数：
  - 接收 `list[DecisionRecord]`，格式化为每条记录的结构化摘要
  - 每条格式：`[{key}] stream_id: {stream_id}, 时间: {time}, 摘要: {input_summary[:100]}, 意图: {intent}, 行动: {action_taken}, 置信度: {confidence}`
  - `key` 为 `ts:stream_id` 格式的记录标识
  - `input_summary` 截断至 100 字符
- 涉及文件：`plugins/proactive-chat/prompts.py`
- 验证方式：`CLEANUP_SYSTEM_PROMPT` 包含判定标准和输出格式；`format_cleanup_records()` 可将 DecisionRecord 列表格式化为 LLM 可分析的结构化文本；key 格式为 `ts:stream_id`

**依赖**：无（独立模板变更）

---

## 17. DeepSeekClient 重构：提取 `_call_api` 核心方法

- [ ] 将 `deepseek_client.py` 中 `analyze()` 方法的 HTTP 请求构建和发送逻辑提取为私有方法 `_call_api()`：
  - 签名：`async def _call_api(self, system_prompt: str, user_prompt: str, model: str, temperature: float, max_tokens: int) -> str`
  - 包含现有的 API Key 可用性检查、HTTP 请求构建、错误处理（429/401/403/5xx/超时/网络错误）、响应解析逻辑
- [ ] 重构 `analyze()` 方法，委托调用 `_call_api()`：
  - 传入 `config.deepseek.deepseek_model`、`config.deepseek.deepseek_temperature`、`config.analysis.max_analysis_tokens`
- [ ] 新增 `analyze_with_params()` 方法：
  - 签名：`async def analyze_with_params(self, system_prompt: str, user_prompt: str, model: str, temperature: float, max_tokens: int) -> str`
  - 委托调用 `_call_api()`，允许调用方指定独立的 model、temperature、max_tokens 参数
  - 智能清理使用此方法，传入低温度（0.1）确保判定稳定性
- 涉及文件：`plugins/proactive-chat/deepseek_client.py`
- 验证方式：重构后 `analyze()` 行为与重构前完全一致；`analyze_with_params()` 可接受自定义参数并正确调用 API；现有测试不回归

**依赖**：无（内部重构，不影响外部接口）

---

## 18. PersistenceManager 扩展：候选记录查询与行级删除

- [ ] 新增 `query_cleanup_candidates()` 异步方法：
  - 签名：`async def query_cleanup_candidates(self, min_age_hours: int, limit: int) -> list[DecisionRecord]`
  - 遍历所有 JSONL 文件，按文件日期从旧到新排序（优先处理旧文件中的记录）
  - 每条记录计算 `time.time() - record.ts` 是否超过 `min_age_hours * 3600`
  - 收集满足条件的记录，达到 `limit` 后停止
  - 使用 `asyncio.to_thread` 避免阻塞事件循环
- [ ] 新增 `remove_records()` 异步方法：
  - 签名：`async def remove_records(self, record_keys: set[tuple[float, str]]) -> int`
  - `record_keys` 为待删除记录的 `(ts, stream_id)` 集合
  - 遍历所有 JSONL 文件，逐行读取并过滤掉匹配 `record_keys` 的行
  - 过滤后为空的文件直接删除
  - 过滤后非空的文件采用"写临时文件 → 原子重命名"策略：先写入 `.tmp` 后缀临时文件，再通过 `os.replace()` 原子重命名
  - 使用 `asyncio.to_thread` 避免阻塞事件循环
  - 返回删除的记录数
- [ ] 新增 `_query_cleanup_candidates_sync()` 同步内部方法（供 `asyncio.to_thread` 调用）
- [ ] 新增 `_remove_records_sync()` 同步内部方法（供 `asyncio.to_thread` 调用）
- 涉及文件：`plugins/proactive-chat/persistence.py`
- 验证方式：`query_cleanup_candidates()` 可正确筛选满足最小年龄条件的记录，按旧到新排序，限制返回数量；`remove_records()` 可从 JSONL 文件中移除指定记录，空文件被删除；文件写入采用原子重命名策略；文件读写异常时记录警告日志并跳过

**依赖**：无（persistence.py 现有代码已稳定）

---

## 19. SmartCleaner 智能清理器实现

- [ ] 创建 `smart_cleanup.py`，定义 `CleanupBatchResult` dataclass：
  - `candidate_count: int = 0` — 候选记录数
  - `completed_count: int = 0` — 已完结清理数
  - `relevant_count: int = 0` — 仍相关保留数
  - `degraded_count: int = 0` — 降级处理数（LLM 不可用时按天数清理的记录数）
  - `error_count: int = 0` — 处理异常数
- [ ] 实现 `SmartCleaner` 类，构造函数接收 `deepseek_client: DeepSeekClient`、`persistence_manager: PersistenceManager` 的引用
- [ ] 实现 `async start(self, config: ProactiveChatConfig) -> None` 方法：
  - 创建 `asyncio.create_task(self._run_cleanup_loop())` 启动定时循环
  - 将 Task 引用保存至 `self._cleanup_task`
  - 记录启动日志
- [ ] 实现 `stop(self) -> None` 方法：
  - 取消 `self._cleanup_task`
  - 记录停止日志
- [ ] 实现 `async _run_cleanup_loop(self) -> None` 方法：
  - 按 `smart_cleanup_interval_hours` 间隔循环执行清理
  - 首次等待 `interval_hours * 3600` 秒后执行
  - 每次循环读取最新配置（通过 `self._config_ref` 或参数传入）
  - 循环内部通过 try/except 包裹，确保异常仅记录日志，不影响下次调度
- [ ] 实现 `async _execute_cleanup(self, config: ProactiveChatConfig) -> None` 方法：
  - 检查 `smart_cleanup_enabled`，未启用则跳过
  - 调用 `PersistenceManager.query_cleanup_candidates()` 查询候选记录
  - 候选为空时记录调试日志并返回
  - 按 `smart_cleanup_batch_size` 分批处理
  - 每批调用 `_judge_with_fallback()` 进行判定
  - 调用 `PersistenceManager.remove_records()` 删除已完结记录
  - 记录每批和总清理统计日志
- [ ] 实现 `async _judge_batch(self, records: list[DecisionRecord], config: ProactiveChatConfig) -> dict[str, str]` 方法：
  - 使用 `format_cleanup_records()` 格式化候选记录
  - 构建 `CLEANUP_SYSTEM_PROMPT` 和 `CLEANUP_USER_TEMPLATE` Prompt
  - 调用 `DeepSeekClient.analyze_with_params()` 进行完结判定
  - 参数：`model=config.smart_cleanup.smart_cleanup_model`、`temperature=0.1`、`max_tokens=config.smart_cleanup.smart_cleanup_max_tokens`
  - 解析 LLM 返回的 JSON，提取 `results` 数组
  - 无法解析的记录默认判定为 `"relevant"`（保守策略）
  - 返回 `{记录标识: "completed" | "relevant"}` 映射
- [ ] 实现 `async _judge_with_fallback(self, records: list[DecisionRecord], config: ProactiveChatConfig) -> dict[str, str]` 方法：
  - 尝试调用 `_judge_batch()`
  - LLM 不可用（API Key 无效/网络不可达）时：降级为按天数清理，将超过 `decision_retention_days` 的记录标记为 `"completed"`，其余标记为 `"relevant"`，记录警告日志
  - LLM 调用超时时：放弃本次智能清理，记录警告日志，返回空映射（不删除任何记录）
  - LLM 返回格式异常时：降级为按天数清理，记录警告日志，记录 LLM 原始响应（截断至 200 字符）
- 涉及文件：`plugins/proactive-chat/smart_cleanup.py`（新建）
- 验证方式：`start()` 可启动定时循环；`stop()` 可取消定时任务；`_execute_cleanup()` 可完整执行筛选→判定→删除流程；LLM 不可用时降级为按天数清理；解析失败的记录默认保留；所有异常被捕获不向外传播；清理统计日志包含候选数/已完结数/仍相关数/降级数

**依赖**：任务 16（Prompt 模板）、任务 17（DeepSeekClient.analyze_with_params）、任务 18（PersistenceManager 候选查询与行级删除）

---

## 20. 插件入口集成智能清理生命周期

- [ ] 在 `plugin.py` 的 import 中新增 `from .smart_cleanup import SmartCleaner`
- [ ] 在 `ProactiveChatPlugin` 类中新增 `_smart_cleaner: SmartCleaner` 属性声明
- [ ] 在 `on_load()` 中新增 SmartCleaner 初始化和启动逻辑：
  - 在 AgentCore 初始化之后创建 `SmartCleaner(deepseek_client, persistence_manager)`
  - 检查 `config.smart_cleanup.smart_cleanup_enabled`，为 True 时调用 `await self._smart_cleaner.start(config)`
- [ ] 在 `on_unload()` 中新增 SmartCleaner 停止逻辑：
  - 在 WebUI 和 DeepSeekClient 清理之前调用 `self._smart_cleaner.stop()`
- [ ] 在 `on_config_update()` 中新增 SmartCleaner 重启逻辑：
  - 先调用 `self._smart_cleaner.stop()`
  - 重新读取配置后，若 `config.smart_cleanup.smart_cleanup_enabled` 为 True，调用 `await self._smart_cleaner.start(config)`
  - 配置变更后智能清理定时任务使用新配置
- 涉及文件：`plugins/proactive-chat/plugin.py`
- 验证方式：插件加载时若 `smart_cleanup_enabled=True` 则智能清理定时任务启动；插件卸载时定时任务被取消；配置热更新时定时任务根据新配置重启；智能清理异常不影响智能体决策循环和主动对话触发

**依赖**：任务 15（SmartCleanupConfig 已定义）、任务 19（SmartCleaner 已实现）

---

## 21. 智能清理降级与容错完善

- [ ] 确保 DeepSeek API 不可用时智能清理降级为按天数清理：`_judge_with_fallback()` 中捕获 `RuntimeError`，调用 `PersistenceManager.cleanup_expired()`，记录警告日志
- [ ] 确保 DeepSeek API 调用超时时放弃本次清理：捕获 `httpx.TimeoutException`，记录警告日志，返回空映射（不删除任何记录）
- [ ] 确保 DeepSeek API 返回格式异常时降级为按天数清理：解析 JSON 失败时记录 LLM 原始响应（截断至 200 字符），降级为按天数清理
- [ ] 确保 JSONL 文件读写异常时跳过该文件继续处理：`remove_records()` 中单个文件异常时记录警告日志，继续处理其他文件
- [ ] 确保智能清理定时任务内部异常不影响下次调度：`_run_cleanup_loop()` 中每次 `_execute_cleanup()` 调用均被 try/except 包裹
- [ ] 确保智能清理与按天数清理不冲突：智能清理按记录行级删除，按天数清理按文件整文件删除，操作粒度不同
- [ ] 确保智能清理不影响主流程：SmartCleaner 作为独立后台任务运行，与 AgentCore 决策循环完全解耦
- [ ] 确保空候选集时跳过清理：`_execute_cleanup()` 中候选为空时记录调试日志并返回
- 涉及文件：`plugins/proactive-chat/smart_cleanup.py`、`plugins/proactive-chat/persistence.py`
- 验证方式：各降级场景下插件不崩溃、不影响主流程；日志中可观察到降级记录；API Key 不出现在日志中；空候选集时跳过清理并记录日志

**依赖**：任务 19（SmartCleaner）、任务 18（PersistenceManager）

---

## 22. 智能清理集成验证

- [ ] 验证配置加载：启动插件，确认 `SmartCleanupConfig` 各字段默认值正确，WebUI 可展示智能清理配置段
- [ ] 验证定时调度：设置 `smart_cleanup_enabled=True`、`smart_cleanup_interval_hours=1`，确认日志显示定时任务已启动
- [ ] 验证候选筛选：创建若干不同年龄的决策记录，确认 `query_cleanup_candidates()` 仅返回超过最小年龄的记录
- [ ] 验证 LLM 判定：准备一批候选记录，确认 DeepSeek API 被正确调用，判定结果可解析
- [ ] 验证行级删除：LLM 判定部分记录为"已完结"，确认 `remove_records()` 正确从 JSONL 文件中移除对应行，空文件被删除
- [ ] 验证降级场景：
  - DeepSeek API Key 不可用 → 降级为按天数清理
  - DeepSeek API 超时 → 放弃本次清理
  - LLM 返回格式异常 → 降级为按天数清理
- [ ] 验证配置热更新：通过 WebUI 修改 `smart_cleanup_enabled`，确认定时任务根据新配置启停
- [ ] 验证不影响主流程：智能清理执行期间，智能体决策循环仍可正常触发主动对话
- [ ] 验证与按天数清理协同：智能清理和按天数清理同时启用时，两者不产生冲突
- 涉及文件：全部插件文件
- 验收标准：智能清理完整流程可走通；降级场景不崩溃；清理统计日志完整；不影响主流程；配置热更新生效

**依赖**：任务 20（插件入口集成）、任务 21（降级容错完善）

---

## 决策记录状态完善编码任务

> 基于 spec.md 5.10 节"决策记录状态管理"和 design.md 末尾"决策记录状态完善"章节生成
> 修改模块：`persistence.py`、`agent.py`、`smart_cleanup.py`、`webui.py`、`config.py`、`plugin.py`
> 新增配置段：`DecisionStatusConfig`

---

## 23. 决策状态配置段新增

- [ ] 在 `config.py` 中新增 `DecisionStatusConfig(PluginConfigBase)` 配置段：
  - `decision_window_seconds: int = Field(default=60, description="决策窗口时长（秒），同一聊天流在此窗口内的重复触发视为同一决策", ge=10, le=600)`
  - `max_retry_count: int = Field(default=3, description="可恢复错误的最大重试次数", ge=1, le=5)`
  - `processing_timeout_seconds: int = Field(default=300, description="处理中超时保护时间（秒），超过此时间的 processing 记录自动转为 completed", ge=60, le=1800)`
  - 设置 `__ui_label__ = "决策状态"`, `__ui_icon__ = "list-checks"`, `__ui_order__ = 9`
- [ ] 在 `ProactiveChatConfig` 中新增 `status: DecisionStatusConfig = Field(default_factory=DecisionStatusConfig)` 聚合字段
- [ ] 在 `config.toml` 中新增 `[status]` 段，包含上述所有字段的默认值
- 涉及文件：`plugins/proactive-chat/config.py`、`plugins/proactive-chat/config.toml`
- 验证方式：所有字段均有默认值；Pydantic 校验约束（ge/le）生效；WebUI 可展示新增的决策状态配置段；`ProactiveChatConfig` 实例化不报错

**依赖**：无（独立配置变更）

---

## 24. DecisionRecord 数据类扩展

- [ ] 在 `persistence.py` 的 `DecisionRecord` dataclass 中新增 6 个状态字段：
  - `record_status: str = "completed"` — 生命周期状态（pending / processing / completed / archived）
  - `processing_phase: str = ""` — 处理阶段细分（perceiving / reasoning / acting / reflecting / ""）
  - `dedup_key: str = ""` — 去重标记，格式为 `{stream_id}:{window_start_ts}`
  - `retry_count: int = 0` — 重试计数，取值 [0, 3]
  - `trigger_anomaly: bool = False` — 触发异常标记（应触发但未触发）
  - `trigger_time: float = 0.0` — 实际触发时间戳，0.0 表示未触发
- [ ] 在 `persistence.py` 中新增 `generate_dedup_key()` 模块级函数：
  - 签名：`def generate_dedup_key(stream_id: str, ts: float, window_seconds: int = 60) -> str`
  - 逻辑：`window_start = int(ts // window_seconds) * window_seconds`，返回 `f"{stream_id}:{window_start}"`
- [ ] 修改 `_query_decisions_sync()` 方法：
  - 新增 `record_status: str = ""` 和 `trigger_anomaly: bool | None = None` 参数
  - 读取 JSONL 记录时补充缺失的新增字段默认值（向后兼容旧版记录）：
    - `record_status` 缺失时默认 `"completed"`
    - `processing_phase` 缺失时默认 `""`
    - `dedup_key` 缺失时默认 `""`
    - `retry_count` 缺失时默认 `0`
    - `trigger_anomaly` 缺失时默认 `False`
    - `trigger_time` 缺失时默认 `0.0`
  - `record_status` 未指定时，默认返回 `completed` 状态的记录（兼容现有行为），不包含 `archived` 记录
  - 显式指定 `record_status="archived"` 时返回归档记录
  - `trigger_anomaly` 非 None 时，按布尔值过滤
- [ ] 修改 `query_decisions()` 异步方法签名，透传新增的 `record_status` 和 `trigger_anomaly` 参数
- [ ] 修改 `_query_cleanup_candidates_sync()` 方法：
  - 新增过滤条件：仅返回 `record_status="completed"` 的记录，排除 `pending`、`processing`、`archived`
  - 读取记录时补充缺失的新增字段默认值（同上）
- [ ] 修改 `_remove_records_sync()` 方法：
  - 读取记录时补充缺失的新增字段默认值（同上）
- 涉及文件：`plugins/proactive-chat/persistence.py`
- 验证方式：`DecisionRecord` 包含 13 个字段（7 个旧 + 6 个新）；`generate_dedup_key()` 可正确计算去重键；旧版 JSONL 记录读取时缺失字段使用默认值填充；`query_decisions()` 支持 `record_status` 和 `trigger_anomaly` 过滤；`query_cleanup_candidates()` 仅返回 `completed` 状态记录

**依赖**：无（persistence.py 现有代码已稳定）

---

## 25. PersistenceManager 新增状态管理方法

- [ ] 新增 `update_record_status()` 异步方法：
  - 签名：`async def update_record_status(self, record_key: tuple[float, str], updates: dict) -> bool`
  - `record_key` 为 `(ts, stream_id)` 元组，定位 JSONL 文件中的特定记录
  - `updates` 为需要更新的字段字典，如 `{"record_status": "processing", "processing_phase": "perceiving"}`
  - 遍历 JSONL 文件，逐行读取，匹配 `record_key` 的记录合并 `updates` 字段后写回
  - 写回策略：读取全部行 → 修改匹配行 → 写入临时文件 `.tmp` → `os.replace()` 原子重命名
  - 使用 `asyncio.to_thread` 避免阻塞事件循环
  - 写入失败时记录警告日志，返回 `False`；成功返回 `True`
- [ ] 新增 `_update_record_status_sync()` 同步内部方法（供 `asyncio.to_thread` 调用）
- [ ] 新增 `check_dedup()` 异步方法：
  - 签名：`async def check_dedup(self, dedup_key: str) -> bool`
  - 检查是否存在相同 `dedup_key` 且 `record_status` 为 `pending` 或 `processing` 的记录
  - 仅扫描当天的 JSONL 文件（决策窗口通常在秒级，无需扫描历史文件）
  - 存在重复返回 `True`，否则返回 `False`
  - 读取失败时返回 `False`（跳过去重检查，允许创建新记录），记录警告日志
- [ ] 新增 `_check_dedup_sync()` 同步内部方法（供 `asyncio.to_thread` 调用）
- [ ] 新增 `recover_stale_processing()` 异步方法：
  - 签名：`async def recover_stale_processing(self, timeout_seconds: int = 300) -> int`
  - 扫描所有 JSONL 文件，查找 `record_status="processing"` 的记录
  - 计算 `time.time() - record.ts` 是否超过 `timeout_seconds`
  - 超时的记录：`record_status` 更新为 `"completed"`，`action_taken` 更新为 `"error_timeout_stale"`，`processing_phase` 更新为 `""`
  - 未超时的记录保持不变
  - 返回恢复的记录数
  - 使用 `asyncio.to_thread` 避免阻塞事件循环
- [ ] 新增 `_recover_stale_processing_sync()` 同步内部方法（供 `asyncio.to_thread` 调用）
- 涉及文件：`plugins/proactive-chat/persistence.py`
- 验证方式：`update_record_status()` 可更新 JSONL 文件中指定记录的字段，采用原子重命名策略；`check_dedup()` 可检测重复的 pending/processing 记录；`recover_stale_processing()` 可将超时的 processing 记录转为 completed；文件读写异常时记录警告日志不崩溃

**依赖**：任务 24（DecisionRecord 字段扩展）

---

## 26. AgentCore 决策循环状态流转

- [ ] 在 `agent.py` 中新增 `RetryableError` 异常类：
  - 继承 `Exception`，用于标识可恢复错误（API 超时、服务端 5xx）
- [ ] 修改 `decision_loop()` 方法，新增状态流转调用：
  - 入口处生成 `dedup_key`：调用 `generate_dedup_key(stream_id, now, config.status.decision_window_seconds)`
  - 去重检查：调用 `self._persistence.check_dedup(dedup_key)`，重复则记录调试日志并返回
  - 创建 `DecisionRecord` 时设置初始状态：`record_status="pending"`, `dedup_key=dedup_key`, `retry_count=0`, `trigger_anomaly=False`, `trigger_time=0.0`, `processing_phase=""`
  - 调用 `save_decision()` 持久化初始记录
  - 进入感知阶段前：调用 `update_record_status()` 设置 `record_status="processing"`, `processing_phase="perceiving"`
  - 进入推理阶段前：调用 `update_record_status()` 设置 `processing_phase="reasoning"`
  - 进入行动阶段前：调用 `update_record_status()` 设置 `processing_phase="acting"`
  - 进入反思阶段前：调用 `update_record_status()` 设置 `processing_phase="reflecting"`
  - 决策循环结束时：调用 `update_record_status()` 设置 `record_status="completed"`, `processing_phase=""`
- [ ] 修改 `reason()` 方法，对可恢复错误抛出 `RetryableError`：
  - DeepSeek API 超时（httpx.TimeoutException）时抛出 `RetryableError`
  - DeepSeek API 返回 5xx 错误时抛出 `RetryableError`
  - 不可恢复错误（401/403 鉴权失败、解析失败）不抛出 `RetryableError`，直接进入 completed
- [ ] 在 `decision_loop()` 中新增重试逻辑：
  - 捕获 `RetryableError`，递增 `retry_count`
  - 调用 `update_record_status()` 更新 `retry_count` 字段
  - 指数退避等待 `2 ** retry_count` 秒后重试
  - `retry_count` 达到 `config.status.max_retry_count` 时，`action_taken` 设为 `"error_api_retry_exhausted"`，进入 completed
- [ ] 修改 `act()` 方法，返回值从 `str` 改为 `tuple[str, float]`：
  - 触发成功时返回 `("triggered", time.time())`
  - 触发失败时返回 `("error_trigger", 0.0)` 或 `("error_trigger_unavailable", 0.0)`
- [ ] 修改 `reflect()` 方法：
  - 新增 `trigger_time: float = 0.0` 参数
  - 新增 `trigger_anomaly` 判定逻辑：`result.should_trigger=True` 且 `action_taken != "triggered"` 时 `trigger_anomaly=True`
  - `trigger_anomaly=True` 时记录警告日志，包含 stream_id、action_taken、未触发的具体原因
  - 构建 `DecisionRecord` 时设置 `record_status="completed"`, `processing_phase=""`, `trigger_anomaly=trigger_anomaly`, `trigger_time=trigger_time if action_taken == "triggered" else 0.0`
- [ ] 更新 `decision_loop()` 中调用 `act()` 和 `reflect()` 的代码，适配新的返回值和参数
- 涉及文件：`plugins/proactive-chat/agent.py`
- 验证方式：决策循环完整执行时，JSONL 文件中记录的状态按 pending → processing → completed 流转；`processing_phase` 在各阶段正确更新；去重检查可阻止同一窗口的重复决策；可恢复错误触发重试逻辑，重试次数耗尽后标记 `error_api_retry_exhausted`；`trigger_anomaly` 在"应触发未触发"时为 True；`trigger_time` 仅在 triggered 时有值

**依赖**：任务 24（DecisionRecord 字段扩展）、任务 25（PersistenceManager 状态管理方法）

---

## 27. SmartCleaner 结构化规则优先判定

- [ ] 在 `smart_cleanup.py` 中新增 `_classify_by_rules()` 方法：
  - 签名：`def _classify_by_rules(self, records: list[DecisionRecord], min_age_hours: int) -> tuple[list[DecisionRecord], list[DecisionRecord], list[DecisionRecord]]`
  - 返回 `(cleanable, uncleanable, need_llm)` 三个列表
  - 不可清理条件（优先判定）：
    - `record_status` 为 `pending` 或 `processing`
    - `trigger_anomaly=True`
    - `action_taken` 以 `"error"` 开头
  - 可清理条件：
    - `record_status=archived`
    - `record_status=completed` 且 `action_taken` 以 `"skipped"` 开头且 `ts` 距今超过 `min_age_hours`
  - 需 LLM 辅助条件：
    - `record_status=completed` 且 `action_taken=triggered` 且 `trigger_anomaly=False` 且 `ts` 距今超过 `min_age_hours`
  - 不满足任何条件的记录归入 `uncleanable`
- [ ] 新增 `_archive_records()` 异步方法：
  - 签名：`async def _archive_records(self, records: list[DecisionRecord]) -> int`
  - 遍历记录列表，调用 `PersistenceManager.update_record_status()` 将 `record_status` 更新为 `"archived"`
  - 返回成功归档的记录数
- [ ] 重构 `_execute_cleanup()` 方法：
  - 查询候选记录后，先调用 `_classify_by_rules()` 进行结构化规则分类
  - 记录分类统计日志：候选数、结构化可清理数、不可清理数、需 LLM 辅助数
  - 结构化规则判定为可清理的记录 → 调用 `_archive_records()` 直接归档
  - 不可清理的记录 → 保留，计入 `relevant_count`
  - 需 LLM 辅助的记录 → 按 `batch_size` 分批调用 `_judge_with_fallback()` 判定
    - LLM 判定"已完结" → 归档
    - LLM 判定"仍相关" → 保留
  - 归档操作使用 `update_record_status()` 而非 `remove_records()`，实现"软删除"
  - 记录总清理统计日志
- [ ] 修改 `_judge_with_fallback()` 方法：
  - LLM 不可用时，降级为按天数清理：将超过 `decision_retention_days` 的 completed 记录归档（而非直接删除）
  - 确保结构化规则与 LLM 判定冲突时以结构化规则为准（防御性编程）
- [ ] 更新 `CleanupBatchResult` dataclass：
  - 新增 `archived_count: int = 0` 字段，记录归档数量
- 涉及文件：`plugins/proactive-chat/smart_cleanup.py`
- 验证方式：`_classify_by_rules()` 可正确将候选记录分为三类；结构化规则可清理的记录不调用 LLM 直接归档；`trigger_anomaly=True` 和 `error*` 记录不会被清理；归档操作通过 `update_record_status()` 写入 JSONL 文件；清理统计日志包含分类统计

**依赖**：任务 25（PersistenceManager.update_record_status）、任务 24（DecisionRecord 新增字段）

---

## 28. WebUI 状态展示与筛选增强

- [ ] 修改 `_handle_stats()` API 响应，新增 3 个统计项：
  - `pending_count`：`record_status="pending"` 的记录数
  - `processing_count`：`record_status="processing"` 的记录数
  - `trigger_anomaly_count`：`trigger_anomaly=True` 的记录数
- [ ] 修改 `_handle_decisions()` API：
  - 新增 `record_status` 查询参数：`request.query.get("record_status", "")`
  - 新增 `trigger_anomaly` 查询参数：`request.query.get("trigger_anomaly", "")`
  - 透传到 `query_decisions()` 调用
- [ ] 修改前端 HTML 表格，新增 4 列：
  - **状态列**（意图列之前）：显示 `record_status` 标签（待处理/处理中/已完成/已归档）
  - **处理阶段列**（状态列之后）：`processing` 状态显示动态标签（感知中/推理中/行动中/反思中），`completed` 显示"-"
  - **触发时间列**（动作列之后）：`triggered` 显示格式化时间，其他显示"-"
  - **异常列**（最后一列）：`trigger_anomaly=True` 显示橙色警告标记
- [ ] 修改前端筛选栏，新增 2 个控件：
  - **状态筛选下拉框**：选项包含 全部、待处理、处理中、已完成、已归档
  - **异常筛选复选框**：勾选后仅显示 `trigger_anomaly=True` 的记录
- [ ] 修改前端统计概览，新增 3 个统计项：
  - 待处理数（默认色）
  - 处理中数（蓝色 badge）
  - 触发异常数（橙色 badge）
- [ ] 新增 JavaScript 辅助函数：
  - `statusBadge(status)`：返回状态标签 HTML，`pending` 黄色、`processing` 蓝色、`completed` 绿色、`archived` 无色
  - `phaseBadge(phase, status)`：`processing` 状态显示脉冲动画 badge，其他显示"-"
  - `anomalyBadge(anomaly)`：`trigger_anomaly=True` 显示橙色感叹号 + "应触发未触发"标签
  - `formatTriggerTime(ts, action)`：`triggered` 显示格式化时间，其他显示"-"
- [ ] 新增异常记录行样式：
  - `trigger_anomaly=True` 的记录行使用浅橙色背景（`rgba(253, 203, 110, 0.1)`）
- [ ] 调整表格列顺序为：时间 | 聊天流 | 状态 | 处理阶段 | 意图 | 置信度 | 动作 | 触发时间 | 原因 | 异常
- 涉及文件：`plugins/proactive-chat/webui.py`
- 验证方式：WebUI 决策记录表格显示状态、处理阶段、触发时间、异常 4 个新列；状态筛选下拉框和异常筛选复选框可正常过滤记录；统计概览显示待处理数、处理中数、触发异常数；异常记录行有浅橙色背景和警告标记；处理中记录的处理阶段列有脉冲动画

**依赖**：任务 24（DecisionRecord 新增字段）、任务 25（query_decisions 支持状态过滤）

---

## 29. 插件入口集成状态管理生命周期

- [ ] 在 `plugin.py` 的 `on_load()` 中新增超时恢复调用：
  - 在 `PersistenceManager` 初始化之后、`AgentCore` 初始化之前，调用 `await self._persistence_manager.recover_stale_processing(config.status.processing_timeout_seconds)`
  - 确保插件重启后不会残留"处理中"的僵尸记录
- [ ] 在 `plugin.py` 中新增触发异常重点追踪逻辑：
  - 在 `on_load()` 中初始化一个内存计数器 `_anomaly_counter: dict[str, int]`，按 `stream_id` 统计连续异常次数
  - 在 `on_config_update()` 或定时检查中，对同一聊天流连续 `trigger_anomaly=True` 超过 3 次的记录，记录错误级别日志，提示管理员关注
  - 可选：在 `AgentCore.reflect()` 中通过返回值或回调传递 `trigger_anomaly` 信息到 `plugin.py` 进行计数
- [ ] 确保 `config.toml` 中新增的 `[status]` 段与 `DecisionStatusConfig` 字段对齐
- 涉及文件：`plugins/proactive-chat/plugin.py`、`plugins/proactive-chat/config.toml`
- 验证方式：插件加载时自动恢复超时的 processing 记录；同一聊天流连续触发异常超过 3 次时记录错误级别日志；配置文件与模型字段对齐

**依赖**：任务 23（DecisionStatusConfig 已定义）、任务 25（recover_stale_processing 方法）、任务 26（AgentCore 状态流转）

---

## 30. 向后兼容与降级完善

- [ ] 确保旧版 JSONL 记录读取时缺失字段使用默认值填充：在 `_query_decisions_sync()`、`_query_cleanup_candidates_sync()`、`_remove_records_sync()`、`_update_record_status_sync()`、`_check_dedup_sync()`、`_recover_stale_processing_sync()` 中统一处理
- [ ] 确保去重检查时 JSONL 读取失败时跳过去重检查，正常创建新记录，记录警告日志
- [ ] 确保状态更新写入失败时内存中状态已更新，文件状态未同步，记录警告日志，下次写入时尝试同步
- [ ] 确保处理中超时记录恢复失败时记录警告日志，不影响其他记录恢复
- [ ] 确保结构化规则与 LLM 判定冲突时以结构化规则结果为准，记录信息日志
- [ ] 确保重试次数耗尽时 `record_status` 变为 `completed`，`action_taken` 标记错误类型
- [ ] 确保归档记录不被常规查询返回，仅显式指定 `record_status="archived"` 时返回
- [ ] 确保 `trigger_anomaly=True` 的记录不受结构化清理规则清理，保留至按天数清理或管理员手动归档
- 涉及文件：`plugins/proactive-chat/persistence.py`、`plugins/proactive-chat/agent.py`、`plugins/proactive-chat/smart_cleanup.py`
- 验证方式：旧版 JSONL 记录可正常读取且默认值正确；各降级场景下插件不崩溃、不影响主流程；归档记录不出现在常规查询中；异常记录不被结构化清理

**依赖**：任务 25（PersistenceManager 状态管理方法）、任务 26（AgentCore 状态流转）、任务 27（SmartCleaner 结构化规则）

---

## 31. 决策记录状态完善集成验证

- [ ] 验证状态流转：触发一次完整的决策循环，检查 JSONL 文件中记录的 `record_status` 按 pending → processing → completed 流转，`processing_phase` 在各阶段正确更新
- [ ] 验证去重检查：同一聊天流在决策窗口内连续触发两次，确认第二次被去重跳过
- [ ] 验证触发异常标记：构造 `should_trigger=True` 但因低置信度未触发的场景，确认 `trigger_anomaly=True`
- [ ] 验证触发时间记录：触发成功的记录 `trigger_time` 有值，未触发的记录 `trigger_time=0.0`
- [ ] 验证重试逻辑：模拟 DeepSeek API 超时，确认 `retry_count` 递增，重试次数耗尽后 `action_taken="error_api_retry_exhausted"`
- [ ] 验证超时恢复：创建 `record_status="processing"` 的旧记录，重启插件后确认自动转为 `completed`（`action_taken="error_timeout_stale"`）
- [ ] 验证结构化清理优先：准备不同类型的候选记录，确认结构化规则可清理的记录不调用 LLM 直接归档
- [ ] 验证归档记录查询：归档后的记录不出现在常规查询中，显式指定 `record_status="archived"` 可查询
- [ ] 验证 WebUI 展示：
  - 决策记录表格显示状态、处理阶段、触发时间、异常列
  - 状态筛选和异常筛选可正常过滤
  - 统计概览显示待处理数、处理中数、触发异常数
  - 异常记录行有浅橙色背景和警告标记
  - 处理中记录的处理阶段有脉冲动画
- [ ] 验证向后兼容：读取旧版 JSONL 文件，确认缺失字段使用默认值填充，WebUI 显示为"已完成"状态
- [ ] 验证降级场景：
  - 去重检查 JSONL 读取失败 → 跳过去重，正常创建记录
  - 状态更新写入失败 → 内存状态已更新，文件下次同步
  - 结构化规则与 LLM 判定冲突 → 以结构化规则为准
- [ ] 验证触发异常重点追踪：同一聊天流连续产生 3 次以上 `trigger_anomaly=True` 记录，确认记录错误级别日志
- 涉及文件：全部插件文件
- 验收标准：状态流转完整可追踪；去重检查有效；触发异常标记正确；结构化清理优先于 LLM；归档记录不污染常规查询；WebUI 信息完整；向后兼容旧版记录；降级场景不崩溃

**依赖**：任务 29（插件入口集成）、任务 30（向后兼容与降级完善）

---

## 决策循环状态流转修复任务

> 基于代码审查发现的决策循环状态流转遗漏和纰漏
> 修改模块：`agent.py`、`persistence.py`、`plugin.py`、`smart_cleanup.py`

---

## 32. 修复 reflect() 产生重复记录问题

- [ ] 修改 `agent.py` 的 `reflect()` 方法签名，新增 `record_key: tuple[float, str]` 参数
- [ ] 重构 `reflect()` 方法，不再创建新 `DecisionRecord` 并调用 `save_decision()`，改为构建 `updates: dict` 并调用 `self._persistence.update_record_status(record_key, updates)`
- [ ] `updates` 字典包含：`action_taken`、`error`、`analysis_result`（含 should_trigger/intent/reason/confidence）、`input_summary`、`record_status="completed"`、`processing_phase=""`、`trigger_anomaly`、`trigger_time`、`retry_count`、`dedup_key`
- [ ] 保留 `trigger_anomaly` 判定逻辑：`result.should_trigger and action_taken != "triggered"` 时为 True
- [ ] 保留 `trigger_anomaly=True` 时的警告日志
- [ ] `reflect()` 内部异常时记录调试日志，不向外传播
- [ ] 更新 `decision_loop()` 中所有调用 `reflect()` 的位置，传入 `record_key` 参数
- [ ] 移除 `decision_loop()` 中所有提前返回路径和正常路径中对 `update_record_status` 的 completed 状态设置调用（因为 `reflect()` 已包含此逻辑），避免冗余写入
  - 具体移除的位置：
    - 第 278-280 行（无消息路径）
    - 第 310-312 行（重试耗尽路径）
    - 第 322-324 行（未触发路径）
    - 第 338-340 行（低置信度路径）
    - 第 360-363 行（正常完成路径）
  - 保留各阶段的 `processing_phase` 更新调用
- 涉及文件：`plugins/proactive-chat/agent.py`
- 验证方式：一次完整的决策循环在 JSONL 文件中只产生一条记录，该记录的状态从 pending → processing → completed 流转；WebUI 不再出现同一决策的重复记录；统计数据准确

**依赖**：无（agent.py 现有代码已稳定）

---

## 33. 补充 processing_phase="reflecting" 阶段更新

- [ ] 在 `agent.py` 的 `decision_loop()` 中，调用 `reflect()` 之前添加 `update_record_status(record_key, {"processing_phase": "reflecting"})`
- [ ] 确保所有进入 reflect 的路径（包括提前返回路径和正常路径）都在 reflect 之前设置 reflecting 阶段
- 涉及文件：`plugins/proactive-chat/agent.py`
- 验证方式：决策循环执行时，JSONL 记录的 `processing_phase` 依次出现 perceiving → reasoning → acting → reflecting → ""（completed）

**依赖**：任务 32（reflect 重构后调用点明确）

---

## 34. 修复外层 except 中 act() 已成功但 action_taken 被覆盖的问题

- [ ] 在 `agent.py` 的 `decision_loop()` 外层 `except` 块中，增加判断：如果 `trigger_time > 0`（即 `act()` 已成功执行），则不覆盖 `action_taken`，保留 `act()` 返回的实际值
- [ ] 具体修改：将 `action_taken = "error_loop"` 改为条件赋值 `if trigger_time == 0.0: action_taken = "error_loop"`
- [ ] 在此场景下记录警告日志，说明 act 已成功但后续步骤异常
- 涉及文件：`plugins/proactive-chat/agent.py`
- 验证方式：act() 成功后如果后续代码异常，记录的 `action_taken` 仍为 "triggered"，`trigger_time` 保留实际值

**依赖**：无

---

## 35. 修复 check_dedup 跨天场景遗漏问题

- [ ] 修改 `persistence.py` 的 `_check_dedup_sync()` 方法，扫描当天和前一天的 JSONL 文件
- [ ] 具体修改：在现有 `today_file` 之外，新增计算前一天日期字符串 `yesterday_str`，扫描 `decisions_{yesterday_str}.jsonl` 文件
- [ ] 先扫描前一天的文件，再扫描当天的文件（按时间顺序）
- 涉及文件：`plugins/proactive-chat/persistence.py`
- 验证方式：23:59 创建的 pending 记录，00:01 去重检查时能正确检测到

**依赖**：无

---

## 36. 新增运行时 stale processing 记录恢复机制

- [ ] 在 `agent.py` 的 `decision_loop()` 入口处、`check_dedup()` 调用之前，调用 `self._persistence.recover_stale_processing(config.status.processing_timeout_seconds)`
- [ ] 仅在距上次恢复超过 `processing_timeout_seconds` 时才执行恢复，避免每次决策循环都扫描所有文件
  - 在 `AgentCore` 中新增 `_last_recovery_time: float = 0.0` 属性
  - 判断条件：`time.time() - self._last_recovery_time > config.status.processing_timeout_seconds`
- [ ] 恢复后更新 `_last_recovery_time = time.time()`
- [ ] 或替代方案：在 `SmartCleaner._run_cleanup_loop()` 中每次循环开始时调用 `recover_stale_processing`
- 涉及文件：`plugins/proactive-chat/agent.py`（或 `plugins/proactive-chat/smart_cleanup.py`）
- 验证方式：插件长时间运行不重启时，僵尸 processing 记录能被定期清理，不会导致去重检查永久阻塞

**依赖**：无

---

## 37. @Tool 路径补充决策记录

- [ ] 在 `plugin.py` 的 `handle_trigger_proactive_chat` 方法中，`act()` 调用后创建 `DecisionRecord` 并持久化
- [ ] 具体实现：
  - 构建 `DecisionRecord`，设置 `stream_id`、`record_status="completed"`、`action_taken=action_taken`、`analysis_result={"should_trigger": True, "intent": intent, "reason": reason, "confidence": 1.0}`、`trigger_time=trigger_time if action_taken == "triggered" else 0.0`
  - 调用 `self._persistence_manager.save_decision(decision)`
- [ ] @Tool 路径不经过 decision_loop，无需 pending/processing 状态流转，直接记录 completed
- 涉及文件：`plugins/proactive-chat/plugin.py`
- 验证方式：通过 @Tool 触发的主动对话在 WebUI 决策记录中可见

**依赖**：任务 32（reflect 重构后 save_decision 语义不变）

---

## 38. 决策循环状态流转修复集成验证

- [ ] 验证重复记录消除：触发一次完整的决策循环，检查 JSONL 文件中只有一条记录，状态从 pending → processing → completed 流转
- [ ] 验证 processing_phase 完整性：检查 JSONL 记录的 processing_phase 依次出现 perceiving → reasoning → acting → reflecting → ""（completed）
- [ ] 验证外层异常路径：模拟 act() 成功后抛出异常，确认 action_taken 仍为 "triggered"，trigger_time 保留
- [ ] 验证跨天去重：创建跨午夜的 pending 记录，确认去重检查能正确检测
- [ ] 验证运行时 stale 恢复：创建超时的 processing 记录，确认运行时能被定期恢复
- [ ] 验证 @Tool 路径记录：通过 @Tool 触发主动对话，确认 WebUI 中有对应的决策记录
- [ ] 验证 WebUI 数据一致性：确认统计概览的今日决策总数、触发数等不再因重复记录而翻倍
- [ ] 验证所有提前返回路径的记录完整性：无消息、重试耗尽、未触发、低置信度等路径均只产生一条记录
- 涉及文件：全部插件文件
- 验收标准：一次决策循环只产生一条记录；processing_phase 四阶段完整；跨天去重有效；运行时 stale 恢复正常；@Tool 路径有决策记录；WebUI 统计数据准确

**依赖**：任务 32、33、34、35、36、37（所有修复任务完成）

---

## WebUI 冷却到期时刻展示优化

> 需求：在 WebUI 冷却状态卡片中显示"约定的触发时间"（冷却到期时刻），让管理员无需心算即可知道每个聊天流何时可再次触发
> 修改模块：`webui.py`

---

## 39. 冷却状态 API 新增到期时刻字段

- [ ] 修改 `webui.py` 的 `_handle_cooldown()` 方法，在 `records.append()` 中新增 2 个字段：
  - `expires_at: float` — 冷却到期时间戳，计算方式为 `rec.triggered_at + cooldown_seconds`
  - `expires_time: str` — 冷却到期时刻的格式化字符串（仅时分秒），格式为 `time.strftime("%H:%M:%S", time.localtime(rec.triggered_at + cooldown_seconds))`
- [ ] 修改 `formatRemaining()` JS 函数：将"已冷却"文案改为"已可触发"，语义更明确
- [ ] 修改 `loadCooldown()` JS 函数中冷却列表条目渲染：
  - 在右侧区域（`.cd-remaining`）下方新增一行，显示冷却到期时刻
  - 新增行样式：`font-size:.7rem;color:var(--text2)`，文案格式为"到期 HH:MM:SS"
  - 将右侧区域包裹在 `<div style="text-align:right">` 容器中，使剩余时间和到期时刻右对齐
- 涉及文件：`plugins/proactive-chat/webui.py`
- 验收方式：冷却状态 API 返回 `expires_at` 和 `expires_time` 字段；WebUI 冷却列表每个条目在剩余时间下方显示"到期 HH:MM:SS"；已冷却的条目显示"已可触发"而非"已冷却"

**依赖**：无（webui.py 现有代码已稳定）

---

## WebUI 体验优化

> 基于对当前 WebUI 实现的全面审查，从数据展示、交互体验、视觉呈现、性能四个维度提出优化
> 修改模块：`webui.py`、`persistence.py`、`cooldown.py`
> 新增 API 端点：`/api/proactive-chat/cooldown/reset`、`/api/proactive-chat/decisions/archive`

---

## 40. 后端分页与统计缓存 — 消除全量加载性能瓶颈

- [x] 修改 `persistence.py` 的 `query_decisions()` 方法，新增 `offset: int = 0` 参数：
  - 在 `_query_decisions_sync()` 中，先收集所有匹配记录（不应用 limit），然后对匹配结果按 `ts` 降序排序，最后应用 `offset` 和 `limit` 切片
  - 返回值改为 `tuple[list[DecisionRecord], int]`，第二个元素为匹配总数（不含 offset/limit）
  - 修改 `query_decisions()` 异步方法签名，透传 `offset` 参数，返回类型改为 `tuple[list[DecisionRecord], int]`
- [ ] 修改 `webui.py` 的 `_handle_decisions()` 方法：
  - 新增 `offset` 查询参数：`request.query.get("offset", "0")`
  - 调用 `query_decisions()` 时传入 `offset` 和 `limit=page_size`
  - 使用返回的匹配总数替代 `len(all_decisions)` 计算分页
  - 移除全量加载 + 前端切片逻辑，直接使用后端返回的分页数据
  - API 响应新增 `total` 字段（来自 `query_decisions` 返回的匹配总数）
- [ ] 修改 `webui.py` 的 `_handle_stats()` 方法：
  - 新增 `StatsCache` 内部类，缓存统计结果，TTL 为 30 秒：
    - `_cache_time: float = 0.0`
    - `_data: dict = {}`
  - 请求到达时检查缓存是否过期，未过期直接返回缓存数据
  - 缓存过期时重新计算，但使用更高效的查询策略：
    - 今日统计：`query_decisions(start_time=today_start, limit=0)` 获取今日总数（limit=0 表示只获取 count 不返回记录）
    - 累计统计：使用 `query_decisions(limit=0)` 获取总数（避免加载全部记录到内存）
  - 修改 `query_decisions()` 支持 `limit=0` 语义：仅返回匹配总数，不返回记录列表
- [ ] 修改前端 JS `loadDecisions()` 函数：
  - 分页请求使用 `offset` 参数替代仅依赖 `page` 参数
  - 分页逻辑适配后端返回的 `total` 值
- 涉及文件：`plugins/proactive-chat/persistence.py`、`plugins/proactive-chat/webui.py`
- 验收方式：`_handle_decisions()` 不再加载全量数据，仅加载当前页记录；`_handle_stats()` 使用 30 秒缓存，不每次全量扫描；`query_decisions(limit=0)` 只返回计数不返回记录；分页导航正确

**依赖**：无（persistence.py 和 webui.py 现有代码已稳定）

---

## 41. 冷却进度条与快捷操作

- [x] 修改前端 HTML/CSS，为冷却列表条目新增进度条：
  - 新增 `.cd-progress` 样式：高度 4px、圆角 2px、背景 `var(--border)`、内嵌 `.cd-progress-bar` 子元素
  - `.cd-progress-bar` 样式：高度 100%、圆角 2px、背景 `var(--accent)`、`transition: width 1s linear`
  - 进度计算：`progress = elapsed / cooldown_seconds * 100`，`elapsed = now - triggered_at`
  - 已冷却时进度条满格，背景色改为 `var(--green)`
- [ ] 修改 `loadCooldown()` JS 函数，在冷却条目中渲染进度条：
  - 在 `.cd-item` 中 `.cd-stream` 和右侧区域之间插入进度条
  - 进度条宽度通过 `style="width: X%"` 内联设置
- [ ] 新增 `/api/proactive-chat/cooldown/reset` POST API 端点：
  - 接收 `stream_id` 参数（从请求体 JSON 读取）
  - 调用 `self._cooldown.reset(stream_id)` 清除指定聊天流的冷却
  - 返回 `{"success": true}` 或 `{"success": false, "error": "..."}`
- [ ] 修改前端冷却列表，为每个条目新增"清除冷却"按钮：
  - 按钮样式：小型文字按钮，`font-size:.7rem`、`color:var(--red)`、`cursor:pointer`、无边框无背景
  - 点击时调用 `POST /api/proactive-chat/cooldown/reset`，传入 `stream_id`
  - 成功后自动刷新冷却列表
  - 已冷却的条目不显示该按钮
- [ ] 在 `webui.py` 的 `start()` 方法中注册新路由：`self._app.router.add_post("/api/proactive-chat/cooldown/reset", self._handle_cooldown_reset)`
- 涉及文件：`plugins/proactive-chat/webui.py`
- 验收方式：冷却列表每个条目显示进度条，进度随时间推进；"清除冷却"按钮点击后该条目消失；已冷却条目不显示按钮；进度条满格时颜色变绿

**依赖**：任务 40（前端 JS 已适配后端分页）

---

## 42. 决策记录耗时列与归档操作

- [x] 修改 `persistence.py` 的 `DecisionRecord` dataclass，新增 `duration_ms: float = 0.0` 字段：
  - 记录决策循环从开始到结束的耗时（毫秒）
  - 在 `_fill_record_defaults()` 中补充默认值
  - 在 `_dict_to_record()` 中补充字段映射
- [ ] 修改 `agent.py` 的 `decision_loop()` 方法，在 reflect 阶段计算并记录 `duration_ms`：
  - 在 `decision_loop()` 入口处记录 `start_time = time.monotonic()`
  - 在构建 `updates` 字典时，新增 `duration_ms = round((time.monotonic() - start_time) * 1000, 1)`
- [ ] 修改前端决策记录表格，新增"耗时"列（在"动作"列之后）：
  - `duration_ms > 0` 时显示为 `Xms` 或 `Xs`（超过 1000ms 显示秒）
  - `duration_ms == 0` 时显示"-"
  - 超过 5000ms 的耗时用 `var(--yellow)` 颜色标记
  - 超过 30000ms 的耗时用 `var(--red)` 颜色标记
- [ ] 新增 `/api/proactive-chat/decisions/archive` POST API 端点：
  - 接收 `record_key` 参数（从请求体 JSON 读取），格式为 `[ts, stream_id]`
  - 调用 `self._persistence.update_record_status((ts, stream_id), {"record_status": "archived"})`
  - 返回 `{"success": true}` 或 `{"success": false, "error": "..."}`
- [ ] 修改前端决策记录表格，为每行新增"归档"操作按钮：
  - 按钮样式：小型文字按钮，`font-size:.7rem`、`color:var(--text2)`、`cursor:pointer`、无边框无背景
  - 仅对 `record_status="completed"` 的记录显示
  - 点击后弹出确认对话框（`confirm("确认归档此记录？")`），确认后调用归档 API
  - 成功后刷新决策记录列表
- [ ] 在 `webui.py` 的 `start()` 方法中注册新路由：`self._app.router.add_post("/api/proactive-chat/decisions/archive", self._handle_decisions_archive)`
- 涉及文件：`plugins/proactive-chat/persistence.py`、`plugins/proactive-chat/agent.py`、`plugins/proactive-chat/webui.py`
- 验收方式：决策记录表格显示耗时列，耗时超过阈值有颜色标记；"归档"按钮点击后记录状态变为"已归档"；归档后记录从默认视图中消失

**依赖**：任务 32（reflect 重构后 updates 字典结构已稳定）

---

## 43. 决策记录排序功能

- [x] 修改前端决策记录表格，为表头添加排序功能：
  - 可排序列：时间（默认降序）、置信度、耗时
  - 表头样式：可排序列显示排序指示箭头（▲/▼），`cursor:pointer`
  - 点击表头切换升序/降序
  - 排序逻辑在前端 JS 中实现（对当前页数据排序，无需后端支持）
- [ ] 新增 JS 排序状态管理：
  - `sortField` 变量：当前排序字段（`ts`、`confidence`、`duration_ms`）
  - `sortOrder` 变量：当前排序方向（`asc`、`desc`）
  - `renderDecisions()` 函数在渲染前根据排序状态对 `d.records` 排序
- [ ] 修改表头 HTML，为可排序列添加 `onclick` 事件和排序指示器：
  - 时间列：`<th onclick="toggleSort('ts')">时间 <span id="sort-ts">▼</span></th>`
  - 置信度列：`<th onclick="toggleSort('confidence')">置信度 <span id="sort-confidence"></span></th>`
  - 耗时列：`<th onclick="toggleSort('duration_ms')">耗时 <span id="sort-duration_ms"></span></th>`
- [ ] 新增 `toggleSort(field)` JS 函数：
  - 点击同一列切换排序方向，点击不同列默认降序
  - 更新排序指示器显示
  - 重新渲染表格
- 涉及文件：`plugins/proactive-chat/webui.py`
- 验收方式：点击时间/置信度/耗时列头可切换排序方向；排序指示器正确显示当前排序状态；表格数据按排序规则重新排列

**依赖**：任务 42（耗时列已添加）

---

## 44. 时间范围快捷筛选

- [x] 修改前端筛选栏，新增时间范围快捷按钮组：
  - 按钮组位于筛选栏最左侧，包含 4 个按钮："1小时"、"6小时"、"24小时"、"7天"
  - 按钮样式：小型按钮，`font-size:.8rem`、`padding:4px 10px`、`border-radius:4px`
  - 选中按钮使用 `var(--accent)` 背景，未选中使用 `var(--card)` 背景
  - 默认不选中任何按钮（显示全部记录）
- [ ] 新增 `timeRange` JS 变量，存储当前选中的时间范围（秒数），0 表示不限制
- [ ] 修改 `loadDecisions()` JS 函数：
  - 当 `timeRange > 0` 时，计算 `start_time = Math.floor(Date.now() / 1000) - timeRange`
  - 在请求 URL 中新增 `start_time` 参数
- [ ] 修改 `_handle_decisions()` API，新增 `start_time` 查询参数：
  - `request.query.get("start_time", "")`
  - 透传到 `query_decisions(start_time=float(start_time))` 调用
  - `persistence.py` 的 `query_decisions()` 已支持 `start_time` 参数，无需修改
- [ ] 新增快捷按钮点击事件处理：
  - 点击已选中按钮 → 取消选中，`timeRange=0`
  - 点击未选中按钮 → 选中该按钮，`timeRange` 设为对应秒数
  - 选择后自动触发 `loadDecisions()`
- 涉及文件：`plugins/proactive-chat/webui.py`
- 验收方式：点击"1小时"按钮后仅显示最近1小时的决策记录；再次点击取消筛选显示全部；筛选栏显示当前选中的时间范围；与现有筛选条件（状态、意图、动作）可组合使用

**依赖**：任务 40（后端分页已实现）

---

## 45. 统计概览趋势图

- [x] 修改 `_handle_stats()` API，新增趋势数据字段：
  - `hourly_trend: list[dict]` — 最近 24 小时触发趋势，每小时一个数据点
  - 每个数据点格式：`{"hour": "HH:00", "total": N, "triggered": M}`
  - 计算方式：遍历今日和昨日的决策记录，按小时分组统计
- [ ] 新增 `_compute_hourly_trend()` 内部方法：
  - 签名：`def _compute_hourly_trend(self, decisions: list[DecisionRecord]) -> list[dict]`
  - 遍历最近 24 小时的决策记录，按小时分组
  - 每组统计 `total`（该小时决策总数）和 `triggered`（该小时触发数）
  - 返回 24 个数据点，不足 24 小时的补零
- [ ] 修改前端统计概览卡片，在现有统计项下方新增趋势图：
  - 使用纯 CSS 柱状图，不引入外部图表库
  - 图表容器 `.trend-chart`：`display:flex;align-items:flex-end;gap:2px;height:60px;margin-top:12px`
  - 每个柱子 `.trend-bar`：`flex:1;min-width:0;border-radius:2px 2px 0 0;transition:height 0.3s`
  - 触发柱使用 `var(--accent)` 颜色，高度按比例计算
  - 柱子底部显示小时标签（每隔 4 小时显示，避免拥挤）
  - hover 时显示 tooltip（`title` 属性）：`"HH:00 触发 M/N"`
- [ ] 修改 `loadStats()` JS 函数，渲染趋势图：
  - 获取 `hourly_trend` 数据后，计算最大 `total` 值作为高度基准
  - 为每个数据点生成柱子元素，高度为 `(triggered / max_total) * 60px`
  - 如果 `max_total == 0`，所有柱子高度为 0
- 涉及文件：`plugins/proactive-chat/webui.py`
- 验收方式：统计概览卡片底部显示 24 小时触发趋势柱状图；柱子高度按比例渲染；hover 显示具体数据；无数据时柱子高度为 0

**依赖**：任务 40（统计缓存已实现，趋势数据可利用缓存）

---

## 46. 冷却状态卡片触发摘要与响应式修复

- [x] 修改 `_handle_cooldown()` API，为每个冷却记录新增 `last_summary` 字段：
  - 查询该 `stream_id` 最近一条决策记录的 `input_summary`（截断至 80 字符）
  - 使用 `query_decisions(stream_id=sid, limit=1)` 获取
  - 为避免 N+1 查询，批量收集所有冷却中的 `stream_id`，一次性查询最近的决策记录
  - 新增 `_batch_query_recent_summaries()` 内部方法优化批量查询
- [ ] 修改前端冷却列表条目，在 `intent` 行下方新增摘要行：
  - 样式：`font-size:.7rem;color:var(--text2);margin-top:2px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:280px`
  - 内容：`last_summary` 字段值，为空时不显示
- [ ] 修复响应式布局问题：
  - 决策记录表格容器新增 `overflow-x:auto`，允许窄屏水平滚动
  - 调整 `.grid` 的 `minmax` 最小宽度从 320px 改为 280px，适配更窄屏幕
  - 表格 `th/td` 新增 `white-space:nowrap` 防止标题行换行
- 涉及文件：`plugins/proactive-chat/webui.py`
- 验收方式：冷却条目显示最近一次决策摘要；窄屏下表格可水平滚动；统计概览和冷却卡片在窄屏下正常堆叠

**依赖**：任务 40（后端分页已实现，批量查询方法可复用）

---

## 47. 决策记录行展开详情

- [x] 修改前端决策记录表格，新增行点击展开详情功能：
  - 点击表格行 → 在该行下方展开详情面板
  - 再次点击 → 收起详情面板
  - 同一时间只展开一个详情面板
- [ ] 新增详情面板样式 `.detail-panel`：
  - `background:rgba(108,92,231,.03);padding:12px 16px;border-bottom:1px solid var(--border)`
  - 内容分两列布局：左侧显示输入摘要和完整原因，右侧显示分析结果 JSON
- [ ] 新增 `toggleDetail(index)` JS 函数：
  - 管理当前展开的行索引 `expandedRow`
  - 点击时切换展开/收起状态
  - 使用 `insertAdjacentHTML` 在当前行后插入详情面板
  - 收起时移除详情面板 DOM
- [ ] 详情面板内容：
  - **输入摘要**：`input_summary` 完整文本（不再截断）
  - **完整原因**：`analysis_result.reason` 完整文本
  - **分析结果**：格式化显示 `should_trigger`、`intent`、`reason`、`confidence`
  - **错误信息**：`error` 字段非空时显示
  - **重试次数**：`retry_count > 0` 时显示
- [ ] 修改表格行渲染，为每行添加 `onclick="toggleDetail(N)"` 事件和 `style="cursor:pointer"`
- 涉及文件：`plugins/proactive-chat/webui.py`
- 验收方式：点击决策记录行可展开详情面板，显示完整信息；再次点击收起；同一时间只展开一个；详情面板内容完整不截断

**依赖**：任务 42（耗时列和归档按钮已添加）

---

## 48. WebUI 优化集成验证

- [x] 验证后端分页：切换到第 2 页，确认请求包含 `offset` 参数，响应 `total` 正确
- [ ] 验证统计缓存：连续快速刷新页面，确认 30 秒内统计数据不变，30 秒后更新
- [ ] 验证冷却进度条：触发主动对话后查看冷却列表，确认进度条随时间推进
- [ ] 验证清除冷却：点击"清除冷却"按钮，确认该条目消失，该聊天流可再次触发
- [ ] 验证耗时列：触发决策后查看记录，确认耗时列显示毫秒/秒数值，超阈值有颜色标记
- [ ] 验证归档操作：点击"归档"按钮，确认记录状态变为"已归档"，从默认视图消失
- [ ] 验证排序功能：点击时间/置信度/耗时列头，确认排序方向切换，指示器正确
- [ ] 验证时间范围筛选：点击"1小时"按钮，确认仅显示最近1小时记录；再次点击取消
- [ ] 验证趋势图：查看统计概览底部，确认 24 小时柱状图正确渲染
- [ ] 验证冷却摘要：查看冷却条目，确认显示最近决策摘要
- [ ] 验证行展开详情：点击决策记录行，确认展开详情面板显示完整信息
- [ ] 验证响应式：在窄屏下查看页面，确认表格可水平滚动，卡片正常堆叠
- [ ] 验证性能：决策记录超过 1000 条时，页面加载和刷新时间不超过 2 秒
- 涉及文件：全部插件文件
- 验收标准：所有优化功能可正常使用；页面性能无明显退化；窄屏下布局正常

**依赖**：任务 40-47（所有 WebUI 优化任务完成）
