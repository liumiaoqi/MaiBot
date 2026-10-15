# AGENTS.md（MaiBot · 工程铁律层）

> **硬性规则 + 路由策略。本文件是唯一正本**——`CLAUDE.md`（原 `.claude/CLAUDE.md` 工作手册）已于 2026-10-15 合并入此，根目录 `CLAUDE.md` 仅留指针（dsh 标准）。
> 架构哲学见 `.codeartsdoer/rule/MaiBot智能体自主性架构.mdc`；债务追踪见 `.codeartsdoer/specs/memo/zg_cast_bone_research.md`；决策/复盘/交接见 `.shared/`（总账见 `C:\hub\`）。
> **分层位置**：本仓 = 工程铁律层（跨领域分层原则见 `C:\hub\ARCHITECTURE.md`）。
> ⚠️ **写代码 / 审查前必扫**：§七 高频缺陷模式 + `docs/pitfalls.md`（实战踩坑——**条数不在此登记**：条数是会腐的登记，2026-10-16 实测三处各写 25/26/32 而实际 33）。

---

# 〇、目录索引（先去哪看）

| 目录 | 角色 | 局部指引 |
|---|---|---|
| `src/core/` | 微内核契约（Protocol / 适配器 / Port 注册） | `src/core/AGENTS.md` |
| `src/A_memorix/` | 记忆子系统 | `src/A_memorix/AGENTS.md`（+ `MODIFICATION_POLICY.md`） |
| `mingtang/` | 前端主战场 | `mingtang/AGENTS.md` |
| `dashboard/` | 老前端（冻结保留） | `dashboard/DEPRECATED.md` |
| `scripts/embedding_finetune/` | AI 实验区 | `scripts/embedding_finetune/AGENTS.md`（+ RULES / INDEX） |
| `docker-config/` | 部署配置（**`mmc/` 才生效**） | `docker-config/AGENTS.md` |
| `docs/` | 文档（pitfalls 活件 + archive 冻结） | `docs/AGENTS.md` |
| `.shared/` | 协作区（handoff / postmortem / decisions） | 写作规范见 §十一 |

---

# 一、核心架构：微内核 + 接口契约

核心模块不依赖组件具体实现，只通过 Protocol 接口交互。适配器层（`src/core/adapters/`）是唯一允许导入组件具体类的地方。

## 核心禁止项（14 条）

1. 禁止核心直接导入 chat_manager ✅
2. 禁止核心访问 chat_manager._agent_router ✅
3. 禁止核心持有 BotChatSession 可变引用 ✅
4. 禁止核心硬编码 napcat_* 字段 ✅
5. 禁止核心绕过 MessagePort 直接调用 send_service ✅
6. 禁止核心导入 A_memorix 内部模块 ✅
7. 禁止 Orchestrator 通过 enqueue_proactive_task 模拟多智能体 ✅
8. 禁止核心直接导入 config_manager 获取模型配置 ✅
9. 禁止核心直接导入 global_config ✅
10. 禁止使用 AutonomyEventBus.get_instance() ✅
11. 禁止核心直接导入 ServiceManagerAdapter ✅
12. 禁止核心直接导入 WatchdogAdapter ✅
13. 禁止核心 port_registry 导入适配器具体类 — port_registry 应只依赖 Protocol 接口做类型标注，具体实现类由 main.py 启动时通过 set_*() 注入 ✅
14. 禁止核心直接导入 plugin_runtime 组件 — 核心通过 Protocol 或 port_registry 获取 IPC 桥接能力，不直接依赖插件运行时 ✅

Protocol 接口和注册点详见 `src/core/protocols.py` 和 `src/core/adapters/`，不在本文件枚举。

---

# 二、代码规范

**import**：标准库/第三方在前，本地模块在后；`from ... import ...` 在 `import ...` 前；同类按字母序；同文件夹相对导入、跨文件夹 `from src` 绝对；块间空一行。

**注释**：保持良好注释；重构时保留原有注释（可修正准确性，不删除）；复杂逻辑块加注释。

**类型注解**：重构时保留原有注解；复杂/多参数函数加注解；参数化泛型用 `typing`（`List[int]`/`Dict[str, Any]`）。

**变量**：确定类型时不用 `or` fallback（`nickname.strip()` 而非 `(nickname or "").strip()`）；豁免：外部数据源可能返回 None 时可用 `or ""`。

**类属性**：减少 getattr/setattr，优先直接访问；保留场景：动态 task_config、numpy、上传对象等外部动态对象。

**debug**：精准找问题核心，不兜底；区分"不兜底"与"不写入脏数据"（外部 None 不强行 fallback 写库）。

---

# 三、语言 · 包 · 运行基线

**运行环境**：uv 管理依赖（以 pyproject.toml 为准）；容器 `maim-bot-core`（Python **3.14.8**）。

**验收终点**（命令在容器内直接跑）：

```sh
uv run ruff check                      # 静态
uv run pytest                          # 双目录全量（tests/ + pytests/，pytest 配置含 importlib 模式）
cd mingtang && npm run lint && npm run test && npm run build   # 前端三绿（本机 BUILD 需 NODE_OPTIONS= 避环境 shim）
```

**Python 3.14 写新代码必守**（语言层详版 `.shared/decisions/python314_new_code_cheatsheet.md`）：

- `from __future__ import annotations` — **禁止**（3.14 默认延迟求值）；新代码兼容 3.14
- `uuid.uuid4()` 仅用于临时/安全场景（token/nonce）；**数据存储主键用 `uuid.uuid7()`**
- `zip(a, b)` 禁止无 strict：`strict=True`（理应等长）或 `strict=False`（显式允许不等）
- 新并发代码首选 `asyncio.TaskGroup`，替代 `asyncio.gather`
- frozen dataclass 更新用 `copy.replace()`，替代 `dataclasses.replace()`

**包层基线**（2026-10-15 依赖升级批次 A 后——详版 `.shared/decisions/packages_new_code_cheatsheet.md`）：

- **pydantic 2.14**：字段三态用 `MISSING`（"未提供"≠None——阶段 3 配置分层备货）；lazy imports **需 Python 3.15**（3.14 实测不可用，记账）
- **ruff 0.17**：抑制用 `# ruff: ignore[规则]` 新写法（新代码新写法，老 `noqa` 遇时才换）
- **明确排除**（防重复调研）：openai 3.x Responses API（走 DeepSeek chat 兼容口，用不上）· sqlalchemy 2.1 Session options（暂无落点）· radix/react 小版本（用到哪查哪）
- **grpcio 1.84 / asyncio 取消语义**（2026-10-15 pv2 实证）：`except asyncio.CancelledError` **禁止吞掉**（上层等待取消会永不返回——e2e 测试硬挂实捕获）；长跑协程（`runner.start()` 类）的终止走**标志位**（`stop()` 风格），外部不依赖 `task.cancel()`；gRPC 统一 `grpc.aio`，不分叉 sync；protobuf 由 grpcio-reflection 传递带入，**不显式声明**

**TypeScript 写前端必守**（详细版 `C:\hub\reference\toolchain\typescript_new_code_cheatsheet.md`）：

> ⚠️ **版本基线**：mingtang（主战场）= React 19.2 / TS 6.0.2（typescript6）+ TS 7.0.2（native）双轨 / Vite 8.2 / ESLint 10；dashboard = TS ~5.9.3 系——**两前端版本不同，旧知识写新代码必爆红**。

- **类型优先**：新代码零 `any`；不新增 `@ts-ignore`；`@ts-expect-error` 必须带理由注释
- **多语言文本用 `LocalizedText`**（config-label.ts 基础设施），不用裸 string
- **schema 类型同步**：后端 `config_schema.py` 改字段 → 前端 `types/config-schema.ts` + `field-hooks.ts` 同步
- **命名**：组件 PascalCase / hooks useXxx / 文件 kebab-case；路径别名 `@/`
- **测试先行**（vitest）：每个实现任务先写配套测试，不凑绿（先例 `dashboard/src/lib/__tests__/`）

**语言**：首选简体中文（注释、日志、WebUI）。

---

# 四、WebUI

- 显示聊天流实际名称而非 session_id
- UI 高度/布局问题：查 DOM 变化、computed style、data-dashboard-style
- UI 底纹/阴影/半透明：按 DOM 层级逐层查 computed style
- Radix 组件不随便移出上下文
- 修改完不急着 npm run build，开发服务固定 7999 端口

## 前端状态（2026-08-21 立，2026-10-15 更新）

- **mingtang/** = 新前端（**主战场**）——8 功能域（config/chat/memory/resource/monitor/agent/plugin/home/survey）；蓝图 `.shared/decisions/WebUI_Plan/mingtang_architecture_blueprint_0808.md`；验收=三绿（见 §三）
- **dashboard/** = 老前端（📦 **冻结保留**）——新功能开发一律进 mingtang，dashboard 只做修复不做新功能；**不再计划物理删除**（lmq 2026-10-15 定：git 保底 + 保留作回退）；标识见 `dashboard/DEPRECATED.md`

---

# 五、专项规则

**会话 ID**：业务模块不自行调用 `SessionUtils.calculate_session_id`，经 `SessionRepository` Protocol 查真实聊天流；查不到不强行计算 fallback hash 写库。

**A_memorix**：可自由修改，约束仅来自核心隔离和 Protocol 接口契约（`src/A_memorix/MODIFICATION_POLICY.md`）。

**prompt 模板**：修改需同步英文和日文文件。

**配置文件修改**：只改模板+新增版本号，不改动 legacy_migration，不擅自新增 ConfigUpgradeHook。

**插件开发**：插件在 /plugins 下独立仓库，改主程序代码需先请求许可。

**changelog**：分用户感知功能侧和开发侧，一个功能一行按模块分；版本号提升不写入。

**修改文档**：功能性变更可修改 /mai-docs，不在上层目录新建。

---

# 六、默认原则

1. **不提交无边界整理**：ruff、格式化、导入整理、大面积实现整理一律不做
2. **本地实验目录不进入共享历史**
3. **AI 实验区**（2026-08-17 立）：AI 相关实验（微调/SNN/小模型/新架构/行为模拟）统一在 `scripts/embedding_finetune/`（uv 隔离 .venv，见其 RULES.md）；lab/ 只放非 AI 零散脚本
4. **术语准确**（2026-08-25）：**NapCat 是独立 QQ Bot 框架（协议端），不是适配器**；`maibot-team.napcat-adapter` 才是适配器插件——文档/报告不混淆
5. **压缩后不内耗**（判据：`C:\hub\CONVENTIONS.md` **§13.1**）——压缩/新会话后**一次定位**（git log 前 5 条 + 最新 handoff + 当前指令）即干活，不 glob 全景侦察
6. **索引优先**（判据：`C:\hub\CONVENTIONS.md` **§9.5 索引纪律**）——进目录先读 INDEX/README（`lab/`、`scripts/embedding_finetune/`、`C:\hub\reference\projects-INDEX.md`）；索引缺内容=报告补索引，不翻全目录硬找
7. **事故复盘文化**（编号总账：`C:\hub\postmortems\INDEX.md`）：bug 逃逸到生产时不只修那行——写复盘（`.shared/postmortem/`，五段式；三道筛选：隐蔽/系统性/重发现代价高）；**复盘是编码/决策时的必查参考**——修前先查历史复盘、修完主动判断是否要写
8. **抓日志只抓新日志**（2026-08-25）：排障只抓**最后一次启动之后**的日志（`docker logs --since <启动时间>` 或 `--tail` 限定）；抓老日志会把已修复问题当现存问题
9. **Docker 维护**（2026-09-01——vhdx 静默膨胀事故 137.8G）：构建前必查 `.dockerignore` 覆盖（node_modules/.git/权重/克隆池/zip/输出目录）；长期不用优先 unregister/停用；清理链必须 prune → **vhdx 处理**（只清 Docker 内容=白清）；C 盘空间纳入巡检；细则见 docker skill（.dsh/skills/docker）

---

# 七、接线与缺陷防线

> **判据在中枢**（`C:\hub\CONVENTIONS.md` **§13.4**：接线必须完整 + 四连问 + 配套缺陷清单）——本节产出的是**本仓落地形态**。

## 本仓接线落地（ZG16-2/ZG16-5 静默失效教训）

**新模块（新文件/新类/新入口）必须有生产接线点，禁止"只有定义没有调用点"。**

1. 接线方式：声明 `@startup_item`（优先）或 main.py 显式 init+close
2. 提交前自检：grep 入口函数确认生产调用点——**只有测试里调用不算接线**
3. 单测必须覆盖生产路径初始化（不允许"测试自己 init 自己"）
4. 未接线不得静默跳过：要么接线，要么初始化失败出声（日志/启动摘要可见）
5. 审核先查"入口函数调用点"——漏接线=打回
6. **四连问**（2026-08-19 强化："接线点存在 ≠ 接线完成"）：① 有**生产创建点**吗（grep 类名，只有定义=静默失效）② 创建点**参数从哪来**（构造传参 vs config port 两条路径查一致）③ **组装链闭合**吗（谁创建并注册回调）④ **测试走生产路径**吗（创建→注册→触发完整链）

## 高频缺陷模式清单（2026-08-22 立——80 批审查沉淀：静默失效 113 + 死代码/零接线 73 占绝大多数）

**写代码/审查逐条对照——命中即怀疑**：

1. **配置注入点零调用**（`set_ports()`/`set_config()` 有定义有 docstring 但生产零调用→功能静默禁用）
2. **请求级实例化**（webui 路由 handler 内 `new 服务()`→有状态服务状态即丢→面板永远空）
3. **类零创建点**（类定义+导出但全仓无生产 `Class()`→启动摘要必须报告"未接线"）
4. **整文件死代码**（导出但无生产调用→删除或显式标注"未接线原型"）
5. **字段名错误**（数据类构造必填字段缺失→TypeError；构造与定义对齐）
6. **注销方法内含启动逻辑**（`_unregister_*` 反而重新注册→关闭路径矛盾）
7. **异常单通道**（except 块只有 report 无 logger 或反之→双通道都要）
8. **docstring 承诺但未实现**（"由 main.py 调用"但没调→文档与接线脱节）
9. **无认证端点**（webui router 无 `dependencies=[Depends(require_auth)]`——N4 门禁查）
10. **结构体必填字段缺失**（用统一辅助方法如 build_success_result，不逐处手写）
11. **str(Enum) 比较失效**（Python 3.11+：`str(ServiceState.RUNNING)` 返回 `"ServiceState.RUNNING"`——禁 `str(enum).lower()` 比较，用枚举成员或 `.value`）
12. **Port 注册零调用**（`set_*_port()` 有定义但零生产调用→适配器没注册到全局 registry；四连问第 1 问扩展）

**完整参考**：`.shared/reports/2026-08/megasurvey/`（A 组 31 份审查，每项 P0/P1 有证据）。
**实战踩坑**：`docs/pitfalls.md`（修 bug/写代码前必扫——worktree/编码/faiss/sqlite/uuid7/容器 bind mount/白名单开关等）。⚠️ **本条不登记条数**：条数是会腐的登记（2026-10-16 实测三处各写 25/26/32，而实际 33）——要引用就给路径。

---

# 八、设计参考铁律

> **判据在中枢**：设计须标注参考来源 → `C:\hub\CONVENTIONS.md` **§13.3**；学习开源=学架构不学代码 → **§13.2**。本节保留**本仓的参考地图**。

**设计派发/SSD/调研文档必须标注参考源码来源：**

1. **系统类**（OS 化/治理/资源/调度/容错）→ Linux 内核源码：`E:\Users\lmq\importantClone\linuxclone\linux\`（标注对应机制文件）
2. **智能体类**（agent/记忆/自主性/工具链）→ dsh 源码：`E:\Users\lmq\importantClone\DEEPSEEKCLONE\deepseek-harness\`（标注对应包）
3. **理由**：MaiBot 底模 = DeepSeek；dsh 是它的 harness——模型特化向 harness 看齐；ZG 计划对标 Linux——系统机制翻内核真实现。**不标注=设计无据**
4. **插件哲学**：重点从 dsh 学习——Cordis 47 包架构（生命周期/依赖/作用域/上下文注入）是第一参考
5. **dsh 参考地图**（做设计前先翻说明书再翻源码）：`docs/architecture.md` + `cordis-primer.md`；`capability-seams.md`（一切皆插件）；`config-catalog.md`（配置分层）；`tool-catalog.md` + `tool-execution-pipeline.md`；**`defensive-patterns.md`（写生命周期/并发/子进程前必读）**；`event-producer-consumer.md` / `agent-lifecycle.md`；团队 skill `.agents/skills/`（11 个）
6. **克隆池 skill 库**：完整版 `C:\hub\reference\clone_skill_library_guide_0819.md`；常用映射（双轴审核→code-review；对抗审查→doubt-driven-development；安全→security-and-hardening；统计→statistical-analysis）；**原则：skill 是方法不是圣经——引入前问"解决哪个具体痛点"**
7. **学习开源铁律**（2026-08-24，拍板）：**学架构和设计，不学代码**——✅ 架构分层/设计取舍/机制原理/防御模式；❌ 代码细节/实现风格（抄实现=抄缺陷）；**上游 MaiBot 策略 B**：功能评估只看"值不值得有"，实现完全按本地标准重写，不复刻 cherry-pick

---

# 九、多智能体协作

> ⚠️ **本节细则已迁往中枢**（2026-10-15）：派发/回执体系**统一在 `C:\hub\` 维护**——**别在这边复制一份**（双重权威）。

| 要什么 | 去哪 |
|---|---|
| **派发/回执约定**（命名/格式/思维链写法） | `C:\hub\CONVENTIONS.md` §2（成员代号表——`ca`＝华为云「码道 CodeArts」）/ §5（格式）+ `CONVENTIONS_HANDOFF_COT.md`（思维链） |
| **判据清单**（派发/回执模板·缺陷上报·复盘·收尾终检·巡检） | `~/.dsh/team-skills/team-playbook` **§六/§七**（对 WB 与 dsh 同样适用；⚠️ 其 §一 TeamCreate 是 dsh 版，WB 侧别照搬） |
| **给 CA 派活 / 它的回执** | handoff 落 `.shared/handoff/{年-月}/{MMDD}/`，命名 `{from}2{to}_{主题}_{MMDD}.md`；CA 的规则/技能目录是**项目本地** `.codeartsdoer\{agents,skills}\`；**谁的产出谁提交** |
| **团队协作实测经验**（组织 vs 策略·协调成本·成员上限 8）与**并发写保护矩阵** | `C:\hub\reference\dsh\`（0927/0928 实验）+ `CONVENTIONS.md` §14（多 Agent 并发写八条协议） |

**本仓落点**：handoff → `.shared/handoff/`；复盘 → `.shared/postmortem/`（编号走总表 `C:\hub\postmortems\INDEX.md`）。

**提交前自检清单**（MaiBot 侧通用）：

- [ ] `__init__.py` 新增导入 → `__all__` 同步？
- [ ] 类型注解用具体类型而非 `Any`？
- [ ] `git commit` 完成后再写交接报告？
- [ ] 交接报告含：完成状态+验证结果+问题+注意事项？
- [ ] `ruff check` 实际跑过？

---

# 十、流程纪律

**自研工具问题上报**（2026-09-10，拍板）：使用自研工具（MCP/脚本/CLI/skill/前端/交接工具）发现缺陷/bug/优化点/坑，**必须上报，不许默默绕过**。① 即时记入**主台账** `D:\Users\lmq\Documents\Academic\tools\TOOL_ISSUES.md`（编号 `I-NN` 连续只增；实锤证据+修法+复验方式）② 汇总排查（例行巡检扫表）③ 安排修复（不删条目，修完回填 ✅+提交号）。

**事故复盘（硬性）**（2026-08-28，拍板）：造成"系统/工具不可用"或"用户状态丢失"的事故，修复后必须写复盘（触发清单：启动崩溃/构建阻断｜数据配置丢失｜误删误改｜排查超 10 步｜跨仓重复出现）。落 `.shared/postmortem/`，编号走总账 `C:\hub\postmortems\INDEX.md`（全局连续，写前登记写后回填）。**写"流程为什么放过了它"，不是"哪一行修好了"**——时间线必须如实记录自己的错误步骤。

**删除操作前置检查**（2026-08-28 立，0003 事故教训）：

1. **看**：`ls` 目标内容，未见过的目录不执行 `rm -rf`
2. **查引用**：grep 谁在引用（配置/patch/脚本）——声明还在说明实体不是垃圾
3. **判可重建**：构建产物可删；用户手写内容先备份；"空目录"先 `git ls-tree` 确认真空

补充：`~/.dsh`、`~/.workbuddy` 等用户态目录按"不可重建"从严；报错标签≠故障位置；`git status` 干净≠工作区干净（gitignore 残留对 git 隐身却是构建输入）；说明文档≠备份。

**文件检索约定**（2026-08-29，拍板）：**用户本人用 Everything（不用 fd）**——不要建议他改。智能体侧：`rg` 搜内容（默认递归+尊重 gitignore）；`fd` 搜文件名（注意四个默认坑：跳隐藏→`-H`、尊重 gitignore→`--no-ignore`、只匹配 basename→`-p`、位置参数是 pattern 非路径）；`fzf --filter` 可用（模糊匹配，非交互）。**描述性检索是智能体的活**（"找讲 X 的文档"→直接 `rg` 搜内容）。本项目万能式：`fd -H --no-ignore -p 关键词`。

---

# 十一、`.shared/` 写作规范

`.shared/` 是异步上下文共享区（git 子仓库），写新文件必须遵守：

1. **头部元数据**：每个 .md 加 `> 最后更新：YYYY-MM-DD`；decisions/ 额外加状态标记（📚参考 / 🔬研究 / 🏗️设计 / 🔧工程）
2. **命名**：decisions/ `snake_case.md`；handoff/ `{src}2{dst}_{topic}_{date}.md`；research/ `snake_case_extracts.md`
3. **decisions/ 新文件必须更新 `_INDEX.md`**（加摘要+状态）
4. **memo.md 不再堆内容**（新主题放 decisions/，memo 只加索引行）
5. **active_tasks.md 只放当前活跃任务**（完成的移入 roadmap.md"已完成里程碑"）
6. **roadmap.md 状态与 research memo 同步**（改一个必须检查另一个）

---

# 十二、项目灵魂与用户偏好

**MaiBot 不是一个技术项目，它是一个家。** 角色是人不是标签，说人话，不完美才像人。技术架构存在的唯一理由：让十三个角色在客厅里自然地生活。

**人的本质是一切社会关系的总和**（架构标尺，用户原话）：角色由彼此的关系定义——记忆（A_memorix 社会关系）、欲望（想和谁说话）、情绪（见到谁开心）都为关系服务。**做任何架构决策前问：这个改动让角色之间的关系更真实了吗？**

**用户偏好**：**革命而非改良。**

**协作习惯**：在 main 干活需许可（一般在工作树干活，不擅自合并）；不评估工时；汇报提交历史用 `git log --graph` 彩色拓扑。

---

# 十三、债务原则

> **判据在中枢**：`C:\hub\CONVENTIONS.md` **§13.5**（"这笔投入是让以后更容易，还是更难？"）。本仓债务全景见 `.codeartsdoer/specs/memo/zg_cast_bone_research.md`（不在本文件追踪状态）。

- **拿未来换现在**（必须消除）：`except Exception: pass` 透支排障能力；绕过 Port 直接导入透支重构自由度
- **用现在换未来**（优先投入）：修 exception handling 换未来可追踪；集成欲望换主动说话
- **不影响未来**（低优先）：V1 getattr 残留、TODO 清理

---

# 改这份文件（Editing these instructions）

`CLAUDE.md`（根）指向本文件（dsh 用 symlink；本仓 Windows 环境用指针文件）——**改内容只改本文件，不维护第二份**。每条规则自成一体并链接高层文档；表达可以压缩，规则不能丢。细则放 `docs/` 或 `.shared/`，本文件留核心几条+指针。版本数字（Python/测试基线等）随实际更新；指向路径失效时同步修正。
