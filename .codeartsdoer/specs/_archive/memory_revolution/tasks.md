# 记忆系统革命 — 编码任务规划

## 阶段概览

| 阶段 | 内容 | 前置条件 | 验收标准 |
|------|------|----------|----------|
| 1 | 数据模型与基础设施 | 无 | Trace/MemoryPersonalityV2/InnerVoice 数据类可实例化，TraceStore 可 CRUD |
| 2 | 概念提取 | 阶段1 | LLMConceptExtractor 可从文本提取概念+关系+情感，LLM不可用时报错跳过 |
| 3 | 记忆性格与内心声音 | 阶段1 | PersonalityRegistry 可注册/查询，InnerVoiceProcessor 可处理情感和概念 |
| 4 | 消息观察（observe） | 阶段1+2+3 | observe() 可选择性记忆，显著性评估正确，内心声音处理正确 |
| 5 | 激活扩散回忆（recall） | 阶段1+3 | recall() 可从种子概念逐跳扩散，per-agent 隔离正确 |
| 6 | 粒度退化与整合 | 阶段1 | granular_decay() 正确衰减 detail_level 和 weight，consolidate() 合并弱连接 |
| 7 | 画像推导与反思 | 阶段1+5 | derive_profile() 实时推导画像，reflect() 展示内心声音视角 |
| 8 | MemoryField 核心运行时 | 阶段4+5+6+7 | MemoryField 整合所有子模块，提供统一 API |
| 9 | 迁移适配层 | 阶段8 | MigrationAdapter 支持四阶段迁移，双写/双读/数据迁移/新系统独立 |
| 10 | 集成与验收 | 阶段9 | 端到端验收测试通过，性能达标，WebUI Admin 可查看记忆统计 |

---

## 阶段1：数据模型与基础设施

### 1A 枚举与数据类定义
- [x] 创建 `src/A_memorix/core/connectionist/__init__.py`
- [x] 创建 `src/A_memorix/core/connectionist/enums.py`：Valence / VoiceStyle / TimeOfDay 枚举
- [x] 创建 `src/A_memorix/core/connectionist/models.py`：Trace dataclass（含 emotional_floor 计算方法）
- [x] 创建 `src/A_memorix/core/connectionist/models.py`：MemoryPersonalityV2 dataclass（含参数校验，有效范围约束）
- [x] 创建 `src/A_memorix/core/connectionist/models.py`：InnerVoice dataclass（含 transform_valence / filter_concepts 方法）
- [x] 创建 `src/A_memorix/core/connectionist/models.py`：ExtractionResult / ExtractedConcept / ExtractedRelation dataclass
- [x] 创建 `src/A_memorix/core/connectionist/models.py`：ObserveResult / AgentMemoryResult / RecallItem / ProfileView / AssociationItem / VoiceView / ContradictionItem / TimelineItem / ReflectResult / DecayResult dataclass
- [x] 验收：所有 dataclass 可实例化，字段约束校验生效，emotional_floor 计算公式正确（NEUTRAL=0.02, POSITIVE/NEGATIVE=min(0.30, 0.10×|valence|×sensitivity)）

### 1B TraceStore 持久化存储
- [x] 创建 `src/A_memorix/core/connectionist/trace_store.py`：TraceStore 类
- [x] 实现 SQLite 持久化：`{data_dir}/connectionist/traces.db`，表结构 (source, target, weight, valence, agent_id, timestamp, detail_level, time_of_day, observation_id, voice_name)
- [x] 实现 CRUD：create_trace / get_trace / update_trace / delete_trace / query_by_concept / query_by_agent
- [x] 实现邻接索引：内存中 `dict[str, dict[str, list[Trace]]]`（概念→agent_id→Trace列表）
- [x] 实现启动恢复：从 SQLite 加载到内存，重建邻接索引
- [x] 实现异步刷盘：observe() 后异步写入，心跳时批量刷盘
- [x] 唯一键约束：(source, target, agent_id, voice_name)
- [x] 验收：TraceStore 可 CRUD，重启后数据恢复，邻接索引正确

### 1C ConceptIndex 概念索引
- [x] 创建 `src/A_memorix/core/connectionist/concept_index.py`：ConceptIndex 类
- [x] 实现概念→类型映射存储：`{data_dir}/connectionist/concepts.json`
- [x] 实现同义词表管理：register_synonym / get_synonyms / expand_seeds
- [x] 实现概念频率统计：increment_count / get_count
- [x] 实现概念注册：register_concept(name, concept_type)
- [x] 验收：ConceptIndex 可注册/查询/同义词扩展，持久化到 JSON

---

## 阶段2：概念提取

### 2A LLMConceptExtractor
- [x] 创建 `src/A_memorix/core/extraction/__init__.py`
- [x] 创建 `src/A_memorix/core/extraction/llm_concept_extractor.py`：LLMConceptExtractor 类
- [x] 实现 LLM 调用：使用 flash 模型，提取概念+关系+情感极性+概念类型
- [x] 实现 prompt 设计：要求 LLM 返回结构化 JSON（concepts + relations + valence + summary），prompt 三语同步（zh-CN / en-US / ja-JP）
- [x] 实现 LLM 不可用处理：记录错误日志并跳过本次 observe，不降级到低质量提取方式（不降级到 jieba）
- [x] 实现 LLM 返回非标准 JSON 处理：记录错误日志并跳过
- [x] 实现概念粒度归一化：LLM 自然归一化（"打游戏"和"游戏"统一为"游戏"）
- [x] 实现概念提取结果为空时返回空 ExtractionResult（消息过短如"嗯"、"好"）
- [x] 验收：LLMConceptExtractor 可从文本提取概念，LLM 不可用时报错跳过而非降级

---

## 阶段3：记忆性格与内心声音

### 3A PersonalityRegistry
- [x] 创建 `src/A_memorix/core/personality/__init__.py`
- [x] 创建 `src/A_memorix/core/personality/personality_registry.py`：PersonalityRegistry 类
- [x] 实现 register_agent(agent_id, personality, voices)：注册/覆盖
- [x] 实现 get_personality(agent_id) → MemoryPersonalityV2
- [x] 实现 get_voices(agent_id) → list[InnerVoice]
- [x] 实现默认性格：未注册时返回全 1.0 默认值 + PRESERVE 默认声音，记录警告日志
- [x] 实现内心声音列表为空时使用默认声音（PRESERVE 风格，保留原始情感，不过滤概念），保证至少一组痕迹被创建
- [x] 验收：PersonalityRegistry 可注册/查询，默认性格正确，空声音列表时回退到默认声音

### 3B InnerVoiceProcessor
- [x] 创建 `src/A_memorix/core/personality/inner_voice_processor.py`：InnerVoiceProcessor 类
- [x] 实现 transform_valence(valence, style)：AMPLIFY(×1.5) / NEUTRALIZE(归零) / PRESERVE(保留) / INVERT(×-1) / CHAOTIC(随机选择)
- [x] 实现 filter_concepts(concepts, focus_concepts, existing_concepts)：focus_concepts 非空时只保留交集+已有记忆概念，为空时保留全部
- [x] 实现 process_experience(valence, concepts, voice, existing_concepts)：组合处理
- [x] 验收：五种声音风格正确处理情感，概念过滤正确，CHAOTIC 风格随机但不崩溃

---

## 阶段4：消息观察（observe）

### 4A SalienceEvaluator 显著性评估
- [x] 创建 `src/A_memorix/core/connectionist/salience_evaluator.py`：SalienceEvaluator 类
- [x] 实现四维度评分：情感显著性(0.4×affinity×sensitivity) + 关注领域匹配(0.5×匹配数) + 关联度(0.2×重叠数) + 新颖性(0.15×新概念数，≥2时才计)
- [x] 实现阈值计算：0.25 / max(0.5, curiosity)——好奇心只影响阈值，不乘以显著性分数
- [x] 实现 evaluate(concepts, agent_id, valence, personality) → (score, reason)
- [x] 验收：13条群聊消息 → 银狼记住18条痕迹（记仇+关注游戏），刃记住10条（只记吵架/战斗），景元记住18条（关注工作）

### 4B observe() 主流程
- [x] 创建 `src/A_memorix/core/connectionist/observer.py`：Observer 类
- [x] 实现 observe(text, valence, timestamp, source_id, session_id) → ObserveResult
- [x] 流程：LLMConceptExtractor.extract → 对每个智能体 SalienceEvaluator.evaluate → InnerVoiceProcessor.process → TraceStore.create/strengthen
- [x] 实现 Trace 强化逻辑：已存在 → weight+boost, detail+0.3（上限1.0）；不存在 → 创建新 Trace(weight=0.5, detail=1.0)
- [x] 实现 observation_id 生成："obs_{counter}"
- [x] 实现 time_of_day 计算：基于 timestamp 判断时段（凌晨/上午/中午/下午/晚上/深夜）
- [x] 实现概念注册：提取到的概念注册到 ConceptIndex
- [x] 实现概念提取结果为空时跳过：remembered=False, reason="无概念提取"
- [x] 实现所有智能体显著性不足时全部返回 remembered=False，不创建任何痕迹
- [x] 实现过滤后概念 < 2 时跳过该声音
- [x] 验收：observe() 可选择性记忆，不同智能体对同一消息有不同记忆决策，被动观察不替智能体做回复决策

---

## 阶段5：激活扩散回忆（recall）

### 5A SpreadingActivation
- [x] 创建 `src/A_memorix/core/connectionist/spreading_activation.py`：SpreadingActivation 类
- [x] 实现激活扩散算法：从种子概念出发，逐跳扩散
- [x] 实现扩散公式：spread = activation × weight × 0.85（衰减系数）× recency_factor × detail_factor
- [x] 实现 recency_factor：近期(<1h) 1.0~1.5，1h后归为1.0。注意：weight 和 detail 已包含时间衰减，recall 不再叠加 recency 惩罚
- [x] 实现 detail_factor：0.3 + 0.7 × detail_level
- [x] 实现 min_weight 过滤：低于阈值的跳过
- [x] 实现 association_depth 控制：默认2跳，最大4跳（从 PersonalityRegistry 获取，集成时由 MemoryField 传入）
- [x] 实现 per-agent 隔离：只返回该智能体的痕迹，禁止回忆结果包含其他智能体的痕迹
- [x] 实现语义扩展种子：通过 ConceptIndex 同义词表扩展
- [x] 实现 relative_time 计算：刚刚/今天/昨天/这几天/上周/很久以前
- [x] 实现种子概念不存在时的处理：尝试语义扩展（同义词），若仍无匹配则返回空列表
- [x] 实现痕迹网络为空时直接返回空列表
- [x] 验收：recall("游戏厅", agent_id="银狼") → 激活扩散到"格斗游戏"→"赢了"→"奶茶"；银狼 recall("小明") 结果只包含 agent_id="银狼" 的痕迹

---

## 阶段6：粒度退化与整合

### 6A GranularDecayEngine
- [x] 创建 `src/A_memorix/core/connectionist/granular_decay_engine.py`：GranularDecayEngine 类
- [x] 实现 granular_decay(elapsed_hours) → DecayResult
- [x] 实现 emotional_slowdown 计算：1.0 / (1.0 + 0.5 × |valence| × sensitivity)
- [x] 实现 detail_level 退化：detail_level -= detail_decay_rate × elapsed_hours × emotional_slowdown
- [x] 实现 weight 衰减：weight = max(emotional_floor, weight × decay_factor)
- [x] 实现 SKELETON 下限：detail_level ≥ 0.1，永不归零
- [x] 实现 weight 永不低于 emotional_floor：即使极长时间衰减，带情感痕迹仍保留最低激活能力
- [x] 实现 consolidate()：合并重复弱连接
- [x] 实现分批处理：痕迹数 >50000 时单次心跳只处理一部分，记录警告日志
- [x] 验收：1年后中性痕迹 weight=0.02，情感痕迹 weight=0.20，detail_level 正确退化；weight ≥ emotional_floor，detail_level ≥ SKELETON(0.1)

---

## 阶段7：画像推导与反思

### 7A ProfileDeriver
- [x] 创建 `src/A_memorix/core/connectionist/profile_deriver.py`：ProfileDeriver 类
- [x] 实现 derive_profile(subject, observer) → ProfileView
- [x] 实现关联概念提取：从痕迹中提取与 subject 相关的概念，按强度降序
- [x] 实现内心声音分组：按 voice_name 分组视角
- [x] 实现矛盾检测：同一概念在不同声音下有不同情感极性，矛盾被保留而非平均化
- [x] 实现时间线构建：按 timestamp 排序的痕迹列表
- [x] 实现画像深度判定：≤3"初识——只有模糊的印象"，≤8"相识——开始有了轮廓"，≤15"熟悉——有了较深的了解"，>15"深知——深入骨髓的理解"
- [x] 实现万物皆可画像：任何概念都可以是画像中心——人、物、地点、活动
- [x] 实现结果截断：关联概念最多 top-20，矛盾点最多 top-10
- [x] 实现被观察概念无任何痕迹时返回空白画像（depth="空白——尚无任何印象"）
- [x] 验收：derive_profile("小明", "银狼") 返回关联概念+内心声音视角+矛盾点+时间线+画像深度；derive_profile("小明", "刃") 返回"初识+模糊印象"

### 7B reflect() 反思
- [x] 在 ProfileDeriver 中实现 reflect(subject, agent_id) → ReflectResult
- [x] 实现收集不同声音的痕迹：展示同一概念在不同内心声音下的痕迹
- [x] 实现矛盾点提取：倔强觉得+，恶作剧心觉得-
- [x] 实现无痕迹时返回空反思
- [x] 验收：reflect("小明", "银狼") → 返回不同声音的视角和矛盾点（倔强觉得迟到是+，恶作剧心觉得迟到是-）

---

## 阶段8：MemoryField 核心运行时

### 8A MemoryField 整合
- [x] 创建 `src/A_memorix/core/connectionist/memory_field.py`：MemoryField 类
- [x] 注入 TraceStore / ConceptIndex / SalienceEvaluator / SpreadingActivation / ProfileDeriver / GranularDecayEngine / PersonalityRegistry / Observer
- [x] 实现 observe() 委托：调用 Observer
- [x] 实现 recall() 委托：调用 SpreadingActivation（从 PersonalityRegistry 获取 association_depth 传入）
- [x] 实现 derive_profile() 委托：调用 ProfileDeriver
- [x] 实现 reflect() 委托：调用 ProfileDeriver
- [x] 实现 granular_decay() 委托：调用 GranularDecayEngine
- [x] 实现 register_agent() 委托：调用 PersonalityRegistry
- [x] 实现 initialize()：从 SQLite 恢复数据，重建邻接索引
- [x] 实现 memory_stats()：返回痕迹数、概念数、各智能体记忆量
- [x] 验收：MemoryField 提供统一 API，所有子模块正确协作

### 8B SDKMemoryKernel 集成
- [x] 在 SDKMemoryKernel 中注入 MemoryField 实例
- [x] 在 host_service 中新增 component_name：observe / recall / derive_profile / reflect / register_agent
- [x] 实现 observe 路由：host_service.invoke("observe", args) → MemoryField.observe()
- [x] 实现 recall 路由：host_service.invoke("recall", args) → MemoryField.recall()
- [x] 实现 derive_profile 路由：host_service.invoke("derive_profile", args) → MemoryField.derive_profile()
- [x] 实现 reflect 路由：host_service.invoke("reflect", args) → MemoryField.reflect()
- [x] 实现 register_agent 路由：host_service.invoke("register_agent", args) → MemoryField.register_agent()
- [x] 在 host_service._disabled_response() 中新增新 component_name 的禁用响应
- [x] 验收：通过 host_service.invoke() 可调用所有新接口

### 8C 核心侧调用集成
- [x] 评估 MemoryServicePort Protocol 是否需要扩展：design.md 决策为"不新增 Protocol 方法，新接口通过 host_service 暴露"，确认此决策并记录
- [x] 在 Orchestrator 中集成 observe() 调用路径：消息流入时通过 host_service.invoke("observe", args) 或 MemoryServicePort 间接调用
- [x] 在 VitalityManager 心跳中集成 granular_decay() 触发：心跳信号（60秒间隔）触发 MemoryField.granular_decay()
- [x] 验收：Orchestrator 消息流入时触发 observe()，VitalityManager 心跳时触发 granular_decay()

---

## 阶段9：迁移适配层

### 9A MigrationAdapter
- [x] 创建 `src/A_memorix/core/migration/__init__.py`
- [x] 创建 `src/A_memorix/core/migration/migration_adapter.py`：MigrationAdapter 类
- [x] 实现迁移状态机：LEGACY_ONLY → DUAL_WRITE → DUAL_READ → DATA_MIGRATION → NEW_INDEPENDENT
- [x] 实现阶段1（双写）：消息流入时同时调用旧 ingest_text() 和新 observe()，新系统 observe 失败但旧系统 ingest 成功时记录不一致日志
- [x] 实现阶段2（双读）：search() 内部同时查询旧系统和新系统，合并去重（旧系统按 Paragraph 排序，新系统按激活强度排序，取并集去重）
- [x] 实现阶段3（数据迁移）：DataConverter 将旧数据转换为 Trace
- [x] 实现阶段4（新系统独立）：search() 只查询新系统，旧系统只读
- [x] 实现回退控制：配置切换即可回退到上一阶段（NEW_INDEPENDENT → DUAL_READ），新系统 Trace 数据独立存储不影响旧系统
- [x] 实现迁移期间不删除旧数据，只标记已迁移
- [x] 验收：四阶段迁移状态机正确，回退可用，旧数据不被删除

### 9B DataConverter
- [x] 创建 `src/A_memorix/core/migration/data_converter.py`：DataConverter 类
- [x] 实现 Paragraph → Trace 转换：LLMConceptExtractor 重新提取概念，创建 Trace(weight=0.5, valence=NEUTRAL, detail_level=0.3)
- [x] 实现 Entity → ConceptIndex 注册：更新概念→类型映射
- [x] 实现 Relation → Trace 转换：subject→object，weight 从 relation 强度映射，valence 默认 NEUTRAL
- [x] 实现 Episode → Trace 转换：LLMConceptExtractor 重新提取概念，保留 timestamp，detail_level=0.3
- [x] 实现 PersonProfile 不转换：derive_profile() 实时推导替代
- [x] 实现迁移失败处理：跳过异常数据，记录错误日志，标记"迁移失败"，不阻塞后续迁移
- [x] 实现从旧数据迁移的痕迹无 time_of_day 字段时默认为"未知"
- [x] 验收：旧数据可转换为 Trace，迁移失败不阻塞

### 9C MemoryServicePort 适配
- [x] 更新 AMemorixMemoryServicePort：search() 内部根据迁移阶段双读合并
- [x] 更新 get_person_profile()：迁移期间兼容旧快照，逐步替换为 derive_profile()
- [x] 实现 set_memory_personality()：实际调用 PersonalityRegistry.register_agent()（当前是空壳 try/except）
- [x] 验收：MemoryServicePort 接口签名不变，内部实现根据迁移阶段切换

---

## 阶段10：集成与验收

### 10A 端到端验收测试
- [x] 场景1：13条群聊消息流入 → 银狼记住18条痕迹（记仇+关注游戏），刃记住10条（只记吵架/战斗），景元记住18条（关注工作）
- [x] 场景2：recall("游戏厅", "银狼") → 激活扩散到"格斗游戏"→"赢了"→"奶茶"
- [x] 场景3：derive_profile("小明", "银狼") → 返回"熟悉+4处矛盾"，derive_profile("小明", "刃") → 返回"初识+模糊印象"
- [x] 场景4：1年后中性痕迹 weight=0.02，情感痕迹 weight=0.20
- [x] 场景5：LLM 不可用 → 记录错误日志并跳过本次 observe，不降级到 jieba
- [x] 场景6：银狼的"倔强"把"迟到"(NEGATIVE)反转为POSITIVE——"哼，迟到了又怎样"
- [x] 场景7：迁移四阶段正确运行，回退可用
- [x] 场景8：概念提取结果为空（"嗯"、"好"）→ 跳过，remembered=False
- [x] 场景9：所有智能体显著性不足（纯环境信号）→ 不创建任何痕迹
- [x] 场景10：种子概念不存在 → 尝试语义扩展，仍无匹配则返回空列表
- [x] 场景11：痕迹网络为空 → recall() 直接返回空列表
- [x] 场景12：智能体未注册性格 → 使用默认性格（全1.0），记录警告日志
- [x] 场景13：内心声音列表为空 → 使用默认声音（PRESERVE），保证至少一组痕迹
- [x] 场景14：数据迁移转换失败 → 跳过异常数据，标记"迁移失败"，不阻塞
- [x] 场景15：双写期间新系统 observe 失败但旧系统 ingest 成功 → 记录不一致日志
- [x] 场景16：per-agent 记忆隔离 → 银狼 recall("小明") 不包含刃的痕迹
- [x] 验收：所有场景通过

### 10B 性能验收测试
- [x] 概念提取延迟：单条消息 LLM 概念提取延迟 ≤ 2秒（使用 flash 模型）
- [x] 回忆延迟：单次 recall() 激活扩散延迟 ≤ 100ms（纯内存计算，不涉及 LLM）
- [x] 画像推导延迟：单次 derive_profile() 延迟 ≤ 200ms
- [x] 观察吞吐量：observe() 支持 ≥ 10条/秒的消息摄入（含 LLM 概念提取的异步处理）
- [x] 心跳衰减开销：单次 granular_decay() 全量扫描 ≤ 500ms（13个智能体，≤10000条痕迹）
- [x] 内存占用：痕迹网络常驻内存 ≤ 200MB（10000条痕迹 × 13智能体）
- [x] 验收：所有性能指标达标

### 10C WebUI Admin 集成
- [x] 在 WebUI Admin 中新增记忆统计页面：痕迹数、概念数、各智能体记忆量
- [x] 在 WebUI Admin 中新增记忆参数调整页面：记忆性格参数可调
- [x] 在 WebUI Admin 中新增迁移控制页面：迁移阶段切换（LEGACY_ONLY/DUAL_WRITE/DUAL_READ/DATA_MIGRATION/NEW_INDEPENDENT）、状态查看
- [x] 验收：WebUI Admin 可查看记忆统计和调整参数

### 10D 配置文件模板
- [x] 在配置模板中新增 `[memory_revolution]` 配置节：phase（LEGACY_ONLY/DUAL_WRITE/DUAL_READ/DATA_MIGRATION/NEW_INDEPENDENT）、enabled（bool）、data_dir（str）
- [x] 新增版本号
- [x] 不改动 legacy_migration，不改动实际 bot_config.toml / model_config.toml
- [x] 验收：配置可解析，迁移阶段可配置切换

### 10E 反馈纠错兼容验证
- [x] 验证现有 FeedbackCorrectionService 和 FuzzyModifyService 在迁移期间仍正常工作
- [x] 验证 host_service 的 enqueue_feedback_task 路由不受影响
- [x] 验收：反馈纠错功能在迁移期间不中断
