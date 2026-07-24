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

# 架构债务追踪
重大架构变更后同步更新本文件和 `.codeartsdoer/rule/` 规则文件

# prompt模板
修改需同步英文和日文文件

# 默认原则
1. 不提交无边界的 ruff、格式化、导入整理或大面积实现整理
2. 本地实验目录不进入共享历史

# 插件开发
- 文档：https://github.com/Mai-with-u/maibot-plugin-sdk/blob/main/docs/guide.md
- 插件在 /plugins 下独立仓库，改主程序代码需先请求许可
- 提交：https://github.com/Mai-with-u/plugin-repo/blob/main/CONTRIBUTING.md

# 修改文档
功能性变更可修改 /mai-docs，不在上层目录新建

# changelog编写
分用户感知功能侧和开发侧，一个功能一行按模块分。版本号提升不写入

# 智能体自主性架构原则

1. **智能体决策权**：消息链路不替智能体做业务决策，智能体是消息的最终消费者和决策者
2. **通知消息处理**：`is_notify=True` 到达智能体，由规则引擎自主分类（环境信号→不触发Planner，交互信号→可能触发）
3. **规则引擎优先**：待命状态环境感知纯规则计算，不调 LLM
4. **组件兼容核心**：核心只依赖 Protocol，不依赖具体实现类
5. **记忆是连接而非对象**：新记忆=新连接，遗忘=连接衰减，回忆=重新激活模式
6. **Agent-owns-Thinking**：每个智能体拥有独立 ThinkingOrgan，Orchestrator 只协调"谁在思考"
7. **思考-行动分离**：content=内心独白（永不外发），reply 工具=对外回复
8. **拒绝脏数据**：不兜底（值应存在时直接用）+ 不写脏数据（外部 None 时不强行 fallback 写库）
9. **改主程序先请示**：插件在 /plugins 下独立仓库，改 src/ 需先许可

## 核心禁止项

1. 禁止核心直接导入 chat_manager ✅
2. 禁止核心访问 chat_manager._agent_router ✅
3. 禁止核心持有 BotChatSession 可变引用 ✅
4. 禁止核心硬编码 napcat_* 字段 ✅
5. 禁止核心绕过 MessagePort 直接调用 send_service ✅
6. 禁止核心导入 A_memorix 内部模块 ✅
7. 禁止 Orchestrator 通过 enqueue_proactive_task 模拟多智能体
8. 禁止核心直接导入 config_manager 获取模型配置 ✅
9. 禁止核心直接导入 global_config ✅（SSD-11 已完全消除，0处违规；8处整体对象场景保留 noqa+原因注释）
10. 禁止使用 AutonomyEventBus.get_instance() ✅（SSD-10 已消除，改用 get_event_bus_port()）

# 核心架构：微内核 + 接口契约

核心模块不依赖组件具体实现，只通过 Protocol 接口交互。适配器层（`src/core/adapters/`）是唯一允许导入组件具体类的地方。

## 核心接口层

| Protocol | 职责 | 实现者 |
|---|---|---|
| MessagePortV2 | 统一消息发送 | SendServiceMessagePortV2 |
| SessionRepository | 会话查询 | ChatManagerAdapter |
| AgentRoutingService | 智能体路由 | ChatManagerRoutingAdapter |
| AgentConfigProvider | 智能体配置查询 | AgentConfigProviderAdapter |
| ChatRuntime | 运行时接口 | MaisakaHeartFlowChatting |
| ChatRuntimeRegistry | 运行时注册表 | HeartflowRuntimeRegistry |
| ChatRuntimeFactory | 运行时工厂 | MaisakaRuntimeFactory |
| NoticeClassifier | 通知分类 | NapCatNoticeClassifier |
| MemoryServicePort | 记忆服务（16方法） | AMemorixMemoryServicePort |
| SessionInfoPort | 会话信息反查 | ChatManagerAdapter |
| SessionLifecyclePort | 会话生命周期 | ChatManagerAdapter |
| SessionQueryPort | 会话批量查询 | ChatManagerAdapter |
| MessageRegistryPort | 入站消息注册 | ChatManagerAdapter |
| ThinkingOrgan | 思维管道 | ThinkingOrgan |
| ThinkingOrganFactory | 思维管道工厂 | ThinkingOrganFactory |
| ReplyerServicePort | 回复生成器服务 | ReplyerServiceAdapter |
| ImageDescriptionPort | 图片描述服务 | ImageDescriptionAdapter |
| PersonInfoPort | 人物信息查询（6方法） | PersonInfoPortAdapter |
| ModelConfigPort | 模型配置查询（4+2方法） | ConfigManagerModelConfigPort |
| LLMService | LLM服务（4方法） | LLMServiceAdapter |
| BotConfigPort | 机器人配置查询（5方法） | GlobalConfigBotConfigPort |
| ChatConfigPort | 聊天配置查询（11方法） | GlobalConfigChatConfigPort |
| AppConfigPort | 应用配置查询（~65方法） | GlobalConfigAppConfigPort |
| AutonomyEventBusPort | 智能体自主性事件总线 | AutonomyEventBus |

### 快照类型

| 快照 | 字段数 | 用途 |
|------|--------|------|
| PluginRuntimeSnapshot | 6 | 插件运行时配置（enabled/ipc_socket_path等） |
| PersonDetailSnapshot | 4 | 人物详情（is_known/person_id/person_name/nickname） |

### 全局注册点

| 注册点文件 | 注册 Protocol | 注册/获取/重置 |
|-----------|-------------|--------------|
| app_config_port_registry.py | AppConfigPort | get/set/reset |
| person_info_port_registry.py | PersonInfoPort | get/set/reset |
| model_config_port_registry.py | ModelConfigPort | register/get/reset |
| runtime_port_registry.py | ChatRuntimeRegistry + ChatRuntimeFactory | register/get |

## 内心状态三层

- **情绪层**：当前情绪状态，由环境刺激和内部驱动共同决定
- **欲望层**：内在需求（表达欲、社交欲、好奇心），驱动主动行为
- **记忆层**：通过 MemoryServicePort 访问，记忆是连接而非对象

## 管家系统

管家（agent_id=rita），客厅守护者。三层过滤（规则→管家LLM→角色LLM）决定插话，定时提醒通过 ThinkingOrgan.think_proactive() 触发。管家专用工具：`switch_primary`/`activate_agent`。

# SSD 审查规范

CA 派发审查任务时，CC 按以下维度输出报告（写入 `.shared/handoff/cc2ca_{task}_review_{date}.md`）：

## 事实准确性
对照实际代码验证文件路径、类名、方法名、行号。grep/Read 确认，不凭记忆。

## 设计合理性
- 是否符合大道至简（过度工程化？DI 容器、DAG 拓扑、本地镜像类型？）
- 是否够彻底（DeprecationWarning 代替删除？fallback 代替异常上浮？）

## 任务可执行性
每个 `- [ ]` 是否真的能完成。验证命令是否可跑。批间依赖是否正确。

## CC/Codex 派发建议
每个子任务标注负责人+理由。参照 `.shared/decisions/cc_vs_codex_routing_guide.md`。

## 遗漏检查
文档没覆盖但代码实际存在的依赖、调用方、边界情况。

## 审查自由度
- 不需逐行核对所有行号，优先核验关键路径
- 发现 SSD 遗漏直接在报告里补充
- 细节小问题不需要卡住整个任务，结论写"建议直接执行，同时修正 N 点"
- 派发建议是参考不是命令，10 行的小文件顺手做掉不用非得派给 Codex
- 报告长度匹配任务复杂度，小任务不凑字数

# 已完成 SSD 摘要

| SSD | 主题 | 关键成果 |
|-----|------|---------|
| SSD-1 | ChatManager Protocol 补全 | ChatManagerAdapter 5合1 Protocol + SessionInfo 不可变快照 |
| SSD-2 | ChatManager 单例拆分 | 604→143行，6子模块（SessionStore/MessageRegistry/SessionNameCache/SessionResolver/BindingRestorer/SessionLifecycle） |
| SSD-3 | ChatManager 单例物理退役 | 子模块直接注入 + 模块级单例移除 |
| SSD-4 | 存量债务清理 | SessionMessage→common层、is_bot_self→core/identity、napcat_*入站化、enqueue_proactive_task瘦身 |
| SSD-5 | 启动流程改革 | 6阶段 StartupOrchestrator + 非关键组件降级 + 核心就绪≤5s |
| SSD-6 | 智能体配置协议化 | AgentConfigProvider Protocol（7方法）替代 AgentConfigRegistry 直接导入 |
| SSD-7 | LLM服务协议化 | LLMService Protocol（4方法）替代 18处 LLMServiceClient 直接导入 |
| SSD-8 | 插件上下文协议化 | MessageIngestionPort + ChatRuntime 扩展，消除 chat_bot/heartflow_manager 直接导入 |
| SSD-9 | Common层架构归正 | H6参数注入消除 heartflow_manager 反向依赖 + M8 PersonInfoPort Protocol |
| 快速修复 | M2+M3+H7+M4 | SessionMessage/is_bot_self 导入路径替换 + ReplyerServicePort/memory_service 绕过修复 |
| SSD-10 | 配置与事件注入化 | BotConfigPort/ChatConfigPort/AppConfigPort/AutonomyEventBusPort Protocol + 15项死配置删除 + 13项DEPRECATED + AutonomyEventBus.get_instance()消除 |
| SSD-11 | SSD-10 遗留协议化 | global_config TID251 从41处降至0处（8处整体对象场景保留noha），ChatConfigPort 5→13方法，AppConfigPort 21→78方法，5个新快照类型，14处死导入清除，is_bot_self替代qq_account直接访问，BotConfigPort新增get_bot_platform/get_bot_primary_account，service_task_resolver.model_name_exists替代config_manager |
| SSD-12 | 剩余 TID251 违规消除 | config_manager 4处/heartflow_manager 2处/Person 4处 TID251 清零，AppConfigPort +5方法（~60→~65），ChatRuntimeRegistry +2方法（3→5），PersonInfoPort +5方法（1→6），新建 model_config_port_registry，新增 PluginRuntimeSnapshot/PersonDetailSnapshot 快照类型 |

# 待后续

- ⬜ 欲望驱动主动发言集成
- ⬜ WebUI 记忆可视化
- ⬜ A_memorix 内部 322 处 bare except
- ⬜ mem_core_gap 未覆盖的 8 项差距（G16/G18/G19/G21/G22/G23/G24/G28）
- ⬜ SSD-11 遗留：runtime.py expression/MCPConfig 整体对象、utils_config.py 多域混合、plugin_runtime 整体对象、maim_message 整体对象、emoji缓存清理/图片缓存清理 整体对象、webui/routes/chat reply_style 整体对象
