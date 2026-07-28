# SSD-7：LLM 服务协议化 — 编码任务规划

## 迁移概览

| 批次 | 主题 | 负责人 | 任务数 |
|------|------|--------|--------|
| 1 | 基础设施（Protocol + 适配器 + 注册点 + 启动注册） | CC | 4 |
| 2 | 核心消费方迁移（自主性层 + 交互层） | Codex | 5 |
| 3 | 基础设施层-学习器迁移 | Codex | 5 |
| 4 | 基础设施层-其他迁移 | Codex | 5 |
| 5 | WebUI/插件层 + ruff 守卫 + 验证 | CC | 4 |

**消费方总计**：18 处直接导入（不含 A_memorix 4 处，本期排除）

**文件锁规则**：同一批次内文件互不重叠；跨批次文件锁在任务描述中标注。

---

## 1. 基础设施搭建（Protocol + 适配器 + 注册点 + 启动注册）

**负责人**：CC（Protocol 接口设计需首次正确，注册点模式需与 MemoryServicePort/AgentConfigProvider 一致）

**前置条件**：无

### 1.1 定义 LLMService Protocol

- [ ] 在 `src/core/protocols.py` 中新增 `LLMService` Protocol，定义 4 个异步方法签名：
  - `generate_response(task_name: str, prompt: str, options: LLMGenerationOptions | None = None, *, request_type: str = "", session_id: str = "") -> LLMResponseResult`
  - `generate_response_with_messages(task_name: str, message_factory: MessageFactory, options: LLMGenerationOptions | None = None, *, request_type: str = "", session_id: str = "") -> LLMResponseResult`
  - `generate_response_for_image(task_name: str, prompt: str, image_base64: str, image_format: str, options: LLMImageOptions | None = None, *, request_type: str = "", session_id: str = "") -> LLMResponseResult`
  - `transcribe_audio(task_name: str, voice_base64: str, *, request_type: str = "", session_id: str = "") -> LLMAudioTranscriptionResult`
  - 使用 `@runtime_checkable` 装饰器
  - 在 `TYPE_CHECKING` 块中导入 `LLMGenerationOptions`、`LLMImageOptions`、`LLMResponseResult`、`LLMAudioTranscriptionResult`、`MessageFactory`（均来自 `src/common/data_models/llm_service_data_models`）
  - **验收标准**：`isinstance(adapter_instance, LLMService)` 返回 True；方法签名与 design.md 2.2.2 完全一致；Protocol 不暴露 `_orchestrator`、`_record_cache_stats`、`embed_text` 等内部方法
  - **文件锁**：`src/core/protocols.py`

### 1.2 实现 LLMServiceAdapter + 注册点函数

- [ ] 在 `src/core/adapters/llm_service_port.py` 中实现适配器和注册点：
  - **LLMServiceAdapter 类**：
    - 构造函数无参数
    - 内部持有 `_client_cache: OrderedDict[str, LLMServiceClient]`（按 `task_name:request_type:session_id` 为键缓存客户端实例，LRU 淘汰 maxlen=64，防止 session_id 无限增长导致内存泄漏）
    - `_get_or_create_client(task_name, request_type, session_id)` 私有方法：从缓存获取或新建 `LLMServiceClient` 实例；缓存满时淘汰最久未使用的条目
    - 4 个公共方法一一委托到 `LLMServiceClient` 对应方法，每个方法内部调用 `_get_or_create_client()` 获取客户端后调用同名方法
    - `generate_response`：`client = _get_or_create_client(task_name, request_type, session_id)` → `return await client.generate_response(prompt, options, session_id=session_id)`
    - `generate_response_with_messages`：同上模式，委托 `client.generate_response_with_messages(message_factory, options, session_id=session_id)`
    - `generate_response_for_image`：同上模式，委托 `client.generate_response_for_image(prompt, image_base64, image_format, options, session_id=session_id)`
    - `transcribe_audio`：同上模式，委托 `client.transcribe_audio(voice_base64, session_id=session_id)`
  - **注册点函数**（与 `agent_config_port.py` 模式一致）：
    - `get_llm_service() -> LLMService`：未注册时抛出 `RuntimeError("LLMService 未注册，请先调用 set_llm_service()")`
    - `set_llm_service(service: LLMService) -> None`：重复注册时覆盖并记录 warning 日志
    - `reset_llm_service() -> None`：清除全局实例（仅用于测试）
  - 模块级 `_provider: LLMService | None = None` 变量
  - logger 命名空间：`core.adapters.llm_service_port`
  - **验收标准**：`LLMServiceAdapter` 满足 `LLMService` Protocol；4 个方法返回值与直接使用 `LLMServiceClient` 完全一致；注册点函数行为与 `get_agent_config_provider()`/`set_agent_config_provider()`/`reset_agent_config_provider()` 一致
  - **文件锁**：`src/core/adapters/llm_service_port.py`

### 1.3 启动流程注册 LLMService

- [ ] 在 `src/main.py` 的 `MainSystem._init_components()` 中新增启动步骤：
  - 在 `CORE_SERVICES` 阶段，`model_config_port`（order=6）之后新增 `llm_service_port`（order=7），`prompt_manager` 顺延为 order=8
  - 新增 `_init_llm_service_port()` 静态方法：
    ```python
    @staticmethod
    async def _init_llm_service_port() -> None:
        from src.core.adapters.llm_service_port import LLMServiceAdapter, set_llm_service
        set_llm_service(LLMServiceAdapter())
    ```
  - **验收标准**：启动后 `get_llm_service()` 可正常返回实例；`CORE_SERVICES` 阶段日志中出现 `llm_service_port` 注册成功记录
  - **文件锁**：`src/main.py`

### 1.4 pyproject.toml 适配器层豁免

- [ ] 在 `pyproject.toml` 的 `[tool.ruff.lint.per-file-ignores]` 中新增：
  - `"src/services/llm_service.py" = ["TID251"]` — 定义文件本身允许导入
  - 确认 `"src/core/adapters/*" = ["TID251"]` 和 `"src/main.py" = ["TID251"]` 已存在（无需新增）
  - **验收标准**：适配器层 `llm_service_port.py` 和 `main.py` 不触发 TID251；`src/services/llm_service.py` 不触发 TID251
  - **文件锁**：`pyproject.toml`

---

## 2. 核心消费方迁移（自主性层 + 交互层）

**负责人**：Codex（机械性替换，模式统一）

**前置条件**：批次 1 完成（LLMService Protocol + 适配器 + 注册点可用）

### 2.1 butler.py 延迟导入迁移（2 处）

- [ ] 迁移 `src/maisaka/agent_autonomy/butler.py` 中 2 处延迟导入：
  - **第 1 处**（`_filter_by_butler_llm` 方法，约 L269）：
    - 删除 `from src.services.llm_service import LLMServiceClient`
    - 新增 `from src.core.adapters.llm_service_port import get_llm_service`
    - 将 `client = LLMServiceClient(task_name="replyer", request_type="butler_filter")` + `result = await client.generate_response(prompt, options)` 改为 `result = await get_llm_service().generate_response("replyer", prompt, options, request_type="butler_filter")`
  - **第 2 处**（`_generate_butler_reply` 方法，约 L523）：
    - 删除 `from src.services.llm_service import LLMServiceClient`
    - 新增 `from src.core.adapters.llm_service_port import get_llm_service`
    - 将 `client = LLMServiceClient(task_name="replyer", request_type="butler_speak")` + `result = await client.generate_response(prompt, options)` 改为 `result = await get_llm_service().generate_response("replyer", prompt, options, request_type="butler_speak")`
  - **验收标准**：`rg "from src.services.llm_service import LLMServiceClient" src/maisaka/agent_autonomy/butler.py` 无结果；功能行为不变
  - **文件锁**：`src/maisaka/agent_autonomy/butler.py`

### 2.2 heuristic_injector.py 构造注入迁移

- [ ] 迁移 `src/maisaka/memory/heuristic_injector.py`：
  - 删除模块级 `from src.services.llm_service import LLMServiceClient`
  - 新增 `from src.core.protocols import LLMService` 和 `from src.core.adapters.llm_service_port import get_llm_service`
  - `HeuristicMemoryInjector.__init__()` 新增可选参数 `llm_service: LLMService | None = None`，内部 `self._llm_service = llm_service or get_llm_service()`
  - 删除 `self._impression_client = LLMServiceClient(task_name="utils", request_type="heuristic_memory_impression")`
  - 所有 `self._impression_client.generate_response(...)` 调用改为 `await self._llm_service.generate_response("utils", ..., request_type="heuristic_memory_impression")`
  - **验收标准**：`rg "LLMServiceClient" src/maisaka/memory/heuristic_injector.py` 无结果；`HeuristicMemoryInjector` 可通过构造注入或注册点获取 `LLMService`
  - **文件锁**：`src/maisaka/memory/heuristic_injector.py`

### 2.3 chat_loop_service.py 缓存消除 + 构造注入迁移

- [ ] 迁移 `src/maisaka/chat_loop_service.py`：
  - 删除模块级 `from src.services.llm_service import LLMServiceClient`
  - 新增 `from src.core.protocols import LLMService` 和 `from src.core.adapters.llm_service_port import get_llm_service`
  - `ChatLoopService.__init__()` 新增可选参数 `llm_service: LLMService | None = None`，内部 `self._llm_service = llm_service or get_llm_service()`
  - 删除 `self._llm_chat_clients: dict[str, LLMServiceClient] = {}`（L511）
  - 删除 `_get_llm_chat_client()` 方法（L561-575）
  - 将 `_chat_with_llm()` 方法中（约 L1107）的 `llm_chat = self._get_llm_chat_client(request_kind)` + `generation_result = await llm_chat.generate_response_with_messages(message_factory, options)` 改为：
    ```python
    model_task_name = self._resolve_model_task_name(request_kind)
    request_type = self._resolve_llm_request_type(request_kind)
    generation_result = await self._llm_service.generate_response_with_messages(
        model_task_name, message_factory, options,
        request_type=request_type,
        session_id=self._session_id,
    )
    ```
  - **验收标准**：`rg "_llm_chat_clients\|_get_llm_chat_client" src/maisaka/chat_loop_service.py` 无结果；`rg "LLMServiceClient" src/maisaka/chat_loop_service.py` 无结果；LLM 调用功能不变
  - **文件锁**：`src/maisaka/chat_loop_service.py`

### 2.4 replyer/generator.py + generator_base.py 参数模式转换

- [ ] 迁移 `src/maisaka/replyer/generator.py` 和 `src/maisaka/replyer/generator_base.py`：
  - **generator_base.py**：
    - 删除 `from src.services.llm_service import LLMServiceClient`（如果存在间接引用）
    - `BaseMaisakaReplyGenerator.__init__()` 参数从 `llm_client_cls: Any` 改为 `llm_service: LLMService`
    - 新增 `from src.core.protocols import LLMService`
    - `self._llm_client_cls = llm_client_cls` 改为 `self._llm_service = llm_service`
    - `self.express_model = llm_client_cls(task_name="replyer", request_type=request_type, session_id=...)` 改为保留 `self.express_model` 但改为通过 `self._llm_service` 调用（注意：`express_model` 在多处被直接调用 `generate_response_with_messages`，需改为 `self._llm_service.generate_response_with_messages("replyer", ...)`）
    - L640 `checker_model = self._llm_client_cls(task_name=..., request_type=..., session_id=...)` + `await checker_model.generate_response_with_messages(...)` 改为 `await self._llm_service.generate_response_with_messages(task_name, message_factory, options, request_type=..., session_id=...)`
    - L1066 `active_model = self._llm_client_cls(task_name=active_task_name, ...)` + `await active_model.generate_response_with_messages(...)` 改为 `await self._llm_service.generate_response_with_messages(active_task_name, message_factory, options, request_type=self.request_type, session_id=preview_chat_id)`
    - 所有 `self.express_model.generate_response_with_messages(...)` 调用改为 `self._llm_service.generate_response_with_messages("replyer", ..., request_type=self.request_type, session_id=...)`
  - **generator.py**：
    - 删除 `from src.services.llm_service import LLMServiceClient`
    - 新增 `from src.core.adapters.llm_service_port import get_llm_service`
    - `MaisakaReplyGenerator.__init__()` 参数从 `llm_client_cls: Optional[Any] = None` 改为 `llm_service: Optional[LLMService] = None`
    - `llm_client_cls=llm_client_cls or LLMServiceClient` 改为 `llm_service=llm_service or get_llm_service()`
  - **验收标准**：`rg "llm_client_cls\|_llm_client_cls" src/maisaka/replyer/` 无结果；`rg "LLMServiceClient" src/maisaka/replyer/` 无结果；replyer 生成功能不变
  - **文件锁**：`src/maisaka/replyer/generator_base.py`、`src/maisaka/replyer/generator.py`

### 2.5 mid_term.py 延迟导入迁移

- [ ] 迁移 `src/maisaka/memory/mid_term.py`：
  - 删除函数内 `from src.services.llm_service import LLMServiceClient`（约 L136）
  - 新增模块级 `from src.core.adapters.llm_service_port import get_llm_service`
  - 将 `llm_client = LLMServiceClient(task_name="mid_memory", request_type="maisaka.mid_term_memory", session_id=session_id)` + `result = await llm_client.generate_response_with_messages(message_factory)` 改为 `result = await get_llm_service().generate_response_with_messages("mid_memory", message_factory, request_type="maisaka.mid_term_memory", session_id=session_id)`
  - **验收标准**：`rg "LLMServiceClient" src/maisaka/memory/mid_term.py` 无结果；中期记忆摘要功能不变
  - **文件锁**：`src/maisaka/memory/mid_term.py`

---

## 3. 基础设施层-学习器迁移

**负责人**：Codex（机械性替换，模块级实例消除）

**前置条件**：批次 1 完成

### 3.1 jargon_miner.py 模块级实例消除

- [ ] 迁移 `src/learners/jargon_miner.py`：
  - 删除模块级 `from src.services.llm_service import LLMServiceClient`
  - 新增 `from src.core.adapters.llm_service_port import get_llm_service`
  - 删除模块级实例 `llm_inference = LLMServiceClient(task_name="learner", request_type="jargon.inference")`
  - 所有 `llm_inference.generate_response(...)` 调用改为 `await get_llm_service().generate_response("learner", ..., request_type="jargon.inference")`
  - **验收标准**：`rg "LLMServiceClient" src/learners/jargon_miner.py` 无结果；`rg "llm_inference" src/learners/jargon_miner.py` 仅剩函数调用处（无模块级实例定义）
  - **文件锁**：`src/learners/jargon_miner.py`

### 3.2 jargon_learner.py 模块级实例消除

- [ ] 迁移 `src/learners/jargon_learner.py`：
  - 删除模块级 `from src.services.llm_service import LLMServiceClient`
  - 新增 `from src.core.adapters.llm_service_port import get_llm_service`
  - 删除模块级实例 `jargon_learn_model = LLMServiceClient(task_name="learner", request_type="jargon.learner")`
  - 所有 `jargon_learn_model.generate_response(...)` 调用改为 `await get_llm_service().generate_response("learner", ..., request_type="jargon.learner")`
  - **验收标准**：`rg "LLMServiceClient" src/learners/jargon_learner.py` 无结果
  - **文件锁**：`src/learners/jargon_learner.py`

### 3.3 expression_utils.py 模块级实例消除

- [ ] 迁移 `src/learners/expression_utils.py`：
  - 删除模块级 `from src.services.llm_service import LLMServiceClient`
  - 新增 `from src.core.adapters.llm_service_port import get_llm_service`
  - 删除模块级实例 `judge_llm = LLMServiceClient(task_name="learner", request_type="expression.check")`
  - 所有 `judge_llm.generate_response(...)` 调用改为 `await get_llm_service().generate_response("learner", ..., request_type="expression.check")`
  - **验收标准**：`rg "LLMServiceClient" src/learners/expression_utils.py` 无结果
  - **文件锁**：`src/learners/expression_utils.py`

### 3.4 expression_learner.py 模块级实例消除（2 个实例）

- [ ] 迁移 `src/learners/expression_learner.py`：
  - 删除模块级 `from src.services.llm_service import LLMServiceClient`
  - 新增 `from src.core.adapters.llm_service_port import get_llm_service`
  - 删除模块级实例 `express_learn_model = LLMServiceClient(task_name="learner", request_type="expression.learner")` 和 `summary_model = LLMServiceClient(task_name="utils", request_type="expression.summary")`
  - 所有 `express_learn_model.generate_response(...)` 调用改为 `await get_llm_service().generate_response("learner", ..., request_type="expression.learner")`
  - 所有 `summary_model.generate_response(...)` 调用改为 `await get_llm_service().generate_response("utils", ..., request_type="expression.summary")`
  - **验收标准**：`rg "LLMServiceClient" src/learners/expression_learner.py` 无结果
  - **文件锁**：`src/learners/expression_learner.py`

### 3.5 behavior_learner.py 模块级实例消除（3 个实例）

- [ ] 迁移 `src/learners/behavior_learner.py`：
  - 删除模块级 `from src.services.llm_service import LLMServiceClient`
  - 新增 `from src.core.adapters.llm_service_port import get_llm_service`
  - 删除模块级实例 `behavior_learn_model = LLMServiceClient(task_name="learner", request_type="behavior.learner")`、`behavior_scene_model = LLMServiceClient(task_name="learner", request_type="behavior.scene_analyzer")`、`behavior_feedback_model = LLMServiceClient(task_name="learner", request_type="behavior.feedback")`
  - 所有 `behavior_learn_model.generate_response(...)` 调用改为 `await get_llm_service().generate_response("learner", ..., request_type="behavior.learner")`
  - 所有 `behavior_scene_model.generate_response(...)` 调用改为 `await get_llm_service().generate_response("learner", ..., request_type="behavior.scene_analyzer")`
  - 所有 `behavior_feedback_model.generate_response(...)` 调用改为 `await get_llm_service().generate_response("learner", ..., request_type="behavior.feedback")`
  - **验收标准**：`rg "LLMServiceClient" src/learners/behavior_learner.py` 无结果
  - **文件锁**：`src/learners/behavior_learner.py`

---

## 4. 基础设施层-其他迁移

**负责人**：Codex（机械性替换，模块级实例消除 + 构造注入）

**前置条件**：批次 1 完成

### 4.1 emoji_manager.py 模块级实例消除（2 个实例）

- [ ] 迁移 `src/emoji_system/emoji_manager.py`：
  - 删除模块级 `from src.services.llm_service import LLMServiceClient`
  - 新增 `from src.core.adapters.llm_service_port import get_llm_service`
  - 删除模块级实例 `emoji_manager_vlm = LLMServiceClient(task_name="vlm", request_type="emoji.see")` 和 `emoji_manager_emotion_judge_llm = LLMServiceClient(task_name="utils", request_type="emoji")`
  - 所有 `emoji_manager_vlm.generate_response_for_image(...)` 调用改为 `await get_llm_service().generate_response_for_image("vlm", ..., request_type="emoji.see")`
  - 所有 `emoji_manager_emotion_judge_llm.generate_response(...)` 调用改为 `await get_llm_service().generate_response("utils", ..., request_type="emoji")`
  - **验收标准**：`rg "LLMServiceClient" src/emoji_system/emoji_manager.py` 无结果
  - **文件锁**：`src/emoji_system/emoji_manager.py`

### 4.2 image_manager.py 模块级实例消除

- [ ] 迁移 `src/chat/image_system/image_manager.py`：
  - 删除模块级 `from src.services.llm_service import LLMServiceClient`
  - 新增 `from src.core.adapters.llm_service_port import get_llm_service`
  - 删除模块级实例 `vlm = LLMServiceClient(task_name="vlm", request_type="image")`
  - 所有 `vlm.generate_response_for_image(...)` 调用改为 `await get_llm_service().generate_response_for_image("vlm", ..., request_type="image")`
  - **验收标准**：`rg "LLMServiceClient" src/chat/image_system/image_manager.py` 无结果
  - **文件锁**：`src/chat/image_system/image_manager.py`

### 4.3 utils_voice.py 模块级实例消除

- [ ] 迁移 `src/common/utils/utils_voice.py`：
  - 删除模块级 `from src.services.llm_service import LLMServiceClient`
  - 新增 `from src.core.adapters.llm_service_port import get_llm_service`
  - 删除模块级实例 `asr_model = LLMServiceClient(task_name="voice", request_type="audio")`
  - 所有 `asr_model.transcribe_audio(...)` 调用改为 `await get_llm_service().transcribe_audio("voice", ..., request_type="audio")`
  - **验收标准**：`rg "LLMServiceClient" src/common/utils/utils_voice.py` 无结果
  - **文件锁**：`src/common/utils/utils_voice.py`

### 4.4 host_llm_bridge.py 构造注入迁移

- [ ] 迁移 `src/mcp_module/host_llm_bridge.py`：
  - 删除模块级 `from src.services.llm_service import LLMServiceClient`
  - 新增 `from src.core.protocols import LLMService` 和 `from src.core.adapters.llm_service_port import get_llm_service`
  - `MCPHostLLMBridge.__init__()` 新增可选参数 `llm_service: LLMService | None = None`，内部 `self._llm_service = llm_service or get_llm_service()`
  - 删除 `self._sampling_client = LLMServiceClient(task_name=self._sampling_task_name, request_type="mcp_sampling")`
  - 所有 `self._sampling_client.generate_response_with_messages(...)` 调用改为 `await self._llm_service.generate_response_with_messages(self._sampling_task_name, ..., request_type="mcp_sampling")`
  - **验收标准**：`rg "LLMServiceClient" src/mcp_module/host_llm_bridge.py` 无结果；MCP Sampling 功能不变
  - **文件锁**：`src/mcp_module/host_llm_bridge.py`

### 4.5 memory_flow_service.py 延迟导入迁移

- [ ] 迁移 `src/services/memory_flow_service.py`：
  - 删除函数内 `from src.services.llm_service import LLMServiceClient`（约 L366）
  - 新增模块级 `from src.core.protocols import LLMService` 和 `from src.core.adapters.llm_service_port import get_llm_service`
  - `MemoryFlowService.__init__()` 新增可选参数 `llm_service: LLMService | None = None`，内部 `self._llm_service = llm_service or get_llm_service()`
  - 删除 `self._extractor = LLMServiceClient(task_name="utils", request_type="A_Memorix.person_fact_writeback")` 懒初始化
  - 将 `self._extractor.generate_response(prompt)` 调用改为 `await self._llm_service.generate_response("utils", prompt, request_type="A_Memorix.person_fact_writeback")`
  - **验收标准**：`rg "LLMServiceClient" src/services/memory_flow_service.py` 无结果；人物事实提取功能不变
  - **文件锁**：`src/services/memory_flow_service.py`

---

## 5. WebUI/插件层 + ruff 守卫 + 全量验证

**负责人**：CC（架构变更，守卫规则需首次正确）

**前置条件**：批次 2-4 完成（所有消费方已迁移）

### 5.1 webui/routers/behavior.py 模块级实例消除

- [ ] 迁移 `src/webui/routers/behavior.py`：
  - 删除模块级 `from src.services.llm_service import LLMServiceClient`
  - 新增 `from src.core.adapters.llm_service_port import get_llm_service`
  - 删除模块级实例 `behavior_scene_debug_model = LLMServiceClient(task_name="learner", request_type="behavior.scene_analyzer")`
  - 所有 `behavior_scene_debug_model.generate_response(...)` 调用改为 `await get_llm_service().generate_response("learner", ..., request_type="behavior.scene_analyzer")`
  - **验收标准**：`rg "LLMServiceClient" src/webui/routers/behavior.py` 无结果
  - **文件锁**：`src/webui/routers/behavior.py`

### 5.2 plugin_runtime/capabilities/core.py 延迟导入迁移

- [ ] 迁移 `src/plugin_runtime/capabilities/core.py`：
  - 删除函数内 `from src.services.llm_service import LLMServiceClient, resolve_task_name`（约 L606）
  - 新增模块级 `from src.core.adapters.llm_service_port import get_llm_service`
  - `resolve_task_name` 保留导入（来自 `src.services.llm_service` 或 `src.services.service_task_resolver`，按需调整）
  - 将 `asr_client = LLMServiceClient(task_name=task_name, request_type=f"plugin.{plugin_id}.asr")` + `result = await asr_client.transcribe_audio(audio_base64)` 改为 `result = await get_llm_service().transcribe_audio(task_name, audio_base64, request_type=f"plugin.{plugin_id}.asr")`
  - **验收标准**：`rg "LLMServiceClient" src/plugin_runtime/capabilities/core.py` 无结果；插件 ASR 能力不变
  - **文件锁**：`src/plugin_runtime/capabilities/core.py`

### 5.3 ruff banned-api 守卫新增

- [ ] 在 `pyproject.toml` 的 `[tool.ruff.lint.flake8-tidy-imports.banned-api]` 中新增：
  ```toml
  "src.services.llm_service.LLMServiceClient" = {msg = "禁止直接导入 LLMServiceClient，请使用 LLMService Protocol 接口（get_llm_service()）"}
  ```
  - **验收标准**：在核心层文件中添加 `from src.services.llm_service import LLMServiceClient` → ruff check 报 TID251 错误；适配器层和启动入口因 per-file-ignores 不受影响
  - **文件锁**：`pyproject.toml`

### 5.4 全量验证

- [ ] 执行全量验证，确认迁移完成：
  - 运行 `rg "from src.services.llm_service import LLMServiceClient" src/` → 仅剩 `src/core/adapters/llm_service_port.py`、`src/main.py`、`src/services/llm_service.py` 自身
  - 运行 `rg "LLMServiceClient(" src/` → 仅剩适配器层、`main.py`、`llm_service.py` 自身、A_memorix 内部 4 处（本期排除）
  - 运行 `ruff check src/` → 零 TID251 违规（A_memorix 目录已有 per-file-ignores 豁免）
  - 确认 A_memorix 4 处（`sdk_memory_kernel.py`、`fuzzy_modify.py`、`feedback_correction.py`、`model_routing.py`）仍通过 `self._ports.llm_api.LLMServiceClient(...)` 或 `llm_api.LLMServiceClient(...)` 调用，本期不迁移
  - **验收标准**：3 条验证命令结果符合预期；A_memorix 4 处不受影响
  - **文件锁**：无（验证任务，不修改文件）

---

## 附录：A_memorix 排除项（本期不迁移）

以下 4 处 `LLMServiceClient` 使用在 A_memorix 内部，通过 `AMemorixServicePorts.llm_service` 注入整个 `llm_service` 模块，本期不改动此端口模式：

| 文件 | 行号 | 使用方式 |
|------|------|---------|
| `src/A_memorix/core/runtime/sdk_memory_kernel.py` | L399 | `self._ports.llm_service.LLMServiceClient(task_name="utils")` |
| `src/A_memorix/core/runtime/services/fuzzy_modify.py` | L603 | `self._llm_api.LLMServiceClient(...)` |
| `src/A_memorix/core/runtime/services/feedback_correction.py` | L1041 | `self._llm_api.LLMServiceClient(...)` |
| `src/A_memorix/core/utils/model_routing.py` | L159 | `llm_api.LLMServiceClient(task_name=model.task_name, request_type=request_type)` |

后续优化方向：将 `AMemorixServicePorts.llm_service` 从模块级注入改为 `LLMService` Protocol 注入。