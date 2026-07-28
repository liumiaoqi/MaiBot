# LT-3: 灵台存储架构重写

## 背景

当前存储层：MetadataStore 8,537 行（SQLite + FTS5 + jieba + schema v15 迁移）、VectorStore 924 行（Faiss SQ8 + 水库采样）、GraphStore 1,470 行（SciPy CSR + pickle）。总数据 584 MB，MetadataStore 占 82%。

## 需求

### STO-1: MetadataStore 拆分

将 8,537 行的 MetadataStore 拆为 4-5 个独立 Store：

| 新 Store | 职责 | 预计行数 |
|----------|------|---------|
| `ParagraphStore` | 段落 CRUD + FTS5 全文索引 | ~600 |
| `EntityStore` | 实体管理 + 实体-段落关联 | ~300 |
| `RelationStore9` | 关系 CRUD + 软删除 + 置信度更新 | ~400 |
| `ProfileStore` | 人物画像 + 画像快照 + 开关 | ~300 |
| `SchemaManager` | schema 版本管理 + 迁移执行 | ~200 |

**共享**：SQLite 连接池（单 WAL 模式连接）、FTS5 索引管理。

**原则**：
- 每个 Store 只暴露自身表的 CRUD，不跨 Store 调用
- 共享连接通过构造函数注入
- FTS5 由 ParagraphStore 独占管理

### STO-2: 向量索引迁移到 HNSW

**当前**：Faiss SQ8（需训练、水库采样、回放）
**目标**：Faiss HNSW（无需训练、直接 add、更高召回率）

**参数**：
- `M=32`（每个节点的邻居数）
- `ef_construction=200`（构建时搜索宽度）
- `ef_search=50`（搜索时搜索宽度）
- 度量：`METRIC_INNER_PRODUCT`（余弦相似度，L2 归一化后等价）

**迁移**：启动时检测旧 SQ8 索引→自动重建为 HNSW→保存新索引文件。一次性操作。

**删除**：水库采样训练代码（DEL-3 已覆盖）。

### STO-3: Schema 版本重置

**当前**：SCHEMA_VERSION = 15，启动时依次执行 v1→v2→...→v15 迁移链。
**目标**：SCHEMA_VERSION = 1，干净 schema。

**迁移策略**：
1. 新增 `lt_migrate_v15_to_v1.py` 一次性脚本
2. 脚本读取当前 v15 数据库→创建新 v1 数据库→数据转换写入
3. 转换完成后替换原文件
4. 运行时不再维护 v1→v15 迁移链

**v1 schema 设计**：
- 保留核心表：paragraphs、entities、relations、paragraph_relations、paragraph_entities
- 删除表：memory_feedback_tasks、memory_fuzzy_modify_plans、paragraph_stale_relation_marks
- 删除列：paragraphs.knowledge_type（或降级为可选默认 'mixed'）
- 保留 FTS5 虚拟表

### STO-4: GraphStore pickle→SQLite

**当前**：graph_metadata.pkl（3.0 MB pickle 文件，启动全量加载）
**目标**：节点/边元数据存入 SQLite，邻接矩阵保留 npz

**收益**：
- 消除 pickle 安全风险
- 支持增量加载（不需要全量读入内存）
- 与 MetadataStore 共享 SQLite 连接

### STO-5: 网页导入批量管道

**当前**：逐条嵌入 API + 逐条 DB 写入 + 逐条 Faiss add = N 次往返
**目标**：批量嵌入（64-128 条/次）→ 批量 SQLite executemany → 批量 Faiss add

**改造点**：
- `web_import_manager.py` 中段落写入循环改为批量累积
- 嵌入调用改为 `encode_batch()`
- SQLite 写入改为 `executemany()`
- Faiss 写入改为 `add_with_ids()` 批量调用

## 约束

1. STO-1 拆分不改变外部 API（host_service._dispatch 入口不变）
2. STO-2 HNSW 迁移向后兼容（能读取旧 SQ8 索引并自动重建）
3. STO-3 schema 重置提供一次性迁移脚本，不丢数据
4. STO-4 pickle→SQLite 迁移同样提供一次性脚本
5. STO-5 批量管道不改变导入结果的正确性
6. 每个子任务独立可提交

## 技术约束

### Python 特性（参见 `.shared/memo.md`）

- **match/case**：STO-1 拆分后 host_service._dispatch 用 match/case 替代 if 链路由
- **dataclass(frozen=True)**：新 Store 的配置/参数对象用 frozen dataclass
- **uuid7**：新 schema 的主键用 uuid7（时间排序，B-tree 索引友好）
- **zip(strict=True)**：STO-5 批量导入中 ID+向量并行迭代必须 strict=True
- **asyncio.TaskGroup**：STO-5 批量嵌入的并发任务用 TaskGroup 替代 gather
- **enum StrEnum** (3.11+)：RetrievalStrategy 等枚举用 StrEnum

### OpenClaw 借鉴（参见 `.shared/memo.md`）

- **SQLite-only storage**：STO-4 pickle→SQLite 对齐此原则——运行时状态统一进 SQLite
- **doctor --fix migration**：STO-3 schema 重置的迁移脚本即 doctor --fix 的雏形
- **Hot path 不重复发现**：STO-2 HNSW 索引启动时加载一次，检索时不再重新组装
- **Startup Trace**：STO-1 拆分后每个 Store 初始化测耗时，定位慢在哪
- **Crash Loop Breaker**：A_memorix 初始化失败降级为"记忆不可用"，不拖垮启动
- **Lean code**：MetadataStore 8537→~2000 行，净删除 >6000 行

## 验收标准

- [ ] STO-1: MetadataStore 拆为 5 个独立 Store，总行数 < 2,000
- [ ] STO-2: HNSW 索引正常 add/search，召回率 ≥ 98%
- [ ] STO-3: v15→v1 迁移脚本执行成功，新 schema 干净
- [ ] STO-4: GraphStore 元数据从 SQLite 读取，无 pickle 依赖
- [ ] STO-5: 网页导入 100 条段落耗时 < 当前耗时的 20%
- [ ] 全部 ruff 通过，MaiBot 启动正常