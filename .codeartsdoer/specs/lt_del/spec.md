# LT-DEL: 灵台代码清算

## 背景

A_memorix 代码量 49,527 行 / 2.2 MB，目标 ~8,750 行。部分功能从未使用或与项目理念相悖，应先删除再重写，降低重写基线复杂度。

## 需求

### DEL-1: 删除模糊修改系统

**删除文件**：
- `src/A_memorix/core/runtime/services/fuzzy_modify.py`（1,052 行）
- `src/A_memorix/core/runtime/services/feedback_correction.py`（1,522 行）

**删除数据库表**：
- `memory_feedback_tasks`
- `memory_fuzzy_modify_plans`
- `paragraph_stale_relation_marks`

**删除引用**：
- `host_service.py` 中 `_dispatch` 对 fuzzy_modify/feedback 的路由分支
- `sdk_memory_kernel.py` 中对 FeedbackCorrectionService 的初始化和调用
- `metadata_store.py` 中 `ensure_feedback_schema()`、反馈相关 CRUD 方法
- `config` 中 feedback/fuzzy_modify 相关配置项

**理由**：从未使用，与"不兜底"理念相悖。预计删除 ~2,600 行。

### DEL-2: 删除老分类学架构

**删除文件**：
- `src/A_memorix/core/storage/knowledge_types.py`（182 行）
- `src/A_memorix/core/storage/type_detection.py`（136 行）

**删除枚举/函数**：
- `KnowledgeType` 枚举（structured/narrative/factual/quote/mixed）
- `ImportStrategy` 枚举
- `resolve_stored_knowledge_type()`、`validate_stored_knowledge_type()`、`detect_knowledge_type()`、`select_import_strategy()` 等函数
- `looks_like_narrative_text()`、`looks_like_factual_text()`、`looks_like_quote_text()`、`looks_like_structured_text()` 等启发式检测

**删除数据库列**：
- `paragraphs.knowledge_type` 列（降级为可选/默认 'mixed'，不删除列避免数据迁移）

**删除引用**：
- `web_import_manager.py` 中 KnowledgeType/ImportStrategy 导入和分类逻辑
- `metadata_store.py` 中 `normalize_paragraph_knowledge_types()`、`list_invalid_paragraph_knowledge_types()`、`get_knowledge_type_distribution()` 及 schema 迁移中 knowledge_type 相关代码
- `sdk_memory_kernel.py` 中 knowledge_type 参数传递
- `scripts/` 中 knowledge_type 校验逻辑

**替代**：导入时不再预分类，所有段落统一为 'mixed'。分类由认知分层（CognitiveStratifier）或未来涌现机制处理。

**理由**：规则式分类器粗糙不可靠（"然后"出现两次就算叙事？），是标本化思维。预计删除 ~800 行代码 + 大量引用简化。

### DEL-3: 删除水库采样训练

**删除代码**（在 `vector_store.py` 内）：
- `RESERVOIR_CAPACITY` 常量
- `_reservoir_samples`、`_reservoir_count` 属性
- `_add_to_reservoir()` 方法
- `_train_quantizer()` 方法
- `_replay_vectors_to_index()` 方法
- 启动时 reservoir→train→replay 流程
- `IndexFlatIP` 回退索引相关逻辑

**保留**：VectorStore 的 add/search/delete 基础功能、FP16 持久化、ID 映射。

**理由**：HNSW 不需要训练，水库采样整套逻辑可删。预计删除 ~200 行。

## 约束

1. 每个删除任务独立可提交，不依赖其他删除任务
2. 删除后 ruff 检查通过，无 dangling import
3. 删除后 MaiBot 可正常启动（记忆系统降级为无分类/无模糊修改，功能不缺失）
4. 不删除数据库列（避免数据迁移），仅删除代码引用和逻辑
5. 删除引用时保持调用链完整——被删功能的调用方要么删除调用，要么用默认值替代

## 技术约束

### Python 特性（参见 `.shared/memo.md`）

- **enum StrEnum** (3.11+)：DEL-2 删除 KnowledgeType 后，如需保留简化类型标记，用 StrEnum 替代 str Enum

### OpenClaw 借鉴（参见 `.shared/memo.md`）

- **Fallback 是产品决策**：DEL-1 删除的模糊修改本质是 fallback——"改不了就模糊改"，违反此原则
- **Lean code**："Refactors should delete about as much local complexity as they add"——纯删除任务天然满足

## 验收标准

- [ ] DEL-1: fuzzy_modify + feedback_correction 文件删除，所有引用清理，ruff 通过
- [ ] DEL-2: knowledge_types + type_detection 文件删除，所有引用清理，ruff 通过
- [ ] DEL-3: 水库采样代码删除，VectorStore 仍可正常 add/search，ruff 通过
- [ ] MaiBot 启动无报错，记忆系统基本功能正常
- [ ] 代码量减少 ≥3,600 行