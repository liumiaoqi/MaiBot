# LT-2: 分类涌现机制

## 背景

当前分类体系：KnowledgeType（5 类，已删除）+ CognitiveStratifier（4 类，待研究）。核心问题：分类是标本化——给记忆钉标签再按标签处理，但记忆的属性是流动的。

前置依赖：LT-0（社会关系动态化）+ LT-1（情绪-记忆桥接）——分类应从关系和情绪中涌现，不从文本规则中推断。

## 需求（待研究，以下为研究方向而非确定方案）

### CLS-1: 调研——离散分类 vs 连续维度 vs 混合方案

**研究问题**：
1. 纯连续维度是否可行？记忆条目只有 confidence/decay_rate/detail_level/emotional_weight 四个浮点数，衰减率连续计算，无离散类别。
2. 离散分类 + 连续参数混合是否更实用？类别决定衰减函数族（如指数衰减 vs 证据依赖衰减），参数决定函数内位置。
3. 类别能否从连续参数中涌现？如 reinforcement_count > 50 自动视为 stable，无需显式标注。
4. Ebbinghaus 遗忘曲线 + 间隔重复理论能否统一建模，取代分类+衰减的双层结构？

**交付物**：调研报告 `.shared/decisions/lt2_classification_research.md`，含方案对比、推荐方案、实现路径。

### CLS-2: 实现分类涌现机制（基于 CLS-1 调研结论）

**待 CLS-1 完成后细化**。大致方向：
- 写入时不预分类，所有记忆统一为"未分类"状态
- 分类从交互证据中涌现（多次独立来源→stable，频繁提及→high confidence，情感强烈→slow decay）
- 分类可降级（stable_trait 长期无证据→dormant→tombstone）
- 分类是视角相关的（同一条记忆对亲密关系是 trait，对陌生关系是 hypothesis）

### CLS-3: 删除 CognitiveStratifier 硬分类（如 CLS-2 确定替代方案）

**条件**：CLS-2 实现后，如果新机制完全替代 CognitiveStratifier，则删除：
- `cognitive_stratifier.py` 的 8 条规则分类逻辑
- `CognitiveType` 枚举
- 证据系统保留（reinforcement_count/contradiction 等连续参数仍有价值）

## 约束

1. CLS-1 是纯研究，不修改任何代码
2. CLS-2 实现不破坏现有记忆数据的可读性（旧数据有 CognitiveType 标签，新数据可能没有）
3. 分类涌现不调 LLM（纯规则/统计，保持 ≤5ms）
4. 如果 CLS-1 结论是"保留离散分类+优化"，则 CLS-2 改为优化现有 CognitiveStratifier 而非替换

## 技术约束

### Python 特性（参见 `.shared/memo.md`）

- **match/case**：CLS-2 涌现规则的分支逻辑用 match/case
- **dataclass(frozen=True)**：分类结果快照用 frozen dataclass
- **enum StrEnum** (3.11+)：如保留离散分类，CognitiveType 用 StrEnum

### OpenClaw 借鉴（参见 `.shared/memo.md`）

- **Lean code**：CLS-3 删除 CognitiveStratifier 后，涌现机制代码量应 ≤ 删除量
- **Comment shape: why, not what**：涌现规则的注释说明"为什么这样涌现"而非"涌现了什么"

## 验收标准

- [ ] CLS-1: 调研报告完成，含 4 个研究问题的分析和推荐方案
- [ ] CLS-2: 分类涌现机制实现，记忆可自动从"未分类"涌现为具体类别
- [ ] CLS-3: 如需删除 CognitiveStratifier，删除后 ruff 通过
- [ ] 全部 ruff 通过，MaiBot 启动正常