# Claude Code — MaiBot 项目笔记

> 工作手册。硬性规则见 `AGENTS.md`，架构哲学见 `.codeartsdoer/rule/MaiBot智能体自主性架构.mdc`，债务追踪见 `.codeartsdoer/specs/memo/zg_cast_bone_research.md`。
.shared\decisions\review_gate_runbook_0801.md  CC调用CX指南
## Python 3.14 速查（写新代码必读）

详细版：`.shared/decisions/python314_new_code_cheatsheet.md`
精简版：`.shared/decisions/python314_features.md`

**写新代码时必须遵守**：
- `from __future__ import annotations` — **禁止**（3.14 默认延迟求值）
- `uuid.uuid4()` — 仅用于临时/安全场景（token、nonce）；数据存储主键用 `uuid.uuid7()`
- `zip(a, b)` — **禁止无 strict**；要么 `strict=True`（理应等长）要么 `strict=False`（显式允许不等）
- 新并发代码首选 `asyncio.TaskGroup`，替代 `asyncio.gather`
- frozen dataclass 更新用 `copy.replace()`，替代 `dataclasses.replace()`
  -在main干活需要许可，一般在工作树干活，不要擅自合并

## 运行环境

- Docker 容器：`maim-bot-core`，Python 3.14.6
- 依赖管理：**uv**，不用 pip
- Docker 可?用：`docker exec maim-bot-core bash -c "cd /MaiMBot && uv run ..."`
- 我的验收终点：`ruff check` 通过 + pytest 通过。验证命令直接在 Docker 容器内执行

## 项目灵魂

MaiBot 不是一个技术项目，它是一个家。角色是人不是标签，说人话，不完美才像人。技术架构存在的唯一理由：让十三个角色在客厅里自然地生活。

## 用户偏好

**革命而非改良。** 

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
7. **merge 必须在主仓库执行** — worktree 内 `git merge` 会 "Already up to date"（merge 的是自己分支，新提交永远合不进来）。犯过 3 次。惯例：`cd /mnt/e/Users/lmq/MaiBot && git merge <branch>`，合并前先 `git worktree list` 确认 cwd 不在 worktree 里
8. **worktree 删除后 shell cwd 会失效** — `git worktree remove` 后当前 shell 若还在该目录，后续 git 命令可能落到错误仓库；删 worktree 前先 `cd` 回主仓库
9. **删除/重构模块必须同步测试** — 测试债务主源（2026-08-02 测试卫生批次根因）：删模块后 behavior_* 测试残留、`_chat_manager` 删除后 monkeypatch 字符串目标失效、`chat_prompts` 移入 `reply_style` 后 setattr 目标没跟、f63ca9bf1 删 monologue 漏 bootstrap.py import（启动路径 ImportError）。规则：**删/改任何模块时，grep 其 import 引用 + monkeypatch 字符串引用（"src.x.y" 形式），同步更新或删除测试**；explore agent 核查"零引用"必须含 import 语句级检查
10. **.py 文件必须 UTF-8 无 BOM** — Windows 编辑器保存事故：tests/webui/__init__.py 变 UTF-16 导致整个目录无法收集（SyntaxError: null bytes）。提交前 `file xxx.py` 抽查；跨平台编辑后留意编码
11. **pytests/ 与 tests/ 双目录并存** — 同模块名（webui.conftest）引发 ImportPathMismatchError；已配 `import-mode = "importlib"`（pyproject），不要再手动删其中一个目录，两目录内容不同都有用
12. **faiss≥1.13 裸 IndexHNSWFlat 不支持 add_with_ids** — C++ 基类默认抛 "add_with_ids not implemented"；必须 `faiss.IndexIDMap2(IndexHNSWFlat(...))` 包装（hnsw 参数先设再包）。裸索引 + add_with_ids 的 VectorStore 生产 save() 必崩（2026-08-03 B 类 T3 发现）
13. **sqlite3 连接"拥有权"决定 commit 语义** — 跨连接操作：`conn is self._conn` 时不 commit（参与调用方事务），外部连接要显式 commit（独立生效）。`fts_upsert/delete_tokenized_paragraph` 的 conn 参数曾被实现丢弃 + 自连自提交（破坏 sparse_bm25 独立连接的 shadow 写入，也破坏外层事务）；commit 方向写反过一次（owns_conn 判断反了）
14. **同名方法 v1/v2 并存是空操作陷阱** — `dual_vector_migration.py` 的 `clear_legacy_single_vector_files_after_dual_ready`（v1）只刷 manifest 不删文件，`_v2` 才是真清理——kernel 注入调 v1 → legacy 文件永不清理（"三池冗余"）。规则：grep 同名方法时检查全部定义；删死方法不留双轨
15. **容器内 src 是 bind mount、tests/pytests 不是** — 改 src 立即生效；tests/pytests 在容器里是旧快照（镜像 COPY），跑测试前必须 `docker exec maim-bot-core rm -rf /MaiMBot/tests /MaiMBot/pytests && docker cp tests maim-bot-core:/MaiMBot/ && docker cp pytests maim-bot-core:/MaiMBot/`。忘了同步会把旧测试文件 + 新 src 混跑，报出幽灵失败（2026-08-03 撞过：容器里多了本地已删的 test_maibot_migration_script.py）
16. **计算回填 ≠ 写盘** — plugin install manifest id 回填只算了 `manifest_plugin_id` 没写回文件，按 id 查找永远失败；`_read_manifest_plugin_id` 用 `str(manifest.get("id")).strip()` 对缺 id 返回 "None" 非空导致回填条件永不触发（str(None) 陷阱第 4 次）
17. **Windows worktree 在 WSL 里 gitdir 失效** — CA 的 Windows 工作树（E:\Users\lmq\MaiBot-fix-send）`.git` 文件内容 `gitdir: E:/...` 是 Windows 绝对路径，WSL 的 git 解析不了 → `git worktree list` 显示 prunable、`git status` 报 "not a git repository: (null)"。修复：`git worktree repair /mnt/e/Users/lmq/MaiBot-fix-send`（2026-08-03 fix_send_failure 合并时撞过）
18. **CA 在子仓库里建嵌套 git 仓库是事故** — CA 的产出目录里若出现带 .git 的子目录（旧副本），`git add` 会作为 gitlink（mode 160000）提交并警告 "adding embedded git repository"——嵌套仓库内容无法被外层仓库管理。规则：合并 CA 产出前先 `find <dir> -name .git` 检查嵌套仓库；内容为旧副本时整个删除，gitlink 从 index 撤销（`git rm --cached`）
19. **submodule 改动两段式提交** — 插件子仓库（plugins/*）的改动必须在子仓库内单独 commit，主仓库只提交指针更新（子仓库 commit → 主仓库 `git add plugins/xxx` 提交指针）
20. **Dummy/假类方法不全 = 错误被吞**（测试卫生批次） — fixture 的 DummyLogger 缺 `debug`/`exception` 方法 → 生产代码调 `logger.debug` 抛 AttributeError → 被外层 try/except 吞 → 断言拿到空字符串、错误不可见。规则：修"断言空结果"类失败时，先检查假类方法是否齐全（logger 至少 debug/info/warning/error/exception），再追链路
21. **fixture 的 sys.modules 假模块替换有时序要求** — 需要 import 真实依赖链的代码（如 port registry 模块）必须在 sys.modules 替换**之前** import；`importlib.reload` 与 sys.modules 假模块互斥（reload 重新 exec 会从被替换模块 import → "cannot import name X from '<unknown module name>'"）。规则：新 import 放 fixture 顶部、不要 reload
22. **Codex 修复可能是"规避"而非"根因"** — 审查 Codex 补丁时对每个生产改动问"它真的修对了吗"：i18n 缺 `import logging`（NameError 根因）被 Codex 用字符串 `"warning"` 规避（破坏 `logger.log(level: int)` 契约）——正确修法是补 import + 走项目 logger 规则。规则：Codex 改了生产代码的语义（参数类型/契约）时重点审查；宁可还原其改动自己修
23. **真实 db 的测试残留要测试内清理** — 走真实 db（AgentActivityStore 等）的测试重跑会 UNIQUE 冲突/数据累积——测试开头 delete 同 id 记录，或改用临时 db 隔离。数据库迁移只跑一次：已跑过新版本的测试环境，后续补列要手动 ALTER（迁移文件对新 db 生效，旧 db 已跳版本）

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
