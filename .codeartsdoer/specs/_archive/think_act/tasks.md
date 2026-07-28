# 思考-行动分离架构迁移 — 编码任务列表

## 1. 数据模型层：新增枚举与数据类

### 1.1 新增 SilenceReason 枚举

- [ ] 在 `src/core/types.py` 中新增 `SilenceReason` 枚举，包含 7 种取值：INTENTIONAL / NO_CONTENT / ERROR / TIMEOUT / REJECTED / TOOL_FAILED / MAX_CYCLES
- 验收：枚举定义完整，7 种取值均有中文注释说明语义；`SilenceReason` 位于 `ThinkAction` 枚举之后

### 1.2 新增 CycleStatus 枚举

- [ ] 在 `src/core/types.py` 中新增 `CycleStatus` 枚举，包含 4 种取值：COMPLETED_REPLY / COMPLETED_SILENT / ERROR / TIMEOUT
- 验收：枚举定义完整，4 种取值均有中文注释说明语义；`CycleStatus` 位于 `SilenceReason` 枚举之后

### 1.3 新增 ThinkCycleLog 数据类

- [ ] 在 `src/core/types.py` 中新增 `ThinkCycleLog` 数据类（`@dataclass(slots=True)`），包含 13 个字段：agent_id / session_name / trigger / status / silence_reason / thought_summary / action_summary / reply_text / cycle_count / tool_calls_made / tool_errors / elapsed_ms / error_detail
- 验收：所有字段均有默认值（向后兼容）；`tool_calls_made` 和 `tool_errors` 使用 `field(default_factory=list)`；包含 `to_log_line()` 方法，生成格式为 `[think] agent=X trigger=Y status=Z reason=W why="..."` 的人类可读日志行
- 验收：`to_log_line()` 中 intentional 沉默包含 `why` 字段（内容为 thought_summary），error/rejected 沉默包含 `detail` 字段（内容为 error_detail）

### 1.4 扩展 ThinkResult 数据类

- [ ] 在 `src/core/types.py` 的 `ThinkResult` 数据类中新增 3 个字段：`silence_reason: SilenceReason | None = None` / `thought_summary: str = ""` / `reply_sent: bool = False`
- 验收：新增字段均有默认值，现有消费者无需修改；`silence_reason` 仅 action=SILENT 时有值；`reply_sent` 标记 reply 工具是否已内部发送消息

## 2. ThinkingOrgan 核心改造：废除简化模式

### 2.1 删除简化模式方法

- [ ] 从 `src/maisaka/agent_autonomy/thinking_organ.py` 中删除 `_think_simple()` 方法（第 574-611 行）
- [ ] 从 `src/maisaka/agent_autonomy/thinking_organ.py` 中删除 `_think_proactive_simple()` 方法（第 613-651 行）
- [ ] 从 `src/maisaka/agent_autonomy/thinking_organ.py` 中删除 `_call_llm()` 辅助方法（第 653-674 行）
- 验收：ThinkingOrgan 类中不存在 `_think_simple` / `_think_proactive_simple` / `_call_llm` 三个方法；类文档字符串中不再提及"简化模式"

### 2.2 删除 has_full_capabilities 分支

- [ ] 修改 `think()` 方法（第 88-110 行）：删除 `if self.has_full_capabilities` 分支，统一调用 `_think_with_tools(context, request_kind="planner")`
- [ ] 修改 `think_proactive()` 方法（第 112-134 行）：删除 `if self.has_full_capabilities` 分支，统一调用 `_think_with_tools(context, request_kind="planner", reason=reason)`
- [ ] 删除 `has_full_capabilities` 属性（第 61-63 行）
- 验收：`think()` 和 `think_proactive()` 无分支判断，所有路径统一走 `_think_with_tools`；`has_full_capabilities` 属性不存在

### 2.3 构造时依赖校验

- [ ] 在 `ThinkingOrgan.__init__` 中新增校验：`chat_loop_service is None` 时抛出 `ValueError("ThinkingOrgan(agent={agent_id}) 需要 chat_loop_service，简化模式已废除，所有思考路径必须走工具循环")`
- [ ] 在 `ThinkingOrgan.__init__` 中新增校验：`tool_registry is None` 时抛出 `ValueError("ThinkingOrgan(agent={agent_id}) 需要 tool_registry，简化模式已废除，所有思考路径必须走工具循环")`
- 验收：构造时缺失必要依赖立即报错，而非运行时静默降级；签名保持 `Any | None` 不变（Protocol 兼容性）

### 2.4 工厂校验同步

- [ ] 在 `ThinkingOrganFactory.__init__` 中新增校验：`chat_loop_service_factory is None` 时抛出 `ValueError("ThinkingOrganFactory 需要 chat_loop_service_factory，简化模式已废除")`
- [ ] 在 `ThinkingOrganFactory.__init__` 中新增校验：`tool_registry is None` 时抛出 `ValueError("ThinkingOrganFactory 需要 tool_registry，简化模式已废除")`
- [ ] 保留 `ThinkingOrganFactory.create()` 中的 `degraded` 日志字段——`is_degraded` 表示提示词模板降级（非简化模式降级），废除简化模式后提示词降级仍有意义
- 验收：工厂构造时缺失必要依赖立即报错；创建的 ThinkingOrgan 实例必定具备完整能力；`is_degraded` 属性保持现有语义不变

## 3. ThinkingOrgan 核心改造：思考-行动分离

### 3.1 删除 content→REPLY 路径

- [ ] 修改 `_think_with_tools()` 中第 209-231 行的无 tool_calls 分支：删除 `content 非空 → REPLY` 路径，统一为 `SILENT + silence_reason` 判定
- 验收：当 LLM 输出无 tool_calls 时，无论 content 是否为空，ThinkResult.action 均为 SILENT；content 非空时 silence_reason=INTENTIONAL，content 为空时 silence_reason=NO_CONTENT；ThinkResult.text 始终为空字符串（不来自 content）

### 3.2 新增 _determine_silence_reason() 方法

- [ ] 在 ThinkingOrgan 中新增 `_determine_silence_reason()` 方法，按优先级判定沉默原因：tool_failed > intentional > no_content > max_cycles
- 方法签名：`def _determine_silence_reason(self, *, has_tool_failure: bool, has_content: bool, reached_max_cycles: bool) -> SilenceReason`
- 验收：有工具失败 → TOOL_FAILED；无工具失败但有内心独白 → INTENTIONAL；无内心独白 → NO_CONTENT；达到循环上限 → MAX_CYCLES；优先级严格按 tool_failed > intentional > no_content > max_cycles

### 3.3 新增 _build_cycle_log() 方法

- [ ] 在 ThinkingOrgan 中新增 `_build_cycle_log()` 方法，在思考循环结束时组装 ThinkCycleLog
- 方法签名：`def _build_cycle_log(self, *, context: ThinkContext, result: ThinkResult, cycle_count: int, tool_calls_made: list[str], tool_errors: list[str], elapsed_ms: int, error_detail: str = "") -> ThinkCycleLog`
- 验收：每次 think()/think_proactive() 调用产生一条完整的 ThinkCycleLog；日志写入失败不影响 ThinkResult 返回（try/except 包裹 logger.info 调用）

### 3.4 reply 工具调用检测与结果提取

- [ ] 新增 `ToolCycleResult` dataclass（thinking_organ.py 内部），替代 `_handle_tool_calls()` 原有 4 元组返回值，新增 `reply_detected: bool` / `reply_text: str` / `reply_failed: bool` 字段
- [ ] 修改 `_handle_tool_calls()` 方法，在遍历 tool_calls 时识别 `func_name == "reply"` 的调用
- [ ] 当检测到 reply 工具调用且执行成功时：从 `ToolExecutionResult.structured_content["reply_text"]` 提取完整回复文本（非 `result.content`，后者仅是人工可读摘要），记录 `reply_detected=True` 和 `reply_text`
- [ ] 当检测到 reply 工具调用且执行失败时：记录 `reply_failed=True`，**立即返回**（不继续循环，避免 LLM 下一轮再次调用 reply 导致重复发送）
- 验收：reply 工具调用被正确识别；成功时 reply_text 有值（来自 structured_content）；失败时 reply_failed=True 且循环立即终止

### 3.5 _think_with_tools 循环改造：集成 reply 检测与 silence_reason

- [ ] 修改 `_think_with_tools()` 循环体：接收 `_handle_tool_calls()` 返回的 `ToolCycleResult`
- [ ] 当 `reply_detected=True` 且 `reply_failed=False` 时：返回 `ThinkResult(action=REPLY, text=reply_text, reply_sent=True, thought_summary=content[:100])`
- [ ] 当 `reply_detected=True` 且 `reply_failed=True` 时：**立即返回** `ThinkResult(action=SILENT, silence_reason=TOOL_FAILED)`，不继续循环（避免重复发送）
- [ ] 当 `reply_detected=False` 时：继续循环，注入工具结果到下一轮
- [ ] 修改无 tool_calls 分支：调用 `_determine_silence_reason()` 判定沉默原因，返回 `ThinkResult(action=SILENT, silence_reason=..., thought_summary=content[:100])`
- [ ] 修改循环上限分支：返回 `ThinkResult(action=SILENT, silence_reason=SilenceReason.MAX_CYCLES, thought_summary=content[:100])`
- [ ] 修改 LLM 异常分支：返回 `ThinkResult(action=ThinkAction.ERROR, silence_reason=SilenceReason.ERROR, error_message=str(exc))`
- [ ] 在循环结束后调用 `_build_cycle_log()` 生成结构化日志并输出
- 验收：ThinkResult.text 仅来源于 reply 工具结果，不来源于 LLM content；所有 SILENT 结果附带 silence_reason；每次循环产生 ThinkCycleLog

## 4. Orchestrator 消费适配

### 4.1 管家插话消费点适配

- [ ] 修改 `orchestrator.py:276` 的管家插话消费逻辑：检查 `result.reply_sent` 标记，当 `reply_sent=True` 时跳过 `MessagePortV2.send_message()` 调用
- 验收：reply 工具已发送的消息不被 Orchestrator 重复发送；reply_sent=False 时行为不变

### 4.2 提醒触发消费点适配

- [ ] 修改 `orchestrator.py:333` 的提醒触发消费逻辑：检查 `result.reply_sent` 标记，当 `reply_sent=True` 时跳过发送
- 验收：同 4.1

### 4.3 主回复消费点适配

- [ ] 修改 `orchestrator.py:686` 的主回复消费逻辑：检查 `result.reply_sent` 标记，当 `reply_sent=True` 时跳过发送
- [ ] 修改 `orchestrator.py:706` 的 SILENT 分支日志：增加 `silence_reason` 和 `thought_summary` 输出
- 验收：同 4.1；SILENT 日志包含 silence_reason 和 thought_summary 信息

## 5. Embodied Prompt 三语强化

### 5.1 中文 prompt 重写

- [ ] 重写 `prompts/zh-CN/maisaka_chat_embodied.prompt` 第 22-33 行（"Using your tools"部分），替换为 design.md 2.3.3 节的中文改造方案
- 验收：包含"你的文本输出（content）是你的内心独白，用户看不到"；包含"必须调用 reply 工具"；包含"只想不回时不调用任何工具"；使用强约束措辞（"必须""只有"），不含弱约束（"建议""尽量"）

### 5.2 英文 prompt 重写

- [ ] 重写 `prompts/en-US/maisaka_chat_embodied.prompt` 对应部分，替换为 design.md 2.3.3 节的英文改造方案
- 验收：包含"content is your inner monologue — users cannot see it"；包含"you MUST call the reply tool"；包含"do not call any tool when you want to think without replying"

### 5.3 日文 prompt 重写

- [ ] 重写 `prompts/ja-JP/maisaka_chat_embodied.prompt` 对应部分，替换为 design.md 2.3.3 节的日文改造方案
- 验收：包含"content は内なる独白であり、ユーザーには見えません"；包含"reply ツールを呼び出さなければなりません"；包含"ツールを呼び出さないでください"

### 5.4 三语同步校验

- [ ] 逐项校验三语模板均包含核心约定：content=内心独白、reply=对外发言、不调工具=不回复
- 验收：三语模板语义一致，措辞强度一致（均为强约束）

## 6. 端到端集成验证

### 6.1 启动阶段验证

- [ ] 重启容器，验证 ThinkingOrganFactory 构造时依赖校验生效：所有智能体的 ThinkingOrgan 实例均注入了 chat_loop_service 和 tool_registry
- 验收：启动日志中无 "degraded" 或 "简化模式" 相关信息；如有依赖缺失，启动阶段即报错而非运行时降级

### 6.2 消息回复验证

- [ ] 向主智能体发送消息，验证思考-行动分离：LLM 输出 content（内心独白）+ reply 工具调用 → 用户收到回复，回复内容来自 reply 工具而非 content
- [ ] 验证 LLM 输出 content 非空但无 tool_calls → 用户不收到任何消息，日志记录 silence_reason=INTENTIONAL
- [ ] 验证 LLM 输出 content 为空且无 tool_calls → 用户不收到任何消息，日志记录 silence_reason=NO_CONTENT
- 验收：内心独白零泄漏（架构级保证）；所有 SILENT 结果附带 silence_reason

### 6.3 插话/提醒验证

- [ ] 触发管家插话场景，验证插话路径统一走工具循环，reply 工具调用后 reply_sent=True，Orchestrator 不重复发送
- [ ] 触发提醒场景，验证提醒路径统一走工具循环，行为与插话一致
- 验收：插话/提醒不再走简化模式；reply_sent 标记正确，无重复发送

### 6.4 工具循环验证

- [ ] 触发多轮工具循环场景（如 LLM 先调用 query_memory 再调用 reply），验证循环正常完成
- [ ] 触发循环上限场景，验证达到 MAX_INTERNAL_ROUNDS 时返回 SILENT + silence_reason=MAX_CYCLES
- [ ] 触发 LLM 调用异常场景，验证返回 ERROR + silence_reason=ERROR
- 验收：工具循环各退出路径均附带正确的 silence_reason；ThinkCycleLog 在所有路径下均正确生成

### 6.5 日志可观测性验证

- [ ] 检查日志输出，验证每次思考循环均产生 ThinkCycleLog 格式的日志行：`[think] agent=X trigger=Y status=Z reason=W why="..."`
- [ ] 验证 intentional 沉默的日志行包含 why 字段（thought_summary）
- [ ] 验证 error 沉默的日志行包含 detail 字段（error_detail）
- 验收：所有 SILENT 结果的日志都附带 silence_reason；日志格式人类可读且支持机器解析

### 6.6 回归验证

- [ ] 验证所有现有功能正常工作：消息回复、插话、提醒、wait、工具循环、WebUI 监控面板
- [ ] 验证 ThinkResult 新增字段不影响现有消费者：Orchestrator/WebUI/其他模块读取 ThinkResult 无报错
- 验收：所有现有功能无回归；新增字段有默认值，旧代码无感知