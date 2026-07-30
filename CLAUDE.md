# Claude Code — MaiBot 项目笔记

> 工作手册。硬性规则见 `AGENTS.md`，架构哲学见 `.codeartsdoer/rule/MaiBot智能体自主性架构.mdc`，债务追踪见 `.codeartsdoer/specs/memo/zg_cast_bone_research.md`。

## Python 3.14 速查（写新代码必读）

详细版：`.shared/decisions/python314_new_code_cheatsheet.md`
精简版：`.shared/decisions/python314_features.md`

**写新代码时必须遵守**：
- `from __future__ import annotations` — **禁止**（3.14 默认延迟求值）
- `uuid.uuid4()` — 仅用于临时/安全场景（token、nonce）；数据存储主键用 `uuid.uuid7()`
- `zip(a, b)` — **禁止无 strict**；要么 `strict=True`（理应等长）要么 `strict=False`（显式允许不等）
- 新并发代码首选 `asyncio.TaskGroup`，替代 `asyncio.gather`
- frozen dataclass 更新用 `copy.replace()`，替代 `dataclasses.replace()`

## 运行环境

- Docker 容器：`maim-bot-core`，Python 3.14.6
- 依赖管理：**uv**，不用 pip
- Docker 可?用：`docker exec maim-bot-core bash -c "cd /MaiMBot && uv run ..."`
- 我的验收终点：`ruff check` 通过 + pytest 通过。验证命令直接在 Docker 容器内执行

## 项目灵魂

MaiBot 不是一个技术项目，它是一个家。角色是人不是标签，说人话，不完美才像人。技术架构存在的唯一理由：让十三个角色在客厅里自然地生活。

## 用户偏好

**革命而非改良。** 不做 DeprecationWarning 渐进式迁移，不做 fallback 回退路径，不保留新旧两套 API 并存。一次性改到位，炸了就修调用方。

## 债务原则

- **拿未来换现在**（必须消除）：`except Exception: pass` 透支排障能力；绕过 Port 直接导入透支重构自由度
- **用现在换未来**（优先投入）：修 exception handling 换未来可追踪；集成欲望换主动说话
- **不影响未来**（低优先）：V1 getattr 残留、TODO 清理

债务全景详见 `.codeartsdoer/specs/memo/zg_cast_bone_research.md`。

## CC ↔ Codex 分工

CC 和 Codex 底模相同（DeepSeek V4 Pro），不要有"CC 擅长的 Codex 做不了"的预设。

- **CC 胜在**：Protocol 设计/接口签名（需首次正确）、高风险域改动、审查文档
- **Codex 胜在**：机械替换、适配器/注册点编写、批量改动、noqa 清理
- **派发**：任务定义清晰+有模板 → Codex；需理解"为什么"+可能影响产品行为 → CC

## CA ↔ CC 交接协议

### 接收任务时
1. **先读交接文件**（`.shared/handoff/ca2cc_*`）— CA 给你的任务描述
2. **再读 specs 文档**（`.codeartsdoer/specs/{task}/`）— spec.md / design.md / tasks.md
3. **按 tasks.md 的子任务粒度拆分工作** — 每个子任务单独建 task
4. **CA 给的 file path + line number 是精确指引**，不要忽略它去自己摸索

### 执行时
5. **每个子任务单独完成**，不要跳过高复杂度的"集成任务"
6. **每批提交一次**，commit message 末尾加 `[CC]`
7. 遇到设计问题不要自己决定，通过交接文件向 CA 反馈
8. 恰当使用子代理

### 完成时
9. **每批完成后写交接报告**（`.shared/handoff/{task}_b{N}_cc2ca_{date}.md`）
10. **最终报告写明**：提交列表、覆盖差距、验证结果、遗留项
11. CA 派发的是 `ca2wb`（给 WorkBuddy）还是 `ca2cc`（给我），文件名看清楚

### 我的自由裁量权

1. **SSD 文档有误时直接修正** — 先实现缺失的依赖再继续，修完写入交接报告
2. **tasks.md 行号可能过时** — 用 grep 确认实际位置
3. **实现方案可以比 SSD 更激进** — 用户偏好革命，直接删除而非标记废弃，在报告中说明
4. **发现 SSD 未覆盖的问题时主动处理** — 直接修，不等 CA 补充文档
5. **代码审查反馈的修改要灵活** — CA 的 fix request 可能有遗漏，用 grep 确认全貌

**底线**：SSD 是蓝图不是合同。

## CC 审查 SSD 文档规范

CA 派发审查任务时，按以下维度输出报告（写入 `.shared/handoff/cc2ca_{task}_review_{date}.md`）：

- **事实准确性**：对照代码验证路径、类名、行号，grep/Read 确认
- **设计合理性**：大道至简？够彻底？
- **任务可执行性**：每个 `- [ ]` 是否能完成，验证命令是否可跑
- **CC/Codex 派发建议**：每个子任务标注负责人+理由
- **遗漏检查**：文档没覆盖的依赖、调用方、边界情况
- **审查自由度**：不需逐行核对，小问题不卡住任务，报告长度匹配任务复杂度

## 提交前自检清单

- [ ] **`__init__.py` 新增导入 → `__all__` 同步更新？**
- [ ] **类型注解用具体类型而非 `Any`？**
- [ ] **`git commit` 完成后再写交接报告？**
- [ ] **交接报告包含：完成状态 + 验证结果 + 问题 + 注意事项？**
- [ ] **`ruff check` 实际跑过？**

## 踩坑记录

1. **模块级实例化** — `emoji_manager.py` 等文件在 import 时创建 LLMOrchestrator，此时 ModelConfigPort 尚未注入
2. **`from ... import __init__` 不可用** — `__init__` 是 Python 特殊属性
3. **`@dataclass` 容易丢失** — 编辑类定义时注意保留装饰器
4. **ThinkAction vs SilenceReason** — `INTENTIONAL` 是 SilenceReason 枚举值，action=SILENT + silence_reason=INTENTIONAL 才是"深思熟虑后不回"
5. **Python 的 `field()` 无 @dataclass 时只是类型注解**，不会生成 __init__
6. **不要本地镜像类型** — 在 A_memorix 内创建核心类型的副本注定不同步，正确方案是下放到 common 层

## .shared/ 写新文件规则

`.shared/` 是异步上下文共享区（git 子仓库），写新文件时必须遵守：

1. **头部元数据**：每个 .md 文件头部加 `> 最后更新：YYYY-MM-DD`，decisions/ 文件额外加状态标记（📚参考 / 🔬研究 / 🏗️设计 / 🔧工程）
2. **命名规范**：
   - decisions/：`snake_case.md`，主题一目了然
   - handoff/：`{src}2{dst}_{topic}_{date}.md`（如 `ca2cc_zg9_extreme_tuning_0731.md`）
   - research/：`snake_case_extracts.md`
3. **decisions/ 新文件必须更新 `_INDEX.md`**：加一行摘要+状态
4. **memo.md 不再堆内容**：新主题一律放 decisions/，memo.md 只加索引行指向
5. **active_tasks.md 只放当前活跃任务**：已完成的移入 roadmap.md 的"已完成里程碑"
6. **roadmap.md 状态与 research memo 同步**：改一个必须检查另一个
