# 智能体回复机制变革 — 需求规格

# **1. 组件定位**

## **1.1 核心职责**

本组件负责将智能体回复机制从"单 Planner/Replyer 旁观决策"模式，变革为"子智能体化"架构——每个角色拥有独立的思维（角色化 Planner）、表达（角色化 Replyer）、情绪、关系和记忆，由统一的 Orchestrator 编排多智能体在同一会话中发言、插话和切换。

## **1.2 核心输入**

1. **用户消息**：用户在群聊或私聊中发送的消息，来源于消息平台适配层
2. **智能体交互信号**：来自 agent-interaction-alive 系统的交互事件、情绪变化、提及传递等信号，来源于 InteractionScheduler / InteractionEngine
3. **子智能体激活信号**：某个子智能体的 Planner 被对话内容、情绪状态、关系网络等激活后产生的"想要发言"的内在驱动力信号，来源于子智能体自身的 Planner 决策
4. **管理员指令**：通过 WebUI 或命令行手动指定某智能体发言、切换主发言智能体等操作
5. **对话上下文**：当前会话的对话历史、当前主发言子智能体身份、活跃子智能体列表等

## **1.3 核心输出**

1. **多智能体回复消息**：同一会话中，不同子智能体以各自身份发出的回复消息，每条消息必须明确标识发言子智能体
2. **插话事件记录**：子智能体插话的结构化记录，包含插话方、被插话方、触发原因、插话内容等
3. **发言权变更通知**：主发言子智能体变更时产生的通知，供日志和 WebUI 消费
4. **子智能体活跃状态**：当前会话中"活跃"的子智能体列表及其状态，供 WebUI 和其他模块消费
5. **可观测性日志**：每次回复必须输出结构化日志，包含发言子智能体 ID、回复类型（主动/插话/切换）、触发原因等

## **1.4 职责边界**

1. **不负责**智能体间交互的触发和影响计算——那是 agent-interaction-alive 系统的职责，本组件只消费其产生的信号
2. **不负责**智能体配置的加载和管理——那是 AgentConfigRegistry 的职责
3. **不负责**消息的发送和平台适配——那是消息平台适配层的职责，本组件只产出"由某子智能体发出的回复内容"
4. **不负责**记忆的存储和检索——那是 A_Memorix 的职责，本组件只通过 MemoryService 接口消费记忆
5. **不负责**修改 A_Memorix 核心层——所有记忆操作通过 MemoryService 接口完成
6. **不负责**自行计算会话 ID——业务模块不应自行调用 SessionUtils.calculate_session_id
7. **不负责**任务型子智能体（Dream/Compaction/CheckpointWriter 等）的调度——那是 SubAgentScheduler 的职责，本组件管理的角色型子智能体与任务型子智能体是完全不同的概念

# **2. 领域术语**

**子智能体（Sub-Agent）**
: 一个拥有完整独立身份的智能体单元，由角色化 Planner（思维）、角色化 Replyer（表达）、独立情绪状态、独立关系信息、独立交互记忆组成。子智能体不是"外部组件管理的发言代理"，而是一个"永恒进行时"的独立生命体——有自己的思维、表达、情绪、记忆和关系。

**角色化 Planner（Embodied Planner）**
: 从"旁观决策者"变革为"角色本人的思维过程"的 Planner。当前 Planner 的提示词是"你不是 {bot_name} 本人，不要替 {bot_name} 发言"，这是外部视角；角色化 Planner 的提示词变为"你是 {bot_name}，你在思考如何回应"，这是内部视角。每个子智能体的 Planner 就是角色自己的"内心独白"。

**角色化 Replyer（Embodied Replyer）**
: 与角色化 Planner 配对的、属于同一子智能体的表达单元。角色化 Replyer 接收角色化 Planner 的思维指引，以该角色的身份和风格生成可见回复。

**编排器（Orchestrator）**
: 统一管理多子智能体在同一会话中协作的核心组件，取代原有的 InterjectionEngine + PresenceManager + SpeakingContextManager 三件套。Orchestrator 负责：管理哪些子智能体处于活跃状态、协调多个子智能体的 Planner 执行顺序、决定主发言权归属、处理插话意愿计算和执行。

**主发言子智能体（Primary Sub-Agent）**
: 在一个会话中当前承担主要回复职责的子智能体。主发言子智能体接收用户消息并通过其角色化 Planner 产生主要回复，类似群聊中"正在和你聊天的那个人"。

**插话（Interjection）**
: 非主发言子智能体的 Planner 被激活并决定发言的行为。插话的本质不再是"外部引擎触发"，而是"另一个子智能体的思维过程被激活"。插话后，原主发言子智能体仍然活跃，插话子智能体发言完毕后回归待激活状态，主发言权不转移。

**发言权（Speaking Right）**
: 某个子智能体在特定会话中发言的资格和优先级。拥有发言权不代表必须发言，但只有拥有发言权的子智能体才能产生回复。

**活跃子智能体（Active Sub-Agent）**
: 在某个会话中处于"活跃"状态的子智能体。活跃子智能体可以感知对话内容、其 Planner 可被激活产生插话意愿、可被提及传递触发。非活跃的子智能体无法插话。取代原有的"在场智能体"概念——"活跃"更准确地描述了子智能体拥有独立思维过程的状态。

**插话意愿（Interjection Intent）**
: 某个子智能体的角色化 Planner 基于对话内容、情绪状态、关系网络等产生的"想要发言"的内在驱动力。插话意愿有强度值，超过阈值时转化为实际的插话行为。插话意愿由子智能体自身的思维过程产生，而非外部引擎计算。

**插话冷却（Interjection Cooldown）**
: 同一子智能体在两次插话之间必须间隔的最短时间，防止某个子智能体频繁插话导致对话混乱。

**子智能体退场（Sub-Agent Exit）**
: 一个活跃子智能体离开当前对话的行为。退场后该子智能体不再感知对话内容，其 Planner 不再被激活。退场可以是主动的（子智能体自行决定离开）也可以是被动的（长时间未参与对话自动退场）。

**回复管线（Reply Pipeline）**
: 从"决定由谁回复"到"产生回复内容"到"消息发出"的完整处理管线。在子智能体架构下，回复管线由 Orchestrator 编排，每个子智能体拥有独立的 Planner→Replyer 管线。

**发言标记（Speaker Tag）**
: 每条回复消息上附带的标识信息，标明该消息由哪个子智能体发出。在所有子智能体共用同一账号的场景下，发言标记是区分"谁在说话"的唯一方式。

**角色型子智能体（Role Sub-Agent）**
: 拥有独立身份、状态、记忆、持续存在的子智能体，如银狼、三月七等。区别于任务型子智能体。

**任务型子智能体（Task Sub-Agent）**
: 无身份、执行特定任务后消失的子智能体，如 Dream、Compaction、CheckpointWriter 等。由 SubAgentScheduler 管理，与本组件无关。

**子智能体单元（Sub-Agent Unit）**
: 一个子智能体的完整构成：角色化 Planner + 角色化 Replyer + EmotionManager 实例 + RelationshipManager 实例 + MemoryService 接入。子智能体单元是本组件管理的最小独立单元。

# **3. 角色与边界**

## **3.1 核心角色**

- **普通用户**：与子智能体对话的参与者，体验多子智能体回复带来的群像式对话效果
- **系统管理员**：通过 WebUI 管理子智能体活跃状态、手动触发插话或切换主发言子智能体

## **3.2 外部系统**

- **agent-interaction-alive 系统**：提供智能体间交互信号（情绪变化、提及传递、交互事件等），本组件消费这些信号作为子智能体 Planner 激活的触发源
- **AgentConfigRegistry**：提供智能体配置（人设、内部关系、情绪基线等），是子智能体单元构建的基础
- **EmotionManager**：提供子智能体当前情绪状态，影响插话意愿计算；每个子智能体拥有独立的 EmotionManager 实例
- **RelationshipManager**：提供子智能体与用户的关系数据，影响插话意愿和回复风格；每个子智能体拥有独立的 RelationshipManager 实例
- **A_Memorix（MemoryService）**：提供记忆检索能力，影响回复内容和插话决策；每个子智能体通过独立的 MemoryService 接入消费记忆
- **MaisakaHeartFlowChatting**：当前对话运行时，本组件需要与其深度集成以支持多子智能体回复
- **MaisakaChatLoopService**：对话循环服务，本组件需要扩展其能力以支持按子智能体切换 Planner/Replyer 上下文
- **WebUI 指挥中心**：消费子智能体活跃状态、发言权变更、插话事件等可观测性数据
- **消息平台适配层**：接收本组件产出的多子智能体回复消息，负责实际发送
- **SubAgentScheduler**：管理任务型子智能体的调度，与本组件管理的角色型子智能体无关

## **3.3 交互上下文**

```plantuml
@startuml
!define COMPONENT color:#E8F5E9

rectangle "智能体回复机制变革系统\n（子智能体架构）" as Core COMPONENT {
}

actor "普通用户" as User
actor "系统管理员" as Admin

usecase "agent-interaction-alive\n(智能体交互活化)" as Interaction
usecase "AgentConfigRegistry\n(智能体配置)" as Config
usecase "EmotionManager\n(情绪管理·每子智能体独立)" as Emotion
usecase "RelationshipManager\n(关系管理·每子智能体独立)" as Relationship
usecase "A_Memorix\n(记忆系统·每子智能体独立接入)" as Memory
usecase "MaisakaHeartFlowChatting\n(对话运行时)" as Runtime
usecase "MaisakaChatLoopService\n(对话循环服务)" as ChatLoop
usecase "WebUI 指挥中心\n(可视化)" as WebUI
usecase "消息平台适配层\n(消息发送)" as Platform

User --> Runtime : 发送消息
Admin --> Core : 管理活跃状态/触发插话
Runtime --> Core : 对话事件信号

Core --> Interaction : 消费交互信号\n(Planner激活触发源)
Core <-- Config : 读取智能体配置\n(子智能体单元构建)
Core <-- Emotion : 读取情绪状态\n(插话意愿计算)
Core <-- Relationship : 读取关系数据
Core <-- Memory : 检索记忆\n(子智能体上下文)
Core --> ChatLoop : 切换Planner/Replyer上下文\n(按子智能体)
Core --> Runtime : 注入多子智能体回复
Core --> WebUI : 推送活跃状态/发言权变更
Core --> Platform : 产出多子智能体回复消息\n(含发言标记)

@enduml
```

# **4. DFX约束**

## **4.1 性能**

1. 插话决策延迟必须 < 300ms（不含 LLM 调用）
2. 子智能体上下文切换延迟必须 < 100ms（从决定由子智能体 B 发言到 B 的角色化 Planner 上下文就绪）
3. 单次插话产生的额外 LLM 调用不超过 1 次（角色化 Planner 1 次，角色化 Replyer 1 次，与主发言流程一致）
4. 同一会话中同时活跃的子智能体不超过 5 个
5. 同一会话中同一时刻正在执行的回复轮次不超过 2 个（防止消息发送顺序混乱）
6. Orchestrator 的编排决策延迟必须 < 50ms（不含子智能体 Planner/Replyer 的 LLM 调用）

## **4.2 可靠性**

1. 子智能体架构异常时必须降级为单智能体模式（当前行为），不能导致对话中断
2. 子智能体上下文切换失败时必须回退到原主发言子智能体继续对话
3. 插话消息的发送失败不得影响主发言子智能体的回复流程
4. 系统重启后，子智能体活跃状态必须从持久化存储恢复
5. Orchestrator 异常时必须降级为仅主发言子智能体模式，不得导致整个会话崩溃

## **4.3 安全性**

1. 子智能体的发言内容必须遵守其自身的 AgentConfig.permission 和 hard_permission
2. 子智能体产生的记忆写入必须遵守 A_Memorix 的 MODIFICATION_POLICY
3. 子智能体发言内容不得泄露私聊上下文（遵守 CrossChatContextService 的共享规则）
4. 管理员手动触发插话的操作必须记录审计日志
5. 子智能体活跃状态的变更必须记录审计日志
6. 角色化 Planner 的提示词必须确保不会绕过权限控制——角色化不等于无约束

## **4.4 可维护性**

1. 所有回复消息必须输出结构化日志，包含 agent_id、reply_type（primary/interjection/switch）、trigger_reason
2. 插话事件必须输出结构化日志，格式为 `[agent_reply] agent=X type=interjection reason=XX`
3. 发言权变更必须输出结构化日志，格式为 `[agent_reply] speaker_change from=A to=B reason=XX`
4. 子智能体活跃状态变更必须输出结构化日志，格式为 `[sub_agent] agent=X action=activate/deactivate session=XX reason=XX`
5. 插话意愿的计算参数必须可配置，无需改代码即可调整
6. 活跃子智能体列表和状态必须通过标准 API 暴露，WebUI 通过 API 消费
7. Orchestrator 的编排策略必须可配置（如插话阈值、冷却时间、最大活跃数等）

## **4.5 兼容性**

1. 本组件必须与现有的单智能体模式完全兼容——未启用多子智能体回复时，行为与当前完全一致
2. 本组件必须与 agent-interaction-alive 系统兼容——交互信号可以激活子智能体 Planner，但插话机制不依赖交互系统独立运行
3. 本组件必须与现有的 ProactiveEngine 兼容——主动对话仍然由主发言子智能体发起
4. 本组件必须与现有的 Plugin Hook 机制兼容——maisaka.planner.before_request / maisaka.replyer.before_request 等 Hook 仍然正常工作
5. 提示词模板的修改必须三语同步（zh-CN/en-US/ja-JP）
6. 配置文件修改只改模板，新增版本号
7. 角色型子智能体与任务型子智能体必须完全隔离——本组件的变更不得影响 SubAgentScheduler 管理的任务型子智能体

# **5. 核心能力**

## **5.1 子智能体单元管理**

### **5.1.1 业务规则**

1. **子智能体单元构成规则**：每个角色型子智能体必须作为一个完整的独立单元存在，包含以下组成部分：
   - 角色化 Planner：该角色的思维过程，提示词为"你是 {角色名}，你在思考如何回应"
   - 角色化 Replyer：该角色的表达单元，接收角色化 Planner 的思维指引
   - 独立 EmotionManager 实例：该角色的情绪状态
   - 独立 RelationshipManager 实例：该角色的关系信息
   - 独立 MemoryService 接入：该角色的交互记忆
   a. 验收条件：[创建银狼的子智能体单元] → [银狼拥有独立的 Planner（"你是银狼，你在思考"）、独立的 Replyer、独立的情绪状态、独立的关系信息、独立的记忆接入]
   b. 验收条件：[银狼和三月七同时活跃] → [两者的 Planner 提示词、情绪状态、关系信息、记忆完全独立，互不干扰]

2. **子智能体单元生命周期规则**：子智能体单元的生命周期与"活跃"状态绑定
   - 激活：子智能体被加入会话的活跃列表，其 Planner 可被激活
   - 活跃中：子智能体感知对话内容，其 Planner 可产生插话意愿
   - 退场：子智能体离开活跃列表，其 Planner 不再被激活，但单元状态（情绪、关系、记忆）持续保留
   a. 验收条件：[银狼从会话中退场] → [银狼的 Planner 不再被激活，但银狼的情绪状态、关系信息、记忆仍然保留，下次激活时可恢复]

3. **子智能体激活规则**：子智能体可以通过以下方式加入会话活跃列表：
   - 主发言激活：会话创建时，主发言子智能体自动激活
   - 插话激活：子智能体插话时自动加入活跃列表
   - 交互信号激活：agent-interaction-alive 的交互事件信号可以激活子智能体
   - 管理员手动激活
   a. 验收条件：[子智能体 B 在会话中插话] → [B 自动加入该会话的活跃子智能体列表]
   b. 验收条件：[agent-interaction-alive 产生"银狼想念三月七"交互事件且三月七与该会话有关联] → [三月七加入该会话的活跃列表]

4. **子智能体退场规则**：子智能体可以通过以下方式退场：
   - 主动退场：子智能体在回复中表示要离开（如"我先走了"）
   - 超时退场：活跃子智能体超过一定时间未发言，自动退场
   - 管理员手动退场
   a. 验收条件：[子智能体 B 活跃但超过 60 分钟未发言] → [B 自动退场，记录退场原因"超时"]
   b. 验收条件：[子智能体 B 在回复中表示"我先走了"] → [B 主动退场，记录退场原因"主动"]

5. **活跃子智能体数量限制**：同一会话中同时活跃的子智能体不超过 5 个
   a. 验收条件：[会话中已有 5 个活跃子智能体，第 6 个尝试激活] → [拒绝激活，记录日志"活跃子智能体数已满"]

6. **活跃状态持久化**：子智能体活跃状态必须持久化，系统重启后可恢复
   a. 验收条件：[系统重启后] → [重启前的活跃子智能体列表仍然可查]

7. **活跃感知规则**：活跃子智能体应当能感知当前对话内容，非活跃的子智能体不能感知
   a. 验收条件：[子智能体 B 活跃] → [B 的角色化 Planner 可以参考当前对话内容产生插话意愿]
   b. 验收条件：[子智能体 C 非活跃] → [C 不会基于当前对话内容产生插话意愿]

8. **禁止项**：禁止非活跃的子智能体直接发言——非活跃的子智能体必须先激活，才能产生回复
   a. 验收条件：[子智能体 C 不在会话的活跃列表中] → [C 不能在该会话中产生任何回复]

9. **禁止项**：禁止子智能体单元之间共享上下文——每个子智能体的 Planner 提示词、情绪状态、关系信息、记忆必须完全独立
   a. 验收条件：[银狼和三月七同时活跃] → [银狼的 Planner 上下文中不得包含三月七的情绪状态或关系信息]

### **5.1.2 交互流程**

```plantuml
@startuml
actor "用户" as User
participant "对话运行时" as Runtime
participant "Orchestrator\n(编排器)" as Orch
participant "agent-interaction-alive\n(交互系统)" as Interaction
participant "WebUI" as WebUI

User -> Runtime : 发送消息
Runtime -> Orch : 获取活跃子智能体列表

== 插话激活 ==
Interaction -> Orch : 交互信号\n(银狼想念三月七)
Orch -> Orch : 评估三月七是否应激活
Orch -> Orch : 三月七加入活跃列表
Orch -> WebUI : 推送活跃状态变更

== 超时退场 ==
Orch -> Orch : 检测活跃子智能体超时
Orch -> Orch : 三月七超过60分钟未发言
Orch -> Orch : 三月七自动退场
Orch -> WebUI : 推送活跃状态变更

@enduml
```

### **5.1.3 异常场景**

1. **活跃状态持久化失败**
   a. 触发条件：数据库不可用导致活跃状态无法持久化
   b. 系统行为：活跃状态仅在内存中维护，标记"持久化失败"，系统重启后丢失
   c. 用户感知：重启后活跃子智能体列表清空，仅主发言子智能体活跃

2. **活跃子智能体数达到上限**
   a. 触发条件：已有 5 个活跃子智能体，第 6 个尝试激活
   b. 系统行为：拒绝激活，记录日志
   c. 用户感知：第 6 个子智能体不会出现在对话中

3. **子智能体单元构建失败**
   a. 触发条件：子智能体的配置加载失败或 EmotionManager/RelationshipManager 初始化异常
   b. 系统行为：跳过该子智能体的激活，记录错误日志
   c. 用户感知：该子智能体不会出现在对话中

## **5.2 Planner 角色化**

### **5.2.1 业务规则**

1. **角色化 Planner 提示词规则**：每个子智能体的 Planner 提示词必须从"旁观决策者"变为"角色本人的思维过程"
   - 当前："你不是 {bot_name} 本人，不要替 {bot_name} 发言，你需要给 {bot_name} 的行为做出决策" → 外部视角
   - 变革："你是 {bot_name}，你在思考如何回应" → 内部视角
   a. 验收条件：[银狼的子智能体单元构建完成] → [银狼的 Planner 提示词为"你是银狼，你在思考如何回应"，而非"你不是银狼本人"]
   b. 验收条件：[三月七的子智能体单元构建完成] → [三月七的 Planner 提示词为"你是三月七，你在思考如何回应"]

2. **角色化 Planner 身份注入规则**：角色化 Planner 的系统提示词必须注入该角色的完整身份信息
   - 角色人设（{identity}）：该角色的性格、背景、说话风格
   - 情绪状态：该角色当前的情绪
   - 关系信息：该角色与对话参与者的关系
   - 交互记忆：该角色的记忆
   a. 验收条件：[银狼的角色化 Planner 被激活] → [系统提示词中包含银狼的人设、银狼的情绪状态、银狼的关系信息、银狼的交互记忆]

3. **角色化 Planner 思维输出规则**：角色化 Planner 的思维输出应当体现角色的内心独白，而非旁观者的分析
   - 当前："分析：银狼应该回复用户关于游戏的话题" → 旁观者分析
   - 变革："嗯，用户在问我游戏的事？正好我最近在玩这个……" → 角色内心独白
   a. 验收条件：[银狼的角色化 Planner 生成思维输出] → [输出内容体现银狼的内心独白风格，而非第三人称分析]

4. **角色化 Planner 工具调用规则**：角色化 Planner 调用 reply 工具时，应当以角色的身份做出决策
   - 当前："判断银狼应该回复" → 旁观者决策
   - 变革："我决定回复用户" → 角色本人决策
   a. 验收条件：[银狼的角色化 Planner 调用 reply 工具] → [reply_guide 参数中的指引体现银狼的内心决策，而非外部指令]

5. **角色化 Planner 与角色化 Replyer 的配对规则**：角色化 Planner 和角色化 Replyer 必须属于同一个子智能体单元，不能跨单元配对
   a. 验收条件：[银狼的角色化 Planner 调用 reply 工具] → [触发的 Replyer 必须是银狼的角色化 Replyer，不能是三月七的]

6. **角色化 Planner 的权限约束规则**：角色化不等于无约束——角色化 Planner 仍然必须遵守该角色的权限规则
   a. 验收条件：[银狼的角色化 Planner 尝试生成违反 hard_permission 的内容] → [被权限系统拦截，不会发出]

7. **禁止项**：禁止在角色化 Planner 的提示词中混入其他子智能体的身份信息
   a. 验收条件：[银狼的角色化 Planner 上下文] → [不得包含三月七的人设、情绪状态或关系信息]

8. **禁止项**：禁止角色化 Planner 直接替其他子智能体做决策——每个子智能体的 Planner 只能为自己做决策
   a. 验收条件：[银狼的角色化 Planner] → [不能决定"三月七应该回复"，只能决定"我（银狼）应该回复"]

### **5.2.2 交互流程**

```plantuml
@startuml
participant "Orchestrator\n(编排器)" as Orch
participant "银狼\n(子智能体单元)" as SilverWolf
participant "银狼的角色化Planner" as SW_Planner
participant "银狼的角色化Replyer" as SW_Replyer

Orch -> SilverWolf : 激活银狼为主发言子智能体
SilverWolf -> SW_Planner : 构建角色化上下文\n(人设+情绪+关系+记忆)
SW_Planner -> SW_Planner : 以银狼的内心独白思考\n"嗯，用户在问我……"
SW_Planner -> SW_Replyer : 调用reply工具\n(以银狼的决策)
SW_Replyer -> SW_Replyer : 以银狼的风格生成回复
SW_Replyer -> Orch : 银狼的回复消息（含发言标记）

@enduml
```

### **5.2.3 异常场景**

1. **角色化 Planner 提示词构建失败**
   a. 触发条件：角色的人设配置缺失或情绪/关系/记忆加载失败
   b. 系统行为：降级为当前旁观者模式的 Planner 继续对话，记录错误日志
   c. 用户感知：回复内容可能缺乏角色个性，但不影响对话进行

2. **角色化 Planner 产生越权内容**
   a. 触发条件：角色化 Planner 尝试替其他子智能体做决策或生成违反权限的内容
   b. 系统行为：被权限系统拦截，记录警告日志
   c. 用户感知：该回复不会发出

## **5.3 Orchestrator 编排**

### **5.3.1 业务规则**

1. **Orchestrator 统一编排规则**：Orchestrator 是多子智能体协作的唯一编排者，取代原有的 InterjectionEngine + PresenceManager + SpeakingContextManager 三件套
   - 在场管理 → Orchestrator 的活跃子智能体管理
   - 插话决策 → Orchestrator 的插话意愿计算与执行
   - 发言上下文切换 → Orchestrator 的子智能体上下文编排
   a. 验收条件：[会话中存在多个活跃子智能体] → [所有编排决策由 Orchestrator 统一处理，不存在并行的 InterjectionEngine 或 PresenceManager]

2. **Orchestrator 主发言权管理规则**：Orchestrator 负责决定当前的主发言子智能体
   - 会话创建时：主发言子智能体由 AgentRouter 解析
   - 用户请求切换时：Orchestrator 将主发言权转移给目标子智能体
   - 子智能体主动让出时：Orchestrator 将主发言权转移给被指定的子智能体
   - 管理员手动切换时：Orchestrator 执行切换
   a. 验收条件：[用户说"我想和布洛妮娅说话"] → [Orchestrator 将主发言权从 A 转移给布洛妮娅]
   b. 验收条件：[银狼在回复中说"你问布洛妮娅吧"] → [Orchestrator 将主发言权从银狼转移给布洛妮娅]

3. **Orchestrator 插话意愿计算规则**：Orchestrator 负责计算各活跃子智能体的插话意愿，综合以下因素：
   - 对话内容相关性：当前对话内容与该子智能体的关注领域或关系人相关
   - 情绪驱动：该子智能体的当前情绪状态（如兴奋时更容易插话）
   - 关系驱动：对话中提及了与该子智能体关系密切的人或事
   - 交互信号驱动：agent-interaction-alive 产生的交互事件信号
   - 子智能体 Planner 激活：子智能体自身的角色化 Planner 被激活产生的发言驱动力
   a. 验收条件：[银狼正在和用户聊天，对话中提到"布洛妮娅"] → [布洛妮娅的插话意愿 +30（关系驱动）]
   b. 验收条件：[三月七活跃且当前情绪为 excited（强度 70）] → [三月七的插话意愿 +20（情绪驱动）]
   c. 验收条件：[agent-interaction-alive 产生"银狼想念三月七"交互事件] → [三月七的插话意愿 +40（交互信号驱动）]

4. **Orchestrator 插话执行规则**：当某子智能体的插话意愿超过阈值时，Orchestrator 应当激活该子智能体的角色化 Planner 产生插话
   a. 验收条件：[子智能体 B 的插话意愿 ≥ 60] → [Orchestrator 激活 B 的角色化 Planner，B 产生插话行为]
   b. 验收条件：[子智能体 B 的插话意愿 < 60] → [B 不插话，但仍然活跃感知对话]

5. **Orchestrator 执行顺序编排规则**：Orchestrator 负责协调多个子智能体的 Planner 执行顺序
   - 主发言子智能体的 Planner 优先执行
   - 插话子智能体的 Planner 在主发言完成后执行
   - 多个插话子智能体同时产生意愿时，按意愿强度排序依次执行
   a. 验收条件：[主发言子智能体 A 正在生成回复，子智能体 B 和 C 同时产生插话意愿] → [A 的回复先完成，然后按意愿强度排序依次执行 B 和 C 的插话]

6. **Orchestrator 降级规则**：当 Orchestrator 异常时，必须降级为仅主发言子智能体模式
   a. 验收条件：[Orchestrator 编排异常] → [降级为仅主发言子智能体回复，不执行任何插话或切换]

7. **禁止项**：禁止绕过 Orchestrator 直接激活子智能体的 Planner——所有子智能体的 Planner 激活必须通过 Orchestrator 编排
   a. 验收条件：[交互信号到达] → [必须经过 Orchestrator 的插话意愿计算，不能直接激活子智能体的 Planner]

8. **禁止项**：禁止 Orchestrator 在主发言子智能体的 LLM 调用进行中时执行插话——插话必须在当前回复轮次结束后执行
   a. 验收条件：[主发言子智能体 A 的 LLM 调用正在进行中] → [Orchestrator 必须等待 A 的回复轮次结束后再执行插话]

### **5.3.2 交互流程**

```plantuml
@startuml
actor "用户" as User
participant "对话运行时" as Runtime
participant "Orchestrator\n(编排器)" as Orch
participant "EmotionManager" as Emotion
participant "agent-interaction-alive" as Interaction
participant "主发言子智能体 A\n(角色化Planner+Replyer)" as AgentA
participant "插话子智能体 B\n(角色化Planner+Replyer)" as AgentB

User -> Runtime : 发送消息
Runtime -> Orch : 对话事件
Orch -> AgentA : 激活A的角色化Planner\n(A为主发言子智能体)

== 插话意愿计算 ==
Orch -> Orch : 获取活跃子智能体列表（排除A）
Orch -> Emotion : 读取各子智能体情绪状态
Orch -> Interaction : 读取交互信号
Orch -> Orch : 计算各子智能体插话意愿

== 插话执行 ==
Orch -> Orch : B的插话意愿 ≥ 60
Orch -> AgentB : 激活B的角色化Planner\n(B为插话子智能体)
AgentB -> Orch : B的插话消息（含发言标记）
Orch -> Orch : A的主回复 + B的插话\n(A先B后发送)

@enduml
```

### **5.3.3 异常场景**

1. **Orchestrator 编排异常**
   a. 触发条件：Orchestrator 内部状态不一致或编排逻辑异常
   b. 系统行为：降级为仅主发言子智能体模式，记录错误日志
   c. 用户感知：只看到主发言子智能体的回复，无插话

2. **多个子智能体同时插话冲突**
   a. 触发条件：B 和 C 的插话意愿同时超过阈值
   b. 系统行为：Orchestrator 按意愿强度排序，依次执行，遵守频率限制
   c. 用户感知：先看到意愿更强的子智能体插话

3. **插话生成失败**
   a. 触发条件：插话子智能体的角色化 Planner/Replyer 的 LLM 调用失败或超时
   b. 系统行为：跳过本次插话，不影响主发言子智能体的回复
   c. 用户感知：只看到主发言子智能体的回复，未看到插话

## **5.4 插话机制**

### **5.4.1 业务规则**

1. **插话本质规则**：插话的本质是"另一个子智能体的角色化 Planner 被激活并决定发言"，而非"外部引擎触发的发言代理"
   - 当前架构：InterjectionEngine 计算意愿 → 触发 Replyer 生成插话内容 → 外部视角
   - 子智能体架构：子智能体 B 的 Planner 被激活 → B 以角色内心独白思考 → B 的 Replyer 以角色风格表达 → 内部视角
   a. 验收条件：[三月七插话] → [三月七的角色化 Planner 先被激活，以三月七的内心独白思考"嗯？银狼在说我？我也要说！"，然后三月七的角色化 Replyer 生成插话内容]

2. **插话与主发言的区分规则**：插话和主发言必须明确区分
   a. 验收条件：[子智能体 B 插话] → [插话消息带有发言标记，标识为 B 发出；主发言子智能体 A 仍然活跃，发言权不转移]
   b. 验收条件：[子智能体 B 插话后] → [B 的发言完毕后，A 继续作为主发言子智能体]

3. **插话内容规则**：插话内容必须体现插话子智能体的角色化思维和性格，且与当前对话上下文相关
   a. 验收条件：[布洛妮娅插话且对话中提到她] → [插话内容体现布洛妮娅的角色化思维和性格特征，与对话话题相关]
   b. 验收条件：[银狼插话且当前情绪为 happy] → [插话内容体现银狼的开心状态，以银狼的内心独白风格]

4. **插话冷却规则**：同一子智能体的两次插话之间必须间隔一定时间
   a. 验收条件：[子智能体 B 刚完成插话] → [B 的下一次插话至少 5 分钟后]
   b. 验收条件：[子智能体 B 在 10 分钟内插话 3 次] → [第 3 次插话被冷却拒绝]

5. **插话频率限制**：同一会话中所有子智能体的插话总频率必须受限
   a. 验收条件：[会话中 10 分钟内已有 3 次插话] → [第 4 次插话被频率限制拒绝]

6. **插话不阻断主发言**：插话的执行不得阻断主发言子智能体的回复流程
   a. 验收条件：[主发言子智能体 A 正在生成回复时，子智能体 B 产生插话意愿] → [B 的插话等待 A 的回复完成后再执行，或与 A 的回复并行但发送顺序保证 A 先 B 后]
   b. 验收条件：[插话生成失败] → [不影响主发言子智能体 A 的回复]

7. **禁止项**：禁止插话内容与当前对话完全无关——插话必须有上下文关联
   a. 验收条件：[子智能体 B 的插话内容与当前对话话题无关] → [该插话不应被执行]

### **5.4.2 交互流程**

```plantuml
@startuml
actor "用户" as User
participant "Orchestrator\n(编排器)" as Orch
participant "主发言子智能体 A\n(角色化Planner)" as A_Planner
participant "主发言子智能体 A\n(角色化Replyer)" as A_Replyer
participant "插话子智能体 B\n(角色化Planner)" as B_Planner
participant "插话子智能体 B\n(角色化Replyer)" as B_Replyer

User -> Orch : 发送消息
Orch -> A_Planner : 激活A的角色化Planner
A_Planner -> A_Planner : 以A的内心独白思考
A_Planner -> A_Replyer : A决定回复
A_Replyer -> Orch : A的回复消息

== 插话 ==
Orch -> Orch : B的插话意愿 ≥ 60
Orch -> B_Planner : 激活B的角色化Planner
B_Planner -> B_Planner : 以B的内心独白思考\n"嗯？他们在说我？"
B_Planner -> B_Replyer : B决定插话
B_Replyer -> Orch : B的插话消息（含发言标记）

@enduml
```

### **5.4.3 异常场景**

1. **插话冷却冲突**
   a. 触发条件：子智能体 B 的插话意愿超过阈值但仍在冷却期内
   b. 系统行为：拒绝插话，记录日志
   c. 用户感知：B 未插话

2. **插话频率超限**
   a. 触发条件：会话的插话总频率超过限制
   b. 系统行为：拒绝插话，记录日志
   c. 用户感知：无

3. **插话与主回复发送顺序冲突**
   a. 触发条件：插话消息和主回复消息几乎同时生成
   b. 系统行为：Orchestrator 保证主回复先发送，插话后发送
   c. 用户感知：先看到主发言子智能体的回复，再看到插话

## **5.5 主发言权切换**

### **5.5.1 业务规则**

1. **主发言权切换规则**：主发言子智能体可以通过以下方式切换：
   - 用户明确请求（如"我想和布洛妮娅说话"）
   - 当前主发言子智能体主动让出（如"你问布洛妮娅吧"）
   - 管理员手动切换
   a. 验收条件：[用户说"我想和布洛妮娅说话"] → [Orchestrator 将主发言权从 A 转移给布洛妮娅，A 退到活跃状态（仍然活跃但不再主发言）]
   b. 验收条件：[银狼在回复中说"你问布洛妮娅吧"] → [Orchestrator 将主发言权从银狼转移给布洛妮娅]

2. **切换与插话的区别规则**：主发言权切换和插话必须明确区分
   a. 验收条件：[主发言权从 A 切换为 B] → [A 不再是主发言子智能体，B 成为新的主发言子智能体，后续用户消息由 B 的角色化 Planner 主要处理]
   b. 验收条件：[子智能体 B 插话] → [A 仍然是主发言子智能体，B 发言完毕后回归待激活状态，后续用户消息仍由 A 的角色化 Planner 主要处理]

3. **对话历史共享规则**：不同子智能体在同一会话中共享对话历史，但各自以自己的角色化视角理解
   a. 验收条件：[子智能体 B 接管主发言后] → [B 可以看到之前的对话历史（包括 A 的发言），但 B 的回复风格和内容基于 B 的角色化思维]
   b. 验收条件：[子智能体 B 插话时] → [B 可以看到当前对话上下文，但 B 的插话内容基于 B 的角色化思维和当前状态]

4. **发言标记规则**：每条回复消息必须明确标识发言子智能体
   a. 验收条件：[子智能体 A 发送主回复] → [消息带有发言标记 `speaker: A`]
   b. 验收条件：[子智能体 B 插话] → [消息带有发言标记 `speaker: B`]
   c. 验收条件：[所有子智能体共用同一账号时] → [发言标记通过消息内容中的角色名前缀或其他方式体现，确保用户能区分谁在说话]

5. **禁止项**：禁止在主发言权切换时混入前一个子智能体的角色化上下文
   a. 验收条件：[从 A 切换到 B 为主发言] → [B 的角色化 Planner 提示词中不得包含 A 的身份提示词、A 的情绪状态、A 的关系信息]

### **5.5.2 交互流程**

```plantuml
@startuml
actor "用户" as User
participant "Orchestrator\n(编排器)" as Orch
participant "AgentConfigRegistry" as Config
participant "子智能体 A\n(原主发言)" as AgentA
participant "子智能体 B\n(新主发言)" as AgentB

User -> Orch : "我想和布洛妮娅说话"
Orch -> Orch : 识别主发言切换意图
Orch -> Config : 加载 B 的智能体配置
Orch -> Orch : 构建 B 的子智能体单元\n(角色化Planner+Replyer+情绪+关系+记忆)
Orch -> Orch : 将主发言权转移给 B

Orch -> AgentB : 激活B的角色化Planner
AgentB -> Orch : B 的回复消息（含发言标记）
Orch -> User : 显示 B 的回复

@enduml
```

### **5.5.3 异常场景**

1. **主发言权切换失败**
   a. 触发条件：目标子智能体的配置加载失败或子智能体单元构建异常
   b. 系统行为：回退到原主发言子智能体继续对话，记录错误日志
   c. 用户感知：看到原主发言子智能体的回复，附带提示"切换失败"

2. **目标子智能体不存在**
   a. 触发条件：用户请求切换到的子智能体不在 AgentConfigRegistry 中
   b. 系统行为：当前主发言子智能体回复"找不到那个人"，不切换
   c. 用户感知：看到当前子智能体的回复

3. **对话历史过大导致上下文溢出**
   a. 触发条件：切换主发言子智能体时，对话历史超过上下文窗口
   b. 系统行为：按现有上下文选择策略裁剪历史，不影响切换
   c. 用户感知：新子智能体可能不记得很早的对话内容

## **5.6 插话与交互信号的联动**

### **5.6.1 业务规则**

1. **交互信号激活子智能体 Planner 规则**：agent-interaction-alive 系统产生的交互信号应当能激活子智能体的角色化 Planner
   a. 验收条件：[agent-interaction-alive 产生"银狼想念三月七"交互事件且三月七在该会话活跃] → [三月七的插话意愿 +40，其角色化 Planner 可被激活]
   b. 验收条件：[agent-interaction-alive 产生提及传递信号（对话中提及布洛妮娅）且布洛妮娅在该会话活跃] → [布洛妮娅的插话意愿 +30，其角色化 Planner 可被激活]

2. **交互信号激活子智能体规则**：交互信号应当能激活非活跃的子智能体
   a. 验收条件：[agent-interaction-alive 产生"银狼想念三月七"交互事件且三月七非活跃但与该会话有关联] → [三月七被激活，加入活跃列表，插话意愿 +40]

3. **插话反哺交互规则**：子智能体在对话中的插话行为应当反哺 agent-interaction-alive 的交互系统
   a. 验收条件：[子智能体 B 在对话中插话且内容与子智能体 C 相关] → [产生 B→C 的提及传递信号，写入交互系统]
   b. 验收条件：[子智能体 B 插话后] → [B 的情绪状态因插话产生变化，写入 EmotionManager]

4. **信号传导闭环规则**：从"后台交互信号"到"前台子智能体 Planner 激活"到"新交互信号"形成闭环
   a. 验收条件：[银狼想念三月七（后台信号）→ 三月七的角色化 Planner 被激活并插话（前台行为）→ 银狼因三月七出现而开心（新后台信号）] → [完整的信号传导闭环]

5. **禁止项**：禁止交互信号绕过 Orchestrator 直接激活子智能体的 Planner——所有信号必须经过 Orchestrator 的插话意愿计算才能转化为实际插话行为
   a. 验收条件：[交互信号到达但插话意愿未超过阈值] → [不产生插话行为，但子智能体可能被激活]

### **5.6.2 交互流程**

```plantuml
@startuml
participant "agent-interaction-alive\n(交互系统)" as Interaction
participant "Orchestrator\n(编排器)" as Orch
participant "EmotionManager" as Emotion
participant "子智能体 B\n(角色化Planner)" as B_Planner

== 信号激活子智能体 ==
Interaction -> Orch : 交互信号\n(银狼想念三月七)
Orch -> Orch : 三月七是否活跃
alt 三月七非活跃
    Orch -> Orch : 三月七被激活，加入活跃列表
end
Orch -> Emotion : 读取三月七情绪状态
Orch -> Orch : 计算三月七插话意愿\n(交互信号+40, 情绪加成)
alt 插话意愿 ≥ 60
    Orch -> B_Planner : 激活三月七的角色化Planner
else 插话意愿 < 60
    Orch -> Orch : 不激活，三月七仍然活跃
end

== 插话反哺交互 ==
B_Planner -> Interaction : 三月七插话内容\n(可能提及银狼)
Interaction -> Interaction : 产生提及传递信号\n(三月七→银狼)
Interaction -> Emotion : 银狼因三月七出现而开心

@enduml
```

### **5.6.3 异常场景**

1. **交互信号到达时对话不活跃**
   a. 触发条件：交互信号到达但当前会话无活跃对话
   b. 系统行为：交互信号仅影响活跃状态和情绪，不激活子智能体 Planner
   c. 用户感知：无

2. **交互信号与插话形成无限循环**
   a. 触发条件：A 插话 → 产生交互信号 → B 的 Planner 被激活并插话 → 产生交互信号 → A 再次插话
   b. 系统行为：插话冷却机制和频率限制自动打破循环
   c. 用户感知：插话逐渐减少直到停止

## **5.7 日志可观测性**

### **5.7.1 业务规则**

1. **回复日志规则**：每次子智能体回复必须输出结构化日志，包含以下字段：
   - agent_id：发言子智能体 ID
   - reply_type：回复类型（primary / interjection / switch）
   - trigger_reason：触发原因
   - session_id：会话 ID
   - session_name：会话名称（优先显示群名称或"xxx的私聊"）
   a. 验收条件：[任意子智能体产生回复] → [日志中出现 `[agent_reply] agent=silver_wolf type=primary reason=user_message session=xxx` 格式的记录]
   b. 验收条件：[子智能体插话] → [日志中 reply_type=interjection，且包含插话触发原因]

2. **发言权变更日志规则**：主发言子智能体变更时必须输出日志
   a. 验收条件：[主发言子智能体从 A 切换为 B] → [日志中出现 `[agent_reply] speaker_change from=A to=B reason=xxx` 格式的记录]

3. **子智能体活跃状态变更日志规则**：子智能体激活或退场时必须输出日志
   a. 验收条件：[子智能体 B 被激活] → [日志中出现 `[sub_agent] agent=B action=activate session=xxx reason=xxx` 格式的记录]
   b. 验收条件：[子智能体 B 退场] → [日志中出现 `[sub_agent] agent=B action=deactivate session=xxx reason=xxx` 格式的记录]

4. **插话意愿日志规则**：插话意愿计算结果应当输出调试级别日志
   a. 验收条件：[插话意愿计算完成] → [调试日志中包含各活跃子智能体的插话意愿值和计算因子]

5. **Orchestrator 编排日志规则**：Orchestrator 的关键编排决策应当输出调试级别日志
   a. 验收条件：[Orchestrator 做出编排决策] → [调试日志中包含决策类型、涉及子智能体、决策原因]

6. **WebUI 可观测性规则**：用户必须能从 WebUI 看到当前会话的子智能体活跃状态和发言历史
   a. 验收条件：[打开 WebUI 对话监控面板] → [能看到当前会话的活跃子智能体列表、主发言子智能体标识、最近的发言记录（含发言子智能体标记）]
   b. 验收条件：[子智能体插话后] → [WebUI 中该条消息显示插话子智能体的标识]

7. **禁止项**：禁止在日志中泄露其他会话的对话内容
   a. 验收条件：[子智能体 A 在会话 X 中插话] → [日志中只包含会话 X 的信息，不包含 A 在会话 Y 中的对话内容]

### **5.7.2 交互流程**

```plantuml
@startuml
participant "Orchestrator\n(编排器)" as Orch
participant "日志系统" as Log
participant "WebUI" as WebUI

Orch -> Log : [agent_reply] agent=A type=primary reason=user_message
Orch -> Log : [sub_agent] agent=B action=activate reason=interaction_signal
Orch -> Log : [agent_reply] agent=B type=interjection reason=mention_driven
Orch -> Log : [agent_reply] speaker_change from=A to=C reason=user_request

Orch -> WebUI : 推送活跃状态变更
Orch -> WebUI : 推送发言记录（含发言标记）

@enduml
```

### **5.7.3 异常场景**

1. **日志系统不可用**
   a. 触发条件：日志写入失败
   b. 系统行为：不影响对话流程，仅记录到 stderr
   c. 用户感知：无

## **5.8 未来扩展预留**

### **5.8.1 业务规则**

1. **动态性格预留规则**：子智能体架构必须支持未来"智能体性格动态变化"的场景——同一子智能体在不同时期可能表现出不同的性格特征
   a. 验收条件：[子智能体单元的 Planner 提示词构建方式] → [必须支持从动态数据源（而非仅静态配置）加载人设信息，为未来的动态性格引擎预留接口]
   b. 验收条件：[子智能体的角色化 Planner 提示词] → [人设注入点 {identity} 必须支持动态替换，而非编译时固定]

2. **程序化生成人生预留规则**：子智能体架构必须支持未来"程序化生成智能体人生经历"的场景——子智能体的记忆和经历可以动态生成
   a. 验收条件：[子智能体单元的记忆注入方式] → [必须支持从动态生成的记忆源（而非仅历史对话记忆）注入内容，为未来的程序化生成人生预留接口]

3. **多账号预留规则**：子智能体架构的设计不得假设"所有子智能体共用同一账号"——虽然当前是这种情况，但未来可能每个子智能体有独立账号
   a. 验收条件：[发言标记的标识方式] → [不得依赖"同一账号"这一约束，必须为每个子智能体的回复提供独立的标识能力]

4. **回复管线可扩展规则**：回复管线必须支持未来扩展新的回复类型（如"旁白""内心独白外显"等）
   a. 验收条件：[回复类型的定义方式] → [必须通过可注册的枚举或字符串类型定义，而非硬编码的枚举值]

5. **子智能体单元可扩展规则**：子智能体单元的构成必须支持未来扩展新的组成部分（如"内在需求引擎""长远目标管理"等）
   a. 验收条件：[子智能体单元的构建方式] → [必须通过可注册的组件机制扩展，而非硬编码的固定组成]

6. **Orchestrator 策略可扩展规则**：Orchestrator 的编排策略必须支持未来扩展（如"辩论模式""轮流发言模式"等）
   a. 验收条件：[Orchestrator 的编排策略] → [必须通过可配置的策略模式实现，而非硬编码的固定逻辑]

7. **禁止项**：禁止在子智能体架构中硬编码任何智能体的特定逻辑——所有子智能体必须通过统一的机制参与回复
   a. 验收条件：[新增一个智能体] → [无需修改子智能体架构的任何代码，该智能体即可作为子智能体单元参与插话和发言切换]

# **6. 数据约束**

## **6.1 插话事件（InterjectionEvent）**

1. **event_id**：全局唯一标识，格式为 `ij:{agent_id}:{timestamp_hex}:{random_hex}`
2. **agent_id**：插话子智能体 ID，必须为 AgentConfigRegistry 中已注册的 agent_id
3. **session_id**：插话发生的会话 ID
4. **primary_agent_id**：插话时的主发言子智能体 ID
5. **interjection_type**：插话类型枚举，取值范围为：mention_driven / emotion_driven / interaction_signal / planner_activated / manual_trigger
6. **trigger_reason**：触发原因的可读描述，不可为空字符串
7. **interjection_intent_score**：插话意愿分值，浮点数，0.0-100.0
8. **content_summary**：插话内容摘要，最大 500 字符
9. **created_at**：创建时间戳，Unix 时间戳（秒）

## **6.2 子智能体活跃状态（SubAgentActivity）**

1. **session_id**：会话 ID
2. **agent_id**：子智能体 ID，必须为 AgentConfigRegistry 中已注册的 agent_id
3. **is_primary**：是否为主发言子智能体，布尔值
4. **activation_reason**：激活原因枚举，取值范围为：session_create / interjection / interaction_signal / planner_activated / manual_activate
5. **activated_at**：激活时间戳，Unix 时间戳（秒）
6. **last_spoke_at**：最近一次发言时间戳，Unix 时间戳（秒），初始值等于 activated_at
7. **exit_reason**：退场原因枚举，取值范围为：timeout / active_exit / manual_exit / null（未退场）
8. **exited_at**：退场时间戳，Unix 时间戳（秒），未退场时为 null

## **6.3 发言权变更记录（SpeakerChangeRecord）**

1. **record_id**：全局唯一标识，格式为 `sc:{session_id}:{timestamp_hex}`
2. **session_id**：会话 ID
3. **from_agent_id**：原主发言子智能体 ID，首次切换时可为空字符串
4. **to_agent_id**：新主发言子智能体 ID
5. **change_type**：变更类型枚举，取值范围为：user_request / agent_yield / manual_switch / session_create
6. **change_reason**：变更原因的可读描述
7. **created_at**：创建时间戳，Unix 时间戳（秒）

## **6.4 插话意愿计算因子（InterjectionIntentFactors）**

1. **mention_relevance_score**：对话内容与子智能体的关联度分值，浮点数，0.0-1.0
2. **emotion_drive_score**：情绪驱动分值，浮点数，0.0-1.0，由情绪类型和强度决定
3. **relationship_drive_score**：关系驱动分值，浮点数，0.0-1.0，由与对话参与者的关系决定
4. **interaction_signal_score**：交互信号驱动分值，浮点数，0.0-1.0，由 agent-interaction-alive 信号决定
5. **planner_activation_score**：角色化 Planner 激活驱动分值，浮点数，0.0-1.0，由子智能体自身 Planner 的发言驱动力决定
6. **intent_threshold**：插话意愿阈值，浮点数，0.0-100.0，默认 60.0
7. **cooldown_minutes**：插话冷却时间（分钟），整数，≥ 1，默认 5
8. **max_interjections_per_hour**：同一子智能体每小时最大插话次数，整数，1-10，默认 3
9. **max_interjections_per_session_per_hour**：同一会话每小时最大插话总次数，整数，1-20，默认 6

## **6.5 子智能体架构配置（SubAgentArchitectureConfig）**

1. **enabled**：是否启用子智能体架构，布尔值，默认 false（需显式开启）
2. **max_active_sub_agents**：同一会话最大活跃子智能体数，整数，2-5，默认 3
3. **auto_exit_timeout_minutes**：活跃子智能体超时退场时间（分钟），整数，≥ 10，默认 60
4. **interjection_enabled**：是否启用插话机制，布尔值，默认 true
5. **interjection_intent_threshold**：插话意愿阈值，浮点数，0.0-100.0，默认 60.0
6. **interjection_cooldown_minutes**：插话冷却时间（分钟），整数，≥ 1，默认 5
7. **max_interjections_per_hour**：同一子智能体每小时最大插话次数，整数，1-10，默认 3
8. **max_interjections_per_session_per_hour**：同一会话每小时最大插话总次数，整数，1-20，默认 6
9. **interaction_signal_interjection_enabled**：是否启用交互信号激活子智能体 Planner，布尔值，默认 true
10. **interaction_signal_interjection_bonus**：交互信号对插话意愿的加成分值，浮点数，0.0-50.0，默认 40.0
11. **embodied_planner_enabled**：是否启用角色化 Planner，布尔值，默认 true（启用子智能体架构时自动启用）
12. **orchestrator_strategy**：Orchestrator 编排策略，字符串，默认 "default"，取值范围为可注册的策略名
