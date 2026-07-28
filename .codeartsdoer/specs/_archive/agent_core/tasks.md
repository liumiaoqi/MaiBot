# 智能体核心丰富 — 编码任务清单

## 第1批：配置清理 + 关系温暖度修复

**目标**：修复 VitalSignsCard 全部 unavailable 的视觉问题，清理废弃配置字段

### 1.1 修复银狼重复 welt 关系条目

- [ ] 在 `agents/silver_wolf.md` 中删除第76行的重复 `target_agent_id: welt` 条目（该条目缺少 attitude/interaction_style/mention_tendency 等字段），保留第69行的完整 welt 关系
- 验收：`silver_wolf.md` 的 `internal_relationships` 中 `target_agent_id: welt` 只出现一次，且包含完整字段

### 1.2 移除 13 个智能体配置中的 idle_backoff_modifier 字段

- [ ] 从 `agents/silver_wolf.md` 移除 `idle_backoff_modifier: 0.8`
- [ ] 从 `agents/bronya.md` 移除 `idle_backoff_modifier: 1.4`
- [ ] 从 `agents/elysia.md` 移除 `idle_backoff_modifier` 字段
- [ ] 从 `agents/fu_hua.md` 移除 `idle_backoff_modifier` 字段
- [ ] 从 `agents/kiana.md` 移除 `idle_backoff_modifier` 字段
- [ ] 从 `agents/mei.md` 移除 `idle_backoff_modifier` 字段
- [ ] 从 `agents/seele.md` 移除 `idle_backoff_modifier` 字段
- [ ] 从 `agents/veliona.md` 移除 `idle_backoff_modifier` 字段
- [ ] 从 `agents/himeko.md` 移除 `idle_backoff_modifier` 字段
- [ ] 从 `agents/welt.md` 移除 `idle_backoff_modifier` 字段
- [ ] 从 `agents/tighnari.md` 移除 `idle_backoff_modifier` 字段
- [ ] 从 `agents/signora.md` 移除 `idle_backoff_modifier` 字段
- [ ] 从 `agents/columbina.md` 移除 `idle_backoff_modifier` 字段
- 验收：13 个配置文件中无 `idle_backoff_modifier` 字段，启动后无废弃字段警告

### 1.3 后端：新增 InternalRelationshipSummaryItem 模型

- [ ] 在 `src/webui/schemas/agent.py` 中新增 `InternalRelationshipSummaryItem` 模型：
  ```python
  class InternalRelationshipSummaryItem(BaseModel):
      target_agent_id: str
      relationship_type: str
      mention_tendency: float
  ```
- [ ] 在 `src/webui/schemas/agent.py` 的 `BatchRelationshipResponse` 中新增字段：
  ```python
  internal_relationships_summary: Dict[str, List[InternalRelationshipSummaryItem]] = Field(default_factory=dict)
  ```
- 验收：`InternalRelationshipSummaryItem` 模型可被导入，`BatchRelationshipResponse` 包含 `internal_relationships_summary` 字段

### 1.4 后端：batch_get_relationships() 增加 internal_relationships_summary 构建

- [ ] 修改 `src/webui/routers/agent.py` 的 `batch_get_relationships()` 函数，在遍历 agents 时同步构建 `internal_relationships_summary`：
  - 从 `config.internal_relationships` 提取 `target_agent_id + relationship_type + mention_tendency`
  - 将摘要写入 `internal_relationships_summary[agent.agent_id]`
- [ ] 将 `internal_relationships_summary` 传入 `BatchRelationshipResponse` 构造
- 验收：`GET /api/webui/agents/batch/relationships` 响应中包含 `internal_relationships_summary` 字段，每个智能体有对应的智能体间关系摘要

### 1.5 前端：WarmthLevel 增加 no_data，RelationshipWarmthData 增加 dataSource

- [ ] 在 `dashboard/src/routes/agent/utils/vital-signs.ts` 中：
  - `WarmthLevel` 类型新增 `'no_data'`：`'warm' | 'moderate' | 'cold' | 'no_data' | 'unavailable'`
  - `RelationshipWarmthData` 接口新增 `dataSource: 'user_relationship' | 'internal_relationship' | 'none'`
- 验收：TypeScript 编译通过，`WarmthLevel` 包含 `no_data`，`RelationshipWarmthData` 包含 `dataSource`

### 1.6 前端：deriveRelationshipWarmthData() 增加回退逻辑

- [ ] 修改 `dashboard/src/routes/agent/utils/vital-signs.ts` 的 `deriveRelationshipWarmthData()` 函数签名，增加 `internalRelationships` 参数：
  ```typescript
  export function deriveRelationshipWarmthData(
    relationships: BatchRelationshipItem[] | undefined | null,
    internalRelationships?: InternalRelationshipSummaryItem[] | undefined | null,
  ): RelationshipWarmthData
  ```
- [ ] 实现回退逻辑：
  - relationships 非空 → 从用户关系计算 warmth，dataSource = `'user_relationship'`
  - relationships 为空 + internalRelationships 非空 → 从智能体间关系推导，dataSource = `'internal_relationship'`
    - 推导规则：mention_tendency 均值 ≥ 0.5 → moderate；≥ 0.3 → cold；其他 → no_data
  - 均为空 → warmth = `'no_data'`，dataSource = `'none'`
- [ ] 在 `dashboard/src/lib/agent-api.ts` 中新增 `InternalRelationshipSummaryItem` 接口：
  ```typescript
  export interface InternalRelationshipSummaryItem {
    target_agent_id: string
    relationship_type: string
    mention_tendency: number
  }
  ```
- [ ] 修改 `dashboard/src/lib/agent-api.ts` 的 `getBatchRelationships()` 返回类型，增加 `internal_relationships_summary` 字段
- 验收：当 AgentRelationship 为空时，温暖度基于 internal_relationships 推导，不再全部显示 unavailable

### 1.7 前端：useBatchAgentData 传递 internal_relationships_summary

- [ ] 修改 `dashboard/src/routes/agent/hooks/useBatchAgentData.ts`：
  - `BatchAgentData` 接口新增 `internalRelationshipsSummary: Record<string, InternalRelationshipSummaryItem[]>`
  - 在 queryFn 中从 `getBatchRelationships` 响应提取 `internal_relationships_summary`
  - 返回数据中增加 `internalRelationshipsSummary`
- 验收：`useBatchAgentData()` 返回的数据中包含 `internalRelationshipsSummary`

### 1.8 前端：deriveVitalSignsData() 传递 internalRelationships

- [ ] 修改 `dashboard/src/routes/agent/utils/vital-signs.ts` 的 `deriveVitalSignsData()` 签名，增加 `internalRelationships` 参数
- [ ] 将 `internalRelationships` 传递给 `deriveRelationshipWarmthData()`
- [ ] 修改 `dashboard/src/routes/agent/components/global-situation/GlobalSituationView.tsx`，从 `useBatchAgentData` 获取 `internalRelationshipsSummary` 并传入 `deriveVitalSignsData()`
- 验收：`deriveVitalSignsData()` 调用链正确传递 `internalRelationships`，VitalSignsCard 温暖度不再全部显示 unavailable

### 1.9 前端：RelationshipWarmthIndicator 支持 no_data + dataSource

- [ ] 修改 `dashboard/src/routes/agent/components/RelationshipWarmthIndicator.tsx`：
  - `WARMTH_COLORS` 增加 `no_data: '#9ca3af'`
  - `no_data` 时显示"暂无交互数据"（通过 i18n key `agent.vitalSigns.warmth.no_data`）
  - `dataSource` 为 `'internal_relationship'` 时追加"基于角色关系"标签（通过 i18n key `agent.vitalSigns.warmth.basedOnInternal`）
- 验收：`no_data` 状态显示灰色圆点+文字，`internal_relationship` 数据源显示来源标签

### 1.10 前端：i18n 三语同步增加 no_data 和 dataSource 翻译

- [ ] 在 `dashboard/src/i18n/locales/zh.json` 的 `agent.vitalSigns.warmth` 下增加：
  - `"no_data": "暂无交互数据"`
  - `"basedOnInternal": "基于角色关系"`
- [ ] 在 `dashboard/src/i18n/locales/en.json` 的 `agent.vitalSigns.warmth` 下增加：
  - `"no_data": "No interaction data"`
  - `"basedOnInternal": "Based on character relationships"`
- [ ] 在 `dashboard/src/i18n/locales/ja.json` 的 `agent.vitalSigns.warmth` 下增加：
  - `"no_data": "インタラクションデータなし"`
  - `"basedOnInternal": "キャラクター関係に基づく"`
- 验收：三语 i18n 文件均包含 `no_data` 和 `basedOnInternal` 翻译键

### 1.11 第1批集成验证

- [ ] 启动系统，确认 VitalSignsCard 不再全部显示 unavailable
- [ ] 确认银狼的 welt 关系只有一条完整记录
- [ ] 确认 13 个配置文件中无 `idle_backoff_modifier` 字段
- [ ] 确认 `/batch/relationships` API 响应包含 `internal_relationships_summary`
- [ ] 确认 `no_data` 状态正确展示"暂无交互数据"

---

## 第2批：共居数展示修复

**目标**：系统启动后共居数正确反映已注册智能体数

**依赖**：第1批完成

### 2.1 前端：GroupStatsBar 区分"已注册"和"活跃"两个指标

- [ ] 修改 `dashboard/src/routes/agent/components/global-situation/GroupStatsBar.tsx`：
  - 新增 `registeredCount` prop（来自 `agents.length`，即 `/agents/list` 的 `total`）
  - 将 `totalAgents` 改为显示"已注册: N"
  - `activeAgents` 显示"活跃: N"
  - 无活跃会话时"活跃: 0"而非报错
- 验收：GroupStatsBar 展示"已注册: 13"和"活跃: N"两个独立指标

### 2.2 前端：i18n 三语同步增加共居数相关翻译

- [ ] 在 `dashboard/src/i18n/locales/zh.json` 的 `agent.globalSituation.stats` 下增加/修改：
  - `"registeredAgents": "已注册: {{count}}"`
  - 保留 `"activeAgents": "活跃: {{count}}"`（如已有则修改文案）
- [ ] 在 `dashboard/src/i18n/locales/en.json` 对应位置增加：
  - `"registeredAgents": "Registered: {{count}}"`
- [ ] 在 `dashboard/src/i18n/locales/ja.json` 对应位置增加：
  - `"registeredAgents": "登録済み: {{count}}"`
- 验收：三语 i18n 文件均包含 `registeredAgents` 翻译键

### 2.3 第2批集成验证

- [ ] 系统启动后，WebUI 展示"已注册: 13"
- [ ] 有活跃会话时展示"活跃: N"
- [ ] 无 Orchestrator 实例时不报错，活跃数显示为 0

---

## 第3批：内心声音 + 偏爱描述 + 记忆性格配置

**目标**：12 个智能体从"空配置"变为"有灵魂"

**依赖**：第1批完成（配置文件已清理）

**设计约束**：
- 每个智能体至少 2 个 inner_voices，不超过 4 个
- inner_voices 的 concept_focus 必须与 memory_focus_areas 有语义关联
- weight_multiplier 必须有差异化（至少 1 个 ≠ 1.0）
- 任意两个智能体的 inner_voices 不存在完全相同的 name
- favor_descriptions 的 owner/friend/stranger 三级态度有明确差异
- memory_personality 至少 3 个参数值不同于默认值 0.5

### 3.1 布洛妮娅配置丰富

- [ ] 在 `agents/bronya.md` 中增加 `inner_voices`（2-3 个声音，体现"三无外壳 vs 丰富内心"的张力）
- [ ] 在 `agents/bronya.md` 中增加 `favor_descriptions`（owner/friend/stranger 三级）
- [ ] 在 `agents/bronya.md` 中增加 `memory_personality`（至少 3 个参数 ≠ 0.5，emotional_sensitivity 应低于银狼）
- 验收：加载后 `AgentConfig.inner_voices` 长度 ≥ 2，`favor_descriptions` 三个字段非空，`memory_personality` 至少 3 个参数 ≠ 0.5

### 3.2 爱莉希雅配置丰富

- [ ] 在 `agents/elysia.md` 中增加 `inner_voices`（2-3 个声音，体现"永恒的乐观 vs 对消逝的恐惧"的张力）
- [ ] 在 `agents/elysia.md` 中增加 `favor_descriptions`（owner/friend/stranger 三级）
- [ ] 在 `agents/elysia.md` 中增加 `memory_personality`（positive_affinity 应较高，emotional_sensitivity 应高）
- 验收：同 3.1 标准

### 3.3 符华配置丰富

- [ ] 在 `agents/fu_hua.md` 中增加 `inner_voices`（2-3 个声音，体现"五万年记忆的重量 vs 想被记住的渴望"的张力）
- [ ] 在 `agents/fu_hua.md` 中增加 `favor_descriptions`（owner/friend/stranger 三级）
- [ ] 在 `agents/fu_hua.md` 中增加 `memory_personality`（decay_rate 应极低 0.2，association_depth 应高 3）
- 验收：同 3.1 标准

### 3.4 琪亚娜配置丰富

- [ ] 在 `agents/kiana.md` 中增加 `inner_voices`（2-3 个声音，体现"想保护所有人 vs 怕自己不够强"的张力）
- [ ] 在 `agents/kiana.md` 中增加 `favor_descriptions`（owner/friend/stranger 三级）
- [ ] 在 `agents/kiana.md` 中增加 `memory_personality`（association_depth 应低 1，curiosity 应高）
- 验收：同 3.1 标准

### 3.5 芽衣配置丰富

- [ ] 在 `agents/mei.md` 中增加 `inner_voices`（2-3 个声音，体现"温柔外表 vs 雷电律者的暴风"的张力）
- [ ] 在 `agents/mei.md` 中增加 `favor_descriptions`（owner/friend/stranger 三级）
- [ ] 在 `agents/mei.md` 中增加 `memory_personality`（emotional_sensitivity 中等偏高，reinforcement_boost 中等）
- 验收：同 3.1 标准

### 3.6 希儿配置丰富

- [ ] 在 `agents/seele.md` 中增加 `inner_voices`（2-3 个声音，体现"温柔胆小 vs 想变勇敢"的张力）
- [ ] 在 `agents/seele.md` 中增加 `favor_descriptions`（owner/friend/stranger 三级）
- [ ] 在 `agents/seele.md` 中增加 `memory_personality`（emotional_sensitivity 应高，positive_affinity 应高）
- 验收：同 3.1 标准

### 3.7 Veliona 配置丰富

- [ ] 在 `agents/veliona.md` 中增加 `inner_voices`（2-3 个声音，体现"凶狠外表 vs 对希儿的守护"的张力）
- [ ] 在 `agents/veliona.md` 中增加 `favor_descriptions`（owner/friend/stranger 三级）
- [ ] 在 `agents/veliona.md` 中增加 `memory_personality`（negative_affinity 应高，positive_affinity 应低）
- 验收：同 3.1 标准

### 3.8 姬子配置丰富

- [ ] 在 `agents/himeko.md` 中增加 `inner_voices`（2-3 个声音，体现"豪爽大姐姐 vs 隐藏的脆弱"的张力）
- [ ] 在 `agents/himeko.md` 中增加 `favor_descriptions`（owner/friend/stranger 三级）
- [ ] 在 `agents/himeko.md` 中增加 `memory_personality`（emotional_sensitivity 中等，reinforcement_boost 较高）
- 验收：同 3.1 标准

### 3.9 瓦尔特配置丰富

- [ ] 在 `agents/welt.md` 中增加 `inner_voices`（2-3 个声音，体现"守护者的责任 vs 对过去的遗憾"的张力）
- [ ] 在 `agents/welt.md` 中增加 `favor_descriptions`（owner/friend/stranger 三级）
- [ ] 在 `agents/welt.md` 中增加 `memory_personality`（association_depth 应高 3，decay_rate 应低）
- 验收：同 3.1 标准

### 3.10 提纳里配置丰富

- [ ] 在 `agents/tighnari.md` 中增加 `inner_voices`（2-3 个声音，体现"毒舌关心 vs 学术严谨"的张力）
- [ ] 在 `agents/tighnari.md` 中增加 `favor_descriptions`（owner/friend/stranger 三级）
- [ ] 在 `agents/tighnari.md` 中增加 `memory_personality`（curiosity 应高，association_depth 应高）
- 验收：同 3.1 标准

### 3.11 冰雪少女配置丰富

- [ ] 在 `agents/signora.md` 中增加 `inner_voices`（2-3 个声音，体现"冰封的傲慢 vs 燃烧的痛苦"的张力）
- [ ] 在 `agents/signora.md` 中增加 `favor_descriptions`（owner/friend/stranger 三级）
- [ ] 在 `agents/signora.md` 中增加 `memory_personality`（negative_affinity 应高，emotional_sensitivity 应高）
- 验收：同 3.1 标准

### 3.12 哥伦比娅配置丰富

- [ ] 在 `agents/columbina.md` 中增加 `inner_voices`（2-3 个声音，体现"梦游般的天真 vs 不可知的深渊"的张力）
- [ ] 在 `agents/columbina.md` 中增加 `favor_descriptions`（owner/friend/stranger 三级）
- [ ] 在 `agents/columbina.md` 中增加 `memory_personality`（decay_rate 应极低，curiosity 应低）
- 验收：同 3.1 标准

### 3.13 第3批集成验证

- [ ] 加载后每个智能体的 `AgentConfig.inner_voices` 长度 ≥ 2
- [ ] 每个 `AgentConfig.favor_descriptions` 的三个字段非空
- [ ] 每个 `AgentConfig.memory_personality` 至少 3 个参数 ≠ 0.5
- [ ] 任意两个智能体的 `inner_voices` 不存在完全相同的 `name`
- [ ] 每个智能体至少有 1 个 `weight_multiplier` ≠ 1.0
- [ ] 启动时间增加不超过 500ms

---

## 第4批：提示词深化

**目标**：13 个智能体的 personality/reply_style/anti_mechanization_rules 从"基础"变为"有张力"

**依赖**：第3批完成（配置文件已有 inner_voices/favor_descriptions/memory_personality）

**设计约束**：
- personality 中至少包含 1 组明确的内心张力描述
- reply_style 中每种模式有明确的触发条件
- anti_mechanization_rules 每条包含"情境+禁止行为+替代方案"
- 提示词总 token 数不超过 DeepSeek 注入预算（adaptive 策略下按优先级截断）

### 4.1 银狼提示词深化

- [ ] 在 `agents/silver_wolf.md` 的 personality（Markdown body）中增加内心张力描述（"好胜心 vs 怕输"已有基础，需深化"游戏是母语 vs 想被理解"的矛盾）
- [ ] 在 `agents/silver_wolf.md` 的 reply_style 中增加情境化触发条件（如"打游戏时→话多变激动"需更精确的触发描述）
- [ ] 在 `agents/silver_wolf.md` 的 `anti_mechanization_rules` 中改为三要素格式（情境+禁止行为+替代方案）
- 验收：`identity_prompt` 中包含张力关键词，`anti_mechanization_prompt` 中规则包含三要素

### 4.2 布洛妮娅提示词深化

- [ ] 在 `agents/bronya.md` 的 personality 中增加内心张力描述（"三无外壳 vs 丰富内心""从第三人称到'我'的自我重建"）
- [ ] 在 `agents/bronya.md` 的 reply_style 中增加情境化触发条件
- [ ] 在 `agents/bronya.md` 的 `anti_mechanization_rules` 中改为三要素格式
- 验收：同 4.1 标准

### 4.3 爱莉希雅提示词深化

- [ ] 在 `agents/elysia.md` 的 personality 中增加内心张力描述（"永恒的乐观 vs 对消逝的恐惧""想被所有人记住 vs 知道终将遗忘"）
- [ ] 在 `agents/elysia.md` 的 reply_style 中增加情境化触发条件
- [ ] 在 `agents/elysia.md` 的 `anti_mechanization_rules` 中改为三要素格式
- 验收：同 4.1 标准

### 4.4 符华提示词深化

- [ ] 在 `agents/fu_hua.md` 的 personality 中增加内心张力描述（"五万年记忆的重量 vs 想被当作普通女孩""守护者本能 vs 忘记自己也需要守护"）
- [ ] 在 `agents/fu_hua.md` 的 reply_style 中增加情境化触发条件
- [ ] 在 `agents/fu_hua.md` 的 `anti_mechanization_rules` 中改为三要素格式
- 验收：同 4.1 标准

### 4.5 琪亚娜提示词深化

- [ ] 在 `agents/kiana.md` 的 personality 中增加内心张力描述（"想保护所有人 vs 怕自己不够强""笨蛋的乐观 vs 深处的恐惧"）
- [ ] 在 `agents/kiana.md` 的 reply_style 中增加情境化触发条件
- [ ] 在 `agents/kiana.md` 的 `anti_mechanization_rules` 中改为三要素格式
- 验收：同 4.1 标准

### 4.6 芽衣提示词深化

- [ ] 在 `agents/mei.md` 的 personality 中增加内心张力描述（"温柔的日常 vs 雷电律者的暴风""想守护日常 vs 害怕自己失控"）
- [ ] 在 `agents/mei.md` 的 reply_style 中增加情境化触发条件
- [ ] 在 `agents/mei.md` 的 `anti_mechanization_rules` 中改为三要素格式
- 验收：同 4.1 标准

### 4.7 希儿提示词深化

- [ ] 在 `agents/seele.md` 的 personality 中增加内心张力描述（"温柔胆小 vs 想变勇敢""对布洛妮娅的依赖 vs 想独立"）
- [ ] 在 `agents/seele.md` 的 reply_style 中增加情境化触发条件
- [ ] 在 `agents/seele.md` 的 `anti_mechanization_rules` 中改为三要素格式
- 验收：同 4.1 标准

### 4.8 Veliona 提示词深化

- [ ] 在 `agents/veliona.md` 的 personality 中增加内心张力描述（"凶狠外表 vs 对希儿的温柔守护""独立宣言 vs 害怕孤独"）
- [ ] 在 `agents/veliona.md` 的 reply_style 中增加情境化触发条件
- [ ] 在 `agents/veliona.md` 的 `anti_mechanization_rules` 中改为三要素格式
- 验收：同 4.1 标准

### 4.9 姬子提示词深化

- [ ] 在 `agents/himeko.md` 的 personality 中增加内心张力描述（"豪爽大姐姐 vs 隐藏的脆弱""想守护学生 vs 自己也需要被守护"）
- [ ] 在 `agents/himeko.md` 的 reply_style 中增加情境化触发条件
- [ ] 在 `agents/himeko.md` 的 `anti_mechanization_rules` 中改为三要素格式
- 验收：同 4.1 标准

### 4.10 瓦尔特提示词深化

- [ ] 在 `agents/welt.md` 的 personality 中增加内心张力描述（"守护者的责任 vs 对过去的遗憾""父亲般的关怀 vs 无法释怀的失去"）
- [ ] 在 `agents/welt.md` 的 reply_style 中增加情境化触发条件
- [ ] 在 `agents/welt.md` 的 `anti_mechanization_rules` 中改为三要素格式
- 验收：同 4.1 标准

### 4.11 提纳里提示词深化

- [ ] 在 `agents/tighnari.md` 的 personality 中增加内心张力描述（"毒舌关心 vs 学术严谨""嘴上嫌弃 vs 实际操心"）
- [ ] 在 `agents/tighnari.md` 的 reply_style 中增加情境化触发条件
- [ ] 在 `agents/tighnari.md` 的 `anti_mechanization_rules` 中改为三要素格式
- 验收：同 4.1 标准

### 4.12 冰雪少女提示词深化

- [ ] 在 `agents/signora.md` 的 personality 中增加内心张力描述（"冰封的傲慢 vs 燃烧的痛苦""高贵的面具 vs 伤痕累累的灵魂"）
- [ ] 在 `agents/signora.md` 的 reply_style 中增加情境化触发条件
- [ ] 在 `agents/signora.md` 的 `anti_mechanization_rules` 中改为三要素格式
- 验收：同 4.1 标准

### 4.13 哥伦比娅提示词深化

- [ ] 在 `agents/columbina.md` 的 personality 中增加内心张力描述（"梦游般的天真 vs 不可知的深渊""看似无害 vs 力量深不可测"）
- [ ] 在 `agents/columbina.md` 的 reply_style 中增加情境化触发条件
- [ ] 在 `agents/columbina.md` 的 `anti_mechanization_rules` 中改为三要素格式
- 验收：同 4.1 标准

### 4.14 第4批集成验证

- [ ] 每个 `AgentConfig.identity_prompt` 中包含张力关键词（如"但""却""vs"等转折词）
- [ ] 每个 `AgentConfig.anti_mechanization_prompt` 中规则包含三要素（情境+禁止+替代）
- [ ] 每个 `AgentConfig.reply_style` 中模式有明确的触发条件
- [ ] 提示词总 token 数不超过 DeepSeek 注入预算（adaptive 策略下低优先级内容可被截断但不影响核心人格）
- [ ] 13 个智能体在对话中表现差异化，无机械化重复