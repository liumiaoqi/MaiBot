# 记忆系统范式迁移 — 编码任务

> **进度**：第1-4批已完成（18/22子任务），Docker运行时验证通过。第5-6批待运行时长期验证。

## 1. 配置驱动的智能体注册（第1批·基础设施）✅

### 1.1 AMemorixConfig 新增记忆性格配置段 ✅

- [x] 修改 `src/config/official_configs.py`：在 `AMemorixConnectionistConfig` 类中新增 `personality` 字段，类型为 `dict[str, MemoryPersonalityV2Config]`，默认空字典
- [ ] 新建 `MemoryPersonalityV2Config(ConfigBase)` 类，包含字段：`decay_rate: float`（默认1.0, ge=0.1, le=5.0）、`emotional_sensitivity: float`（默认1.0, ge=0.1, le=3.0）、`association_depth: int`（默认2, ge=1, le=4）、`reinforcement_boost: float`（默认0.3, ge=0.1, le=0.5）、`attention_tags: list[str]`（默认空列表）、`positive_affinity: float`（默认1.0, ge=0.0, le=3.0）、`negative_affinity: float`（默认1.0, ge=0.0, le=3.0）、`curiosity: float`（默认1.0, ge=0.5, le=2.0）
- [ ] 每个字段添加三语 label（zh_CN/en_US/ja_JP）和描述
- **验收**：`AMemorixConfig().connectionist.personality` 可访问，字段校验生效

### 1.2 AMemorixConfig 新增内心声音配置段 ✅

- [x] 修改 `src/config/official_configs.py`：在 `AMemorixConnectionistConfig` 类中新增 `inner_voices` 字段，类型为 `dict[str, list[InnerVoiceItemConfig]]`，默认空字典
- [ ] 新建 `InnerVoiceItemConfig(ConfigBase)` 类，包含字段：`name: str`（必填）、`style: str`（默认"preserve"）、`focus_concepts: list[str]`（默认空列表）、`weight_multiplier: float`（默认1.0, ge=0.1, le=2.0）、`description: str`（默认""）
- [ ] 每个字段添加三语 label 和描述
- **验收**：`AMemorixConfig().connectionist.inner_voices` 可访问，`style` 值校验为 VoiceStyle 枚举成员

### 1.3 配置模板更新 ✅

- [x] 修改配置模板文件（`config/bot_config.toml` 模板），在 `[a_memorix.connectionist]` 段下新增 `personality` 和 `inner_voices` 子段注释示例
- [ ] 新增配置版本号（`src/config/config.py` 中 `CONFIG_VERSION` 递增）
- **验收**：新部署时配置模板包含 personality/inner_voices 段，升级流程正常

### 1.4 启动时智能体注册流程 ✅

- [x] 修改 `src/A_memorix/host_service.py` 的 `_ensure_kernel()` 方法：在 `kernel.initialize()` 成功后，新增 `_register_agents_from_config(kernel)` 调用
- [ ] 在 `AMemorixHostService` 类中新增 `_register_agents_from_config(self, kernel: SDKMemoryKernel) -> None` 方法：
  - 从 `self._read_config()` 读取 `connectionist.personality` 和 `connectionist.inner_voices`
  - 遍历 personality 字典，构造 `MemoryPersonalityV2` 和 `list[InnerVoice]`，调用 `kernel._memory_field.register_agent(agent_id, personality, voices)`（注：MemoryField 内部持有 PersonalityRegistry，register_agent() 实际委托到 PersonalityRegistry.register_agent()）
  - 未配置的角色不注册（observe 时使用默认性格，记录警告日志）
  - 参数校验失败时启动报错
- [ ] 从配置读取 `connectionist.phase`，构造 `MigrationPhase` 枚举，设置 `kernel._migration_adapter` 的初始阶段（见任务 2.2）
- **验收**：启动后 `kernel._memory_field.memory_stats()["registered_agents"]` 包含所有已配置角色

### 1.5 jieba 降级概念提取器 ✅

- [x] 新建 `src/A_memorix/core/extraction/semantic_concept_extractor.py`，实现 `SemanticConceptExtractor` 类：
  - `__init__(self, concept_index: ConceptIndex)` — 持有 ConceptIndex 引用
  - `async def extract(self, text: str) -> ExtractionResult` — 使用 jieba 分词 + ConceptIndex 同义词表归一化，valence 固定 NEUTRAL，不提取关系
- [ ] 修改 `src/A_memorix/core/extraction/llm_concept_extractor.py`：在 `extract()` 方法的异常处理中，LLM 失败时降级到 `SemanticConceptExtractor`：
  - `LLMConceptExtractor.__init__` 新增 `concept_index: ConceptIndex | None = None` 参数
  - `extract()` 失败时，如果 `self._concept_index` 不为 None，构造 `SemanticConceptExtractor(self._concept_index)` 并调用其 `extract()`
  - jieba 也失败时返回空 `ExtractionResult()`
- [ ] 修改 `src/A_memorix/core/connectionist/memory_field.py`：`LLMConceptExtractor()` 构造改为 `LLMConceptExtractor(concept_index=self._concept_index)`，传入 ConceptIndex 引用
- [ ] 注：对应 spec 5.1.3 的 jieba+同义词表降级场景，SemanticConceptExtractor 是 spec 中"回退到 jieba+同义词表"的具体实现类
- **验收**：LLM 不可用时，observe() 仍能通过 jieba 提取概念写入痕迹（概念质量低于 LLM 但非空）

## 2. 迁移框架搭建（第2批·迁移框架）✅

**目标**：MigrationAdapter 增加阶段约束，host_service.invoke() 连接主义组件名增加阶段判断，granular_decay 集成到心跳。此批改造后 LEGACY_ONLY 阶段行为与改造前完全一致。

### 2.1 MigrationAdapter 阶段约束扩展 ✅

- [x] 修改 `src/A_memorix/core/migration/migration_adapter.py`：
  - 新增 `advance_phase(self) -> MigrationPhase` 方法：只允许前进一级（LEGACY_ONLY→DUAL_WRITE→DUAL_READ→DATA_MIGRATION→NEW_INDEPENDENT），跳过或回退时抛出 ValueError
  - 新增 `can_advance(self) -> bool` 方法：检查是否可以推进（当前不是 NEW_INDEPENDENT 即可推进）
  - 修改 `set_phase(self, phase: MigrationPhase)` 方法：增加校验，只允许设置当前阶段或下一阶段（保留回滚能力，但回退需显式调用 set_phase 而非 advance_phase）
- [ ] 新增 `_PHASE_ORDER: list[MigrationPhase]` 常量列表，用于阶段序号比较
- **验收**：`adapter.advance_phase()` 从 LEGACY_ONLY 推进到 DUAL_WRITE 成功；从 LEGACY_ONLY 直接推进到 DUAL_READ 抛出 ValueError；`adapter.can_advance()` 在 NEW_INDEPENDENT 阶段返回 False

### 2.2 SDKMemoryKernel 持有 MigrationAdapter 实例 ✅

- [x] 修改 `src/A_memorix/core/runtime/sdk_memory_kernel.py`：在 `initialize()` 方法中，`MemoryField` 创建后，新增 `self._migration_adapter = MigrationAdapter(self._memory_field)` 实例创建
- [ ] MigrationAdapter 的初始 phase 从配置读取（与任务 1.4 联动：`_register_agents_from_config` 中设置）
- **验收**：`kernel._migration_adapter` 存在，`kernel._migration_adapter.phase` 为配置中指定的阶段（默认 LEGACY_ONLY）

### 2.3 host_service.invoke() 连接主义组件名阶段判断 ✅

- [x] 修改 `src/A_memorix/host_service.py` 的 `invoke()` 方法：
  - 在 `component_name == "observe"` 分支前，获取 `migration_adapter = kernel._migration_adapter`
  - `observe` 分支：如果 `not migration_adapter.should_observe()`，返回 `ObserveResult(text=str(payload.get("text", "")))`
  - `recall` 分支：如果 `not migration_adapter.should_recall()`，返回空列表 `[]`
  - `derive_profile` 分支：如果 `not migration_adapter.should_recall()`，返回空白 `ProfileView(subject=str(payload.get("subject", "")))`
  - `reflect` 分支：如果 `not migration_adapter.should_recall()`，返回空白 `ReflectResult()`
  - `register_agent` 分支：不受阶段限制（注册始终可用）
  - `connectionist_stats` 分支：不受阶段限制（统计始终可用）
- [ ] 在 `_disabled_response()` 方法中新增连接主义组件名的降级响应
- **验收**：LEGACY_ONLY 阶段调用 `invoke("observe", ...)` 返回空 ObserveResult；DUAL_WRITE 阶段正常执行 observe

### 2.4 granular_decay 集成到心跳 ✅

- [x] 修改 `src/A_memorix/host_service.py` 的 `invoke()` 方法：在 `component_name == "maintain_memory"` 分支中，当 `action == "decay"` 时：
  - 获取 `migration_adapter = kernel._migration_adapter`
  - 如果 `migration_adapter.should_observe()`（DUAL_WRITE 及之后阶段）：在分类学 decay 后，同时调用 `kernel._memory_field.granular_decay(elapsed_hours=hours or 1.0)`
  - 如果 `migration_adapter.is_new_independent()`：仅调用 `kernel._memory_field.granular_decay(elapsed_hours=hours or 1.0)`，跳过分类学 decay
- **验收**：DUAL_WRITE 阶段心跳 decay 同时执行分类学退化和粒度退化；LEGACY_ONLY 阶段仅执行分类学退化

### 2.5 新增 migration_status 组件名 ✅

- [x] 修改 `src/A_memorix/host_service.py` 的 `invoke()` 方法：新增 `component_name == "migration_status"` 分支，返回 `{"phase": kernel._migration_adapter.phase.value, "can_advance": kernel._migration_adapter.can_advance()}`
- [ ] 在 `_disabled_response()` 方法中新增 `migration_status` 降级响应
- **验收**：`invoke("migration_status")` 返回当前迁移阶段名称和是否可推进

## 3. 迁移路由层与翻译层（第3批·核心改造）✅

**目标**：新增 MigrationRouter 和 ConnectionistTranslator，AMemorixMemoryServicePort 的方法委托到 MigrationRouter 而非直接走分类学。此批改造后 DUAL_WRITE 阶段开始双写，核心调用方零修改。

### 3.1 ConnectionistTranslator 格式翻译层 ✅

- [x] 新建 `src/A_memorix/core/migration/translator.py`，实现 `ConnectionistTranslator` 类：
  - `@staticmethod recall_to_search_result(items: list[RecallItem], query: str) -> MemorySearchResult`：RecallItem.concept→MemoryHit.content，activation→MemoryHit.score，valence/detail_level/relative_time→MemoryHit.metadata
  - `@staticmethod profile_view_to_dict(profile: ProfileView) -> dict[str, Any]`：associations→evidence（含 concept/strength/valence/voice），depth→summary 描述（空白/初识/相识/熟悉/深知），contradictions→traits 中的矛盾标注
  - `@staticmethod profile_view_to_injection_text(profile: ProfileView) -> str`：从 ProfileView 生成紧凑注入文本——关联概念按强度排序生成描述，矛盾点生成矛盾描述，depth 生成熟悉度描述
  - `@staticmethod query_to_seeds(query: str, concept_index: ConceptIndex | None = None) -> list[str]`：短查询（≤4字符）直接作为种子，长查询用 jieba 提取关键词，有 ConceptIndex 时调用 expand_seeds() 扩展同义词
- [ ] 翻译函数为纯函数，无副作用，输入为空时返回空结果
- **验收**：`recall_to_search_result([RecallItem(concept="小明", activation=0.8)], "小明")` 返回 `MemorySearchResult(hits=[MemoryHit(content="小明", score=0.8)])`；`profile_view_to_dict` 返回与分类学画像格式兼容的字典

### 3.2 MigrationRouter 迁移感知路由 ✅

- [x] 新建 `src/A_memorix/core/migration/migration_router.py`，实现 `MigrationRouter` 类：
  - `__init__(self, migration_adapter: MigrationAdapter, memory_field: MemoryField, kernel: SDKMemoryKernel, translator: ConnectionistTranslator)` — 持有四个引用
  - `async def search(self, query: str, *, agent_id: str = "", **kwargs) -> MemorySearchResult`：
    - LEGACY_ONLY/DUAL_WRITE：走分类学 `kernel.search_memory()`
    - DUAL_READ：分类学 search + 连接主义 recall，记录差异日志，返回分类学结果
    - DATA_MIGRATION/NEW_INDEPENDENT：query→seeds → 连接主义 recall → RecallItem→MemorySearchResult 翻译
  - `async def get_person_profile(self, person_id: str, *, agent_id: str = "", limit: int = 4) -> Optional[dict[str, Any]]`：
    - LEGACY_ONLY/DUAL_WRITE：走分类学 `kernel.get_person_profile()`
    - DUAL_READ：分类学画像 + 连接主义 derive_profile，记录差异日志，返回分类学画像
    - DATA_MIGRATION/NEW_INDEPENDENT：连接主义 derive_profile → ProfileView→画像字典 翻译
  - `async def ingest_text(self, text: str, **kwargs) -> MemoryWriteResult`：
    - LEGACY_ONLY：仅分类学 ingest_text
    - DUAL_WRITE/DUAL_READ/DATA_MIGRATION：分类学 ingest_text + 连接主义 observe，返回分类学结果
    - NEW_INDEPENDENT：仅连接主义 observe，ObserveResult→MemoryWriteResult 翻译
  - `async def build_profile_injection_text(self, raw_text: str, *, agent_id: str = "") -> str`：
    - NEW_INDEPENDENT：连接主义 derive_profile → ProfileView→注入文本 翻译
    - 其他阶段：走分类学 `build_profile_injection_text()`
- [ ] DUAL_READ 阶段的差异日志使用 `logger.info` 级别，不阻断迁移
- [ ] NEW_INDEPENDENT 阶段连接主义调用失败时直接抛出异常（不兜底）
- **验收**：LEGACY_ONLY 阶段 search/get_person_profile/ingest_text 行为与改造前完全一致；DUAL_WRITE 阶段 ingest_text 同时写入两套系统

### 3.3 SDKMemoryKernel 持有 MigrationRouter 实例 ✅

- [x] 修改 `src/A_memorix/core/runtime/sdk_memory_kernel.py`：在 `initialize()` 方法中，`MigrationAdapter` 创建后，新增 `self._migration_router = MigrationRouter(self._migration_adapter, self._memory_field, self, ConnectionistTranslator())` 实例创建
- **验收**：`kernel._migration_router` 存在，可调用 `search()/get_person_profile()/ingest_text()/build_profile_injection_text()`

### 3.4 host_service.invoke() 新增迁移路由组件名 ✅

- [x] 修改 `src/A_memorix/host_service.py` 的 `invoke()` 方法：新增四个组件名分支：
  - `migration_search`：委托 `kernel._migration_router.search(query, agent_id=agent_id, **payload)`
  - `migration_get_person_profile`：委托 `kernel._migration_router.get_person_profile(person_id, agent_id=agent_id, limit=limit)`
  - `migration_ingest_text`：委托 `kernel._migration_router.ingest_text(text, **payload)`
  - `migration_build_profile_injection_text`：委托 `kernel._migration_router.build_profile_injection_text(raw_text, agent_id=agent_id)`
- [ ] 在 `_disabled_response()` 方法中新增四个组件名的降级响应
- **验收**：`invoke("migration_search", {"query": "小明"})` 返回 MemorySearchResult 格式结果

### 3.5 MemoryService 新增迁移路由方法 ✅

- [x] 修改 `src/services/memory_service.py`：`MemoryService` 类新增四个方法：
  - `async def migration_search(self, query: str, *, agent_id: str = "", **kwargs) -> MemorySearchResult`：通过 `self._invoke("migration_search", {...})` 委托，用 `_coerce_search_result()` 格式化
  - `async def migration_get_person_profile(self, person_id: str, *, agent_id: str = "", limit: int = 4) -> PersonProfileResult`：通过 `self._invoke("migration_get_person_profile", {...})` 委托，用 `_coerce_profile_result()` 格式化
  - `async def migration_ingest_text(self, text: str, **kwargs) -> MemoryWriteResult`：通过 `self._invoke("migration_ingest_text", {...})` 委托，用 `_coerce_write_result()` 格式化
  - `async def migration_build_profile_injection_text(self, raw_text: str, *, agent_id: str = "") -> str`：通过 `self._invoke("migration_build_profile_injection_text", {...})` 委托
- **验收**：`memory_service.migration_search("小明")` 返回 `MemorySearchResult`

### 3.6 AMemorixMemoryServicePort 最终委托切换 ✅

- [x] 修改 `src/core/adapters/memory_service.py`：将 `search()/get_person_profile()/ingest_text()/build_profile_injection_text()` 的委托从 `memory_service.xxx()` 改为 `memory_service.migration_xxx()`
- [ ] 保留原 `memory_service.search()` 等方法的调用路径（WebUI 等外部调用方仍直接走分类学）
- **验收**：核心模块通过 MemoryServicePort 调用时走迁移路由；WebUI 通过 MemoryService 直接调用时仍走分类学

## 4. 数据迁移增强（第4批·数据迁移）✅

**目标**：DataConverter 使用 LLM 提取概念替代截取前50字符的自环痕迹，确保迁移后的痕迹是有效的概念间连接。此批在 DATA_MIGRATION 阶段执行。

### 4.1 DataConverter LLM 增强 — convert_paragraph ✅

- [x] 修改 `src/A_memorix/core/migration/data_converter.py`：
  - `DataConverter.__init__` 新增 `llm_extractor: LLMConceptExtractor` 参数
  - `convert_paragraph` 方法改造：对文本调用 `llm_extractor.extract(text)`，从提取的概念对创建痕迹（source→target 从 ExtractedRelation 或相邻概念对生成），valence 从 ExtractionResult 获取
  - 返回值从 `Trace | None` 改为 `list[Trace]`（一次提取可创建多条痕迹）
  - LLM 提取失败时降级到 `SemanticConceptExtractor`（需传入 concept_index），再失败则跳过该条数据（记录警告日志）
  - 保留 observation_id 前缀 `migrated_p_`
- **验收**：`convert_paragraph({"content": "小明和小红在游戏厅打格斗游戏"})` 返回多条 Trace，source≠target

### 4.2 DataConverter LLM 增强 — convert_episode ✅

- [x] 修改 `src/A_memorix/core/migration/data_converter.py`：
  - `convert_episode` 方法改造：同 convert_paragraph 逻辑，对文本调用 LLM 提取概念后创建痕迹
  - 返回值从 `Trace | None` 改为 `list[Trace]`
  - 保留 observation_id 前缀 `migrated_e_`
- **验收**：`convert_episode({"content": "小明赢了格斗游戏很开心"})` 返回多条 Trace，source≠target

### 4.3 DataConverter LLM 增强 — convert_relation 返回值统一 ✅

- [x] `convert_relation` 方法保持现有映射逻辑不变：subject→object 直接映射为 Trace，这是正确的映射
- [ ] 返回值从 `Trace | None` 改为 `list[Trace]`，统一 DataConverter 所有方法的返回类型（与 convert_paragraph/convert_episode 的 `list[Trace]` 一致）；有映射结果时返回单元素列表，无映射时返回空列表
- **验收**：`convert_relation({"subject": "小明", "object": "游戏厅"})` 返回 `[Trace(source="小明", target="游戏厅")]`；无有效映射时返回 `[]`

### 4.4 数据迁移执行脚本 ✅

- [x] 新建 `scripts/migrate_taxonomy_to_connectionist.py`，实现一次性数据迁移脚本：
  - 从分类学 SQLite 读取所有 Paragraph/Entity/Relation/Episode 数据
  - 对 Entity 调用 `convert_entity()` 注册概念
  - 对 Relation 调用 `convert_relation()` 创建痕迹
  - 对 Paragraph/Episode 调用 `convert_paragraph()/convert_episode()` 创建痕迹
  - 输出迁移统计（总条数、成功数、失败数、跳过数）
  - 支持断点续传（记录已迁移的 observation_id，重复执行不重复迁移）
- [ ] 脚本通过 `a_memorix_host_service.invoke()` 访问数据，不直接导入 A_memorix 内部模块
- [ ] 注：正式脚本放 `scripts/`，实验性原型放 `lab/`；此脚本为正式迁移工具，非实验性质
- **验收**：运行脚本后，TraceStore 中有从分类学数据迁移来的痕迹，source≠target

## 5. 分类学代码退役（第5批·最终目标）

**目标**：NEW_INDEPENDENT 阶段确认后，删除分类学遗留代码。此批需充分验证后执行，风险最高。

### 5.1 分类学检索路径退役验证

- [ ] 前置条件：6.5 NEW_INDEPENDENT 阶段验证通过（连接主义独立运行确认后，方可开始分类学退役）
- [ ] 在 NEW_INDEPENDENT 阶段运行系统，验证以下功能全部走连接主义路径：
  - MemoryServicePort.search() → 连接主义 recall
  - MemoryServicePort.get_person_profile() → 连接主义 derive_profile
  - MemoryServicePort.ingest_text() → 连接主义 observe
  - MemoryServicePort.build_profile_injection_text() → 连接主义 ProfileView→注入文本
  - maintain_memory(action="decay") → 连接主义 granular_decay
- [ ] 验证 WebUI 记忆管理功能正常（通过 MemoryService 直接调用仍可用）
- **验收**：所有核心记忆功能在连接主义独立运行下正常，无分类学依赖

### 5.2 分类学数据模型退役

- [ ] 删除 `src/A_memorix/core/runtime/sdk_memory_kernel.py` 中分类学相关的写入/检索方法（`search_memory/ingest_text/ingest_summary/get_person_profile/maintain_memory` 及其委托的 Service 类）
- [ ] 删除分类学数据模型（Paragraph/Entity/Relation/Episode/Profile 相关的存储类和 Service 类）
- [ ] 保留 `SDKMemoryKernel` 类壳和 `_memory_field`/`_migration_adapter`/`_migration_router` 属性
- [ ] 保留 `metadata_store`（WebUI 时间线功能仍依赖）
- **验收**：`SDKMemoryKernel` 不再包含分类学检索/写入方法，仅保留连接主义和元数据访问

### 5.3 分类学配置段退役

- [ ] 修改 `src/config/official_configs.py`：将分类学相关配置段（`AMemorixRetrievalConfig`/`AMemorixThresholdConfig`/`AMemorixFilterConfig`/`AMemorixEpisodeConfig`/`AMemorixPersonProfileConfig`/`AMemorixMemoryEvolutionConfig`）标记为 deprecated 或移除
- [ ] 新增配置版本号
- **验收**：配置中不再包含分类学专用配置段

### 5.4 分类学 Admin Handler 退役

- [ ] 删除 `src/A_memorix/admin/` 中分类学相关的 Admin Handler（graph/source/episode/profile/feedback/v5 等）
- [ ] 修改 `host_service.invoke()` 中 `_ADMIN_HANDLER_MAP`，移除分类学组件名
- [ ] 保留 `delete`/`correction`/`runtime`/`import`/`tuning` 等通用管理组件
- **验收**：`invoke()` 不再接受分类学管理组件名

## 6. 集成验证与回归测试

**目标**：确保迁移各阶段功能无回归，核心调用方零修改，性能达标。

### 6.1 LEGACY_ONLY 阶段回归验证

- [ ] 启动系统（配置 `connectionist.phase = "legacy_only"`），验证分类学读写正常运行
- [ ] 验证连接主义组件名（observe/recall/derive_profile）返回空结果，不执行实际逻辑
- [ ] 验证 MemoryServicePort.search/get_person_profile/ingest_text 行为与改造前一致
- [ ] 验证心跳 maintain_memory(action="decay") 仅执行分类学退化
- **验收**：LEGACY_ONLY 阶段所有功能与改造前行为完全一致

### 6.2 DUAL_WRITE 阶段验证

- [ ] 推进到 DUAL_WRITE 阶段，验证消息同时写入分类学和连接主义
- [ ] 验证检索仍走分类学，连接主义在后台积累数据
- [ ] 验证 TraceStore 有数据积累
- [ ] 验证心跳同时执行分类学退化和粒度退化
- **验收**：DUAL_WRITE 阶段分类学检索不受影响，TraceStore 有新数据

### 6.3 DUAL_READ 阶段验证

- [ ] 推进到 DUAL_READ 阶段，验证检索同时走两套系统
- [ ] 检查差异日志，确认两套系统结果差异可观测
- [ ] 验证核心模块仍返回分类学结果
- **验收**：DUAL_READ 阶段差异日志正常记录，核心功能不受影响

### 6.4 DATA_MIGRATION 阶段验证

- [ ] 执行数据迁移脚本，验证分类学存量数据成功转换为连接主义痕迹
- [ ] 验证迁移后痕迹 source≠target（无自环痕迹）
- [ ] 验证连接主义 recall() 能覆盖分类学 search() 的核心结果
- **验收**：迁移后痕迹质量优于改造前，recall 覆盖核心检索场景

### 6.5 NEW_INDEPENDENT 阶段验证

- [ ] 推进到 NEW_INDEPENDENT 阶段，验证所有记忆功能走连接主义
- [ ] 验证 MemoryServicePort 行为兼容
- [ ] 验证性能：recall() 延迟不高于分类学 search()；granular_decay() 13 智能体 ≤50ms
- [ ] 验证 13 个智能体记忆性格差异化：银狼记仇、刃忘得快、景元关注工作
- **验收**：连接主义独立运行，所有功能正常，性能达标

### 6.6 架构验收

- [ ] 验证核心模块零直接导入 A_memorix 内部模块（核心禁止项6）
- [ ] 验证 MemoryServicePort Protocol 签名不变
- [ ] 验证 WebUI 记忆管理界面功能不退化
- [ ] 验证配置驱动：13 个角色的记忆性格从配置文件加载，不硬编码
- **验收**：所有架构约束满足

## 任务依赖关系

```
1.1 ──→ 1.4（配置模型是启动注册的前提）
1.2 ──→ 1.4（内心声音配置是启动注册的前提）
1.3 ──→ 1.4（配置模板是配置加载的前提）
1.5（jieba 降级，独立于 1.1-1.4，可与 1.4 并行）

2.1 ──→ 2.2（阶段约束是 MigrationAdapter 实例化的前提）
1.4 ──→ 2.2（启动注册设置 MigrationAdapter 初始阶段）
2.2 ──→ 2.3（MigrationAdapter 实例是 invoke 阶段判断的前提）
2.1 ──→ 2.3（advance_phase/can_advance 是阶段判断的前提）
2.2 ──→ 2.4（MigrationAdapter 实例是 granular_decay 集成的前提）
2.2 ──→ 2.5（MigrationAdapter 实例是 migration_status 的前提）

3.1 ──→ 3.2（翻译层是路由层的前提）
2.2 ──→ 3.2（MigrationAdapter 是路由层的前提）
2.3 ──→ 3.2（invoke 阶段判断是路由层的前提）
3.2 ──→ 3.3（路由层是 MigrationRouter 实例化的前提）
3.3 ──→ 3.4（MigrationRouter 实例是 invoke 新组件名的前提）
3.4 ──→ 3.5（invoke 组件名是 MemoryService 方法的前提）
3.5 ──→ 3.6（MemoryService 方法是适配器委托切换的前提）

1.5 ──→ 4.1（jieba 降级是 DataConverter LLM 降级的前提）
3.2 ──→ 4.1（路由层完成后 DataConverter 改造才有意义）
4.1 ──→ 4.4（convert_paragraph 改造是迁移脚本的前提）
4.2 ──→ 4.4（convert_episode 改造是迁移脚本的前提）

6.5 ──→ 5.1（NEW_INDEPENDENT 阶段验证通过后才可开始分类学退役）
1-4 全部完成 ──→ 5（分类学退役依赖所有改造完成）
5.1 ──→ 5.2（验证通过后才可删除分类学代码）
5.2 ──→ 5.3（代码退役后配置才可清理）
5.2 ──→ 5.4（代码退役后 Admin Handler 才可清理）

1-5 全部完成 ──→ 6（集成验证依赖所有改造完成）
```

## 改造涉及的文件清单

| 文件 | 改造类型 | 涉及任务 |
|------|---------|---------|
| `src/config/official_configs.py` | 修改 | 1.1, 1.2, 5.3 |
| `src/config/config.py` | 修改 | 1.3, 5.3 |
| `config/bot_config.toml` 模板 | 修改 | 1.3 |
| `src/A_memorix/host_service.py` | 修改 | 1.4, 2.3, 2.4, 2.5, 3.4, 5.4 |
| `src/A_memorix/core/extraction/semantic_concept_extractor.py` | 新建 | 1.5 |
| `src/A_memorix/core/extraction/llm_concept_extractor.py` | 修改 | 1.5 |
| `src/A_memorix/core/connectionist/memory_field.py` | 修改 | 1.5 |
| `src/A_memorix/core/migration/migration_adapter.py` | 修改 | 2.1 |
| `src/A_memorix/core/runtime/sdk_memory_kernel.py` | 修改 | 2.2, 3.3, 5.2 |
| `src/A_memorix/core/migration/translator.py` | 新建 | 3.1 |
| `src/A_memorix/core/migration/migration_router.py` | 新建 | 3.2 |
| `src/core/adapters/memory_service.py` | 修改 | 3.6 |
| `src/services/memory_service.py` | 修改 | 3.5 |
| `src/A_memorix/core/migration/data_converter.py` | 修改 | 4.1, 4.2, 4.3 |
| `scripts/migrate_taxonomy_to_connectionist.py` | 新建 | 4.4 |