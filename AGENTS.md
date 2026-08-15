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

# 会话 ID 规范
业务模块不应自行调用 `SessionUtils.calculate_session_id`，应通过 `SessionRepository` Protocol 查询已存在的真实聊天流；查询不到不应强行计算 fallback hash 写入数据库

# A_memorix 修改
可自由修改，约束仅来自核心隔离和 Protocol 接口契约（详见 `src/A_memorix/MODIFICATION_POLICY.md`）

# prompt模板
修改需同步英文和日文文件

# 默认原则
1. 不提交无边界的 ruff、格式化、导入整理或大面积实现整理
2. 本地实验目录不进入共享历史

# 新模块接线（硬性规则——2026-08-15 立，ZG16-2/ZG16-5 两次静默失效教训）

**新模块（新文件/新类/新入口函数）必须存在生产接线点，禁止"只有定义没有调用点"。**

1. **接线方式二选一**：
   - 声明 `@startup_item`（ZG-10 启动编排收集）——优先
   - 或 main.py 启动流程显式 init + 关闭流程显式 close
2. **编码自检（提交前必做）**：grep 新模块的入口函数（如 `init_xxx`/`xxx_recorder`/`get_xxx`），确认存在生产调用点——**只有测试里调用不算接线**
3. **单测必须覆盖生产路径初始化**：不允许只测"测试自己 init 自己"——需有一条测试验证生产路径（main.py 或 @startup_item）会初始化该模块
4. **静默失效禁令**：新模块未接线时不得静默跳过——要么接线，要么初始化失败要出声（日志/启动摘要可见）
5. **审核对照**：dsh 审核时先查"新模块入口函数的调用点"——漏接线 = 打回（ZG16-2 usage_anchor / ZG16-5 scope_audit 均为此模式）

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
