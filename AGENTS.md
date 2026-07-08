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
2. `or ""` 兜底消除进度：当前 SDKMemoryKernel 中 87 处（已低于 ≤150 目标）。合理豁免场景：外部数据源返回值可能为 None（如 `dict.get(key, "") or ""` 中 dict.get 已提供默认值时可删除；`str(x or "").strip()` 在 x 已知为 str 时可简化为 `x.strip()`）。

## 类属性使用规范
1. 应该尽量减少使用getattr和setattr方法，除非是在对一个动态类进行处理或者使用Monkeypatch完成Pytest
2. 在重构代码时，如果遇到getattr和setattr，应该尝试检查这个类实例是否有这个属性，如果有，则直接替换为类属性访问写法。
    - 举例：`v = getattr(instance, "value", "")` 在检查到`instance`有`value`属性后应该改为`v = instance.value`
3. getattr 消除进度：当前 SDKMemoryKernel 中 8 处（目标 ≤5）。保留场景判定标准：对动态能力检测的 getattr（如 `encode_batch`、`iter_vectors_by_ids`）通过 Protocol 接口统一后消除；对已知接口的 getattr 替换为直接属性访问。

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

当前重构进展：SDKMemoryKernel 已从 9650 行瘦身至 2911 行；`services/` 目录已提取 14 个服务文件；`admin/` 目录已提取 13 个 Admin Handler；`_KernelRuntimeFacade` 已删除；`host_service` 直接访问服务实例。

当前约束：子模块不反向持有 SDKMemoryKernel 引用；外部 API 签名不变；不引入新的循环依赖。

# 架构债务追踪
重大架构变更（新增/删除 Protocol、消除架构债务、核心模块迁移）完成后，应同步更新 AGENTS.md 和 tasks.md 中的相关描述，确保规则性文件与代码实际状态一致。

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

6. **主智能体-子智能体协作原则**：主智能体是用户的"哲学守护者"，子智能体是"代码专家"。分工不可避免，但必须防止两者孤立甚至对立：
   - **原则随任务传递**：主智能体分派编码任务时，必须同时传递完成该任务所需遵循的特定原则（从 AGENTS.md 和会话上下文中提取），而非只传递"做什么"
   - **审核双重标准**：主智能体审核子智能体产出时，不仅审核代码正确性，更审核是否违背用户的根本原则（核心禁止项、代码风格、架构约束）
   - **禁止自动推进流程**：不得在用户未明确表示"进入下一阶段"时自动推进 SSD 流程；不得主动询问"有什么代码任务"——等待用户发起
   - **上下文压缩后优先恢复原则**：压缩后丢失的首先是"为什么"，恢复时应优先从 AGENTS.md 重新加载核心原则，而非仅恢复任务状态

## 核心禁止项

1. 禁止核心直接导入 chat_manager
2. 禁止核心访问 chat_manager._agent_router
3. 禁止核心持有 BotChatSession 可变引用
4. 禁止核心硬编码 napcat_* 字段
5. 禁止核心绕过 MessagePort 直接调用 send_service
6. 禁止核心导入 A_memorix 内部模块
7. 禁止 Orchestrator 通过 enqueue_proactive_task 模拟多智能体

# 核心架构

## 微内核 + 接口契约

核心模块（智能体 + 消息管道）不依赖组件具体实现，只通过 Protocol 接口交互。适配器层（`src/core/adapters/`）是唯一允许导入组件具体类的地方。

### 核心接口层

| Protocol | 职责 | 实现者 |
|----------|------|--------|
| SessionRepository | 会话查询 | ChatManagerSessionRepository |
| AgentRoutingService | 智能体路由 | ChatManagerRoutingAdapter |
| ChatRuntime | 运行时接口 | MaisakaHeartFlowChatting |
| ChatRuntimeRegistry | 运行时注册表 | HeartflowRuntimeRegistry |
| NoticeClassifier | 通知分类 | NapCatNoticeClassifier |
| MemoryServicePort | 记忆服务 | AMemorixMemoryServicePort |
| SessionInfoPort | 会话信息反查 | ChatManagerSessionInfoPort |
| ThinkingOrgan | 思维管道 | ThinkingOrgan（agent_autonomy） |
| ThinkingOrganFactory | 思维管道工厂 | ThinkingOrganFactory |

## 内心状态三层

- **情绪层**：当前情绪状态，由环境刺激和内部驱动共同决定
- **欲望层**：内在需求（表达欲、社交欲、好奇心），驱动主动行为
- **记忆层**：通过 MemoryServicePort 访问，记忆是连接而非对象

## Agent-owns-Thinking

每个智能体拥有自己的思维管道（ThinkingOrgan），Orchestrator 只协调"谁在思考"，不关心"怎么思考"。共居智能体可并行思考（ParallelThinkScheduler）。

## 管家系统

- **三层过滤**：相关性 → 时机 → 价值，决定是否触发插话
- **提醒流**：到时提醒通过 ThinkingOrgan.think_proactive() 触发，不走 enqueue_proactive_task
- **插话流**：通过 ThinkingOrgan.think() 触发，结果通过 MessagePort.send() 发出

# changelog编写
建议分为两部分，一部分是用户感知功能侧，一部分是开发侧（包含修复和插件sdk,api改动）。最好一个功能一行，按模块分。
一般不写入changelog的内容：
版本号提升或更新项目依赖
