# SSD-4 存量债务继续清 — 编码任务清单

## 概述

消除 4 项核心禁止项（#2/#3 验证关闭、#4 napcat_* 入站化、#7 enqueue 协议瘦身）、core 层 re-export 桥接残留、MemoryField 竞态 bug，以及 mem_core_gap 未覆盖差距标注。

5 批次，每批次可独立验证。批次间有严格依赖：批次 N 验证通过后才进入批次 N+1。

---

## 1. 批次1：P0 验证关闭 + 竞态修复

**目标**：验证核心禁止项 #2/#3 已消除并更新文档；修复 MemoryField._async_write_started 竞态根因。

**风险等级**：低（#2/#3 为纯验证；竞态修复为 A_memorix 内部改造，不影响外部 API）
**回滚策略**：git revert 单任务 commit

### 1.1 核心禁止项 #2/#3 验证关闭

- [ ] 执行 grep 验证 #2：核心层（不含 adapters/）零 `chat_manager._agent_router` 引用
  ```bash
  rg "chat_manager\._agent_router" src/core/ --glob '!adapters/**'
  # 或 grep 等价：grep -rn "chat_manager\._agent_router" src/core/ | grep -v "adapters/"
  # 预期：零匹配
  ```
- [ ] 执行 grep 验证 #2：全局零 `chat_manager._agent_router` 引用（适配器自身持有的是 `_agent_router` 私有属性，不是 ChatManager 的）
  ```bash
  rg "chat_manager\._agent_router" src/
  # 预期：零匹配
  ```
- [ ] 执行 grep 验证 #3：核心层（不含 adapters/）零 `BotChatSession` 引用
  ```bash
  rg "BotChatSession" src/core/ --glob '!adapters/**'
  # 或 grep 等价：grep -rn "BotChatSession" src/core/ | grep -v "adapters/"
  ```
- [ ] 执行 grep 验证 #3：maisaka 层零 `BotChatSession` 引用
  ```bash
  rg "BotChatSession" src/maisaka/
  # 预期：零匹配
  ```
- [ ] 更新 `AGENTS.md` 核心禁止项 #2 状态为 `✅ 已消除（构造注入 AgentRouter + ruff TID251 守卫，SSD-4 验证关闭）`
- [ ] 更新 `AGENTS.md` 核心禁止项 #3 状态为 `✅ 已消除（SessionInfo 不可变快照 + ChatManagerAdapter 立即转换，SSD-4 验证关闭）`

**验收标准**：
```bash
rg "chat_manager\._agent_router" src/  # → 零匹配
rg "BotChatSession" src/core/ --glob '!adapters/**'  # → 零匹配
rg "BotChatSession" src/maisaka/  # → 零匹配
grep "✅ 已消除.*SSD-4 验证关闭" AGENTS.md  # → #2 和 #3 均有匹配
```

**风险点**：验证发现残留引用时，暂停关闭流程，先消除残留
**依赖**：无
**影响文件**：1 个（AGENTS.md）
**派发建议**：Codex（纯验证+文档更新，简单快速）

### 1.2 MemoryField._async_write_started 竞态修复

- [ ] 修改 `src/A_memorix/core/connectionist/memory_field.py` 的 `__init__` 方法，在构造时同步创建 `AsyncWriteQueue` 对象：
  ```python
  # 在 __init__ 末尾添加
  from .async_write_queue import AsyncWriteQueue
  self._async_write_queue = AsyncWriteQueue(self._observer)
  ```
- [ ] 新增 `MemoryField.initialize()` 异步方法，替代 `start_async_queue()`：
  ```python
  async def initialize(self) -> None:
      """异步初始化 — 启动 AsyncWriteQueue 消费协程。必须在首次 observe() 前完成。"""
      await self._async_write_queue.start()
  ```
- [ ] 删除 `start_async_queue()` 方法（原 L80-88）
- [ ] 修改 `observe()` 方法（原 L116-118），消除 `getattr` 竞态检测：
  ```python
  # 原代码：
  # if not getattr(self, "_async_write_started", False):
  #     await self.start_async_queue()
  # 改为：直接入队（队列对象已在 __init__ 中创建）
  if async_write:
      return await self._async_write_queue.enqueue(...)
  ```
- [ ] 删除所有 `getattr(self, "_async_write_started", False)` 引用（L81, L117）
- [ ] 删除 `self._async_write_started = True` 赋值（L88）
- [ ] 修改 `src/A_memorix/core/runtime/sdk_memory_kernel.py:413`，将 `await self._memory_field.start_async_queue()` 改为 `await self._memory_field.initialize()`
- [ ] 确认 `sdk_memory_kernel.py:418` 的 `await self._memory_field._async_write_queue.stop()` 保持不变（队列对象已在 `__init__` 中创建，可直接访问）

**验收标准**：
```bash
rg "getattr.*_async_write_started" src/A_memorix/  # → 零匹配
rg "start_async_queue" src/A_memorix/  # → 零匹配
rg "_async_write_started" src/A_memorix/  # → 零匹配
rg "memory_field.*initialize\|_memory_field\.initialize" src/A_memorix/core/runtime/sdk_memory_kernel.py  # → 1 匹配
```

**风险点**：AsyncWriteQueue.__init__ 中如有异步依赖则无法同步创建；需确认 `AsyncWriteQueue.__init__` 仅创建 asyncio.Queue 和初始化状态（已确认：L26-29 为纯同步操作）
**依赖**：无
**影响文件**：2 个（memory_field.py, sdk_memory_kernel.py）
**派发建议**：CC（A_memorix 核心模块改造，需理解竞态语义）

---

## 2. 批次2：P1 re-export 桥接消除

**目标**：消除 core 层对 chat 层的 6 处 re-export 桥接，实现 core 层（不含 adapters/）零 `from src.chat.*` 导入。

**风险等级**：中（涉及跨层物理迁移，需逐项验证导入链无断裂）
**回滚策略**：每步骤独立 git commit，可精确 revert 单步骤

### 2.1 SessionMessage 物理迁移到 common 层

- [ ] 在 `src/common/data_models/` 下新建 `session_message_data_model.py`，将 `SessionMessage` 类和 `MsgIDMapping` 辅助类从 `src/chat/message_receive/message.py` 物理迁移过来
- [ ] 确认迁移后的 `SessionMessage` 所有依赖均在 common 层：
  - `MaiMessage`（`src/common/data_models/mai_message_data_model.py`）✅
  - `Messages` 数据库模型（`src/common/database/database_model.py`）✅
  - `get_db_session`（`src/common/database/database.py`）✅
  - `MessageSequence`、各种 Component（`src/common/data_models/message_component_data_model.py`）✅
- [ ] 修改 `src/core/types.py:818`，将 re-export 指向新位置：
  ```python
  # 原：from src.chat.message_receive.message import SessionMessage as SessionMessage
  # 改：from src.common.data_models.session_message_data_model import SessionMessage as SessionMessage
  ```
  同时移除 `# ruff: noqa: TID251` 注释（不再需要豁免）
- [ ] 在 `src/chat/message_receive/message.py` 原位置添加 re-export：
  ```python
  from src.common.data_models.session_message_data_model import SessionMessage as SessionMessage
  ```
  保持 chat 层内部 20+ 文件和 plugin_runtime 6 文件从原位置导入不受影响
- [ ] 确认 maisaka 13 文件无需修改（从 `core.types` 导入路径不变）

**验收标准**：
```bash
rg "from src\.chat\.message_receive\.message import SessionMessage" src/core/  # → 零匹配
python -c "from src.common.data_models.session_message_data_model import SessionMessage; print('common OK')"  # → common OK
python -c "from src.chat.message_receive.message import SessionMessage; print('chat re-export OK')"  # → chat re-export OK
python -c "from src.core.types import SessionMessage; print('core re-export OK')"  # → core re-export OK
```

**风险点**：SessionMessage 迁移后 chat 层循环导入；需确认 `message.py` 的 re-export 不会触发循环
**依赖**：无（SessionMessage 无上游 re-export 依赖）
**影响文件**：3 个（新建 session_message_data_model.py, types.py, message.py）
**派发建议**：CC（跨层物理迁移，需理解 SessionMessage 依赖链）

### 2.2 is_bot_self/get_bot_account 物理迁移到 core/identity.py

- [ ] 将以下函数从 `src/chat/utils/utils.py` 物理迁移到 `src/core/identity.py`：
  - `get_bot_account(platform: str) -> str`
  - `is_bot_self(platform: str, user_id: str) -> bool`
  - 辅助函数：`parse_platform_accounts()`、`get_all_bot_accounts()`
  - 模块级变量：`_warned_unconfigured_platforms`
  - ⚠️ 注意：`_get_configured_qq_account()` 已在 identity.py 中定义（CC 审查确认），迁移时不可重复定义，需合并或复用已有定义
- [ ] 确认迁移后依赖无 chat 层引用：
  - `global_config`（`src/config/config.py`）— 全局可访问 ✅
  - `parse_platform_accounts` — 纯配置解析 ✅
- [ ] 修改 `src/core/identity.py`，从 re-export 桥接改为函数的真实定义：
  - 删除 `from src.chat.utils.utils import get_bot_account as get_bot_account`
  - 删除 `from src.chat.utils.utils import is_bot_self as is_bot_self`
  - 删除 `# ruff: noqa: TID251` 注释
  - 更新模块文档字符串
- [ ] 在 `src/chat/utils/utils.py` 原位置添加 re-export：
  ```python
  from src.core.identity import is_bot_self, get_bot_account
  ```
  保持 chat 层内部调用方无需修改

**验收标准**：
```bash
rg "from src\.chat\.utils\.utils import (get_bot_account|is_bot_self)" src/core/  # → 零匹配
python -c "from src.core.identity import is_bot_self, get_bot_account; print('core OK')"  # → core OK
python -c "from src.chat.utils.utils import is_bot_self, get_bot_account; print('chat re-export OK')"  # → chat re-export OK
```

**风险点**：辅助函数 `_get_configured_qq_account` / `parse_platform_accounts` 可能有 chat 层内部依赖，需逐个确认
**依赖**：无
**影响文件**：2 个（identity.py, utils.py）
**派发建议**：CC（函数迁移需确认依赖链完整性）

### 2.3 is_mentioned_bot_in_message/get_chat_type_and_target_info 物理迁移到 core/message_utils.py

- [ ] 将 `is_mentioned_bot_in_message` 及其辅助函数 `_has_at_component_targeting_bot` 从 `src/chat/utils/utils.py` 物理迁移到 `src/core/message_utils.py`
- [ ] 将 `get_chat_type_and_target_info` 从 `src/chat/utils/utils.py` 物理迁移到 `src/core/message_utils.py`
- [ ] 确认迁移后依赖无 chat 层引用：
  - `SessionMessage` — T2.1 已迁移到 common 层 ✅
  - `global_config` — 全局可访问 ✅
  - `AtComponent` — common 层 ✅
  - `get_bot_account` — T2.2 已迁移到 core/identity.py ✅
  - `get_session_info` — `src/core/session_port_registry.py`（已在 core 层）✅
  - `Person` — `src/person_info/person_info.py`（外部模块，不在 chat 层）✅
  - `ChatTargetInfo` — common 层 ✅
- [ ] 修改 `src/core/message_utils.py`，从 re-export 桥接改为函数的真实定义：
  - 删除 `from src.chat.utils.utils import is_mentioned_bot_in_message as is_mentioned_bot_in_message`
  - 删除 `from src.chat.utils.utils import get_chat_type_and_target_info as get_chat_type_and_target_info`
  - 删除 `# ruff: noqa: TID251` 注释
  - 更新桥接注释段落
- [ ] 在 `src/chat/utils/utils.py` 原位置添加 re-export：
  ```python
  from src.core.message_utils import is_mentioned_bot_in_message, get_chat_type_and_target_info
  ```

**验收标准**：
```bash
rg "from src\.chat\.utils\.utils import (is_mentioned_bot_in_message|get_chat_type_and_target_info)" src/core/  # → 零匹配
python -c "from src.core.message_utils import is_mentioned_bot_in_message, get_chat_type_and_target_info; print('core OK')"  # → core OK
```

**风险点**：`_has_at_component_targeting_bot` 依赖 `AtComponent` 和 `get_bot_account`，需确保导入路径正确；`get_chat_type_and_target_info` 依赖 `Person`（外部模块），需确认不引入循环
**依赖**：T2.1（SessionMessage 在 common 层）、T2.2（get_bot_account 在 core/identity.py）
**影响文件**：2 个（message_utils.py, utils.py）
**派发建议**：CC（函数迁移需确认依赖链完整性）

### 2.4 HeartflowRuntimeRegistry 构造注入

- [ ] 修改 `src/core/adapters/runtime_registry.py` 的 `HeartflowRuntimeRegistry.__init__`，新增 `heartflow_manager: Any` 参数：
  ```python
  def __init__(self, heartflow_manager: Any) -> None:
      self._heartflow_manager = heartflow_manager
  ```
- [ ] 删除 `_ensure_manager()` 方法（原 L20-23）
- [ ] 修改 `get_runtime()` 方法，将 `manager = self._ensure_manager()` 替换为直接使用 `self._heartflow_manager`
- [ ] 修改 `get_or_create_runtime()` 方法，同理替换
- [ ] 修改 `list_runtimes()` 方法，同理替换
- [ ] 修改 `src/main.py` 中构造 `HeartflowRuntimeRegistry` 的代码，注入 `heartflow_manager` 实例

**验收标准**：
```bash
rg "_ensure_manager" src/core/adapters/runtime_registry.py  # → 零匹配
rg "from src\.chat\.heart_flow\.heartflow_manager import heartflow_manager" src/core/  # → 零匹配
```

**风险点**：heartflow_manager 在 Registry 构造时尚未初始化 → main.py 中需确认构造时序
**依赖**：无
**影响文件**：2 个（runtime_registry.py, main.py）
**派发建议**：Codex（简单构造注入改造）

### 2.5 core 层零 chat 导入验证 + ruff TID251 守卫确认

- [ ] 执行全量验证：core 层（不含 adapters/）零 `from src.chat.*` 导入
  ```bash
  rg "from src\.chat\." src/core/ --glob '!adapters/**'
  # 预期：零匹配
  ```
- [ ] 确认 core/adapters/ 中仅保留必要的 chat 层导入
  ```bash
  rg "from src\.chat\." src/core/adapters/
  # 预期：仅 chat_manager_adapter.py 和 notice_classifier.py 中的合理导入
  ```
- [ ] 确认 ruff TID251 守卫覆盖 `src/core/` 目录（已在 SSD-3 配置）
- [ ] 确认 `src/core/types.py` 的 `# ruff: noqa: TID251` 注释已移除（T2.1 完成后）
- [ ] 确认 `src/core/identity.py` 的 `# ruff: noqa: TID251` 注释已移除（T2.2 完成后）
- [ ] 确认 `src/core/message_utils.py` 的 `# ruff: noqa: TID251` 注释已移除（T2.3 完成后）
- [ ] 执行 ruff 检查确认无 TID251 违规：
  ```bash
  ruff check src/core/ --select TID251  # → 零错误（adapters/ 豁免生效）
  ```

**验收标准**：
```bash
rg "from src\.chat\." src/core/ --glob '!adapters/**'  # → 零匹配
ruff check src/core/ --select TID251  # → 零错误
```

**风险点**：re-export 桥接残留未清理干净
**依赖**：T2.1, T2.2, T2.3, T2.4
**影响文件**：0 个（纯验证任务）
**派发建议**：Codex（纯验证 + ruff 检查）

---

## 3. 批次3：P1 napcat_* 入站化

**目标**：将通知分类从适配器层拉取模式改为入站点推送模式，消除核心层所有 `napcat_` 前缀字段名引用。

**风险等级**：中（涉及 bot.py 入站处理流程改造和 NapCatNoticeClassifier 行为变更）
**回滚策略**：每步骤独立 git commit，NapCatNoticeClassifier 保留兼容回退

### 3.1 映射常量迁移到 notice_type_mapping.py

- [ ] 在 `src/chat/message_receive/` 下新建 `notice_type_mapping.py`，将 `_NAPCAT_*_SUBTYPES` 常量从 `src/core/adapters/notice_classifier.py` 迁移为统一的映射字典：
  ```python
  """NapCat 通知子类型 → NoticeKind 映射常量。

  仅由 bot.py 入站分类使用，核心层不引用此文件。
  """
  from src.core.types import NoticeKind

  NAPCAT_NOTICE_KIND_MAP: dict[str, NoticeKind] = {
      # INPUT_STATUS（最高优先级）
      "input_status": NoticeKind.INPUT_STATUS,
      # AMBIENT
      "group_ban": NoticeKind.AMBIENT,
      "group_increase": NoticeKind.AMBIENT,
      "group_decrease": NoticeKind.AMBIENT,
      "group_name": NoticeKind.AMBIENT,
      "group_upload": NoticeKind.AMBIENT,
      "group_msg_emoji_like": NoticeKind.AMBIENT,
      # INTERACTION
      "poke": NoticeKind.INTERACTION,
      "group_poke": NoticeKind.INTERACTION,
      "friend_add": NoticeKind.INTERACTION,
      "group_admin": NoticeKind.INTERACTION,
  }
  ```
- [ ] 确认映射常量与 `NapCatNoticeClassifier` 现有三级常量逻辑一致（INPUT_STATUS 优先于 AMBIENT，input_status 同时出现在两个集合中，映射字典中 INPUT_STATUS 优先匹配）

**验收标准**：
```bash
python -c "from src.chat.message_receive.notice_type_mapping import NAPCAT_NOTICE_KIND_MAP; print(len(NAPCAT_NOTICE_KIND_MAP))"  # → 11
```

**风险点**：映射常量遗漏通知类型 → UNKNOWN 兜底，不崩溃
**依赖**：无
**影响文件**：1 个（新建 notice_type_mapping.py）
**派发建议**：Codex（新建文件 + 常量迁移，简单快速）

### 3.2 bot.py 入站分类实现

- [ ] 在 `src/chat/message_receive/bot.py` 的通知消息处理流程中，增加 NoticeKind 映射逻辑：
  - 在 `handle_notice_message()` 或 `receive_message()` 中，对通知消息读取 `napcat_notice_sub_type` 并映射为 `NoticeKind`
  - 映射结果写入 SessionMessage 的 `notice_kind` 属性
- [ ] 确认 SessionMessage 是否已有 `notice_kind` 属性：
  - 如果没有，需在 SessionMessage 类中新增 `notice_kind: NoticeKind = NoticeKind.UNKNOWN` 属性
  - 或在 CoreMessage 构造时从 additional_config 中提取
- [ ] 确认 CoreMessage 构造时能正确读取 SessionMessage 的 `notice_kind` 字段

**验收标准**：
```bash
# bot.py 中存在 NAPCAT_NOTICE_KIND_MAP 引用
rg "NAPCAT_NOTICE_KIND_MAP" src/chat/message_receive/bot.py  # → 有匹配
# bot.py 中存在 NoticeKind 导入
rg "from src.core.types import NoticeKind" src/chat/message_receive/bot.py  # → 有匹配
```

**风险点**：SessionMessage 与 CoreMessage 的 notice_kind 字段传递链路需完整验证；入站分类遗漏的通知类型按 UNKNOWN 处理
**依赖**：T3.1（映射常量在 notice_type_mapping.py 中）
**影响文件**：2-3 个（bot.py, message.py 可能需新增字段, core/types.py 的 CoreMessage 构造逻辑）
**派发建议**：CC（涉及消息处理流程改造，需理解 SessionMessage→CoreMessage 转换链路）

### 3.3 NapCatNoticeClassifier 改造

- [ ] 修改 `src/core/adapters/notice_classifier.py` 的 `classify()` 方法，优先使用 `CoreMessage.notice_kind`：
  ```python
  def classify(self, message: Any) -> NoticeKind:
      # 优先使用 CoreMessage.notice_kind（入站分类已完成）
      if hasattr(message, "notice_kind") and message.notice_kind != NoticeKind.UNKNOWN:
          return message.notice_kind
      # 兼容回退：从 additional_config 中读取（过渡期，SSD-5 移除）
      sub_type = self._extract_napcat_sub_type(message)
      if not sub_type:
          return NoticeKind.UNKNOWN
      # ... 现有映射逻辑保留
  ```
- [ ] 删除 `_NAPCAT_*_SUBTYPES` 常量（已迁移到 `notice_type_mapping.py`）
- [ ] 保留 `_extract_napcat_sub_type()` 方法作为兼容回退，标注 `# TODO: SSD-5 移除`
- [ ] 更新类文档字符串，说明分类逻辑已从"拉取"改为"优先使用入站分类结果"

**验收标准**：
```bash
# NapCatNoticeClassifier 优先使用 notice_kind
rg "notice_kind" src/core/adapters/notice_classifier.py  # → 有匹配
# 兼容回退标注 TODO
rg "TODO.*SSD-5" src/core/adapters/notice_classifier.py  # → 有匹配
# _NAPCAT_*_SUBTYPES 常量已删除
rg "_NAPCAT_" src/core/adapters/notice_classifier.py  # → 零匹配
```

**风险点**：兼容回退期间，如果 bot.py 入站分类未生效，仍能通过回退路径正确分类
**依赖**：T3.1（常量已迁移）、T3.2（bot.py 入站分类已实现）
**影响文件**：1 个（notice_classifier.py）
**派发建议**：CC（适配器行为变更，需理解分类优先级逻辑）

### 3.4 ruff banned-api 守卫新增

- [ ] 在 `pyproject.toml` 的 `[tool.ruff.lint.flake8-tidy-imports.banned-api]` 中新增：
  ```toml
  "napcat_notice_sub_type" = {msg = "禁止在核心层直接使用 napcat_ 字段，应通过 NoticeKind 枚举"}
  "napcat_notice_type" = {msg = "禁止在核心层直接使用 napcat_ 字段，应通过 NoticeKind 枚举"}
  "napcat_notice_payload" = {msg = "禁止在核心层直接使用 napcat_ 字段，应通过 NoticeKind 枚举"}
  ```
- [ ] 确认限制范围为 `src/core/` 目录（不含 `src/core/adapters/`），适配器层保留豁免（通过 `per-file-ignores`）
- [ ] 执行 ruff 检查确认新守卫生效：
  ```bash
  ruff check src/core/ --select TID251  # → 零错误（adapters/ 豁免生效）
  ```

**验收标准**：
```bash
grep "napcat_notice_sub_type" pyproject.toml  # → 有匹配（banned-api 配置）
ruff check src/core/ --select TID251  # → 零错误
```

**风险点**：banned-api 规则可能误报 chat 层合法使用 → 限制范围仅 src/core/ 不含 adapters/
**依赖**：T3.3（NapCatNoticeClassifier 改造完成后再加守卫，避免过渡期误报）
**影响文件**：1 个（pyproject.toml）
**派发建议**：Codex（ruff 配置修改，简单快速）

### 3.5 核心层零 napcat_ 引用验证

- [ ] 执行全量验证：核心层（不含 adapters/）零 `napcat_` 引用
  ```bash
  rg "napcat_" src/core/ --glob '!adapters/**'
  # 预期：零匹配
  ```
- [ ] 确认适配器层 napcat_ 引用仅剩兼容回退：
  ```bash
  rg "napcat_" src/core/adapters/notice_classifier.py
  # 预期：仅 _extract_napcat_sub_type 方法内的兼容回退 + TODO 标注
  ```
- [ ] 确认 bot.py 入站分类在实际运行中生效（容器启动后发送通知消息，验证 notice_kind 正确填充）

**验收标准**：
```bash
rg "napcat_" src/core/ --glob '!adapters/**'  # → 零匹配
rg "napcat_" src/core/adapters/notice_classifier.py  # → 仅兼容回退 + TODO
```

**风险点**：核心层残留 napcat_ 引用未清理干净
**依赖**：T3.1, T3.2, T3.3, T3.4
**影响文件**：0 个（纯验证任务）
**派发建议**：Codex（纯验证 + grep 检查）

---

## 4. 批次4：P2 enqueue 协议瘦身

**目标**：移除 chat_loop_adapter 中多余的 enqueue_proactive_task 代理方法，新增 ruff 守卫限制非插件调用方，强化文档字符串约束。

**风险等级**：低（代理层已无实际调用方；Protocol 签名不变，不影响插件兼容性）
**回滚策略**：git revert 单任务 commit

### 4.1 chat_loop_adapter 代理移除评估与实施

- [ ] 评估 `src/maisaka/agent_autonomy/bridge/chat_loop_adapter.py:90-99` 的 `enqueue_proactive_task` 代理方法调用方：
  - plugin_runtime 已绕过代理层，直接通过 heartflow_manager 获取 runtime 调用
  - 管家/提醒已改用 ThinkingOrgan 直接触发
  - 代理层文档说"让管家/提醒等核心模块触发 Planner"，但已无实际用途
- [ ] 删除 `chat_loop_adapter.py` 中的 `enqueue_proactive_task` 代理方法（L90-104）
- [ ] 确认删除后无 ImportError 或调用链断裂

**验收标准**：
```bash
rg "enqueue_proactive" src/maisaka/agent_autonomy/bridge/chat_loop_adapter.py  # → 零匹配
```

**风险点**：可能有未发现的调用方依赖代理层 → 评估时需全局搜索
**依赖**：无
**影响文件**：1 个（chat_loop_adapter.py）
**派发建议**：Codex（简单方法删除 + 验证）

### 4.2 ruff 守卫限制非插件调用方

- [ ] 在 `pyproject.toml` 的 ruff 配置中新增约束，限制 `enqueue_proactive_task` 仅在合法位置调用：
  - 合法位置：`src/plugin_runtime/`、`src/maisaka/runtime.py`（实现方）、`src/core/protocols.py`（定义方）
  - 禁止位置：`src/maisaka/agent_autonomy/`（不含 `bridge/`）
- [ ] 具体方案：在 `per-file-ignores` 或 banned-api 中配置，确保 `src/maisaka/agent_autonomy/` 目录下零 `enqueue_proactive` 调用
- [ ] 执行 ruff 检查确认守卫生效

**验收标准**：
```bash
rg "enqueue_proactive" src/maisaka/agent_autonomy/ --glob '!bridge/**'  # → 零匹配
ruff check src/maisaka/agent_autonomy/ --select TID251  # → 零错误
```

**风险点**：ruff 规则可能误报合法调用方 → 需精确配置豁免
**依赖**：T4.1（代理方法已移除后再加守卫）
**影响文件**：1 个（pyproject.toml）
**派发建议**：Codex（ruff 配置修改）

### 4.3 enqueue_proactive_task 文档字符串强化

- [ ] 确认 `src/core/protocols.py` 中 `ChatRuntime.enqueue_proactive_task` 的文档字符串包含"仅用于插件主动对话，禁止用于多智能体插话"约束
- [ ] 如果文档字符串不够明确，补充以下内容：
  - 用途限制说明
  - 合法调用方列表（plugin_runtime）
  - 禁止用途说明（多智能体插话应通过 ThinkingOrgan 直接触发）
  - 违反约束的后果（CI 不通过）
- [ ] 确认 `src/maisaka/runtime.py:648` 的 `enqueue_proactive_task` 实现方文档字符串同步更新

**验收标准**：
```bash
rg "仅用于插件主动对话" src/core/protocols.py  # → 有匹配
rg "仅用于插件主动对话" src/maisaka/runtime.py  # → 有匹配
```

**风险点**：无
**依赖**：T4.2（守卫配置完成后再强化文档，形成三重约束）
**影响文件**：2 个（protocols.py, runtime.py）
**派发建议**：Codex（文档字符串更新，简单快速）

---

## 5. 批次5：P3 文档标注 + 同步

**目标**：更新 AGENTS.md 核心禁止项状态、存量债务表、mem_core_gap 差距标注，同步 .mdc 规则文件，确保文档与代码实际状态一致。

**风险等级**：极低（纯文档更新，零代码变更）
**回滚策略**：git revert 单任务 commit

### 5.1 AGENTS.md 核心禁止项状态更新

- [ ] 更新核心禁止项 #4 状态为 `✅ 已消除（入站分类 + NapCatNoticeClassifier 改造 + ruff banned-api 守卫，SSD-4 完成）`
- [ ] 更新核心禁止项 #7 状态为 `⚠️ 已限制（文档约束 + chat_loop_adapter 代理移除 + ruff 守卫，SSD-4 瘦身）`
- [ ] 确认 #2/#3 状态已在 T1.1 中更新为 `✅ 已消除`（如未更新则在此补齐）
- [ ] 确认所有 8 条核心禁止项状态与代码实际状态一致：
  - #1 ✅、#2 ✅、#3 ✅、#4 ✅、#5 ✅、#6 ✅、#7 ⚠️ 已限制、#8 ✅

**验收标准**：
```bash
grep "✅ 已消除.*SSD-4" AGENTS.md  # → #2, #3, #4 均有匹配
grep "⚠️ 已限制.*SSD-4" AGENTS.md  # → #7 有匹配
```

**风险点**：状态更新与代码实际不一致 → 需在批次1-4全部验证通过后再更新
**依赖**：T1.1, T3.1-T3.5, T4.1-T4.3
**影响文件**：1 个（AGENTS.md）
**派发建议**：Codex（文档更新，简单快速）

### 5.2 AGENTS.md 存量债务表更新

- [ ] 新增/更新以下债务条目：
  - `core 层 re-export 桥接` → `✅ 已消除（SessionMessage/identity/message_utils 物理迁移 + HeartflowRuntimeRegistry 构造注入，SSD-4 完成）`
  - `napcat_* 字段分类在适配器层` → `✅ 已消除（入站分类 + NapCatNoticeClassifier 改造，SSD-4 完成）`
  - `MemoryField._async_write_started 竞态` → `✅ 已修复（两阶段初始化，SSD-4 完成）`
  - `host_service 私有属性访问` → `⚠️ 已知债务（31+80处，排期待定）`
  - `A_memorix bare except` → `⚠️ 已知债务（327处，逐个审查需单独排期）`

**验收标准**：
```bash
grep "re-export 桥接.*SSD-4 完成" AGENTS.md  # → 有匹配
grep "入站分类.*SSD-4 完成" AGENTS.md  # → 有匹配
grep "两阶段初始化.*SSD-4 完成" AGENTS.md  # → 有匹配
```

**风险点**：无
**依赖**：T1.2, T2.1-T2.5, T3.1-T3.5
**影响文件**：1 个（AGENTS.md）
**派发建议**：Codex（文档更新）

### 5.3 mem_core_gap 8 项差距标注

- [ ] 在 AGENTS.md 的 mem_core_gap 未覆盖差距部分，更新 8 项差距标注：

| 差距 | 标注文本 |
|------|---------|
| G16 | `⚠️ 已知债务：host_service 31处 + admin 80+处访问 kernel._* 私有属性，修复成本高影响低，排期待定` |
| G18 | `⚠️ 部分完成：agent_id 参数已传递，深度联动（记忆性格影响检索权重）待后续` |
| G19 | `⚠️ 待后续：管家三层过滤第二层无法利用记忆关系数据，需新增关系查询接口` |
| G21 | `⚠️ 待后续：weave_narrative 已暴露在 MemoryServicePort，智能体思考时引用叙事上下文待集成` |
| G22 | `✅ SSD-4 修复：MemoryField 两阶段初始化根治 AsyncWriteQueue 延迟启动竞态` |
| G23 | `⚠️ 已有 None 保护：ModelConfigPort 注入时序无编译时检查，待后续` |
| G24 | `⚠️ 待后续：智能体记忆性格注册窗口期，需核心调度时序保证` |
| G28 | `⚠️ 已知债务：327处 bare except，逐个审查需单独排期` |

**验收标准**：
```bash
grep "G16.*已知债务" AGENTS.md  # → 有匹配
grep "G22.*SSD-4 修复" AGENTS.md  # → 有匹配
grep "G28.*已知债务" AGENTS.md  # → 有匹配
```

**风险点**：无
**依赖**：T1.2（G22 依赖竞态修复完成）
**影响文件**：1 个（AGENTS.md）
**派发建议**：Codex（文档更新）

### 5.4 .mdc 规则文件同步

- [ ] 同步更新 `.codeartsdoer/rule/MaiBot智能体自主性架构.mdc` 中对应表格和状态：
  - 核心禁止项 #2/#3/#4/#7 状态与 AGENTS.md 一致
  - 存量债务表与 AGENTS.md 一致
  - 核心接口层表格行数与 `src/core/protocols.py` 中 Protocol 数量一致
- [ ] 执行同步检查（每次 PR 必须自检）：
  - .mdc 文件"核心接口层"表格行数 == `src/core/protocols.py` 中 Protocol 数量
  - .mdc 文件"核心禁止项"状态 == AGENTS.md"核心禁止项"状态
  - .mdc 文件"存量债务表"状态 == AGENTS.md 相关描述

**验收标准**：
```bash
grep "✅ 已消除.*SSD-4" .codeartsdoer/rule/MaiBot智能体自主性架构.mdc  # → #2, #3, #4 均有匹配
grep "⚠️ 已限制.*SSD-4" .codeartsdoer/rule/MaiBot智能体自主性架构.mdc  # → #7 有匹配
```

**风险点**：.mdc 与 AGENTS.md 状态不一致 → 以 AGENTS.md 为准修正 .mdc
**依赖**：T5.1, T5.2, T5.3
**影响文件**：1 个（.mdc 规则文件）
**派发建议**：Codex（文档同步更新）

---

## 6. 全量集成验证

**目标**：确认所有债务消除后系统功能无回归。

**风险等级**：低（验证任务，不修改代码）
**前置条件**：批次1-5 全部完成

- [ ] 启动容器，确认所有功能无回归：
  - 消息收发正常
  - 通知消息分类正确（poke→INTERACTION, input_status→INPUT_STATUS, group_ban→AMBIENT）
  - 会话创建/持久化/恢复正常
  - 记忆系统 observe() 正常入队（无 AttributeError）
  - 插件主动对话正常触发
  - WebUI 聊天流管理正常
- [ ] CI 全量检查通过（ruff + mypy + pytest）
- [ ] 执行全量 grep 验证：
  ```bash
  rg "chat_manager\._agent_router" src/  # → 零匹配
  rg "BotChatSession" src/core/ --glob '!adapters/**'  # → 零匹配
  rg "BotChatSession" src/maisaka/  # → 零匹配
  rg "from src\.chat\." src/core/ --glob '!adapters/**'  # → 零匹配
  rg "napcat_" src/core/ --glob '!adapters/**'  # → 零匹配
  rg "getattr.*_async_write_started" src/A_memorix/  # → 零匹配
  rg "enqueue_proactive" src/maisaka/agent_autonomy/ --glob '!bridge/**'  # → 零匹配
  ruff check src/ --select TID251  # → 零错误（豁免生效）
  ```

**派发建议**：CC（全量集成验证需理解系统行为）