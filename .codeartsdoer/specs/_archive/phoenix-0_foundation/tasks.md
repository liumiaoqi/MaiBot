# Phoenix-0：基础准备 — 编码任务

## 1. 定义 .proto Schema

**执行者建议**：CA（首次设计，需要精确的 gRPC 接口设计）

### 1.1 创建 proto 目录和 common.proto

- [ ] 创建 `src/plugin_runtime_v2/proto/` 目录，放置 `__init__.py`（空文件）
- [ ] 编写 `src/plugin_runtime_v2/proto/common.proto`，定义双向流消息封装：
  - `RunnerMessage`（oneof: HelloPayload / EventPayload / HeartbeatResponse）
  - `HostMessage`（oneof: HelloResponse / HeartbeatRequest / ShutdownRequest）
  - 包名 `maibot.plugin.v2`，proto3 语法
  - 每个 message 和字段必须有中文注释
- [ ] 验收：`protoc --python_out=. common.proto` 编译通过，无报错

### 1.2 编写 plugin_host.proto

- [ ] 编写 `src/plugin_runtime_v2/proto/plugin_host.proto`，定义 `service PluginHost`：
  - `rpc Connect(stream RunnerMessage) returns (stream HostMessage)` — 双向流连接
  - `rpc RegisterComponents(RegisterComponentsRequest) returns (RegisterComponentsResponse)` — 组件注册
- [ ] 定义握手消息：`HelloPayload`（runner_id, sdk_version, session_token, scopes[]）、`HelloResponse`（accepted, host_version, reason, rejected_scopes[]）
- [ ] 定义组件声明消息：`ToolDeclaration`（name, description, parameters_schema, output_schema）、`EventDeclaration`（name, description, event_schema）、`RegisterComponentsRequest`（plugin_id, plugin_version, tools[], events[]）、`RegisterComponentsResponse`（accepted, reasons[]）
- [ ] 定义心跳消息：`HeartbeatRequest`（timestamp_ms）、`HeartbeatResponse`（timestamp_ms）
- [ ] 定义关停消息：`ShutdownRequest`（reason, drain_timeout_ms）
- [ ] 每个 message 和字段必须有中文注释
- [ ] 验收：`protoc --python_out=. plugin_host.proto` 编译通过；审查确认不存在与 `src/core/types.py` 重复的 message 定义（如 CoreMessage、SessionInfo）

### 1.3 编写 plugin_runner.proto

- [ ] 编写 `src/plugin_runtime_v2/proto/plugin_runner.proto`，定义 `service PluginRunner`：
  - `rpc InvokeTool(InvokeToolRequest) returns (InvokeToolResponse)` — Tool 调用
- [ ] 定义 Tool 调用消息：`InvokeToolRequest`（tool_name, args, timeout_ms）、`InvokeToolResponse`（success, result, error）
- [ ] 定义 Event 推送消息：`EventPayload`（event_name, payload）、`EventAck`（received）
- [ ] 每个 message 和字段必须有中文注释
- [ ] 验收：`protoc --python_out=. plugin_runner.proto` 编译通过；InvokeToolRequest.args 使用 JSON 字符串传递（非 protobuf 结构）

### 1.4 生成 Python 代码并验证

- [ ] 使用 `grpcio-tools` 对 3 个 .proto 文件执行编译，生成 `_pb2.py` 和 `_pb2_grpc.py` 文件到 `src/plugin_runtime_v2/proto/` 目录
- [ ] 验证生成的 Python 代码可正常 import：`from src.plugin_runtime_v2.proto import common_pb2, plugin_host_pb2, plugin_runner_pb2`
- [ ] 验证 `service PluginHost` 和 `service PluginRunner` 的 gRPC stub 类已生成
- [ ] 验收：Python REPL 中可成功创建 PluginHostStub 和 PluginRunnerStub

## 2. 创建 v2 目录骨架

**执行者建议**：Codex（机械执行，定义清晰的分项任务）

### 2.1 创建目录结构和占位文件

- [ ] 创建 `src/plugin_runtime_v2/` 目录及以下子目录，每个含 `__init__.py`：
  - `src/plugin_runtime_v2/__init__.py` — 包入口，导出公共 API（当前为空）
  - `src/plugin_runtime_v2/proto/__init__.py` — protobuf 生成代码的导出（1.4 完成后补充）
  - `src/plugin_runtime_v2/host/__init__.py` — gRPC Host 端逻辑占位（Phoenix-1 实现）
  - `src/plugin_runtime_v2/runner/__init__.py` — gRPC Runner 端逻辑占位（Phoenix-1 实现）
  - `src/plugin_runtime_v2/scope/__init__.py` — Scope 公共 API 占位（Phoenix-3 实现）
  - `src/plugin_runtime_v2/mcp/__init__.py` — MCP Tool/Event 组件模型占位（Phoenix-2 实现）
  - `src/plugin_runtime_v2/sdk/__init__.py` — SDK v4 接口定义占位（Phoenix-2 实现）
- [ ] 每个 `__init__.py` 包含模块级 docstring，说明该子目录的职责和实现阶段
- [ ] 验收：7 个子目录均存在且含 `__init__.py`；`src/plugin_runtime_v2/` 下无其他文件

### 2.2 验证 v1/v2 隔离

- [ ] 在 `src/plugin_runtime_v2/` 下执行 `grep -r "from src.plugin_runtime" .`，确认零匹配
- [ ] 在 `src/plugin_runtime_v2/` 下执行 `grep -r "import src.plugin_runtime" .`，确认零匹配
- [ ] 验收：v2 目录无任何对 v1 的交叉引用

## 3. 实现 Scope 词汇表

**执行者建议**：Codex（定义清晰的分项任务，机械执行）

### 3.1 编写 Scope 词汇表数据定义

- [ ] 创建 `src/plugin_runtime_v2/scope/vocabulary.py`，定义 `ScopeEntry` 数据类：
  - 字段：scope（str）、description（str）、replaces（str | None）、risk_level（Literal["low", "medium", "high"]）、approval_required（bool）
- [ ] 定义 `ScopeVocabulary` 类：
  - 类属性 `version: str = "1.0.0"`
  - 类属性 `scopes: frozenset[ScopeEntry]` — 包含全部 ~45 个 scope 条目
  - 方法 `validate(scope_str: str) -> bool` — 校验 scope 是否在词汇表中，O(1) 查找
  - 方法 `lookup(scope_str: str) -> ScopeEntry` — 查找 scope 条目，不存在抛出 KeyError
  - 方法 `map_capability(cap: str) -> list[str]` — 将旧 capability 映射为新 scope 列表
- [ ] 验收：`ScopeVocabulary.validate("message:send:text")` 返回 True；`ScopeVocabulary.validate("invalid:scope")` 返回 False；`ScopeVocabulary.map_capability("send.text")` 返回 `["message:send:text"]`

### 3.2 填写完整 Scope 条目

- [ ] 按 design.md 2.3.2.3 的完整清单，填写 11 个资源域的全部 scope 条目：
  - message 资源域：9 个 scope
  - database 资源域：8 个 scope
  - session 资源域：3 个 scope
  - memory 资源域：3 个 scope
  - config 资源域：3 个 scope
  - agent 资源域：3 个 scope
  - person 资源域：2 个 scope
  - llm 资源域：5 个 scope
  - emoji 资源域：5 个 scope
  - plugin 资源域：5 个 scope
  - system 资源域：6 个 scope
- [ ] 验收：`len(ScopeVocabulary.scopes)` 约为 52；每个 scope 均为三段式格式，以冒号分隔

### 3.3 填写 capabilities→scope 映射表

- [ ] 按 design.md 2.3.2.5 的完整映射表，在 `ScopeVocabulary` 中实现 `_CAPABILITY_MAP: dict[str, list[str]]`：
  - 覆盖全部 76 个 capabilities（send.*、db.*、chat.*、maisaka.*、agent.*、person.*、emoji.*、config.*、llm.*、frequency.*、tool.*、api.*、component.*、knowledge.*、statistics.*、render.*）
  - `map_capability()` 方法基于此映射表查询
- [ ] 验收：逐一核对 `registry.py` 中 76 个 capabilities，每个都有 `map_capability()` 的等价映射；无权限降级（risk_level 不低于原 capability 的隐含风险）

### 3.4 验证 Scope 词汇表约束

- [ ] 确认不存在通配 scope（`*:*:*`、`database:*:*` 等）
- [ ] 确认每个 scope 的 risk_level 为 low/medium/high 之一
- [ ] 确认 approval_required 与 risk_level 一致（low→false, medium/high→true）
- [ ] 确认 scope_version 为 `"1.0.0"`
- [ ] 验收：编写简单验证脚本，遍历所有 ScopeEntry 检查上述约束，全部通过

## 4. 编写 SDK v4 接口设计文档

**执行者建议**：CC（复杂编码，需要理解 ThinkingOrgan 工具循环和 ToolProvider 对接）

### 4.1 编写 MaiBotPlugin 基类

- [ ] 在 `src/plugin_runtime_v2/sdk/` 下创建 `plugin.py`，实现 `MaiBotPlugin` 基类：
  - 类属性：`plugin_id: str`、`plugin_version: str = "1.0.0"`、`scopes: list[str] = []`
  - 实例属性：`ctx: PluginContext`（由 Runner 注入）
  - 生命周期方法：`async on_load()`、`async on_unload()`、`async on_config_update(config: dict[str, Any])`
  - 类级 docstring 说明用法和约束
- [ ] 验收：`MaiBotPlugin` 可被正常继承；子类可覆盖 on_load/on_unload/on_config_update

### 4.2 编写 @Tool 装饰器

- [ ] 在 `src/plugin_runtime_v2/sdk/` 下创建 `decorators.py`，实现 `@Tool` 装饰器：
  - 参数：name（str）、description（str）、parameters_schema（dict | None）、output_schema（dict | None）
  - 装饰器将被装饰方法标记为 MCP Tool，在方法上设置 `_mcp_tool` 属性存储声明信息
  - 被装饰方法签名约束：`async def method(self, args: dict[str, Any]) -> dict[str, Any]`
- [ ] 验收：被 @Tool 装饰的方法可通过 `method._mcp_tool` 获取 ToolDeclaration 信息

### 4.3 编写 @Event 装饰器

- [ ] 在 `src/plugin_runtime_v2/sdk/decorators.py` 中实现 `@Event` 装饰器：
  - 参数：name（str）、description（str）、event_schema（dict | None）
  - 装饰器将被装饰方法标记为 MCP Event，在方法上设置 `_mcp_event` 属性存储声明信息
  - 被装饰方法不是处理函数，而是事件声明
- [ ] 验收：被 @Event 装饰的方法可通过 `method._mcp_event` 获取 EventDeclaration 信息

### 4.4 编写 @Command 装饰器

- [ ] 在 `src/plugin_runtime_v2/sdk/decorators.py` 中实现 `@Command` 装饰器：
  - 参数：name（str）、pattern（str）、description（str）、parameters_schema（dict | None）
  - 底层实现为带 pattern 约束的 Tool 语法糖，在 `_mcp_tool` 属性中额外存储 pattern
- [ ] 验收：被 @Command 装饰的方法可通过 `method._mcp_tool` 获取 ToolDeclaration，且 `method._mcp_tool.pattern == pattern`

### 4.5 编写 @HomeCard 装饰器

- [ ] 在 `src/plugin_runtime_v2/sdk/decorators.py` 中实现 `@HomeCard` 装饰器：
  - 参数：name（str）、title（str）、description（str）、width（str = "medium"）
  - 底层实现为推送卡片数据的 Event 语法糖，在 `_mcp_event` 属性中额外存储卡片元数据
- [ ] 验收：被 @HomeCard 装饰的方法可通过 `method._mcp_event` 获取 EventDeclaration，且包含卡片元数据

### 4.6 编写 PluginContext 上下文对象

- [ ] 在 `src/plugin_runtime_v2/sdk/` 下创建 `context.py`，实现 `PluginContext` 类：
  - 属性：`send`（SendContext）、`storage`（StorageContext）、`logger`（LoggerContext）
  - 方法：`emit_event(name, payload)`、`emit_card(name, data)`
- [ ] 实现 `SendContext` 类：
  - 方法：`text(session_id, text)`、`image(session_id, image_base64)`、`emoji(session_id, emoji_base64)`、`hybrid(session_id, segments)`
  - 每个方法调用前校验 scope，未授权抛出 `ScopeDeniedError`
- [ ] 实现 `StorageContext` 类：
  - 方法：`get(key, default)`、`set(key, value)`、`delete(key)`
  - 需要 `database:read:self` / `database:write:self` scope
- [ ] 实现 `LoggerContext` 类：
  - 方法：`debug(msg)`、`info(msg)`、`warning(msg)`、`error(msg)`
  - 无需 scope
- [ ] 验收：PluginContext 的所有子对象方法签名与 design.md 2.2.2.9 一致；所有方法使用 `session_id` 而非 `stream_id`

### 4.7 编写 SDK 公共导出

- [ ] 在 `src/plugin_runtime_v2/sdk/__init__.py` 中导出公共 API：
  - `MaiBotPlugin`、`Tool`、`Event`、`Command`、`HomeCard`
  - `PluginContext`、`SendContext`、`StorageContext`、`LoggerContext`
  - `ScopeDeniedError`
- [ ] 验收：`from src.plugin_runtime_v2.sdk import MaiBotPlugin, Tool, Event, Command, HomeCard` 成功

### 4.8 验证 SDK v4 禁止项

- [ ] 在 `src/plugin_runtime_v2/sdk/` 下 grep `capabilities`，确认零匹配（注释中的说明除外）
- [ ] 在 `src/plugin_runtime_v2/sdk/` 下 grep `stream_id`，确认零匹配
- [ ] 验收：SDK v4 中不存在 capabilities 和 stream_id 概念

## 5. 定义 Manifest v3 格式

**执行者建议**：Codex（数据格式定义，机械执行）

### 5.1 编写 Manifest v3 模型和示例

- [ ] 在 `src/plugin_runtime_v2/sdk/` 下创建 `manifest.py`，定义 `ManifestV3` Pydantic 模型：
  - 字段：manifest_version（Literal[3]）、id（str, 格式 `组织名.插件名`）、version（str）、name（str）、description（str）、author（AuthorInfo）、license（str）、host_application（HostAppRequirement）、sdk（SDKRequirement）、scopes（list[str], 至少1项）、dependencies（list[str]）、i18n（I18nConfig | None）
  - 嵌套模型：AuthorInfo（name, url）、HostAppRequirement（min_version, max_version）、SDKRequirement（min_version, max_version）、I18nConfig（default_locale, locales[]）
- [ ] 编写示例 manifest JSON 文件，与 design.md 2.3.2.4 一致
- [ ] 验收：`ManifestV3.model_validate_json(sample_json)` 成功；manifest_version=2 的 JSON 校验失败

## 6. 集成验证与文档

**执行者建议**：CC（需要理解全局架构，验证各模块对接）

### 6.1 验证 .proto 与核心 ToolSpec 的对齐

- [ ] 验证 `ToolDeclaration`（proto）与 `ToolSpec`（`src/core/tooling.py`）的字段对齐：
  - name ↔ name
  - description ↔ description
  - parameters_schema ↔ parameters_schema
  - output_schema ↔ output_schema
- [ ] 编写对齐说明文档，记录字段映射关系和差异（如 proto 用 string 传 JSON Schema，ToolSpec 用 dict）
- [ ] 验收：对齐说明文档记录了所有字段映射，无遗漏

### 6.2 验证 Scope 词汇表覆盖度

- [ ] 对比 `src/plugin_runtime/capabilities/registry.py` 中 76 个 capabilities，逐一确认每个都有 `ScopeVocabulary.map_capability()` 的映射
- [ ] 对比 `registry.py` 中的 capabilities 列表与 design.md 2.3.2.5 映射表，确认无遗漏
- [ ] 验收：覆盖度 100%，无 capability 遗漏

### 6.3 验证 v2 目录完整性

- [ ] 检查 `src/plugin_runtime_v2/` 目录结构，确认与 design.md 2.3.2.1 一致
- [ ] 确认每个 `__init__.py` 包含模块级 docstring
- [ ] 确认 v2 目录无对 v1 的交叉引用
- [ ] 验收：目录结构、docstring、隔离性全部通过

### 6.4 编写 SDK v4 使用示例

- [ ] 编写一个完整的 SDK v4 插件示例（伪代码级别），展示：
  - 继承 MaiBotPlugin
  - 使用 @Tool 声明工具
  - 使用 @Event 声明事件
  - 使用 @Command 声明命令
  - 使用 @HomeCard 声明卡片
  - 在 scopes 中声明权限
  - 通过 self.ctx 调用宿主能力
- [ ] 验收：示例代码可被 Python 解析器解析（语法正确），且覆盖所有 SDK v4 API

### 6.5 最终审查

- [ ] 审查 .proto 文件：proto3 语法、中文注释完整、无核心类型重复定义
- [ ] 审查 Scope 词汇表：三段式格式、无通配 scope、version=1.0.0、覆盖全部 capabilities
- [ ] 审查 SDK v4 接口：无 capabilities/stream_id 术语、生命周期钩子完整、PluginContext 子对象完整
- [ ] 审查 v2 目录：7 个子目录、零交叉引用
- [ ] 审查 Manifest v3：manifest_version=3、scopes 替代 capabilities_required
- [ ] 验收：所有审查项通过，记录审查结果