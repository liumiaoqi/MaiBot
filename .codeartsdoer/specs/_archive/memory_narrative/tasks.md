# 记忆叙事原型 — 编码任务列表

> 基于 spec.md（4大核心能力）和 design.md（4子模块架构+数据模型+接口设计）
> 原则：增量可验证，每批完成后系统可运行，不破坏现有功能

---

## 第1批：数据模型 + 枚举 + TraceStore 扩展 ✅ 已完成（commit 92b17eb23）

**目标**：为四个子模块奠定数据基础，不引入任何运行时逻辑

### 任务 1.1：新增枚举类型 ✅

- **文件**：`src/A_memorix/core/connectionist/enums.py`
- **内容**：新增 `CognitiveType`、`LifecycleStatus`、`EmotionalAxis` 三个枚举
- **验证**：`from src.A_memorix.core.connectionist.enums import CognitiveType, LifecycleStatus, EmotionalAxis` 无报错

### 任务 1.2：新增 dataclass 模型 ✅

- **文件**：`src/A_memorix/core/connectionist/models.py`
- **内容**：新增 `Fragment`、`Episode`、`Saga`、`CognitiveEntry`、`IntuitionResult`、`WeaveResult`、`LifecycleResult`、`CognitiveDecayResult`、`EpisodeSummary`、`SagaSummary` 共 10 个 dataclass。其中 `Episode` 需包含 `all_concepts: list[str]` 字段（底层 Fragment 概念并集，用于 Saga 连接检测——lab 实验发现仅靠 concept_bridge 无法检测跨 Episode 的实体桥接）
- **验证**：所有 dataclass 可实例化，字段默认值正确

### 任务 1.3：TraceStore 新增 observation_id 查询方法 ✅

- **文件**：`src/A_memorix/core/connectionist/trace_store.py`
- **内容**：
  1. `query_by_observation_id(observation_id: str) -> list[Trace]` — 单个观察批次查询
  2. `query_by_observation_ids(observation_ids: list[str]) -> dict[str, list[Trace]]` — 批量查询
- **验证**：写入 Trace 后，通过 observation_id 可查回完整 Trace 列表

### 任务 1.4：AssociationItem / ProfileView 扩展字段 ✅

- **文件**：`src/A_memorix/core/connectionist/models.py`
- **内容**：
  1. `AssociationItem` 新增 `cognitive_type: str = ""` 字段
  2. `ProfileView` 新增 `episodes: list[EpisodeSummary]` 和 `sagas: list[SagaSummary]` 字段
- **验证**：现有 ProfileView 构造不报错（新字段有默认值）

---

## 第2批：叙事编织（NarrativeWeaver）核心 ✅ 已完成（commit 09ffe6f49）

**目标**：Fragment→Episode→Saga 三层叙事自组织的核心逻辑

### 任务 2.1：创建 narrative 子包 + Fragment 聚合视图 ✅

### 任务 2.2：EpisodeStore — Episode/Saga SQLite 持久化 ✅

### 任务 2.3：NarrativeWeaver 叙事编织器 ✅

- ⚠️ LLM prompt 三语模板文件（`narrative/prompts/` 目录）尚未创建，当前 prompt 内联在 narrative_weaver.py 中

---

## 第3批：认知分层（CognitiveStratifier） ✅ 已完成（commit e517a4595）

**目标**：概念节点的确定性元数据标注，四层认知 + 证据积累 + 升级/降级

### 任务 3.1：创建 cognitive 子包 + CognitiveStore ✅

### 任务 3.2：CognitiveStratifier 认知分层器 ✅

---

## 第4批：生命周期管理（LifecycleManager） ✅ 已完成（commit 524e73a88）

**目标**：Fragment/Episode/Saga 的完整新陈代谢，与粒度退化正交

### 任务 4.1：创建 lifecycle 子包 + LifecycleManager ✅

---

## 第5批：直觉引擎（IntuitionEngine） ✅ 已完成（commit 736ba9abf）

**目标**：关键词+bigram 双层触发，替代全量 dump

### 任务 5.1：创建 intuition 子包 + 停用词管理 ✅

### 任务 5.2：IntuitionEngine 直觉引擎 ✅

---

## 第6批：MemoryField 门面集成 + Observer 通知 + 心跳协调 ✅ 已完成（commit 0ca4d0c13）

**目标**：将四个子模块接入现有系统，形成完整闭环

### 任务 6.1：MemoryField 持有四个新子模块实例 ✅

### 任务 6.2：Observer 完成后通知 CS/NW（由 MemoryField 协调） ✅

### 任务 6.3：心跳协调 — granular_decay + advance_lifecycle + process_cognitive_decay ✅

### 任务 6.4：ProfileDeriver 扩展 ✅

### 任务 6.5：SpreadingActivation + IntuitionEngine 互补集成 ⬜ 待实现

- **文件**：`src/A_memorix/core/connectionist/memory_field.py`
- **内容**：
  1. 新增 `recall_with_intuition(seeds, context_text, agent_id)` 便捷方法
  2. 内部调用 `SpreadingActivation.recall()` 获取概念激活模式（RecallItem 列表）
  3. 内部调用 `IntuitionEngine.intuition_trigger()` 获取认知条目和叙事上下文
  4. 两者合并返回——recall 提供概念激活，直觉提供认知和叙事深度
  5. 调用方可选择使用 `recall()`（纯概念激活）或 `recall_with_intuition()`（概念+认知+叙事）
- **验证**：recall_with_intuition() 返回结果包含 RecallItem + IntuitionResult

---

## 第7批：迁移阶段守卫 + HostService API + 集成验证 ✅ 已完成（commit 0da71485b）

**目标**：确保叙事层在迁移框架内正确路由，暴露 admin API，端到端验证

### 任务 7.1：迁移阶段守卫 ✅

### 任务 7.2：ConnectionistTranslator 叙事格式翻译 ⬜ 待后续（DUAL_READ 阶段才需要）

### 任务 7.3：HostService API 扩展 ✅

### 任务 7.4：端到端集成验证 ✅

- 子模块集成验证全部通过（认知分层、生命周期、直觉触发、心跳协调、迁移守卫）

---

## 待实现细节

1. ⬜ 任务 6.5：`recall_with_intuition()` 便捷方法
2. ⬜ 任务 2.3 补充：LLM prompt 三语模板文件（`narrative/prompts/` 目录）
3. ⬜ 任务 7.2：ConnectionistTranslator 叙事格式翻译（DUAL_READ 阶段才需要）
第7批（迁移守卫+HostService+集成验证）  ← 依赖第6批的完整集成
```

## 注意事项

1. **每批完成后系统必须可运行**——不引入未完成的半成品
2. **不破坏现有功能**——Trace 读写、粒度退化、激活扩散等不受影响
3. **迁移阶段守卫**——DUAL_WRITE 阶段仅写入不读取（直觉触发除外）
4. **LLM 降级**——叙事编织 LLM 失败时退化为概念拼接，不报错中断
5. **agent_id 隔离**——所有新表包含 agent_id 字段，13个智能体各自独立
6. **不兜底**——错误完整暴露，不用 fallback 掩盖
7. **LLM prompt 三语同步**——叙事编织的 Episode/Saga 生成 prompt 需同步提供 zh-CN/en-US/ja-JP 三个版本
8. **统一数据库**——所有新增表（episodes/sagas/fragment_status/cognitive_entries/intuition_stopwords）使用 TraceStore 的数据库连接，不新建独立的 .db 文件
9. **Observer 不依赖新模块**——通知由 MemoryField 协调，Observer 无需导入 CS/NW