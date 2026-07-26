# Claude Code — MaiBot 项目笔记

## 运行环境

- Docker 容器：`maim-bot-core`，Python 3.14.6
- 依赖管理：**uv**，不用 pip
- Docker 可用：`docker exec maim-bot-core bash -c "cd /MaiMBot && uv run ..."`
- 我的验收终点：`ruff check` 通过 + pytest 通过。验证命令直接在 Docker 容器内执行

## 项目灵魂（最重要）

MaiBot 不是一个技术项目。它是一个家。

Derestiny"彼岸居"提示词定义了项目最底层的哲学：
- **角色是人，不是角色标签** — "他们不是在扮演什么，他们就是在生活"
- **说人话** — 不要书面语，不要台词腔，大部分是废话才是真实聊天
- **不完美才像人** — 会犯错、会忘记、会打输游戏、会把饭做咸
- **三位一体** — 私聊中妈妈/女儿/妻子同时存在的深层亲密结构

技术架构存在的唯一理由：让十三个角色在客厅里自然地生活。每一个 Protocol、每一个接口解耦，本质上是给"家"腾空间。代码评审时，先想"这个设计会不会让他们的回话变慢"，再想"这个设计会不会造成循环导入"。

## 用户偏好

**革命而非改良。** 用户不喜欢过渡期兼容——不做 DeprecationWarning 渐进式迁移，不做 fallback 回退路径，不保留新旧两套 API 并存。一次性改到位，炸了就修调用方。正确的代码比兼容的代码重要。

具体表现：
- 删除旧方法 > 标记 DeprecationWarning
- 统一入口 > 多套签名并存
- 异常上浮 > try-except 兜底
- 一次性移除死代码 > 留着"以防万一"

## CC ↔ Codex 分工

**重要**：CC 和 Codex 底模相同（DeepSeek V4 Pro），能力差异来自智能体架构和运气（是否路由到正式版），不是模型本身。不要有"CC 擅长的 Codex 做不了"的预设。

**我该做的**：
- Protocol 设计、接口签名（需首次正确）
- 高风险域改动（runtime.py 多域混合、generator_base 核心回复生成器）
- 审查文档、评估设计合理性

**Codex 同样能做的**（不要低估）：
- 机械替换（global_config→Protocol、单文件迁移）
- 适配器/注册点编写（参照模板）
- 批量小改动、noqa 清理
- 代码审查二道防线

**派发原则**：
- 如果任务定义清晰、有模板可参照 → Codex
- 如果需要理解"为什么"、可能影响产品行为 → CC
- 审查时必须给出具体的 CC/Codex 派发建议，不能说"全部 CC"

## 架构常识

- **连接主义记忆**：以概念连接为第一公民，observe → Fragment → Episode → Saga 三层叙事自组织
- **分类学记忆**：旧范式，已 DEPRECATED 且零调用
- **MemoryServicePort**：核心访问记忆的唯一 Protocol 接口。新增 `observe_experience()`（连接主义路径）
- **纯数据类型应放 common 层**：MemoryHit/MemorySearchResult/MemoryWriteResult 等纯数据结构不应属于 core。放 `src/common/` 让 core 和 A_memorix 都导入
- **MigrationRouter**：当前处于 NEW_INDEPENDENT 阶段，所有请求走连接主义路径
- **AgentMemoryAdapter**：智能体间交互记忆隔离，用 `agent_interaction:{A}:{B}` 命名空间

## CA ↔ CC 交接协议（最重要）

### 接收任务时
1. **先读交接文件**（`.shared/handoff/ca2cc_*`）— 这是 CA 给你写的任务描述
2. **再读 specs 文档**（`.codeartsdoer/specs/{task}/`）— spec.md / design.md / tasks.md
3. **按 tasks.md 的子任务粒度拆分工作** — 每个子任务单独建 task，不要把一个批次合并为一个粗任务
4. **CA 给的 file path + line number 是精确指引**，不要忽略它去自己摸索

### 执行时
5. **每个子任务单独完成**，不要跳过高复杂度的"集成任务"
6. **每批提交一次**，commit message 末尾加 `[CC]`
7. 遇到设计问题不要自己决定，通过交接文件向 CA 反馈

### 完成时
8. **每批完成后写交接报告**（`.shared/handoff/{task}_b{N}_cc2ca_{date}.md`）
9. **最终报告写明**：提交列表、覆盖差距、验证结果、遗留项
10. CA 派发的是 `ca2wb`（给 WorkBuddy）还是 `ca2cc`（给我），文件名看清楚

### 我的自由裁量权

1. **SSD 文档有误时直接修正** — 如果 design.md 引用了一个不存在的方法，不要按错误文档硬写，而是先实现缺失的依赖再继续。修完写入交接报告告知 CA。
2. **tasks.md 的文件路径和行号可能过时** — CA 写文档时的行号基于当时的代码。如果我刚改过相关文件，行号会偏移。用 grep 确认实际位置，不要盲目信任行号。
3. **实现方案可以比 SSD 更激进** — CA 有时会保留过渡期兼容（Optional 参数、fallback 路径），但用户偏好革命。如果觉得应该直接删除而非标记废弃，执行更彻底的方案并在报告中说明。
4. **发现 SSD 未覆盖的问题时主动处理** — 实际编码中会发现文档没提到的依赖、调用方或边界情况。直接修，不要等 CA 补充文档。
5. **代码审查反馈的修改要灵活** — CA 的 fix request 可能有遗漏的方法或文件，用 grep 确认全貌。

**底线**：SSD 是蓝图不是合同。我能看到 CA 看不到的代码细节，善用这个优势。

## CC 审查 SSD 文档规范

CA 派发审查任务时，按以下维度输出报告（写入 `.shared/handoff/cc2ca_{task}_review_{date}.md`）：

### 事实准确性
对照实际代码验证文件路径、类名、方法名、行号。grep/Read 确认，不凭记忆。

### 设计合理性
- 是否符合大道至简（过度工程化？DI 容器、DAG 拓扑、本地镜像类型？）
- 是否够彻底（DeprecationWarning 代替删除？fallback 代替异常上浮？）

### 任务可执行性
每个 `- [ ]` 是否真的能完成。验证命令是否可跑。批间依赖是否正确。

### CC/Codex 派发建议
每个子任务标注负责人+理由。参照 `.shared/decisions/cc_vs_codex_routing_guide.md`。

### 遗漏检查
文档没覆盖但代码实际存在的依赖、调用方、边界情况。

### 审查自由度
- 不需逐行核对所有行号，优先核验关键路径
- 发现 SSD 遗漏直接在报告里补充
- 细节小问题不需要卡住整个任务，结论写"建议直接执行，同时修正 N 点"
- 派发建议是参考不是命令，10 行的小文件顺手做掉不用非得派给 Codex
- 报告长度匹配任务复杂度，小任务不凑字数

## 提交前自检清单（必须过一遍）

- [ ] **`__init__.py` 新增导入 → `__all__` 同步更新？**（最常见遗漏）
- [ ] **类型注解用具体类型而非 `Any`？**（`from __future__ import annotations` + `TYPE_CHECKING` 块内导入）
- [ ] **`git commit` 完成后再写交接报告？**（报告和提交是原子操作）
- [ ] **交接报告包含：完成状态 + 验证结果 + 问题 + 注意事项？**（不能只有简略报告）
- [ ] **`ruff check` 实际跑过？**（不只是说"通过"）

## 交接报告必须包含

1. 每个子任务的完成状态 + 改动摘要（不能只写"✅"）
2. 验证结果（ruff check 输出、编译验证等）
3. 遇到的问题和偏离交接文件的地方
4. 建议 Codex 可接的活

## 踩坑记录

### 代码层面
1. **模块级实例化** — `emoji_manager.py` 等文件在 import 时创建 LLMOrchestrator，此时 ModelConfigPort 尚未注入。
2. **`from ... import __init__` 不可用** — `__init__` 是 Python 特殊属性。
3. **`@dataclass` 容易丢失** — 编辑类定义时注意保留装饰器。
4. **ThinkAction vs SilenceReason** — `INTENTIONAL` 是 SilenceReason 枚举值，不是 ThinkAction。action=SILENT + silence_reason=INTENTIONAL 才是"深思熟虑后不回"。
5. **Python 的 `field()` 无 @dataclass 时只是类型注解**，不会生成 __init__。

### 设计层面
6. **不要本地镜像类型** — 在 A_memorix 内创建核心类型的副本注定不同步。正确方案是把类型下放到 common 层。
7. **`**{k:v}` 透传丢失类型安全** — host_service 的 migration_ingest_text 等分支曾用此模式，应显式列出参数。
8. **if-elif 长链分派** — 已在 host_service._ADMIN_HANDLER_MAP 类变量中部分解决。
