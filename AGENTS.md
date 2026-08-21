> 硬性规则 + 路由策略。架构哲学见 `.codeartsdoer/rule/MaiBot智能体自主性架构.mdc`，工作手册见 `CLAUDE.md`，债务追踪见 `.codeartsdoer/specs/memo/zg_cast_bone_research.md`。

# 代码规范

## import 规范
1. 标准库/第三方库在前，本地模块在后，`from ... import ...` 在 `import ...` 前
2. 同类导入按字母序排列（不引起 import 错误前提下）
3. 同文件夹用相对导入，跨文件夹用 `from src` 绝对导入
4. 各导入块间空一行

## 注释规范
1. 保持良好注释
2. 重构时保留原有注释（可修改准确性，不删除）
3. 复杂逻辑块添加注释

## 类型注解规范
1. 重构时保留原有类型注解
2. 复杂函数/多参数函数添加类型注解
3. 参数化泛型用 `typing` 模块（如 `List[int]`、`Dict[str, Any]`）

## 变量规范
1. 确定类型时不使用 `or` fallback（如 `global_config.bot.nickname.strip()` 而非 `(global_config.bot.nickname or "").strip()`）
2. 合理豁免：外部数据源可能返回 None 时可用 `or ""`

## 类属性使用规范
1. 减少 getattr/setattr，优先类属性直接访问
2. 保留场景：动态 LLM task_config、numpy 数组、上传对象等动态外部对象

## debug规范
1. 精准找问题核心，不兜底
2. 区分"不兜底"（值应存在时直接用）与"不写入脏数据"（外部返回 None 时不强行 fallback 写入数据库）

# 运行/调试/构建/测试/依赖
优先使用 uv，依赖项以 pyproject.toml 为准

# Python 版本
新代码必须兼容 Python 3.14.6。不使用 `from __future__ import annotations`。

# 语言规范
首选简体中文（注释、日志、WebUI）

# 配置文件修改
只改模板+新增版本号，不改动 legacy_migration，不擅自新增 ConfigUpgradeHook

# Webui规范
- 显示聊天流实际名称而非 session_id
- UI 高度/布局问题：查 DOM 变化、computed style、data-dashboard-style
- UI 底纹/阴影/半透明：按 DOM 层级逐层查 computed style
- Radix 组件不随便移出上下文
- 修改完不急着 npm run build，开发服务固定 7999 端口

## WebUI 前端状态（2026-08-21 立）
- **mingtang/** = 新前端（**主战场**）——React 19.2 + TS 双轨（typescript6 包）/Vite 8.2/ESLint 10；8 功能域已实现（config/chat/memory/resource/monitor/agent/plugin/home/survey），135 测试；蓝图见 `.shared/decisions/WebUI_Plan/mingtang_architecture_blueprint_0808.md`；验收终点：`cd mingtang && npm run lint && npm run test && npm run build` 三绿（当前基线 135 tests）
- **dashboard/** = 老前端（⚠️ **遗留，待 mingtang 验收后废弃**）——React 19.2/TS ~5.9.3/Vite 7.2/ESLint 9.39；**当前生产仍挂载其 dist**（docker-compose `MAIBOT_WEBUI_USE_LOCAL_DASHBOARD=1` + `app.py:300` 静态路径）；**新功能开发一律进 mingtang，dashboard 只做修复不做新功能**；废弃标识见 `dashboard/DEPRECATED.md`
- **切换条件**（未到）：R4 债清理收尾 + mingtang 三绿验收通过 + 后端挂载切换（app.py 加 mingtang 静态路径 + docker-compose 换挂载）+ 功能对照验收——全完成后才废弃 dashboard

# 会话 ID 规范
业务模块不应自行调用 `SessionUtils.calculate_session_id`，应通过 `SessionRepository` Protocol 查询已存在的真实聊天流；查询不到不应强行计算 fallback hash 写入数据库

# A_memorix 修改
可自由修改，约束仅来自核心隔离和 Protocol 接口契约（详见 `src/A_memorix/MODIFICATION_POLICY.md`）

# prompt模板
修改需同步英文和日文文件

# 默认原则
1. 不提交无边界的 ruff、格式化、导入整理或大面积实现整理
2. 本地实验目录不进入共享历史
3. **AI 实验区（2026-08-17 立）**：所有 AI 相关实验（微调/SNN/小模型/新架构/行为模拟）统一在 `scripts/embedding_finetune/` 做（uv 隔离 .venv 3.12 + torch cu128，与主项目 3.14 隔离）——规则见该目录 RULES.md；lab/ 只放非 AI 零散脚本

# 设计参考铁律（2026-08-17 立，用户拍板）

**设计派发/SSD/调研文档必须标注参考源码来源：**

1. **设计系统类（OS 化/系统治理/资源/调度/容错）**——必须标注 Linux 内核源码参考：
   `E:\Users\lmq\importantClone\linuxclone\linux\`（对应机制所在文件，如 mm/vmscan.c、kernel/workqueue.c）
2. **设计智能体类（agent/记忆/自主性/工具链）**——必须标注 dsh（deepseek-harness）源码参考：
   `E:\Users\lmq\importantClone\DEEPSEEKCLONE\deepseek-harness\`（对应包，如 packages/compaction、packages/token-meter）
3. **理由**：MaiBot 底模 = DeepSeek 模型，dsh 是它的 harness——模型特化必须向 harness 看齐；
   ZG 计划整体对标 Linux——系统机制必须翻内核真实现。两者是最重要的参考，不标注=设计无据。
4. **插件哲学（2026-08-17 用户拍板）**：MaiBot 插件体系的设计哲学**重点从 dsh 学习**——
   deepseek-harness 的 47 包 Cordis 插件架构（生命周期/依赖/作用域/上下文注入）是插件设计的第一参考，
   先于通用插件框架（如 Home Assistant 等仅作补充对照）。
5. **范围**：派发文档（dsh2ca_*）、SSD（spec/design/tasks）、调研报告均需在输入材料/引用中体现。
6. **dsh 参考文档地图（2026-08-17 立——做设计前先翻说明书再翻源码）**：
   - 架构总览：`DEEPSEEKCLONE/deepseek-harness/docs/architecture.md` + `cordis-primer.md`
   - 「一切皆插件」落地：`docs/capability-seams.md`（核心脊柱/可换接缝/bundle 组合点）
   - 配置设计：`docs/config-catalog.md`（132KB 全量配置目录——模型配置分层/编组直接参考）
   - 工具设计：`docs/tool-catalog.md`（80KB）+ `docs/tool-execution-pipeline.md`
   - **防御模式（缺陷类规则）**：`docs/defensive-patterns.md`——写生命周期/并发/子进程代码前必读
   - 事件体系：`docs/event-producer-consumer.md` / 生命周期：`docs/agent-lifecycle.md`
   - 团队 skill（工作流即插件）：`.agents/skills/`（11 个——code-review/pre-push-checks/trim-cot-leakage 等）
   - 全部有中文版（.zh.md）；详见 `.shared/decisions/dsh_team_skills_observation_0817.md`

7. **克隆池 Skill 库使用引导（2026-08-19 立——5 库 + dsh 11 + 用户 6 全景）**：
   - 完整版：`.shared/decisions/clone_skill_library_guide_0819.md`
   - 常用映射：双轴审核→skills/code-review；对抗审查→agent-skills/doubt-driven-development；安全加固→agent-skills/security-and-hardening；科学统计→scientific-agent-skills/statistical-analysis；代码审计→reverse-skill/code-audit
   - 原则：skill 是方法不是圣经——引入前问"它解决我们哪个具体痛点"

# 新模块接线（硬性规则——2026-08-15 立，ZG16-2/ZG16-5 两次静默失效教训）

**新模块（新文件/新类/新入口函数）必须存在生产接线点，禁止"只有定义没有调用点"。**

1. **接线方式二选一**：
   - 声明 `@startup_item`（ZG-10 启动编排收集）——优先
   - 或 main.py 启动流程显式 init + 关闭流程显式 close
2. **编码自检（提交前必做）**：grep 新模块的入口函数（如 `init_xxx`/`xxx_recorder`/`get_xxx`），确认存在生产调用点——**只有测试里调用不算接线**
3. **单测必须覆盖生产路径初始化**：不允许只测"测试自己 init 自己"——需有一条测试验证生产路径（main.py 或 @startup_item）会初始化该模块
4. **静默失效禁令**：新模块未接线时不得静默跳过——要么接线，要么初始化失败要出声（日志/启动摘要可见）
5. **审核对照**：dsh 审核时先查"新模块入口函数的调用点"——漏接线 = 打回（ZG16-2 usage_anchor / ZG16-5 scope_audit 均为此模式）
6. **接线完整性四连问（2026-08-19 ZH-1 教训强化——'接线点存在 ≠ 接线完成'）**：
   - ① 新模块有**生产创建点**吗？——grep 类名：只有定义 1 处 = 零创建点 = 静默失效（ZH-1：PersonalityDriftManager 仅类定义，全仓无 new）
   - ② 创建点的**参数从哪来**？——配置流：构造函数传参 vs 既有 config port，两条路径不一致要查
   - ③ **组装链闭合**吗？——A 创建 B 并传回调给 C，链上每一环都要有真实调用（不能只查"回调有调用"，要查"谁创建并注册"）
   - ④ **测试走生产路径**吗？——测试自己 init 自己不算；要测"组装后真实触发"（创建 → 注册 → 触发 完整链）
   - 审核规则：grep 类名看创建点（不只 grep 调用点）；对每个回调参数问"谁传的"——接线点存在 ≠ 接线完成（ZG16-2/5 + ZG-28 + ZH-1 三代同款模式）

# 派发模式（2026-08-21 立——按任务类型选）
- **修复类任务**（改代码）：严格串行一批一报——CA 每批回执，dsh 逐批验收后放行下一批（P0/P1/P2 模式）
- **调研/审查类大批量**（几十-上百批）：**汇总表模式**——派发时给 CA 汇总表（总清单），CA 对照它一直干到底：①勾选制（每干完一批表中打勾+一句话结论）②BLOCKED 上报制（卡住标 BLOCKED+原因→跳下一批）③每批独立产出文件（N 批=N 份，不是 1 封大报告）④不写中间交接，只有最终汇总
- **小批量调研**（1-3 批）：单文档派发（既有模式）
- 完整定义：`.shared/decisions/mega_survey_dispatch_mode_0821.md`

# 插件开发
- 插件在 /plugins 下独立仓库，改主程序代码需先请求许可

# 修改文档
功能性变更可修改 /mai-docs，不在上层目录新建

# changelog编写
分用户感知功能侧和开发侧，一个功能一行按模块分。版本号提升不写入

# 核心架构：微内核 + 接口契约

核心模块不依赖组件具体实现，只通过 Protocol 接口交互。适配器层（`src/core/adapters/`）是唯一允许导入组件具体类的地方。

## 核心禁止项

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

Protocol 接口和注册点详见 `src/core/protocols.py` 和 `src/core/adapters/`，不在此枚举。


# 债务原则：用现在换未来，不是拿未来换现在

- **拿未来换现在**（必须消除）：`except Exception: pass` 透支排障能力；绕过 Port 直接导入透支重构自由度
- **用现在换未来**（优先投入）：修 exception handling 换未来可追踪；集成欲望换主动说话
- **不影响未来**（低优先）：V1 getattr 残留、TODO 清理

债务全景和路线图详见 `.codeartsdoer/specs/memo/zg_cast_bone_research.md`，不在本文件追踪具体状态。
