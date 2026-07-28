# 发言权转移 — 实现任务清单

## 1. 数据模型

### 1.1 新增发言权转移枚举和数据类

- [x] 在 `src/maisaka/agent_autonomy/speaker_transfer.py` 中新增 `SpeakerTransferType` 枚举（`TEMPORARY_BORROW` / `PERMANENT_TRANSFER`）、`TransferDecisionSource` 枚举（`RULE` / `LLM` / `MANUAL` / `AGENT_EXIT`）、`TransferDecision` 数据类（`transfer_type` / `target_agent_id` / `reason` / `decision_source` / `display_name`）、`SpeakerTransferEvent` 数据类（`from_agent_id` / `to_agent_id` / `transfer_type` / `change_reason` / `decision_source` / `timestamp`，保留用于 WebUI 查询，Orchestrator 不直接构造）
- 涉及文件：`src/maisaka/agent_autonomy/speaker_transfer.py`（新建）
- 验证标准：枚举值正确、数据类字段完整、`TransferDecision(transfer_type=None, ...)` 可正常构造
- 依赖：无

### 1.2 新增 ButlerConfig 模型与 SPEAKER_TRANSFER 事件类型

- [x] 在 `src/maisaka/agent_autonomy/speaker_transfer.py` 中新增 `ButlerConfig` Pydantic 模型，包含 `can_switch_primary: bool = False`、`consecutive_silent_threshold: int = 2`、`consecutive_response_threshold: int = 3`、`butler_takeover_threshold: int = 2`、`borrow_upgrade_threshold: int = 3`；在 `src/maisaka/agent_autonomy/autonomy_logger.py` 的 `AutonomyEventType` 中新增 `SPEAKER_TRANSFER = "speaker_transfer"`
- 涉及文件：`src/maisaka/agent_autonomy/speaker_transfer.py`、`src/maisaka/agent_autonomy/autonomy_logger.py`
- 验证标准：`ButlerConfig` 可从 `dict` 解析、`AutonomyEventType.SPEAKER_TRANSFER` 值为 `"speaker_transfer"`
- 依赖：无

## 2. 管家状态追踪

### 2.1 Butler 初始化新增计数器与状态更新方法

- [x] 在 `Butler.__init__()` 中新增 4 个状态追踪计数器：`_consecutive_silent_count: int = 0`、`_consecutive_responder: tuple[str, int] | None = None`、`_butler_takeover_count: int = 0`、`_borrow_counts: dict[str, int] = {}`；从 `AgentConfig.butler_config` 解析 `ButlerConfig` 存为 `_butler_transfer_config`；新增 `update_primary_status(status: str, responder_id: str = "")` 方法：`status="reply"` 时重置 `_consecutive_silent_count` 和 `_butler_takeover_count`、更新 `_consecutive_responder`；`status="silent"` 时递增 `_consecutive_silent_count`；`status="butler_takeover"` 时递增 `_butler_takeover_count`
- 涉及文件：`src/maisaka/agent_autonomy/butler.py`
- 验证标准：`update_primary_status("reply")` 后 `_consecutive_silent_count == 0`；`update_primary_status("silent")` 后 `_consecutive_silent_count` 递增；`_butler_transfer_config` 正确解析 `butler_config` 字典
- 依赖：1.2

### 2.2 Butler.update_primary() 方法

- [x] 在 `Butler` 中新增 `update_primary(new_primary_id: str)` 方法，更新 `_primary_agent_id` 和 `_primary_display_name`，重置所有计数器（`_consecutive_silent_count = 0`、`_consecutive_responder = None`、`_butler_takeover_count = 0`、`_borrow_counts = {}`）
- 涉及文件：`src/maisaka/agent_autonomy/butler.py`
- 验证标准：调用 `update_primary("tighnari")` 后 `_primary_agent_id == "tighnari"`、所有计数器归零
- 依赖：2.1

## 3. 管家决策逻辑

### 3.1 永久转移规则评估

- [x] 在 `Butler` 中新增 `_evaluate_permanent_transfer(user_text: str) -> TransferDecision | None` 方法，纯规则判断永久转移条件：1) `_consecutive_silent_count >= consecutive_silent_threshold`；2) `_consecutive_responder` 连续回应同一共居者 >= `consecutive_response_threshold`；3) 用户文本中明确要求切换（名字被提到 + 关键词匹配"接管/来回答/换你"等，纯规则不额外调 LLM）；优先级：用户明确要求 > 连续沉默 > 连续回应；返回匹配的共居者 `TransferDecision(transfer_type=PERMANENT_TRANSFER, ...)` 或 `None`；若 `can_switch_primary == False` 则返回 `None`
- 涉及文件：`src/maisaka/agent_autonomy/butler.py`
- 验证标准：连续沉默 2 次 + 有活跃共居者 → 返回 `PERMANENT_TRANSFER` 决策；`can_switch_primary=False` → 返回 `None`；用户说"让布洛妮娅来回答" → 返回目标为布洛妮娅的永久转移决策
- 依赖：2.1

### 3.2 借用升级评估

- [x] 在 `Butler` 中新增 `_evaluate_borrow_upgrade() -> TransferDecision | None` 方法，检查 `_borrow_counts` 中是否有智能体借用次数 >= `borrow_upgrade_threshold`，若有则返回 `TransferDecision(transfer_type=PERMANENT_TRANSFER, target_agent_id=该智能体, reason="借用升级", decision_source=RULE)`；若 `can_switch_primary == False` 则返回 `None`
- 涉及文件：`src/maisaka/agent_autonomy/butler.py`
- 验证标准：某智能体借用 3 次 → 返回借用升级决策；`can_switch_primary=False` → 返回 `None`
- 依赖：2.1

### 3.3 发言权转移统一决策入口

- [x] 在 `Butler` 中新增 `decide_speaker_transfer(user_text: str, agent_text: str, primary_status: str) -> list[TransferDecision]` 方法：1) `primary_status="reply"` → 复用 `decide_interjection()` 三层过滤，将 `InterjectionCandidate` 转为 `TransferDecision(transfer_type=TEMPORARY_BORROW, ...)`（无需修改 InterjectionCandidate 本身）；2) `primary_status="silent"` → 先调用 `_evaluate_permanent_transfer()`，若返回非 None 则输出永久转移决策，否则复用三层过滤输出临时借用决策；3) 检查 `_evaluate_borrow_upgrade()`；4) 保留 `decide_interjection()` 不变，作为子调用；5) 多决策优先级：永久转移最多 1 个，临时借用最多 2 个，永久转移优先执行
- 涉及文件：`src/maisaka/agent_autonomy/butler.py`
- 验证标准：主智能体 REPLY + 管家选中布洛妮娅 → 返回 `TEMPORARY_BORROW`；主智能体 SILENT + 连续沉默达阈值 → 返回 `PERMANENT_TRANSFER`；主智能体 SILENT + 未达阈值 → 返回空列表或临时借用
- 依赖：3.1、3.2

## 4. ActivityStore 与日志扩展

### 4.1 save_speaker_change 扩展与数据库模型

- [x] 在 `AgentActivityStore.save_speaker_change()` 中新增可选参数 `transfer_type: str = "permanent_transfer"` 和 `decision_source: str = "manual"`；在 `AgentAutonomySpeakerChangeRecord` 数据库模型中新增对应列（默认值分别为 `"permanent_transfer"` 和 `"manual"`，向后兼容旧记录）；确保 `save_speaker_change()` 将新字段写入数据库
- 涉及文件：`src/maisaka/agent_autonomy/activity_store.py`、`src/common/database/database_model.py`
- 验证标准：调用 `save_speaker_change(..., transfer_type="temporary_borrow", decision_source="rule")` 后数据库记录包含新字段；旧调用方式（不传新参数）仍正常工作
- 依赖：无

### 4.2 SPEAKER_TRANSFER 日志记录

- [x] 在 `switch_primary_speaker()` 和发言权转移相关路径中，通过 `AutonomyLogger.log()` 记录 `SPEAKER_TRANSFER` 事件，格式：`{transfer_type} from={from_id} to={to_id} reason={reason} source={source}`；临时借用完成时也记录日志（`interjection_borrow` 触发来源）
- 涉及文件：`src/maisaka/agent_autonomy/orchestrator.py`（后续批次改造时集成）
- 验证标准：永久转移后日志包含 `speaker_transfer: permanent_transfer from=X to=Y reason=Z source=W`；临时借用后日志包含 `speaker_transfer: temporary_borrow`
- 依赖：1.2、4.1

## 5. Orchestrator 改造 — switch_primary_speaker

### 5.1 switch_primary_speaker 扩展参数与 Butler 同步

- [x] 扩展 `switch_primary_speaker()` 签名，新增 `transfer_type: SpeakerTransferType = SpeakerTransferType.PERMANENT_TRANSFER` 和 `decision_source: TransferDecisionSource = TransferDecisionSource.MANUAL` 参数；在切换成功后调用 `self._butler.update_primary(target_agent_id)` 同步管家的 `_primary_agent_id`；在 `save_speaker_change()` 调用中传递 `transfer_type` 和 `decision_source`；在 `AutonomyLogger` 中使用 `SPEAKER_TRANSFER` 事件类型替代 `ORCHESTRATION`
- 涉及文件：`src/maisaka/agent_autonomy/orchestrator.py`
- 验证标准：`switch_primary_speaker("tighnari", "test", transfer_type=PERMANENT_TRANSFER, decision_source=RULE)` 执行后 `_primary_agent_id == "tighnari"`、`Butler._primary_agent_id == "tighnari"`、ActivityStore 记录包含 `transfer_type` 和 `decision_source`；原有调用方式（不传新参数）仍正常工作
- 依赖：2.2、4.1

### 5.2 deactivate_agent 传递 decision_source

- [x] 在 `deactivate_agent()` 中调用 `switch_primary_speaker()` 时传递 `decision_source=TransferDecisionSource.AGENT_EXIT` 和 `transfer_type=SpeakerTransferType.PERMANENT_TRANSFER`
- 涉及文件：`src/maisaka/agent_autonomy/orchestrator.py`
- 验证标准：智能体退场触发的切换在 ActivityStore 中记录 `decision_source="agent_exit"`
- 依赖：5.1

## 6. Orchestrator 改造 — 主回复与插话流程

### 6.1 _schedule_primary_reply 计数器更新

- [x] 在 `_schedule_primary_reply()` 中集成计数器更新：1) REPLY 分支：调用 `self._butler.update_primary_status("reply", responder_id=self._primary_agent_id)` 更新计数器；2) SILENT 分支：调用 `self._butler.update_primary_status("silent")` 更新沉默计数。此任务仅添加计数器调用，不改变 SILENT 分支的决策逻辑
- 涉及文件：`src/maisaka/agent_autonomy/orchestrator.py`
- 验证标准：主智能体 REPLY 后 `_consecutive_silent_count == 0`；主智能体 SILENT 后 `_consecutive_silent_count` 递增
- 依赖：2.1

### 6.2 _schedule_primary_reply SILENT 分支决策重构

- [x] 重构 `_schedule_primary_reply()` 的 SILENT 分支：1) 调用 `self._butler.decide_speaker_transfer(content, "", "silent")` 评估永久转移；2) 若返回 `PERMANENT_TRANSFER` 决策，执行 `switch_primary_speaker(target, reason, change_type="butler_auto", transfer_type=PERMANENT_TRANSFER, decision_source=decision.decision_source)` 并触发新主发言思考；3) 若无永久转移，调用管家接管 `speak_and_send()`，接管后调用 `update_primary_status("butler_takeover")`；4) 接管次数达阈值时触发永久转移评估；5) 多决策优先级：永久转移优先，执行后临时借用自动取消
- 涉及文件：`src/maisaka/agent_autonomy/orchestrator.py`
- 验证标准：主智能体 SILENT + 连续沉默达阈值 → 执行永久转移而非管家接管；主智能体 SILENT + 未达阈值 → 管家接管；主智能体 REPLY → 计数器正确更新
- 依赖：3.3、5.1、6.1

### 6.3 handle_message 管家插话分支重构

- [x] 重构 `handle_message()` 中管家插话分支：将 `decide_interjection()` → `_trigger_interjection_for()` 替换为 `decide_speaker_transfer(content, primary_reply_text, "reply")` → 根据转移类型分发：`TEMPORARY_BORROW` → 调用 `_trigger_interjection_for(agent_id, content)`（source 传 `interjection_borrow`），借用完成后调用 `update_primary_status` 更新 `_borrow_counts`；`PERMANENT_TRANSFER` → 调用 `switch_primary_speaker()` + 触发新主发言思考
- 涉及文件：`src/maisaka/agent_autonomy/orchestrator.py`
- 验证标准：主智能体 REPLY + 管家选中布洛妮娅 → 布洛妮娅临时借用发言，发言后发言权自动归还（`ChatSession.agent_id` 不变）；主智能体 REPLY + 连续回应达阈值 → 永久转移
- 依赖：3.3、5.1

## 7. 配置启用与兼容

### 7.1 can_switch_primary 启用与 WebUI 兼容

- [x] 在 `Butler.decide_speaker_transfer()` 中检查 `_butler_transfer_config.can_switch_primary`，`False` 时永久转移降级为管家接管（`speak_and_send`）；在 WebUI `/autonomy/switch-speaker` 端点中调用 `switch_primary_speaker()` 时传递 `decision_source=TransferDecisionSource.MANUAL` 和 `transfer_type=SpeakerTransferType.PERMANENT_TRANSFER`
- 涉及文件：`src/maisaka/agent_autonomy/butler.py`、`src/webui/routers/agent.py`
- 验证标准：`can_switch_primary=False` + 连续沉默达阈值 → 管家接管而非永久转移；WebUI 手动切换 → ActivityStore 记录 `decision_source="manual"`
- 依赖：3.3、5.1

### 7.2 ThinkCycleLog 触发来源扩展

- [x] 在 `ThinkContext.trigger_reason` 和 `ThinkCycleLog.trigger` 中新增 `interjection_borrow` 触发来源，区分临时借用和普通插话；在 `_trigger_interjection_for()` 中根据调用来源传递 `trigger_reason="interjection_borrow"` 或 `"butler_interjection"`
- 涉及文件：`src/maisaka/agent_autonomy/orchestrator.py`、`src/core/types.py`（`ThinkContext.trigger_reason` 注释更新）
- 验证标准：临时借用触发的思考日志中 `trigger=interjection_borrow`；普通插话触发的思考日志中 `trigger=butler_interjection`
- 依赖：6.3

## 8. 永久转移回退

### 8.1 永久转移回退验证

- [ ] 验证永久转移回退流程：永久转移后新主发言连续 SILENT → 管家 `_evaluate_permanent_transfer()` 评估回退（检查新主发言的沉默计数）→ 若原主仍活跃则执行回退转移 → 若原主已退场则保持当前主发言；验证用户要求切回（"银狼你回来"）触发回退；验证回退后所有状态同步一致
- 涉及文件：`src/maisaka/agent_autonomy/orchestrator.py`、`src/maisaka/agent_autonomy/butler.py`
- 验证标准：新主发言连续 SILENT 达阈值 + 原主仍活跃 → 回退转移成功；原主已退场 → 保持当前主发言；用户说"银狼你回来" → 回退给银狼
- 依赖：6.2、6.3、7.1

说明：回退逻辑复用 `_evaluate_permanent_transfer()`（检查当前主发言的沉默计数），不需要新增方法。永久转移后管家 `update_primary()` 已重置计数器，新主发言的沉默会重新累积，自然触发回退评估。

## 9. 集成验证

### 9.1 临时借用端到端验证

- [ ] 验证临时借用完整流程：用户消息 → 主智能体 REPLY → 管家 `decide_speaker_transfer(primary_status="reply")` → 返回 `TEMPORARY_BORROW` → 借用者思考并发言 → 发言权自动归还主智能体 → 下一条消息由主智能体处理；验证 `ChatSession.agent_id` 在借用期间不变；验证借用计数器正确更新；验证借用者 SILENT 时不计入有效借用
- 涉及文件：`src/maisaka/agent_autonomy/orchestrator.py`、`src/maisaka/agent_autonomy/butler.py`
- 验证标准：临时借用后 `ChatSession.agent_id` 仍为主智能体；借用计数器递增；借用者 SILENT 时不递增
- 依赖：6.3、7.1、7.2

### 9.2 永久转移端到端验证

- [ ] 验证永久转移完整流程：主智能体连续 SILENT → 管家 `decide_speaker_transfer(primary_status="silent")` → 返回 `PERMANENT_TRANSFER` → `switch_primary_speaker()` 执行 → 5 个状态同步一致（`_primary_agent_id`、`Butler._primary_agent_id`、`ActivityStore`、`ChatSession.agent_id`、`chat_loop_adapter`）；验证退场触发转移；验证 WebUI 手动切换；验证 `can_switch_primary=False` 时降级为管家接管；验证永久转移后管家计数器重置
- 涉及文件：`src/maisaka/agent_autonomy/orchestrator.py`、`src/maisaka/agent_autonomy/butler.py`、`src/maisaka/agent_autonomy/activity_store.py`
- 验证标准：永久转移后 5 个状态全部指向新主发言；退场转移 `decision_source="agent_exit"`；WebUI 转移 `decision_source="manual"`；`can_switch_primary=False` 时不执行永久转移
- 依赖：6.2、6.3、7.1
