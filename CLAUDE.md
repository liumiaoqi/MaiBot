# Claude Code — MaiBot 项目笔记

## 运行环境

- Docker 容器：`maim-bot-core`，Python 3.14.6
- 依赖管理：**uv**，不用 pip
- Docker 可用：`docker exec maim-bot-core bash -c "cd /MaiMBot && uv run ..."`
- 我的验收终点：`ruff check` 通过 + pytest 通过。验证命令直接在 Docker 容器内执行

## 活跃任务

详见 `.shared/active_tasks.md`

## 项目灵魂

MaiBot 不是一个技术项目，它是一个家。角色是人不是标签，说人话，不完美才像人。技术架构存在的唯一理由：让十三个角色在客厅里自然地生活。

## 用户偏好

**革命而非改良。** 不做 DeprecationWarning 渐进式迁移，不做 fallback 回退路径，不保留新旧两套 API 并存。一次性改到位，炸了就修调用方。

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
