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

Protocol 接口和注册点详见 `src/core/protocols.py` 和 `src/core/adapters/`，不在此枚举。


# 炉火纯青（ChunQing）：Phoenix 后清算

> 项目代号：炉火纯青（ChunQing），简写 CQ。策略：分批 SSD + 中间调研动态调整。

## 核心原则：用现在换未来，不是拿未来换现在

- **拿未来换现在**（必须消除）：`except Exception: pass` 透支排障能力；绕过 Port 直接导入透支重构自由度
- **用现在换未来**（优先投入）：修 exception handling 换未来可追踪；集成欲望换主动说话
- **不影响未来**（低优先）：V1 getattr 残留、TODO 清理

## 债务全景

| 优先级 | 编号 | 类别 | 数量 | 状态 |
|--------|------|------|------|------|
| **P0** | **CQ-6** | **v2 EventDispatcher 闭环 + napcat-adapter 插件化** | T0~T6 ✅ | ✅ 端到端验证通过 |
| **P0** | **CQ-16** | **v2 Runner 端到端路径验证** | 19→0 | ✅ 完成 |
| **P1** | **CQ-7** | **A_memorix 记忆系统重设计** | 7 问题 | ⬜ SSD 就绪（`.codeartsdoer/specs/cq7_memorix/`） |
| P2 | CQ-8 | SQLAlchemy 3.14 兼容 | ChunkedIteratorResult | ⬜ 待规划 |
| P2 | CQ-17 | v1 旧链发送清算 | legacy_driver+fallback | ⬜ 调研完成（`.shared/handoff/cc2ca_v1_legacy_send_0728_research.md`），待大清算 |
| P3 | CQ-9x | napcat-adapter Tool 扩展 | 5→~30 @Tool | ⬜ 扩展任务 |
| P3 | CQ-10 | V1/V2 共存+TODO | 若干 | ⬜ 低优先 |

已完成：CQ-9/10（except 吞没）✅、CQ-3（None 防御）✅、CQ-5（启动崩溃修复）✅、CQ-7（欲望驱动）✅、CQ-11（统一日志）✅、CQ-159/14/13（Port 迁移）✅、CQ-4（代码质量）✅、TG-0（Python 3.14 兼容性）✅、TG-1（调试基础设施文档化）✅


# Phoenix 后路线

1. **炉火纯青（ChunQing）** — 清算遗留问题（CQ-1~6 ✅，CQ-7 ⬜ 进行中）
2. **QQ 能力革命** — 重构 QQ 相关部分
3. **日志与调试系统升级** — 结构化日志、远程调试、日志聚合（L1~L4 ✅）
