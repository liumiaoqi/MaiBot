# 代码规范
# import 规范
在从外部库进行导入时候，请遵循以下顺序：
1. 对于标准库和第三方库的导入，请按照如下顺序：
    - 需要使用`from ... import ...`语法的导入放在前面。
    - 直接使用`import ...`语法的导入放在后面。
    - 对于使用`from ... import ...`导入的多个项，请**在保证不会引起import错误的前提下**，按照**字母顺序**排列。
    - 对于使用`import ...`导入的多个项，请**在保证不会引起import错误的前提下**，按照**字母顺序**排列。
2. 对于本地模块的导入，请按照如下顺序：
    - 对于同一个文件夹下的模块导入，使用相对导入，排列顺序按照**不发生import错误的前提下**，随便排列。
    - 对于不同文件夹下的模块导入，使用绝对导入。这些导入应该以`from src`开头，并且按照**不发生import错误的前提下**，尽量使得第二层的文件夹名称相同的导入放在一起；第二层文件夹名称排列随机。
3. 标准库和第三方库的导入应该放在本地模块导入的前面。
4. 各个导入块之间应该使用一个空行进行分隔。
5. 对于现有的代码，如果导入顺序不符合上述规范，在重构代码时应该调整导入顺序以符合规范。

## 注释规范
1. 尽量保持良好的注释
2. 如果原来的代码中有注释，则重构的时候，除非这部分代码被删除，否则相同功能的代码应该保留注释（可以对注释进行修改以保持准确性，但不应该删除注释）。
3. 如果原来的代码中没有注释，则重构的时候，如果某个功能块的代码较长或者逻辑较为复杂，则应该添加注释来解释这部分代码的功能和逻辑。
## 类型注解规范
1. 重构代码时，如果原来的代码中有类型注解，则相同功能的代码应该保留类型注解（可以对类型注解进行修改以保持准确性，但不应该删除类型注解）。
2. 重构代码时，如果原来的代码中没有类型注解，则重构的时候，如果某个函数的功能较为复杂或者参数较多，则应该添加类型注解来提高代码的可读性和可维护性。（对于简单的变量，可以不添加类型注解）
3. 对于参数化泛型，应该使用`typing`模块中的类型注解来指定参数化泛型的类型。
    - 例如，使用`List[int]`来表示一个包含整数的列表，使用`Dict[str, Any]`来表示一个键为字符串，值为任意类型的字典。

## 变量规范
1. 当确定某个变量/实例是某种类型的时候（优先按照类型注解确定，除非你分析出类型注解是错误的），可以不必使用`or`进行fallback。
    - 例如，`bot_nickname = (global_config.bot.nickname or "").strip()` 可以改为 `bot_nickname = global_config.bot.nickname.strip()`，前提是我们确定`global_config.bot.nickname`一定是一个字符串。
2. `or ""` 兜底消除进度：当前 A_memorix 全局 ~1315 处（分类学代码占大头，将在第5批退役时清理）。已清理：host_service.py 50→1、memory_service.py 23→13、SDKMemoryKernel 3 处。合理豁免场景：外部数据源返回值可能为 None（如 `dict.get(key, "") or ""` 中 dict.get 已提供默认值时可删除；`str(x or "").strip()` 在 x 已知为 str 时可简化为 `x.strip()`）。

## 类属性使用规范
1. 应该尽量减少使用getattr和setattr方法，除非是在对一个动态类进行处理或者使用Monkeypatch完成Pytest
2. 在重构代码时，如果遇到getattr和setattr，应该尝试检查这个类实例是否有这个属性，如果有，则直接替换为类属性访问写法。
    - 举例：`v = getattr(instance, "value", "")` 在检查到`instance`有`value`属性后应该改为`v = instance.value`
3. getattr 消除进度：SDKMemoryKernel 中 8→0 处（✅ 已完成）。retrieval_tuning_manager 22→3（保留：动态 LLM task_config、搜索结果 hash_value）。web_import_manager 15→5（保留：numpy ndim、动态属性名循环、上传对象、LLM task_config）。plugin.py 3→1（保留：动态方法分派）。新增 SDKMemoryKernel.is_embedding_degraded() 方法暴露降级状态。保留场景判定标准：对动态能力检测的 getattr（如 `encode_batch`、`iter_vectors_by_ids`）通过 Protocol 接口统一后消除；对已知接口的 getattr 替换为直接属性访问；对动态外部对象（LLM task_config、numpy 数组、上传对象）的 getattr 合理保留。

## debug规范
1. 不要总是想找兜底，一定要精准的找到问题的核心，然后提出建议，兜底是不合适，难以维护的。
2. 不要总是考虑fallback，如果哪里有错误，一定要让他及时完整的暴露，而不是用fall_back兜底掩盖过去
3. 区分"不兜底"与"不写入脏数据"：
    - **不兜底**：当确定某个值应该存在时，直接使用，不用 `or ""` / `or None` 掩盖可能的错误。错误应完整暴露。
    - **不写入脏数据**：当某个值确实可能不存在（如外部数据源返回 None），不应强行计算一个 fallback 值写入数据库，而应跳过或报错。这不是"兜底"，而是"拒绝脏数据"。

# 运行/调试/构建/测试/依赖
优先使用uv
依赖项以 pyproject.toml 为准，要同步更新requirements.txt
不要总是考虑fallback，如果哪里有错误，一定要让他及时完整的暴露，而不是用fall_back兜底掩盖过去

# 语言规范
项目的首选语言为简体中文，无论是注释语言，日志展示语言，还是 WebUI 展示语言都首要以简体中文为首要实现目标

# 配置文件修改
如果你需要改动配置文件，不需要修改实际的bot_config.toml或者model_config.toml，只需要修改配置文件模版，并新增一个版本号即可，也不必要为配置改动创建测试文件。
除非明确说明，否则不要擅自新增 ConfigUpgradeHook
禁止改动 legacy_migration，此文件以固定

# Webui规范
涉及显示聊天流信息的，优先显示聊天流实际名称（群名称或 xxx的私聊），而不是session_id

如果遇到 UI 高度/布局问题：
对比展开前后 DOM，找新增元素和新增属性。
查 data-dashboard-style 主题样式，尤其是 !important。
查 computed style 的实际 height/min-height，而不是只看 Tailwind class。
如果遇到 UI 底纹、阴影、半透明、模糊或颜色叠加问题，先按 DOM 层级拆分父容器、触发器、内部装饰元素和伪元素，逐层查 computed style 的 background/background-color/background-image/backdrop-filter/box-shadow/opacity，不要只盯着截图中最显眼的子元素或只看 class。
涉及 Tabs/TabsList/TabsTrigger、Radix 或 motion 动画指示器时，要先确认视觉效果来自 TabsList 容器、TabsTrigger 本体、内部 motion/span，还是父级 header/card/dialog 的 backdrop-filter 或主题覆盖，再做最小范围修改。
Radix 组件不随便移出上下文，像 TabsTrigger 必须留在 TabsList 里。

修改完webui不用急着npm run build，这个应该手动来
WebUI 开发服务固定起到 7999 端口。

# 会话 ID 规范
除聊天流创建/注册链路外，业务模块不应自行调用 `SessionUtils.calculate_session_id` 计算资源归属 ID。表达学习、黑话、记忆、WebUI、配置匹配等模块应通过 `SessionRepository` Protocol 接口查询已存在的真实聊天流；如果查询不到真实 `ChatSession.session_id`，不应强行计算 fallback hash 写入数据库——这是拒绝脏数据，不是兜底。

# 关于 A_memorix 修改
A_Memorix 是 MaiBot 的核心记忆子系统，可以自由修改。修改约束仅来自 MaiBot 自身架构原则（核心隔离、Protocol 接口契约），详见 `src/A_memorix/MODIFICATION_POLICY.md`。

当前重构进展：SDKMemoryKernel 已从 9650 行瘦身至 2911 行；`services/` 目录已提取 14 个服务文件；`admin/` 目录已提取 13 个 Admin Handler；`_KernelRuntimeFacade` 已删除；`host_service` 直接访问服务实例；**SDKMemoryKernel 完全隔离已完成**（`src/A_memorix/core/` 零违规导入，28→0，所有外部依赖通过 AMemorixServicePorts 构造注入）。

当前约束：子模块不反向持有 SDKMemoryKernel 引用；外部 API 签名不变；不引入新的循环依赖。

# 架构债务追踪
重大架构变更（新增/删除 Protocol、消除架构债务、核心模块迁移）完成后，应同步更新 AGENTS.md、tasks.md 和 `.codeartsdoer/rule/` 规则文件中的相关描述，确保规则性文件与代码实际状态一致。详见 `.codeartsdoer/rule/MaiBot智能体自主性架构.mdc` 末尾的"规则文件同步元规则"。

# prompt模板
涉及对prompt模板的修改，要同步修改英文和日文的文件，对齐到中文

默认原则：
1. 不要提交无边界的 `ruff`、格式化、导入整理或大面积实现整理。
2. 本地实验目录或依赖其运行的测试，除非明确说明并确认，否则不要进入共享历史。

# maibot插件开发文档
https://github.com/Mai-with-u/maibot-plugin-sdk/blob/main/docs/guide.md

如果你要编写插件，不要改动根目录的.gitignore，而是在/plugins下创建独立仓库，然后进行编写
如果你要编写插件有需求需要改动主程序代码，请你先请求许可。

插件仓库路径在本地上层文件夹plugin-repo下


# 修改文档
如果有功能性的变更或者api或者开发变更，可以对根目录下/mai-docs进行修改，不要在上层目录新建内容

# 如何提交maibot插件
https://github.com/Mai-with-u/plugin-repo/blob/main/CONTRIBUTING.md

# 智能体自主性架构原则

1. **智能体决策权原则**：外部系统（bot.py、HeartFlow、ChatManager等消息链路模块）不应替智能体做业务决策。消息是否需要回复、是否触发Planner，应由智能体自身的规则引擎决定，而非在链路中硬编码过滤或分流。消息链路保持透明，智能体是消息的最终消费者和决策者。

2. **通知消息处理原则**：`is_notify=True`的通知消息应到达智能体（通过Orchestrator），由智能体自主分类处理：
   - 纯环境信号（如input_status）→ 规则引擎判定不触发Planner，仅调整生命力/环境上下文
   - 可能需要回应的通知（如poke、入群）→ 规则引擎判定触发Planner，智能体自主决定是否回复
   - 分类规则可配置，但决策权在智能体，不在链路层

3. **规则引擎优先原则**：待命状态的环境感知必须是纯规则计算，不调用LLM。能用规则判断的决策（如"用户正在输入不需要回复"），不应交给Planner推理。规则调整参数而非替智能体决策——规则决定"是否触发Planner"，Planner决定"如何回应"。

4. **组件兼容核心原则**：核心定义接口契约，组件实现契约。核心不依赖组件的具体实现类，只依赖 Protocol。新增代码禁止引入对 chat_manager、send_service、HeartFlow 等组件具体实现的直接导入。

5. **记忆是连接而非对象原则**：记忆不是带标签的标本，而是概念之间的激活模式。新记忆 = 新连接，遗忘 = 连接衰减，回忆 = 重新激活模式。

6. **主智能体-子智能体协作原则**：CA、CC、Codex 是三个平级主智能体，各有优劣，用户根据任务类型选择派发。子智能体是各主智能体下的代理（如 Task subagent、MCP 工具等），由主智能体自主调度。
   - **CA 赢在"想清楚再动手"**：结构化需求分析、Protocol 接口设计、SSD 三阶段文档、代码审查双重标准（正确性 + 是否违背核心原则）、跨智能体协调与任务拆分。CA 是三元协作的协调中枢。
   - **CC 赢在"第一遍就对"**：跨文件重构首次正确率 ~95%、1M 上下文吃透依赖图、协议变更不漏实现。适合需要"理解为什么"的任务。
   - **Codex 赢在"让子弹飞"**：响应速度 ~3× CC、异步执行、代码审查二道防线（不同训练分布捕获 CC 盲点）。适合"定义清晰、只需执行"的任务。
   - **环境隔离**：CC 和 Codex 不在同一环境，无法直接通信，所有协调只能通过 `.shared/handoff/` 和用户中继
   - **原则随任务传递**：任一主智能体分派编码任务时，必须同时传递完成该任务所需遵循的特定原则（从 AGENTS.md 和会话上下文中提取），而非只传递"做什么"
   - **审核双重标准**：主智能体审核其他主智能体产出时，不仅审核代码正确性，更审核是否违背用户的根本原则（核心禁止项、代码风格、架构约束）
   - **禁止自动推进流程**：不得在用户未明确表示"进入下一阶段"时自动推进 SSD 流程；不得主动询问"有什么代码任务"——等待用户发起
   - **上下文压缩后优先恢复原则**：压缩后丢失的首先是"为什么"，恢复时应优先从 AGENTS.md 重新加载核心原则，而非仅恢复任务状态
   - **派发决策**：架构重构→CC；快速修复/Debug/CI→Codex；需求设计/审查→CA；UI/前端→CC；批量后台→Codex；不确定→CC。详细决策参考见 `.shared/decisions/cc_vs_codex_routing_guide.md`。
   - **反模式禁止**：①给 Codex 模糊大任务（必须精确到文件和函数级别）②CC 和 Codex 同时改同一文件（一个周期一方一模块）③只用 CC 自审查（Codex 做二道防线）④让 Codex 做架构决策⑤让 CC 做机械性批量改动⑥用同一个智能体跑到底
   - **文件锁**：CA 派发任务时必须按文件拆分，确保 CC 和 Codex 不会同时改同一文件；编码智能体发现需要改不在任务列表中的文件时先停下来问用户

## 核心禁止项

1. 禁止核心直接导入 chat_manager ✅ 已消除（子模块直接注入 + 单例移除 + ruff TID251 守卫）
2. 禁止核心访问 chat_manager._agent_router ✅ 已消除（构造注入 AgentRouter + ruff TID251 守卫，SSD-4 验证关闭）
3. 禁止核心持有 BotChatSession 可变引用 ✅ 已消除（SessionInfo 不可变快照 + ChatManagerAdapter 立即转换，SSD-4 验证关闭）
4. 禁止核心硬编码 napcat_* 字段 ✅ 已消除（入站点 notice_type_mapping.py 映射 + NapCatNoticeClassifier 改读 notice_kind + ruff banned-api 守卫，SSD-4 T3.1-T3.5）
5. 禁止核心绕过 MessagePort 直接调用 send_service ✅ 已消除 + ruff TID251 守卫
6. 禁止核心导入 A_memorix 内部模块 ✅ 已消除（core/零违规导入 + ruff TID251 守卫 + CI AST脚本）
7. 禁止 Orchestrator 通过 enqueue_proactive_task 模拟多智能体
8. 禁止核心直接导入 config_manager 获取模型配置 ✅ 已迁移（llm_models/services/A_memorix 通过 ModelConfigPort，rff TID251 守卫）

# 核心架构

## 微内核 + 接口契约

核心模块（智能体 + 消息管道）不依赖组件具体实现，只通过 Protocol 接口交互。适配器层（`src/core/adapters/`）是唯一允许导入组件具体类的地方。

### 核心接口层

| Protocol             | 职责　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　 | 实现者　　　　　　　　　　　　　　　　　　　　 |
| ----------------------| --------------------------------------------------------------------------------------------------------------------------| ------------------------------------------------|
| MessagePortV2        | 统一消息发送（1个方法 send_message）　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　 | SendServiceMessagePortV2　　　　　　　　　　　 |
| SessionRepository    | 会话查询　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　 | ChatManagerAdapter　　　　　　　　　　　　　　 |
| AgentRoutingService  | 智能体路由　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　 | ChatManagerRoutingAdapter　　　　　　　　　　　|
| AgentConfigProvider  | 智能体配置查询（7方法，替代直接导入AgentConfigRegistry）　　　　　　　　　　　　　　　　　　　　　　　　　　　　 | AgentConfigProviderAdapter　　　　　　　　　　 |
| ChatRuntime          | 运行时接口　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　 | MaisakaHeartFlowChatting　　　　　　　　　　　 |
| ChatRuntimeRegistry  | 运行时注册表　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　 | HeartflowRuntimeRegistry　　　　　　　　　　　 |
| ChatRuntimeFactory   | 运行时工厂（打破 heartflow→maisaka 依赖）　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　| MaisakaRuntimeFactory　　　　　　　　　　　　　|
| NoticeClassifier     | 通知分类　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　 | NapCatNoticeClassifier　　　　　　　　　　　　 |
| MemoryServicePort    | 记忆服务（16方法：observe/recall/recall_with_intuition/derive_profile/reflect/weave_narrative/heartbeat_maintenance 等） | AMemorixMemoryServicePort　　　　　　　　　　　|
| SessionInfoPort      | 会话信息反查　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　 | ChatManagerAdapter（通过注册点注入 A_memorix） |
| SessionLifecyclePort | 会话生命周期（创建/持久化/初始化）　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　 | ChatManagerAdapter　　　　　　　　　　　　　　 |
| SessionQueryPort     | 会话批量查询/路由元数据　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　| ChatManagerAdapter　　　　　　　　　　　　　　 |
| MessageRegistryPort  | 入站消息注册　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　 | ChatManagerAdapter　　　　　　　　　　　　　　 |
| ThinkingOrgan        | 思维管道　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　 | ThinkingOrgan（agent_autonomy）　　　　　　　　|
| ThinkingOrganFactory | 思维管道工厂　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　 | ThinkingOrganFactory　　　　　　　　　　　　　 |
| ReplyerServicePort   | 回复生成器服务（maisaka 通过此接口获取 replyer）　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　 | ReplyerServiceAdapter　　　　　　　　　　　　　|
| ImageDescriptionPort | 图片描述服务（maisaka 通过此接口获取图片描述）　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　 | ImageDescriptionAdapter　　　　　　　　　　　　|
| PersonInfoPort       | 人物信息查询（core 层通过此接口查询人物，替代 Person 直接导入）　　　　　　　　　　　　　　　　　　　　　　　　　　　| PersonInfoPortAdapter　　　　　　　　　　　　　|
| ModelConfigPort      | 模型配置查询（4查询+2回调，支持智能体级覆盖）　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　| ConfigManagerModelConfigPort　　　　　　　　　 |
| LLMService           | LLM服务（4方法：generate_response/generate_response_with_messages/generate_response_for_image/transcribe_audio）　　　　　 | LLMServiceAdapter　　　　　　　　　　　　　　 |

## 内心状态三层

- **情绪层**：当前情绪状态，由环境刺激和内部驱动共同决定
- **欲望层**：内在需求（表达欲、社交欲、好奇心），驱动主动行为
- **记忆层**：通过 MemoryServicePort 访问，记忆是连接而非对象

## Agent-owns-Thinking

每个智能体拥有自己的思维管道（ThinkingOrgan），Orchestrator 只协调"谁在思考"，不关心"怎么思考"。共居智能体可并行思考（ParallelThinkScheduler）。

## 管家系统

管家是第14个智能体——**丽塔·洛丝薇瑟**（agent_id=rita），客厅的守护者。

### 核心机制
- **协调插话**：管家看到用户消息 + 主智能体回复，三层过滤（规则→管家LLM→角色LLM）决定谁该插话，每次最多2人
- **管家发言**：管家以丽塔人格自己发言——引导话题、接话、提醒，主智能体 SILENT 时自动接管回复
- **定时提醒**：管家创建和管理定时提醒（如"3点提醒我开会"）
- **主发言权切换**：管家通过 `switch_primary` 工具切换主发言智能体
- **智能体激活**：管家通过 `activate_agent` 工具唤醒待命的智能体

### 管家智能体特性
- `is_butler: true` — 标记为管家，始终 active，不进入 standby
- 从来不能被选为 primary（router + registry 双重防护）
- 主智能体 prompt 中注入管家存在提示（`{butler_context}`）

### 管家专用工具
- `switch_primary` — 切换主发言权（deferred，仅管家可用）
- `activate_agent` — 唤醒待命智能体（deferred，仅管家可用）

### 三层过滤
- 规则过滤（零成本）：名字被提到→必看见；有关系→可能看见；无关→很少看见
- 管家LLM（1次调用）：理解话题+角色性格+关系网，判断"谁会关心"
- 角色LLM（仅选中者）：被选中的角色决定插话内容

### 提醒流
- 到时提醒通过 ThinkingOrgan.think_proactive() 触发，不走 enqueue_proactive_task

### 插话流
- 通过 ThinkingOrgan.think() 触发，结果通过 MessagePortV2.send_message() 发出

# 回复系统迁移进展

**迁移已完成**（阶段1-5全部完成）

## 迁移架构

- **MessagePortV2**：统一消息端口协议，1个方法 `send_message(session_id, message, *, reply_to_id, agent_id, source)`
- **SendServiceMessagePortV2**：直通实现，send_service 自身实现 MessagePortV2 Protocol，直接调用 `_send_to_target_with_message`
- **segments_to_message_sequence**：模块级工具函数，dict → MessageSequence 转换（供插件运行时使用）

## 已完成

- ✅ 阶段1：新 Protocol + 桥接适配器（零风险引入）
- ✅ 阶段2：reply.py 迁移（删除 _message_sequence_to_segments，消除 dict 序列化层）
- ✅ 阶段3：直通实现（SendServiceMessagePortV2 替代 BridgedMessagePortV2，消除桥接层和延迟导入）
- ✅ 阶段4：所有调用方迁移（butler/orchestrator/vitality_manager/emoji/send_image/plugin_runtime）
- ✅ 阶段5：旧 MessagePort Protocol 移除（7方法→1方法，SendServicePort 删除，plugin_runtime send_command/send_custom 迁移）

## 消除的 bug

1. dict 序列化丢失 content/binary_data → 消除（MessageSequence 直传）
2. _resolve_reply_message 全表扫描 → 消除（简化查找）
3. set_reply=bool(reply_to) 误判 → 消除（基于 reply_message is not None）

# ChatManager Protocol 补全进展（SSD-1）

**迁移已完成**（阶段1-5全部完成）

## 迁移架构

- **ChatManagerAdapter**：统一适配器，同时满足 5 个 Protocol（SessionRepository + SessionInfoPort + SessionLifecyclePort + SessionQueryPort + MessageRegistryPort）
- **session_port_registry**：全局注册点，4 对注册/获取函数
- **SessionInfo**：不可变会话快照，新增 account_id/scope/user_cardname 字段

## 已完成

- ✅ 阶段1：Protocol 定义 + 适配器实现（3个新Protocol + ChatManagerAdapter + 注册点扩展）
- ✅ 阶段2：核心层消费者迁移（main.py → SessionLifecyclePort，heartflow_manager → SessionInfoPort）
- ✅ 阶段3：BotChatSession 可变引用消除（replyer/runtime/send_service/database_service/CLI）
- ✅ 阶段4：外围模块导入消除（WebUI 6文件 + 学习器 4文件 + 插件运行时 2文件 + 工具/配置 4文件 + person_info）
- ✅ 阶段5：旧适配器清理（删除 ChatManagerSessionRepository，统一注册逻辑）

## 待后续

- ✅ SSD-2：ChatManager 单例拆分（已完成，详见下方 SSD-2 章节）

# ChatManager 单例拆分进展（SSD-2）

**迁移已完成**（阶段1-6全部完成）

## 拆分架构

- **ChatManager**：薄协调层（143行），持有6个子模块实例，对外方法逐一委托
- **SessionStore**：会话存储 CRUD + 单条持久化（`session_store.py`）
- **MessageRegistry**：消息注册 + 缓存 + 身份更新（`message_registry.py`）
- **SessionNameCache**：名称查询（`session_name_cache.py`）
- **SessionResolver**：路由解析 + 数据库懒加载（`session_resolver.py`）
- **BindingRestorer**：启动时智能体绑定恢复（`binding_restorer.py`）
- **SessionLifecycle**：创建/获取 + 批量持久化 + 初始化（`session_lifecycle.py`）

## 已完成

- ✅ 阶段1：SessionStore 提取（sessions 字典 CRUD + 单条持久化 + 延迟注入 MessageRegistry）
- ✅ 阶段2：MessageRegistry 提取（消息注册 + 缓存 + 身份更新）
- ✅ 阶段3：SessionNameCache 提取（名称查询）
- ✅ 阶段4：SessionResolver 提取（路由解析 + 数据库懒加载）
- ✅ 阶段5：BindingRestorer 提取（智能体绑定恢复）
- ✅ 阶段6：SessionLifecycle 提取 + ChatManager 清理（604→143行，routes.py sessions.pop 已封装）

# 存量债务继续清（SSD-4）

**编码已完成**（5 批次 17 任务全部完成，CC+Codex 协作 + CA 审查修正）

## 完成的变更

| 批次 | 任务 | 负责人 | 内容 |
|------|------|--------|------|
| 1 | T1.1 | Codex | #2/#3 验证关闭（chat_manager 单例 + BotChatSession 可变引用） |
| 1 | T1.2 | Codex | MemoryField 竞态修复（两阶段初始化） |
| 2 | T2.1 | CC | SessionMessage 物理迁移到 common 层 |
| 2 | T2.2 | Codex | is_bot_self/get_bot_account 物理迁移到 core/identity.py |
| 2 | T2.3 | CC | is_mentioned_bot_in_message/get_chat_type_and_target_info 迁移到 core/message_utils.py |
| 2 | T2.4 | Codex | HeartflowRuntimeRegistry 构造注入 |
| 2 | T2.5 | CC | core 层零 chat 导入验证（ruff TID251 确认） |
| 3 | T3.1-T3.5 | CC | napcat_* 入站化（notice_type_mapping.py + bot.py 入站点 + NapCatNoticeClassifier 改读 notice_kind + ruff banned-api 守卫 + 全量验证） |
| 4 | T4.1-T4.3 | Codex | enqueue_proactive_task 协议瘦身（chat_loop_adapter 代理移除 + grep 守卫 + 文档字符串强化） |
| 5 | 修正 | CA | CC 审查修正（补导入/清 getattr/删残留）+ SSD-3 遗留函数体清理 |

## 关键架构变更

1. **SessionMessage → common 层**：chat/message_receive/message.py 从 549 行瘦身至 3 行纯 re-export
2. **is_mentioned_bot_in_message → core 层**：core/message_utils.py 持有真实定义，消除 getattr 8 处
3. **napcat_* 入站化**：核心层零 napcat_ 代码引用，通知分类在入站点（bot.py）完成
4. **NapCatNoticeClassifier 改造**：优先读取入站点预填充的 notice_kind，兼容回退已标注 TODO
5. **utils.py 函数体清理**：911→284 行，SSD-3+SSD-4 全部已迁移函数体删除，仅保留 re-export

# 记忆系统范式迁移进展

当前阶段：**NEW_INDEPENDENT**（分类学代码 graph_ops/ 已标记 DEPRECATED 且零调用，所有请求走连接主义系统 `src/A_memorix/core/connectionist/`）

## 迁移架构

- **MigrationAdapter**：5阶段状态机（LEGACY_ONLY→DUAL_WRITE→DUAL_READ→DATA_MIGRATION→NEW_INDEPENDENT），advance_phase() 逐级推进，跳级报错
- **MigrationRouter**：迁移感知路由，NEW_INDEPENDENT 阶段所有请求走连接主义
- **ConnectionistTranslator**：连接主义→分类学格式翻译（RecallItem→MemoryHit，ProfileView→画像字典）
- **MemoryServicePort** 已切换到迁移路由（核心调用方零修改）
- **SemanticConceptExtractor**：jieba 降级概念提取器（LLM 失败时降级）

## 已完成

- ✅ 第1批：配置驱动的智能体注册（MemoryPersonalityV2Config/InnerVoiceItemConfig + 启动注册 + jieba降级）
- ✅ 第2批：迁移框架（MigrationAdapter阶段约束 + invoke阶段守卫 + granular_decay心跳 + migration_status）
- ✅ 第3批：迁移路由层与翻译层（ConnectionistTranslator + MigrationRouter + MemoryService委托切换）
- ✅ 第4批：数据迁移（DataConverter LLM增强 + 迁移脚本）
- ✅ 默认阶段跳至 NEW_INDEPENDENT（v8.24.0，分类学代码保留但不再调用）

# 记忆叙事原型进展

**编码已完成**（第1-7批全部完成，端到端集成验证通过）

## 叙事原型架构

- **NarrativeWeaver**：Fragment→Episode→Saga 三层叙事自组织（LLM 生成+降级）
- **CognitiveStratifier**：概念节点四层认知标注（immutable_fact/stable_trait/current_state/active_hypothesis）+ 证据积累 + 升级/降级
- **LifecycleManager**：Fragment/Episode/Saga 生命周期推进（active→cooling→frozen→tombstone），与粒度退化正交
- **IntuitionEngine**：关键词+bigram 双层直觉触发，纯规则计算 ≤5ms，替代全量 dump
- **MemoryField**：门面集成，持有4个子模块实例，observe() 后 fire-and-forget 通知 CS/NW，心跳协调 granular_decay→advance_lifecycle→process_cognitive_decay

## 已完成

- ✅ 第1批：数据模型+枚举+TraceStore扩展（commit 92b17eb23）
- ✅ 第2批：NarrativeWeaver叙事编织核心（commit 09ffe6f49）
- ✅ 第3批：CognitiveStratifier认知分层（commit e517a4595）
- ✅ 第4批：LifecycleManager生命周期管理（commit 524e73a88）
- ✅ 第5批：IntuitionEngine直觉引擎（commit 736ba9abf）
- ✅ 第6批：MemoryField集成+Observer通知+心跳协调+ProfileDeriver扩展（commit 0ca4d0c13）
- ✅ 第7批：迁移守卫+HostService API+集成验证（commit 0da71485b）

## 待实现细节

- ✅ recall_with_intuition() 便捷方法（mem_core_gap 已实现）
- ⬜ LLM prompt 三语模板文件（narrative/prompts/ 目录）
- ⬜ ConnectionistTranslator 叙事格式翻译（DUAL_READ 阶段才需要）

## 关键设计决策

1. Fragment 是视图不是表——通过 TraceStore.query_by_observation_ids() 动态构建
2. Episode/Saga 有独立存储（EpisodeStore SQLite），但可追溯到底层 Trace
3. Episode.all_concepts 字段——底层 Fragment 概念并集，用于 Saga 连接检测
4. 四个子模块通过 MemoryField 门面协调，不互相直接依赖
5. 异步非阻塞集成——Observer.observe() 完成后由 MemoryField 异步通知 CS 和 NW
6. 迁移阶段守卫——DUAL_WRITE 阶段仅写入，DUAL_READ 及以后才读取直觉/认知
7. 生命周期与粒度退化正交——退化管细节（detail_level），生命周期管存在权（status）
8. 直觉触发纯规则——关键词+bigram 双层匹配，停用词过滤，零 LLM 调用

# 记忆系统与核心架构差距（mem_core_gap，已完成）

**6 批编码全部完成**，21/29 项差距覆盖，8 项不在本期范围。

## 关键变更

1. **MemoryServicePort 从 10 方法扩展到 16 方法** — 新增 recall/recall_with_intuition/derive_profile/reflect/weave_narrative/heartbeat_maintenance，删除 ingest_text
2. **异常子类体系** — MemoryServiceError → TemporaryMemoryError / PermanentMemoryError / MemoryNotFoundError
3. **单例模式** — `get_memory_service_port()` + `reset_memory_service_port()` 替代 13 处独立实例化
4. **数据类型下放 common 层** — `src/common/memory_types.py`（8 个纯数据类型），`src/common/memory_utils.py`（从 core 迁移），core/types.py 重新导出
5. **A_memorix/core/ 零运行时 core 导入** — 4 文件切到 common，1 个改 AMemorixServicePorts 注入
6. **observe_experience() 统一 ObserveRequest 对象**
7. **MemoryWriteResult 扩展** — 新增 observation_id / concept_names
8. **直觉接入思考循环** — `_build_think_context()` 调用 `recall_with_intuition()`，填充 `memory_snippets` + `intuition_context`
9. **heuristic_injector 直觉优先** — `recall_with_intuition()` + `search()` 降级
10. **情绪联动** — ExperienceWriter 新增 `emotion_manager` 注入，实时情绪→valence 自动推导

## 未覆盖的 8 项差距（不在本期范围）

- G16 host_service 直接访问 kernel 私有属性（修复成本高，影响低）
- G18 Agent-owns-Thinking 与记忆性格未联动（agent_id 参数已传递，深度联动待后续）
- G19 管家系统与记忆系统未联动（需新增关系查询接口）
- G21 叙事弧未接入智能体认知（weave_narrative 已暴露，深度集成待后续）
- G22 AsyncWriteQueue 延迟启动竞态（已有保护机制）
- G23 ModelConfigPort 注入时序无检查（已有 None 保护）
- G24 记忆性格注册窗口期（需核心调度时序保证）
- G28 A_memorix 内部 322 处 bare except（修复成本极高，逐个审查需单独排期）

# 启动流程改革进展（SSD-5，已完成）

**6 批次编码+集成验证全部完成**，消除了启动流程7类缺陷。

## 关键变更

1. **6阶段 StartupOrchestrator**：CONFIG_LOAD→INFRASTRUCTURE→CORE_SERVICES→SUBSYSTEMS→SESSION_RESTORE→READY，每阶段独立计时
2. **非关键组件降级**：A_memorix/插件运行时/WebUI/交互调度器失败时系统降级运行而非崩溃
3. **核心就绪指标**：CoreReadiness 三条件（消息管道+智能体思考+回复能力），核心就绪 ≤5s
4. **config_manager 延迟初始化**：模块级 `None` + `initialize_config()` 显式调用，消除模块级副作用
5. **就绪屏障**：消息处理器在消息服务启动前注册，消除启动窗口期消息丢失
6. **消除 hack**：3处 asyncio.sleep 轮询 + 1处 getattr 私有属性访问

## 新增文件

- `src/core/startup/__init__.py` — 包导出
- `src/core/startup/types.py` — 数据模型（StartupPhase/ComponentStatus/CoreReadiness 等）
- `src/core/startup/orchestrator.py` — StartupOrchestrator（阶段编排+启动摘要+降级逻辑）
- `src/core/startup/validator.py` — StartupValidator（配置前置校验）

## 修改文件

- `bot.py` — 入口补充 `initialize_config()` 调用
- `src/main.py` — 重构为6阶段启动，接入 StartupOrchestrator
- `src/config/config.py` — config_manager 延迟初始化
- `src/plugin_runtime/integration.py` — 新增 ready_event
- `src/A_memorix/host_service.py` — 新增 ready_event

# LLM 服务协议化进展（SSD-7，已完成）

**迁移已完成**（5 批次全部完成）

## 迁移架构

- **LLMService** Protocol：4 方法（generate_response/generate_response_with_messages/generate_response_for_image/transcribe_audio），task_name 从构造参数提升为方法参数
- **LLMServiceAdapter**：纯委托适配器，OrderedDict LRU 缓存（maxlen=64），按 task_name:request_type:session_id 为键
- **注册点**：`get_llm_service()`/`set_llm_service()`/`reset_llm_service()`，与 MemoryServicePort/AgentConfigProvider 模式一致
- **ruff 守卫**：`src.services.llm_service.LLMServiceClient` banned-api + `src/services/llm_service.py` per-file-ignores

## 已完成

- ✅ 批次1：LLMService Protocol + LLMServiceAdapter + 注册点 + 启动注册 + ruff 守卫
- ✅ 批次2：核心消费方迁移（butler/heuristic_injector/chat_loop_service/replyer/mid_term）
- ✅ 批次3：学习器迁移（jargon_miner/jargon_learner/expression_utils/expression_learner/behavior_learner）
- ✅ 批次4：其他基础设施迁移（emoji_manager/image_manager/utils_voice/host_llm_bridge/memory_flow_service）
- ✅ 批次5：WebUI/插件层迁移（behavior.py/core.py）+ 全量验证

## 消除的架构债务

1. 18 处 `LLMServiceClient` 直接导入 → 全部替换为 `LLMService` Protocol
2. `chat_loop_service._llm_chat_clients` 缓存字典 → 适配器统一管理
3. `replyer/generator_base.llm_client_cls` 类参数 → `llm_service: LLMService` 实例参数
4. 6 个模块级 `LLMServiceClient` 实例 → 注册点 `get_llm_service()`

## 待后续

- ⬜ A_memorix 4 处 `LLMServiceClient` 通过 `AMemorixServicePorts.llm_service` 注入整个模块，后续优化为 `LLMService` Protocol 注入

# 插件上下文协议化进展（SSD-8，已完成）

**迁移已完成**（4 批次全部完成）

## 迁移架构

- **MessageIngestionPort** Protocol：2 方法（receive_message/message_process），替代 chat_bot 全局单例的直接导入
- **ChatBotMessageIngestionPort**：鸭子类型适配器，包裹 chat_bot 实例，不要求 ChatBot 继承 Protocol
- **ChatRuntime 扩展**：3 新方法（append_context_message/get_talk_frequency_adjust/adjust_talk_frequency）+ enqueue_proactive_task 签名修复（补 priority 参数，返回类型 Optional[dict]→dict）
- **注册点**：`get_message_ingestion_port()`/`set_message_ingestion_port()`/`reset_message_ingestion_port()`
- **ruff 守卫**：`src.chat.message_receive.bot.chat_bot` + `src.chat.heart_flow.heartflow_manager.heartflow_manager` banned-api

## 已完成

- ✅ 批次1：基础设施搭建（MessageIngestionPort Protocol + ChatBotMessageIngestionPort 适配器 + 注册点 + MaisakaRuntime 新增方法 + main.py 启动注册 + ruff 守卫）
- ✅ 批次2：H4 消费方迁移（integration.py/message_gateway.py/webui chat service.py — chat_bot→MessageIngestionPort）
- ✅ 批次3：H5 消费方迁移（capabilities/core.py/data.py — heartflow_manager→ChatRuntimeRegistry + _chat_history→append_context_message + _talk_frequency_adjust→get_talk_frequency_adjust + async 转换）
- ✅ 批次4：验证与清理（SessionInfo 导入修复 + heartflow_manager banned-api 守卫 + per-file-ignores + 全量 TID251 验证通过）

## 消除的架构债务

1. H4: 3 处 `chat_bot` 直接导入 → 全部替换为 `MessageIngestionPort` Protocol
2. H5: 2 处 `heartflow_manager` 直接导入 + 私有属性访问 → 全部替换为 `ChatRuntimeRegistry` Protocol
3. `_chat_history.append()` 私有属性写入 → `append_context_message()` 公开方法
4. `_talk_frequency_adjust` 私有属性读取 → `get_talk_frequency_adjust()` 公开方法
5. `_get_frequency_adjust_value` 同步→异步转换，调用方已加 `await`

## 待后续

- ⬜ `webui/routers/chat/routes.py` 的 heartflow_manager 导入（H5 残留，需 ChatRuntime 扩展或新接口）
- ⬜ `cli/maisaka_cli.py` 的 heartflow_manager 导入（CLI 层，优先级低）
- ⬜ `common/utils/utils_message.py` 的 heartflow_manager 导入（H6/M8，SSD-9 范围）

# changelog编写
建议分为两部分，一部分是用户感知功能侧，一部分是开发侧（包含修复和插件sdk,api改动）。最好一个功能一行，按模块分。
一般不写入changelog的内容：
版本号提升或更新项目依赖

# lab 原型实验室

## 定位

Lab 是 MaiBot 的**实验场**，不是生产代码。所有未经验证的架构假设、算法思路、交互模式，先在 lab 里跑通再进主仓库。核心原则：**lab 是沙盒，不是草稿箱**——每个原型必须有明确的实验假设和验证标准。

Lab 是独立 git 仓库（`lab/.git`），不入主仓库共享历史（主仓库 `.gitignore` 排除 `lab/`），但通过子模块引用追踪。

## 目录结构

```
lab/
├── NOTES.md              # 全局探索笔记（按时间线记录）
├── LAB_CONVENTION.md     # 实验室规范
├── {topic}/              # 按主题分组（如 memory/、reply/、architecture/）
│   ├── NOTES.md          # 主题探索笔记（假设、实验、结论）
│   └── {topic}_v{n}.py   # 版本化原型（架构性改变升版本）
├── graduated/            # 已毕业的原型（验证通过，已集成到主仓库）
├── exploratory/          # 一次性探索脚本（分析、提取、回归测试）
└── architecture/         # 架构验证原型（迁移安全性、竞态检测等）
```

## 毕业流程

```
lab/{topic}/ → lab/integration/ → 主仓库 src/
概念验证         集成验证            生产代码
```

毕业标准：核心假设已验证 + 接口契约已明确 + 集成验证通过 + 按主仓库规范重写。毕业后原型移入 `graduated/` 保留作为决策记录。

## 当前实验线

| 主题 | 目录 | 最新版本 | 状态 |
|------|------|---------|------|
| 记忆系统 | `memory/` | v11 | ✅ 已毕业（连接主义范式，主线集成） |
| 回复系统 | `reply/` | v7 | ✅ 已毕业（直通发送，MessagePortV2） |
| 管家系统 | `graduated/` | v4 | ✅ 已毕业（三层过滤+提醒，主线集成） |
| 架构验证 | `architecture/` | - | ✅ 已完成（maisaka 独立、replyer 迁移、fallback 清理） |
| 探索脚本 | `exploratory/` | - | 活跃（fallback 分析、冗余检测等） |

## 阶段 0 架构验证原型

- ✅ `lab/architecture/maisaka_v2_standalone.py` — 验证 maisaka 可脱离 chat 独立运行（4/4 PASS）
- ✅ `lab/memory/memory_e2e_v1.py` — 验证连接主义记忆 + 叙事编织端到端（4/4 PASS，生成 10 Fragment/2 Episode/1 Saga，召回 0.01ms）
- ✅ `lab/architecture/replyer_relocate_dry.py` — 验证 replyer 迁移安全性（5/5 PASS，7 个导入点可安全改写）
- ✅ `lab/architecture/fallback_cleanup_dry.py` — 验证 fallback 清理安全性（5/5 PASS，扫描 1328 处/74 文件）
