# ruff 守卫规则 — 编码任务

## 1. 启用 ruff TID251 规则

### 1.1 在 pyproject.toml 中启用 flake8-tidy-imports

- [ ] 在 `pyproject.toml` 的 `[tool.ruff.lint]` 的 `select` 列表中新增 `"TID"`（flake8-tidy-imports 规则集）；同时检查是否需要 ignore 其他 TID 规则（如 TID252 相对导入限制），若项目使用相对导入则需 ignore TID252
- 验收：`ruff check --select TID` 不报配置错误；`ruff rule TID251` 输出规则说明

## 2. 配置 banned-api 规则2（核心→A_memorix 隔离）

### 2.1 在 pyproject.toml 中新增 banned-api 配置

- [ ] 在 `pyproject.toml` 中新增 `[tool.ruff.lint.flake8-tidy-imports.banned-api]` 段，添加以下禁止导入规则：
  - `"src.A_memorix.core"` = `"核心模块禁止直接导入 A_memorix 内部实现，请通过 MemoryServicePort Protocol 接口交互"`
  - `"src.A_memorix.core.runtime"` = `"核心模块禁止直接导入 A_memorix 运行时，请通过 MemoryServicePort Protocol 接口交互"`
  - `"src.A_memorix.core.runtime.sdk_memory_kernel"` = `"核心模块禁止直接导入 SDKMemoryKernel，请通过 MemoryServicePort Protocol 接口交互"`
- 验收：在 `src/core/` 中临时添加 `from src.A_memorix.core.runtime.sdk_memory_kernel import SDKMemoryKernel` 并运行 `ruff check` → 报告 TID251 违规；移除临时导入后 → 无违规

## 3. 配置 banned-api 规则3（核心/maisaka→send_service 隔离）

### 3.1 在 pyproject.toml 中新增 send_service 遗留函数的 banned-api

- [ ] 在 `[tool.ruff.lint.flake8-tidy-imports.banned-api]` 段中添加以下禁止导入规则：
  - `"src.services.send_service.text_to_stream"` = `"核心模块禁止直接调用 send_service 发送函数，请使用 get_message_port_v2().send_message()"`
  - `"src.services.send_service.text_to_stream_with_message"` = 同上消息
  - `"src.services.send_service.emoji_to_stream"` = 同上消息
  - `"src.services.send_service.emoji_to_stream_with_message"` = 同上消息
  - `"src.services.send_service.image_to_stream"` = 同上消息
  - `"src.services.send_service.custom_to_stream"` = 同上消息
  - `"src.services.send_service.custom_reply_set_to_stream"` = 同上消息
  - `"src.services.send_service._send_to_target_with_message"` = `"核心模块禁止直接调用 send_service 内部函数，请使用 get_message_port_v2().send_message()"`
- 验收：在 `src/maisaka/builtin_tool/reply.py` 中临时添加 `from src.services.send_service import text_to_stream` 并运行 `ruff check` → 报告 TID251 违规；移除临时导入后 → 无违规

## 4. 配置 per-file-ignores 豁免

### 4.1 在 pyproject.toml 中新增 per-file-ignores

- [ ] 在 `pyproject.toml` 中新增 `[tool.ruff.lint.per-file-ignores]` 段，添加以下豁免规则：
  - `"src/core/adapters/*" = ["TID251"]` — 适配器层是唯一允许导入组件具体实现的地方
  - `"src/main.py" = ["TID251"]` — 组合根允许导入 A_memorix 公共 API
  - `"src/services/memory_service.py" = ["TID251"]` — A_memorix 的公共 API 消费者
  - `"src/core/message_port_registry.py" = ["TID251"]` — MessagePortV2 注册点
  - `"src/maisaka/message_port.py" = ["TID251"]` — MessagePortV2 向后兼容重导出
  - `"src/plugin_runtime/hook_catalog.py" = ["TID251"]` — Hook 注册
  - `"src/services/send_service.py" = ["TID251"]` — send_service 自身不受守卫约束
- 验收：豁免文件中的现有导入不报 TID251 违规；非豁免文件中的违规导入正常报告

## 5. 创建 CI 验证脚本（规则1：A_memorix/core/ 隔离）

### 5.1 创建 check_import_guards.py

- [ ] 在 `scripts/check_import_guards.py` 中创建 A_memorix/core/ 导入守卫验证脚本：
  - 使用 Python `ast` 模块解析 `src/A_memorix/core/` 下所有 `.py` 文件
  - 检查每个文件的 `import` 和 `from ... import` 语句
  - 禁止导入列表：`src.services`、`src.config.config`、`src.common.database`、`src.llm_models`、`src.A_memorix.host_service`
  - 豁免导入列表：`src.common.logger`、`src.common.prompt_i18n`、`src.common.data_models`、`src.core.types`、`src.core.protocols`
  - 对每个违规导入输出：文件路径、行号、导入语句、违反的规则
  - 退出码：0（通过）或 1（有违规）
  - 支持 `--verbose` 参数显示检查详情
- 验收：运行 `python scripts/check_import_guards.py` → 退出码 0（当前零违规）；在 `src/A_memorix/core/` 中临时添加 `from src.services import llm_service` → 退出码 1，输出违规详情

### 5.2 验证脚本与现有代码的兼容性

- [ ] 确认 `check_import_guards.py` 的禁止导入列表与 `src/A_memorix/core/ports.py` 的设计意图一致（AMemorixServicePorts 注入的服务不包含在禁止列表中）；确认豁免导入列表与 spec 5.1.1 规则6 一致
- 验收：`src/A_memorix/core/ports.py` 中的导入不被误报；`src/A_memorix/core/` 中的 `from src.common.logger import get_logger` 不被误报

## 6. 全局验证

### 6.1 ruff check 全量验证

- [ ] 运行 `ruff check` 确认所有现有合法代码不报 TID251 违规；确认豁免文件中的导入正常通过；确认非豁免文件中不存在违规导入（当前零违规，应全部通过）
- 验收：`ruff check` 退出码 0；无 TID251 违规报告

### 6.2 CI 验证脚本全量验证

- [ ] 运行 `python scripts/check_import_guards.py` 确认 `src/A_memorix/core/` 零违规
- 验收：脚本退出码 0；无违规输出

### 6.3 守卫规则有效性验证

- [ ] 在 `src/A_memorix/core/` 中临时添加 `from src.services import llm_service`，运行 `python scripts/check_import_guards.py` → 报告违规；移除临时导入
- [ ] 在 `src/core/orchestrator.py` 中临时添加 `from src.A_memorix.core.runtime.sdk_memory_kernel import SDKMemoryKernel`，运行 `ruff check` → 报告 TID251 违规；移除临时导入
- [ ] 在 `src/maisaka/builtin_tool/reply.py` 中临时添加 `from src.services.send_service import text_to_stream`，运行 `ruff check` → 报告 TID251 违规；移除临时导入
- 验收：三条守卫规则均能有效拦截违规导入

### 6.4 豁免文件验证

- [ ] 确认以下文件的现有导入不报 TID251 违规：
  - `src/core/adapters/memory_service.py`（导入 `from src.services.memory_service import memory_service`）
  - `src/main.py`（导入 `from src.A_memorix.host_service import a_memorix_host_service`）
  - `src/core/message_port_registry.py`（导入 `from src.services.send_service import SendServiceMessagePortV2`）
  - `src/maisaka/message_port.py`（导入 `from src.services.send_service import SendServiceMessagePortV2`）
  - `src/plugin_runtime/hook_catalog.py`（导入 `from src.services.send_service import register_send_service_hook_specs`）
- 验收：所有豁免文件的现有导入正常通过 ruff check

## 7. 更新项目文档

### 7.1 更新 AGENTS.md

- [ ] 在 AGENTS.md 的"核心禁止项"部分，为每条禁止项添加守卫机制说明：
  - 禁止项1（核心直接导入 chat_manager）→ 标注"待守卫"（chat_manager 单例拆分后配置）
  - 禁止项5（核心绕过 MessagePort 直接调用 send_service）→ 标注"✅ ruff TID251 守卫已配置"
  - 禁止项6（核心导入 A_memorix 内部模块）→ 标注"✅ ruff TID251 守卫已配置"
- 验收：AGENTS.md 核心禁止项与实际守卫配置一致

### 7.2 更新 A_memorix MODIFICATION_POLICY.md

- [ ] 在 `src/A_memorix/MODIFICATION_POLICY.md` 的"修改约束"部分，添加 CI 验证脚本说明：A_memorix/core/ 的导入隔离由 `scripts/check_import_guards.py` 强制检查
- 验收：MODIFICATION_POLICY.md 提及 CI 验证脚本