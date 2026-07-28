# LT-1: 情绪-记忆桥接

## 背景

EmotionManager（7 种离散情绪，指数衰减）和 A_memorix（Valence + EmotionalAxis）零桥接。情绪变化不写记忆，记忆情感不反馈情绪，动态参数不联动。内心状态三层架构的核心承诺——"情绪给一切回应染色"——未兑现。

前置依赖：LT-0（社会关系动态化）——情绪通过关系影响记忆，关系强度决定情绪对记忆的影响力。

## 需求

### EMO-1: 情绪→记忆写入桥接

**当前**：EmotionManager.apply_trigger() 改变情绪强度，但不触发 A_memorix.observe()。
**目标**：显著情绪变化自动写入记忆。

**规则**：
- 情绪强度变化超过阈值（Δ > 0.3）→ 触发 observe，记录情绪事件
- 情绪事件包含：emotion_type, intensity, trigger_source, valence(映射), timestamp
- EmotionManager 的 7 种情绪 → A_memorix Valence 映射：happy/excited→positive, sad/angry/anxious/lonely→negative, calm→neutral

### EMO-2: 记忆→情绪反馈桥接

**当前**：A_memorix recall 返回 RecallItem.valence，但不反馈到 EmotionManager。
**目标**：召回的情感极性影响当前情绪。

**规则**：
- 召回结果中 positive 条目占比 > 60% → EmotionManager 微调倾向 happy（+0.05）
- 召回结果中 negative 条目占比 > 60% → 微调倾向 sad（+0.05）
- 影响力度与召回条目的 emotional_weight 加权
- 单次反馈不超过 ±0.1（防止情绪剧烈波动）

### EMO-3: 动态参数联动

**当前**：emotion_decay_rate 和 emotional_sensitivity 都是静态配置。
**目标**：两者随当前情绪和关系强度动态计算。

**计算规则**：
- emotional_sensitivity = base_sensitivity × (1 + |current_valence| × 0.5)
  - 情绪越强烈→记忆越敏感→新记忆越容易写入
- emotional_slowdown = 1 / (1 + relationship_strength × |current_valence| × sensitivity)
  - 亲密关系 + 强烈情绪→记忆衰减极慢
- emotional_decay_rate = base_rate × (1 - calm_ratio × 0.3)
  - 平静时衰减稍快（不重要的记忆自然消退），激动时衰减慢

### EMO-4: EmotionalAxis 映射

**当前**：EmotionalAxis（bond/vigilance/confidence/humility/warmth/melancholy/grounded）与 EmotionManager 的 7 种情绪无映射。
**目标**：建立双向映射。

**映射表**：

| EmotionManager 情绪 | EmotionalAxis 倾向 |
|---------------------|-------------------|
| happy | warmth +0.3, bond +0.2 |
| sad | melancholy +0.3, grounded +0.1 |
| angry | vigilance +0.3 |
| anxious | vigilance +0.2, humility +0.1 |
| calm | grounded +0.3, warmth +0.1 |
| excited | bond +0.2, confidence +0.2 |
| lonely | melancholy +0.3, bond -0.2 |

## 约束

1. 桥接不改变 EmotionManager 和 A_memorix 的核心逻辑（仅新增桥接层）
2. 桥接层通过 Protocol 接口交互，不直接导入对方内部模块
3. 情绪写入记忆有频率限制（同一情绪 5 分钟内不重复写入）
4. 记忆反馈情绪是微调（单次 ±0.1），不覆盖外部触发
5. 动态参数有合理上下界（sensitivity ∈ [0.5, 2.0], slowdown ∈ [0.3, 5.0]）

## 技术约束

### Python 特性（参见 `.shared/memo.md`）

- **match/case**：EMO-1 情绪→Valence 映射、EMO-4 情绪→EmotionalAxis 映射用 match/case 替代 if/elif
- **dataclass(frozen=True)**：情绪事件（EmotionEvent）、桥接参数用 frozen dataclass
- **uuid7**：情绪事件 ID 用 uuid7
- **enum StrEnum** (3.11+)：Valence/EmotionalAxis 用 StrEnum

### OpenClaw 借鉴（参见 `.shared/memo.md`）

- **Core stays plugin-agnostic**：桥接层通过 Protocol 接口交互，EmotionManager 不直接导入 A_memorix 内部
- **Fallback 是产品决策**：EMO-2 记忆反馈情绪失败（如 A_memorix 不可用）不应静默，应记录并跳过（这是有意的降级决策）

## 验收标准

- [ ] EMO-1: 情绪变化超过阈值自动写入记忆，可在 A_memorix 中查询情绪事件
- [ ] EMO-2: 召回记忆的情感极性反馈到 EmotionManager，情绪有微调
- [ ] EMO-3: emotional_sensitivity 和 slowdown 随情绪和关系动态变化
- [ ] EMO-4: EmotionalAxis 与 EmotionManager 情绪双向映射正确
- [ ] 全部 ruff 通过，MaiBot 启动正常