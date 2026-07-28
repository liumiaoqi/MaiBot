# MessagePort 全面采用 + send_service 绕过消除 — 编码任务

## 1. 审计 send_service 遗留函数的外部调用者

### 1.1 逐函数审计外部调用者

- [ ] 对以下 7 个遗留公共函数，使用 grep 全局搜索确认无外部调用者（仅在 `src/services/send_service.py` 内部有定义和调用）：
  - `text_to_stream`
  - `text_to_stream_with_message`
  - `emoji_to_stream`
  - `emoji_to_stream_with_message`
  - `image_to_stream`
  - `custom_to_stream`
  - `custom_reply_set_to_stream`
- 验收：每个函数名的 grep 结果仅在 `src/services/send_service.py` 中出现；若发现外部调用者，先记录到待迁移列表

### 1.2 审计 send_service 内部调用链

- [ ] 确认 `text_to_stream` 调用 `text_to_stream_with_message`；确认 `emoji_to_stream` 调用 `emoji_to_stream_with_message`；确认 `image_to_stream`、`custom_to_stream`、`custom_reply_set_to_stream` 调用 `_send_to_target`（非 `_send_to_target_with_message`）；确认 `_send_to_target_with_message` 被 `SendServiceMessagePortV2.send_message()` 调用
- 验收：内部调用链关系清晰，无遗漏

## 2. 内部化遗留公共函数

### 2.1 重命名 text_to_stream 系列为模块私有

- [ ] 在 `src/services/send_service.py` 中：
  - 将 `async def text_to_stream_with_message(` 改为 `async def _text_to_stream_with_message(`
  - 将 `async def text_to_stream(` 改为 `async def _text_to_stream(`
  - 更新 `text_to_stream` 内部对 `text_to_stream_with_message` 的调用为 `_text_to_stream_with_message`
- 验收：`grep "def text_to_stream" src/services/send_service.py` 无结果（只有 `_text_to_stream`）；send_service 内部调用链不受影响

### 2.2 重命名 emoji_to_stream 系列为模块私有

- [ ] 在 `src/services/send_service.py` 中：
  - 将 `async def emoji_to_stream_with_message(` 改为 `async def _emoji_to_stream_with_message(`
  - 将 `async def emoji_to_stream(` 改为 `async def _emoji_to_stream(`
  - 更新 `emoji_to_stream` 内部对 `emoji_to_stream_with_message` 的调用为 `_emoji_to_stream_with_message`
- 验收：`grep "def emoji_to_stream" src/services/send_service.py` 无结果（只有 `_emoji_to_stream`）

### 2.3 重命名 image_to_stream 为模块私有

- [ ] 在 `src/services/send_service.py` 中：将 `async def image_to_stream(` 改为 `async def _image_to_stream(`
- 验收：`grep "def image_to_stream" src/services/send_service.py` 无结果（只有 `_image_to_stream`）

### 2.4 重命名 custom_to_stream 为模块私有

- [ ] 在 `src/services/send_service.py` 中：将 `async def custom_to_stream(` 改为 `async def _custom_to_stream(`
- 验收：`grep "def custom_to_stream" src/services/send_service.py` 无结果（只有 `_custom_to_stream`）

### 2.5 重命名 custom_reply_set_to_stream 为模块私有

- [ ] 在 `src/services/send_service.py` 中：将 `async def custom_reply_set_to_stream(` 改为 `async def _custom_reply_set_to_stream(`
- 验收：`grep "def custom_reply_set_to_stream" src/services/send_service.py` 无结果（只有 `_custom_reply_set_to_stream`）

### 2.6 更新 send_service.py 内部引用

- [ ] 在 `src/services/send_service.py` 中，搜索所有对已重命名函数的引用（如 `_build_message_sequence_from_custom_message` 的调用、`_send_to_target` 的调用等），确保内部调用链使用新的模块私有名称
- 验收：`ruff check src/services/send_service.py` 无未定义名称错误；send_service 内部调用链完整

## 3. 配置 ruff TID251 守卫（与 ruff_guard_rules 协同）

### 3.1 确认 ruff_guard_rules 已配置 TID251

- [ ] 确认 `pyproject.toml` 中已配置 `[tool.ruff.lint.flake8-tidy-imports.banned-api]` 段，包含 send_service 遗留函数的禁止导入规则；确认 `[tool.ruff.lint.per-file-ignores]` 段包含豁免文件列表
- 验收：ruff_guard_rules 的任务 1-4 已完成；`ruff check --select TID251` 可正常运行

### 3.2 更新 banned-api 为内部化后的函数名

- [ ] 在 `pyproject.toml` 的 `[tool.ruff.lint.flake8-tidy-imports.banned-api]` 中，将 send_service 遗留函数的禁止导入路径更新为内部化后的名称：
  - `"src.services.send_service._text_to_stream"` 替代 `"src.services.send_service.text_to_stream"`
  - `"src.services.send_service._text_to_stream_with_message"` 替代 `"src.services.send_service.text_to_stream_with_message"`
  - 以此类推，所有 7 个函数名加 `_` 前缀
  - 保留 `"src.services.send_service._send_to_target_with_message"` 不变（已是模块私有）
- 验收：在 `src/core/` 中临时添加 `from src.services.send_service import _text_to_stream` → ruff 报告 TID251 违规；移除临时导入后 → 无违规

**注意**：如果 ruff_guard_rules 的任务 3 尚未完成，此步骤应在其之后执行。若 ruff TID251 对模块私有成员（`_` 前缀）的 `from ... import` 检测行为不同，需验证 banned-api 是否仍能拦截。

## 4. 迁移完整性验证

### 4.1 零绕过验证（直接导入）

- [ ] 在 `src/core/` 和 `src/maisaka/` 中搜索 `from src.services.send_service import`（排除豁免文件 `message_port_registry.py`、`message_port.py`、`hook_catalog.py`、`adapters/`）→ 无匹配结果
- 验收：核心侧不存在 send_service 发送函数的直接导入

### 4.2 零绕过验证（间接导入）

- [ ] 在 `src/core/` 和 `src/maisaka/` 中搜索 `from src.services import send_service`（排除豁免文件）→ 无匹配结果
- 验收：核心侧不存在 send_service 模块的间接导入

### 4.3 功能回归验证

- [ ] 验证以下消息发送功能正常：
  - reply 工具发送多段回复（含引用）
  - send_image 工具发送图片
  - 表情系统发送表情
  - 插件运行时发送文本/图片/表情/混合/转发/命令/自定义消息
  - 管家插话
  - 提醒发送
  - 生命力主动发言
- 验收：所有消息类型发送成功率不低于内部化前

## 5. 更新项目文档

### 5.1 更新 AGENTS.md

- [ ] 在 AGENTS.md 的"回复系统迁移进展"部分，将"MessagePort 全面采用"从"待后续"移至"已完成"；在"存量债务"表中，将"send_service 绕过 MessagePort"的状态从 `⬜` 更新为 `✅`
- 验收：AGENTS.md 与实际代码状态一致

### 5.2 更新 send_service 模块文档

- [ ] 在 `src/services/send_service.py` 的模块文档字符串中，更新公共 API 说明：明确列出 `SendServiceMessagePortV2` 和 `register_send_service_hook_specs` 为仅有的公共 API；说明遗留函数已内部化，外部模块应通过 `get_message_port_v2()` 发送消息
- 验收：模块文档准确反映公共 API 表面
