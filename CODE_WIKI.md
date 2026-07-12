# MaiBot Code Wiki

> **版本**: v1.0.11  
> **文档生成日期**: 2026-07-12  
> **项目仓库**: [Mai-with-u/MaiBot](https://github.com/MaiM-with-u/MaiBot)

---

## 目录

- [1. 项目概览](#1-项目概览)
- [2. 项目架构总览](#2-项目架构总览)
- [3. 核心架构：微内核 + 接口契约](#3-核心架构微内核--接口契约)
- [4. 主要模块职责](#4-主要模块职责)
- [5. 关键类与函数说明](#5-关键类与函数说明)
- [6. 依赖关系](#6-依赖关系)
- [7. 项目运行方式](#7-项目运行方式)
- [8. 开发规范与架构原则](#8-开发规范与架构原则)

---

## 1. 项目概览

### 1.1 项目简介

**MaiBot（麦麦 MaiSaka）** 是一个基于大语言模型的可交互智能体。她不追求完美和高效，而是致力于以真实人类的风格进行交互——一个会犯错、有自己感知和想法的"数字生命"。

**核心设计理念**：

- **反标本化**：角色不是被钉死的蝴蝶，而是仍在呼吸的种子
- **反叙事耗竭**：让所有人渴望结局，却又甘愿让结局永远保持在未抵达的远方
- **动态生命感**：角色内心有持续流淌的、未解决的张力

**核心特性**：

| 特性 | 说明 |
|------|------|
| 自然对话风格 | 摒弃 GPT 式长篇大论，采用贴合人类习惯的闲谈 |
| 情境感知 | 懂得在合适时机说话/闭嘴，把握聊天气氛 |
| 自主进化 | 模仿他人说话风格，理解新词和黑话 |
| 持续学习 | 基于心理学人格理论，不断积累对用户的了解 |
| 插件系统 | 提供强大 API 和事件系统，无限扩展可能 |
| 多智能体共居 | 12+ 角色共居，管家协调插话，每个角色独立思考 |

### 1.2 技术栈

| 类别 | 技术 |
|------|------|
| 语言 | Python 3.12+（目标 3.14.6） |
| 异步框架 | asyncio |
| Web 框架 | FastAPI + uvicorn |
| 数据库 | SQLite（SQLModel + SQLAlchemy） |
| 向量检索 | Faiss（SQ8 量化） |
| 图计算 | SciPy 稀疏矩阵 |
| LLM 客户端 | OpenAI SDK + Google GenAI |
| 嵌入模型 | sentence-transformers |
| 依赖管理 | uv |
| 容器化 | Docker + docker-compose |
| WebUI | React + Vite + TailwindCSS + shadcn/ui |
| 日志 | structlog + rich |
| 国际化 | 自研 i18n（zh-CN / en-US / ja-JP / ko） |

---

## 2. 项目架构总览

### 2.1 架构分层

MaiBot 采用**微内核 + 接口契约**架构，核心模块只依赖 Protocol 接口，不依赖组件具体实现：

```
┌─────────────────────────────────────────────────────────────────┐
│                        外部平台适配器                            │
│              (NapCat / 其他 QQ Bot 协议实现)                      │
└──────────────────────────┬──────────────────────────────────────┘
                           │ 消息入站/出站
┌──────────────────────────▼──────────────────────────────────────┐
│                    Platform IO 层                                │
│         (platform_io/ — 统一消息路由、去重、驱动管理)              │
└──────────────────────────┬──────────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────────┐
│                    消息链路层 (chat/)                             │
│    bot.py → chat_manager → heartflow_manager → runtime           │
└──────────────────────────┬──────────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────────┐
│              核心层 (core/) — Protocol 接口契约                   │
│   SessionRepository | AgentRoutingService | ChatRuntime          │
│   MemoryServicePort | ThinkingOrgan | MessagePortV2 | ...        │
└──────────────────────────┬──────────────────────────────────────┘
                           │
          ┌────────────────┼────────────────────┐
          │                │                    │
┌─────────▼─────┐ ┌────────▼────────┐ ┌────────▼────────┐
│  Maisaka      │ │  A_memorix      │ │  Services       │
│  智能体自主性  │ │  记忆系统        │ │  业务服务层      │
│  (agent_auton)│ │  (记忆检索/写入) │ │  (send/memory)  │
└───────────────┘ └─────────────────┘ └─────────────────┘
          │                │                    │
          │         ┌──────▼──────┐             │
          │         │  LLM Models │             │
          │         │  (LLM调度)  │             │
          │         └─────────────┘             │
          │                                     │
┌─────────▼─────────────────────────────────────▼─────────────────┐
│                    插件运行时 (plugin_runtime/)                   │
│         Host-Runner 双进程 IPC 架构 + Hook 系统                   │
└─────────────────────────────────────────────────────────────────┘
          │                                     │
┌─────────▼─────────────────────────────────────▼─────────────────┐
│              基础设施 (common/ + config/ + webui/)               │
│   数据库 | i18n | 日志 | 配置管理 | WebUI 后端                    │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 目录结构

```
MaiBot/
├── bot.py                      # 主入口（Runner + Worker 双进程）
├── saka.py                     # 辅助入口
├── pyproject.toml              # 项目配置与依赖
├── docker-compose.yml          # Docker 编排
├── Dockerfile                  # 容器构建
│
├── src/                        # 源码主目录
│   ├── main.py                 # MainSystem 系统初始化
│   ├── core/                   # 核心 Protocol 接口层
│   ├── maisaka/                # Maisaka 智能体系统
│   │   ├── agent/              #   智能体配置与路由
│   │   ├── agent_autonomy/     #   自主性架构（Orchestrator/Butler/...）
│   │   ├── agent_interaction/  #   智能体交互系统
│   │   ├── builtin_tool/       #   内置工具
│   │   ├── chat_loop_service.py#   对话循环服务
│   │   ├── runtime.py          #   会话运行时
│   │   └── ...                 #   其他子系统
│   ├── A_memorix/              # 记忆系统
│   │   ├── core/               #   记忆核心（连接主义+分类学）
│   │   ├── host_service.py     #   对外服务入口
│   │   └── ...
│   ├── chat/                   # 聊天与消息系统
│   │   ├── message_receive/    #   消息接收与会话管理
│   │   ├── heart_flow/         #   HeartFlow 运行时管理
│   │   ├── replyer/            #   回复生成器
│   │   └── image_system/       #   图片处理
│   ├── services/               # 业务服务层
│   ├── plugin_runtime/         # 插件运行时（Host-Runner IPC）
│   ├── platform_io/            # 平台 IO 统一管理
│   ├── config/                 # 配置系统
│   ├── webui/                  # WebUI 后端（FastAPI）
│   ├── llm_models/             # LLM 模型客户端
│   ├── common/                 # 公共模块（DB/i18n/日志/工具）
│   ├── emoji_system/           # 表情包系统
│   ├── learners/               # 学习器（行为/表情/黑话）
│   ├── prompt/                 # 提示词管理
│   └── manager/                # 任务管理器
│
├── agents/                     # 智能体配置（Markdown 格式）
├── prompts/                    # 提示词模板（zh-CN/en-US/ja-JP）
├── locales/                    # 国际化资源
├── dashboard/                  # WebUI 前端（React）
├── plugins/                    # 插件目录
├── docs/                       # 文档
├── scripts/                    # 脚本工具
└── pytests/                    # 测试
```

---

## 3. 核心架构：微内核 + 接口契约

### 3.1 架构理念

MaiBot 的核心架构遵循一个明确原则：**核心定义接口契约，组件实现契约**。核心模块（智能体 + 消息管道）不依赖组件具体实现，只通过 Protocol 接口交互。

> **核心定义**：核心 = 智能体 + 消息管道，只关心一件事：**消息进来，智能体思考，回复出去**
>
> 核心接口只有三个：`receive(message)` → `think()` → `respond(text)`

### 3.2 核心 Protocol 接口

所有核心 Protocol 定义在 [protocols.py](file:///c:/Users/lmq/.trae-cn/worktrees/MaiBot/docs-code-wiki-generation-DL8IFc/src/core/protocols.py)：

| Protocol | 职责 | 实现者 |
|----------|------|--------|
| `SessionRepository` | 会话信息查询（不可变快照） | ChatManagerAdapter |
| `AgentRoutingService` | 智能体-会话路由 | ChatManagerRoutingAdapter |
| `ChatRuntime` | 运行时生命周期 | MaisakaHeartFlowChatting |
| `ChatRuntimeRegistry` | 运行时注册表 | HeartflowRuntimeRegistry |
| `NoticeClassifier` | 平台无关通知分类 | NapCatNoticeClassifier |
| `MemoryServicePort` | 记忆检索与画像 | AMemorixMemoryServicePort |
| `SessionInfoPort` | 组件反向查询会话 | ChatManagerAdapter |
| `SessionLifecyclePort` | 会话生命周期（创建/持久化） | ChatManagerAdapter |
| `SessionQueryPort` | 会话批量查询 | ChatManagerAdapter |
| `MessageRegistryPort` | 入站消息注册 | ChatManagerAdapter |
| `ThinkingOrgan` | 智能体思维管道 | ThinkingOrgan |
| `ThinkingOrganFactory` | 思维管道工厂 | ThinkingOrganFactory |
| `MessagePortV2` | 统一消息发送（1个方法） | SendServiceMessagePortV2 |

### 3.3 适配器层

适配器层（`src/core/adapters/`）是**唯一允许导入组件具体类**的地方：

| 适配器 | 文件 | 实现的 Protocol |
|--------|------|----------------|
| ChatManagerAdapter | `chat_manager_adapter.py` | SessionInfoPort + SessionLifecyclePort + SessionQueryPort + MessageRegistryPort |
| ChatManagerRoutingAdapter | `routing_adapter.py` | AgentRoutingService |
| AMemorixMemoryServicePort | `memory_service.py` | MemoryServicePort |
| SendServiceMessagePortV2 | `message_port_v2.py` | MessagePortV2 |
| NapCatNoticeClassifier | `notice_classifier.py` | NoticeClassifier |
| HeartflowRuntimeRegistry | `runtime_registry.py` | ChatRuntimeRegistry |

### 3.4 核心数据模型

定义在 [types.py](file:///c:/Users/lmq/.trae-cn/worktrees/MaiBot/docs-code-wiki-generation-DL8IFc/src/core/types.py)：

**CoreMessage**（平台无关入站消息）：
- `session_id`, `plain_text`, `is_notify`, `notice_kind`, `sender_id`, `sender_name`, `platform`, `timestamp`, `additional_data`

**SessionInfo**（不可变会话快照）：
- `session_id`, `session_name`, `platform`, `is_group_session`, `primary_agent_id`, `cohabitant_agent_ids`, `account_id`, `scope`, `user_cardname`

**NoticeKind**（平台无关通知枚举）：
- `AMBIENT`（环境信号，不触发 Planner）
- `INTERACTION`（交互信号，可能触发）
- `INPUT_STATUS` / `UNKNOWN`

**ThinkContext / ThinkResult**（思维管道输入输出）：
- ThinkContext: messages, inner_voice_text, emotion_state_text, relationship_text, memory_snippets, cohabitant_summary
- ThinkResult: action(REPLY/SILENT/ERROR), text, thinking_time_ms

### 3.5 核心禁止项

以下模式是架构债务，新增代码禁止引入：

1. 禁止核心直接导入 `chat_manager`
2. 禁止核心访问 `chat_manager._agent_router`
3. 禁止核心持有 `BotChatSession` 可变引用
4. 禁止核心硬编码 `napcat_*` 字段
5. 禁止核心绕过 `MessagePort` 直接调用 `send_service` ✅ 已消除
6. 禁止核心导入 `A_memorix` 内部模块 ✅ 已消除
7. 禁止 Orchestrator 通过 `enqueue_proactive_task` 模拟多智能体

这些禁止项通过 `ruff` 的 `TID251` 规则在 CI 中强制执行。

---

## 4. 主要模块职责

### 4.1 Maisaka 智能体自主性系统

**路径**: `src/maisaka/agent_autonomy/`

这是 MaiBot 最核心的创新——让智能体从"反射弧"进化为"有内心世界的生命体"。

#### 4.1.1 AgentOrchestrator（编排器）

**文件**: [orchestrator.py](file:///c:/Users/lmq/.trae-cn/worktrees/MaiBot/docs-code-wiki-generation-DL8IFc/src/maisaka/agent_autonomy/orchestrator.py)

多智能体协作的唯一编排者，**只协调执行顺序和资源分配，不替智能体做决策**。

**核心职责**：
- 智能体生命周期管理（激活/退场/恢复/切换主发言）
- 消息处理与编排（通知分类 → 管家过滤 → 并行思考调度）
- 插话调度机制（动态共居参数 + 策略过滤）
- 提醒流处理（30 秒周期检查到期提醒）
- 交互信号处理（唤醒目标智能体）
- 环境感知订阅（事件总线）

**关键方法**：
- `handle_message(message)` — 消息处理主入口
- `activate_agent(agent_id, reason)` — 激活智能体
- `switch_primary_speaker(target, reason, change_type)` — 切换主发言
- `_schedule_interjections()` — 插话调度
- `_reminder_tick_loop()` — 提醒心跳循环

#### 4.1.2 ThinkingOrgan（思维管道）

**文件**: [thinking_organ.py](file:///c:/Users/lmq/.trae-cn/worktrees/MaiBot/docs-code-wiki-generation-DL8IFc/src/maisaka/agent_autonomy/thinking_organ.py)

每个智能体拥有独立的 ThinkingOrgan 实例，以角色内部视角运行 Planner。

**关键方法**：
- `think(context: ThinkContext) -> ThinkResult` — 执行思考（消息触发）
- `think_proactive(reason, context) -> ThinkResult` — 主动思考（欲望/提醒/管家触发）
- `build_system_prompt()` / `build_personality_prompt()` — 构建角色化提示词

**设计原则**：ThinkingOrgan 只关心"怎么思考"，不关心"何时思考"（由 Orchestrator/管家决定）。

#### 4.1.3 Butler（管家系统）

**文件**: [butler.py](file:///c:/Users/lmq/.trae-cn/worktrees/MaiBot/docs-code-wiki-generation-DL8IFc/src/maisaka/agent_autonomy/butler.py)

"彼岸居客厅规则"的化身——管家**不说话**，只做过滤（谁看见了消息）和协调（谁先抢到键盘）。

**三层过滤机制**：

| 层次 | 方法 | 成本 | 说明 |
|------|------|------|------|
| 第一层：规则过滤 | `_rule_filter()` | 零成本 | 名字提及→必看见；有关系→50%概率；无关→10%概率 |
| 第二层：管家 LLM | `_llm_filter()` | 1次调用 | LLM 判断"哪些角色会自然想插话" |
| 第三层：角色 LLM | ThinkingOrgan | 仅选中者 | 被选中角色决定插话内容，可回复 SILENT |

**成本**：最差 1(主)+1(管家)+2(插话)=4 次 LLM 调用；最好 1+1+0=2 次。

#### 4.1.4 VitalityManager（生命力管理）

**文件**: [vitality_manager.py](file:///c:/Users/lmq/.trae-cn/worktrees/MaiBot/docs-code-wiki-generation-DL8IFc/src/maisaka/agent_autonomy/vitality_manager.py)

负责待命智能体的生命力计算、跃迁判定与共居参数动态调整。

**状态转换**：
```
dormant → standby (add_to_standby)
standby → active (check_instant_activation / evaluate_vitality_tick)
active → standby (deactivate_agent)
standby → dormant (vitality_depleted)
```

**心跳评估**（60 秒周期）：
- 内在需求加成（最多 +20）
- 情绪加成（最多 +10）
- 时间衰减
- 跃迁判定（生命力 >= 阈值 → 激活）

#### 4.1.5 InnerNeedEngine（欲望系统）

**文件**: [inner_need.py](file:///c:/Users/lmq/.trae-cn/worktrees/MaiBot/docs-code-wiki-generation-DL8IFc/src/maisaka/agent_autonomy/inner_need.py)

欲望是**规则引擎**（不是 LLM），让智能体在无人输入时也决定调用 LLM：

```
心跳(60s) → 规则评估内心状态 → 欲望是否足够强？
                                    ↓ 是
                               构造 prompt → 调 LLM → 发送
                                    ↓ 否
                               继续待命
```

**三个计算器**：
- `EmotionNeedCalculator` — 基于情绪（lonely→companionship, excited→sharing, ...）
- `MemoryNeedCalculator` — 基于交互记忆（超过 24 小时未交互→missing）
- `TimeNeedCalculator` — 基于时间画像（深夜→night_chat）

#### 4.1.6 EmotionManager（情绪系统）

**文件**: [emotion.py](file:///c:/Users/lmq/.trae-cn/worktrees/MaiBot/docs-code-wiki-generation-DL8IFc/src/maisaka/agent/emotion.py)

7 种情绪类型：happy / sad / anxious / angry / calm / excited / lonely

**关键特性**：
- 指数衰减：`decayed = base + (current - base) * exp(-decay_rate * elapsed_hours)`
- 情绪触发行为倾向（`get_behavior_tendency()`）
- 情绪染色回应（通过 `to_prompt_text()` 注入提示词）

#### 4.1.7 ParallelThinkScheduler（并行思考）

**文件**: [parallel_think.py](file:///c:/Users/lmq/.trae-cn/worktrees/MaiBot/docs-code-wiki-generation-DL8IFc/src/maisaka/agent_autonomy/parallel_think.py)

使用 `asyncio.Semaphore` 控制并发数（默认 max_concurrent=2），避免同时发起过多 LLM 请求。

#### 4.1.8 Reminder（提醒系统）

**文件**: [reminder.py](file:///c:/Users/lmq/.trae-cn/worktrees/MaiBot/docs-code-wiki-generation-DL8IFc/src/maisaka/agent_autonomy/reminder.py)

支持两种提醒：
- **直接提醒**：用户明确要求"3点提醒我开会"
- **间接提醒**：用户提到"下午有个考试"，到时间关心

时间解析支持正则匹配 + LLM 提取双重机制。

#### 4.1.9 Runtime（会话运行时）

**文件**: [runtime.py](file:///c:/Users/lmq/.trae-cn/worktrees/MaiBot/docs-code-wiki-generation-DL8IFc/src/maisaka/runtime.py)

`MaisakaHeartFlowChatting` 是会话级别的 Maisaka 运行时，实现 `ChatRuntime` Protocol。

**核心职责**：
- 会话级消息缓存与处理循环
- 上下文窗口管理与历史恢复
- 工具注册（内置工具、插件工具、MCP 工具）
- 情绪/关系管理器初始化
- 智能体自主性架构初始化

### 4.2 A_memorix 记忆系统

**路径**: `src/A_memorix/`

A_memorix 是 MaiBot 的核心记忆子系统，正在进行从**分类学**到**连接主义**的范式迁移。

#### 4.2.1 架构层次

```
MaiBot 核心 (MemoryServicePort Protocol)
        ↓ 适配器层
AMemorixMemoryServicePort (Protocol 实现)
        ↓
AMemorixHostService (服务层入口，单例)
        ↓ invoke() 分发
SDKMemoryKernel (运行时核心，2911 行薄协调层)
   ├─ services/ (14 个服务)
   ├─ admin/ (13 个 Admin Handler)
   ├─ MemoryField (连接主义核心)
   ├─ MigrationAdapter + MigrationRouter (迁移框架)
   └─ 持久化存储 + 嵌入管理 + 检索器
        ↓
核心层 (connectionist/ + storage/ + retrieval/ + ...)
```

#### 4.2.2 分类学 vs 连接主义

| 维度 | 分类学（旧） | 连接主义（新） |
|------|------------|--------------|
| 记忆单位 | 标本（Paragraph/Entity/Relation/Episode/Profile） | Trace（概念间的连接） |
| 新记忆 | 新增标本 | 新增连接 |
| 遗忘 | 删除标本 | 连接权重衰减 |
| 回忆 | 向量相似度检索 | 激活扩散（概念图遍历） |
| 画像 | 结构化字段聚合 | 关联概念+矛盾点实时推导 |
| 智能体差异 | 无 | 每个智能体有独立性格+内心声音 |

#### 4.2.3 迁移框架（5 阶段状态机）

```
LEGACY_ONLY → DUAL_WRITE → DUAL_READ → DATA_MIGRATION → NEW_INDEPENDENT
  (仅分类学)   (双写)       (双读对比)   (数据迁移)      (仅连接主义)
```

- 禁止跳级，必须逐级推进
- `MigrationRouter` 根据阶段将请求路由到分类学或连接主义
- 当前阶段：**DUAL_WRITE**（第 1-4 批编码完成）

#### 4.2.4 关键组件

| 组件 | 文件 | 职责 |
|------|------|------|
| AMemorixHostService | `host_service.py` | 对外服务入口，`invoke()` 统一分发 |
| SDKMemoryKernel | `core/runtime/sdk_memory_kernel.py` | 运行时核心，薄协调层 |
| MemoryField | `core/connectionist/memory_field.py` | 连接主义核心（observe/recall/derive_profile/reflect） |
| TraceStore | `core/connectionist/trace_store.py` | Trace 持久化（SQLite + 内存邻接索引） |
| SpreadingActivation | `core/connectionist/spreading_activation.py` | 激活扩散回忆算法 |
| SalienceEvaluator | `core/connectionist/salience_evaluator.py` | 4 维显著性评估 |
| GranularDecayEngine | `core/connectionist/granular_decay_engine.py` | 粒度退化引擎 |
| PersonalityRegistry | `core/personality/personality_registry.py` | 智能体记忆性格注册 |
| GraphStore | `core/storage/graph_store.py` | 图存储（SciPy 稀疏矩阵） |
| VectorStore | `core/storage/vector_store.py` | 向量存储（Faiss SQ8） |
| MetadataStore | `core/storage/metadata_store.py` | 元数据存储（SQLite） |
| DualPathRetriever | `core/retrieval/dual_path.py` | 双路检索器 |
| EmbeddingManager | `core/embedding/manager.py` | 嵌入管理（sentence-transformers） |

### 4.3 聊天与消息系统

**路径**: `src/chat/`

#### 4.3.1 消息处理流程

```
外部平台 → ChatBot.message_process() → receive_message()
    → SessionUtils.calculate_session_id() 计算会话ID
    → SessionMessage.process() 处理消息组件
    → 过滤检查（敏感词/正则）
    → chat_manager.register_message() 注册消息
    → chat_manager.get_or_create_session() 获取会话
    → 命令处理（若命中）
    → heartflow_manager.get_or_create_heartflow_chat() 获取运行时
    → MaisakaHeartFlowChatting.register_message() 注册到运行时
    → orchestrator.handle_message() 智能体自主处理
```

#### 4.3.2 ChatManager 拆分架构

ChatManager 已从 604 行瘦身至 143 行薄协调层，持有 6 个子模块：

| 子模块 | 文件 | 职责 |
|--------|------|------|
| SessionStore | `session_store.py` | 会话字典 CRUD + 单条持久化 |
| MessageRegistry | `message_registry.py` | 消息注册 + 缓存 + 身份更新 |
| SessionNameCache | `session_name_cache.py` | 名称查询 |
| SessionResolver | `session_resolver.py` | 路由解析 + 数据库懒加载 |
| BindingRestorer | `binding_restorer.py` | 启动时智能体绑定恢复 |
| SessionLifecycle | `session_lifecycle.py` | 创建/获取 + 批量持久化 + 初始化 |

#### 4.3.3 HeartFlow 系统

**HeartflowManager**（[heartflow_manager.py](file:///c:/Users/lmq/.trae-cn/worktrees/MaiBot/docs-code-wiki-generation-DL8IFc/src/chat/heart_flow/heartflow_manager.py)）是消息链路与智能体思考之间的桥梁层：

- LRU + 时间窗口双重淘汰策略
- 最多 100 个活跃运行时（`HEARTFLOW_MAX_ACTIVE_CHATS = 100`）
- 24 小时活跃保护窗口

#### 4.3.4 回复生成器

**MaisakaReplyGenerator**（[maisaka_generator.py](file:///c:/Users/lmq/.trae-cn/worktrees/MaiBot/docs-code-wiki-generation-DL8IFc/src/chat/replyer/maisaka_generator.py)）：

- `generate_reply_with_context()` — 主入口
- 三层 Hook 体系（before_request / before_model_request / after_response）
- 重生成循环（最多 3 次）
- 富回复检查（emoji/pic/at/split/send）
- i18n 支持（zh-CN/en-US/ja-JP）

### 4.4 服务层

**路径**: `src/services/`

| 服务 | 文件 | 职责 |
|------|------|------|
| send_service | `send_service.py` | 消息发送服务，实现 MessagePortV2 Protocol |
| memory_service | `memory_service.py` | 记忆服务封装层，桥接核心与 A_memorix |
| memory_flow_service | `memory_flow_service.py` | 记忆自动化（人物事实写回） |
| llm_service | `llm_service.py` | LLM 服务门面 |
| embedding_service | `embedding_service.py` | 嵌入服务门面 |
| database_service | `database_service.py` | 通用数据库 CRUD |
| generator_service | `generator_service.py` | 回复器服务 |

### 4.5 插件运行时

**路径**: `src/plugin_runtime/`

采用 **Host-Runner 双进程架构**，内置插件和第三方插件各自运行在独立子进程中。

```
src/plugin_runtime/
├── host/              # Host 端（主进程）
│   ├── supervisor.py       # Runner 监督器
│   ├── rpc_server.py       # RPC 服务器
│   ├── hook_dispatcher.py  # Hook 分发系统
│   ├── component_registry.py # 组件注册表
│   └── capability_service.py # 能力服务
├── runner/            # Runner 端（子进程）
├── protocol/          # RPC 协议定义
│   └── envelope.py         # 消息信封（MsgPack 编码）
├── transport/         # 传输层（UDS/Named Pipe/TCP）
└── capabilities/      # 能力混入
```

**关键特性**：
- 双 Supervisor 架构（内置 + 第三方）
- 分帧协议：4-byte 长度前缀 + payload，最大帧 16MB
- Hook 系统：blocking（串行可修改）+ observe（并发旁路）
- 熔断器集成防止故障插件拖垮系统
- 文件监视器支持热重载
- LLM Provider 冲突检测

### 4.6 Platform IO 层

**路径**: `src/platform_io/`

统一协调平台消息 IO 的路由、去重与状态跟踪。

| 组件 | 职责 |
|------|------|
| PlatformIOManager | 中心 Broker 管理器 |
| DriverRegistry | 驱动注册表 |
| RouteTable | 发送/接收路由表 |
| MessageDeduplicator | 消息去重 |
| OutboundTracker | 出站跟踪 |
| drivers/ | 驱动实现（legacy/plugin） |

### 4.7 配置系统

**路径**: `src/config/`

| 文件 | 职责 |
|------|------|
| `config_base.py` | 配置基类（AttrDocBase 通过 AST 解析字段文档） |
| `config.py` | 全局配置管理器（ConfigManager），25+ 配置段 |
| `official_configs.py` | 所有官方配置类定义 |
| `model_configs.py` | API Provider 和模型信息配置 |
| `file_watcher.py` | 基于 watchfiles 的文件变更监视器 |
| `legacy_migration.py` | 旧版迁移（禁止改动） |

**配置版本**：
- `CONFIG_VERSION` = "8.23.0"
- `MODEL_CONFIG_VERSION` = "1.17.6"

**热重载机制**：FileWatcher 检测变更 → ConfigManager.reload() → 回调通知（WebUI 重建、插件 Runner 通知）

### 4.8 WebUI 系统

**路径**: `src/webui/`（后端） + `dashboard/`（前端）

**后端**（FastAPI）：
- 应用工厂模式（`create_app()`）
- IPv4 + IPv6 双栈绑定
- 配置热重载（ASGI Proxy 模式）
- WebSocket 统一连接管理（订阅模型 `domain:topic`）
- 认证 + 频率限制 + 安全中间件

**前端**（React + Vite）：
- shadcn/ui 组件库
- i18n 支持（zh/en/ja/ko）
- Electron 桌面应用支持

### 4.9 LLM 模型系统

**路径**: `src/llm_models/`

| 组件 | 职责 |
|------|------|
| LLMOrchestrator (`utils_model.py`) | LLM 请求核心调度器，负载均衡 |
| AdapterClient (`model_client/adapter_base.py`) | Provider 适配器统一骨架 |
| OpenAIClient | OpenAI 兼容客户端 |
| GeminiClient | Google Gemini 客户端 |
| PluginClient | 插件提供的 LLM Provider 客户端 |
| exceptions.py | 异常体系（NetworkConnectionError/ReqAbortException/...） |

**负载均衡**：`model_usage` 字典记录每个模型的 (total_tokens, penalty)，用于动态选择模型。

### 4.10 公共模块

**路径**: `src/common/`

| 模块 | 职责 |
|------|------|
| `database/` | SQLite 数据库管理（WAL 模式，36 个版本迁移） |
| `i18n/` | 国际化管理（ContextVar 协程级隔离） |
| `logger.py` | structlog + rich 日志系统 |
| `message_server/` | FastAPI 消息服务器 |
| `message_repository.py` | 消息数据库查询层 |
| `service_registry.py` | 极简服务注册表 |
| `shutdown.py` | 优雅关闭 |
| `data_models/` | 15+ 数据模型文件 |
| `utils/` | 工具函数集合 |

### 4.11 其他模块

| 模块 | 路径 | 职责 |
|------|------|------|
| 表情包系统 | `src/emoji_system/` | 表情包管理与缓存 |
| 学习器 | `src/learners/` | 行为学习/表情学习/黑话学习 |
| 提示词管理 | `src/prompt/` | 提示词模板加载与渲染 |
| 任务管理 | `src/manager/` | 异步任务管理器 |
| 智能体配置 | `agents/` | 12+ 角色的 Markdown 配置 |
| 提示词模板 | `prompts/` | 三语提示词模板（.prompt 文件） |

---

## 5. 关键类与函数说明

### 5.1 系统入口

#### MainSystem

**文件**: [src/main.py](file:///c:/Users/lmq/.trae-cn/worktrees/MaiBot/docs-code-wiki-generation-DL8IFc/src/main.py)

系统初始化与任务调度的核心类。

```python
class MainSystem:
    async def initialize(self) -> None:
        """初始化系统组件：
        - 注册全局 Protocol 端口
        - 启动插件运行时
        - 启动 A_memorix 记忆系统
        - 加载提示词
        - 初始化聊天管理器
        - 启动 WebUI 服务器
        - 启动智能体交互调度器
        """

    async def schedule_tasks(self) -> None:
        """调度定时任务：
        - 注册消息处理器
        - 启动消息服务器
        - 启动表情/图片缓存清理
        """
```

#### bot.py 入口

**文件**: [bot.py](file:///c:/Users/lmq/.trae-cn/worktrees/MaiBot/docs-code-wiki-generation-DL8IFc/bot.py)

采用 **Runner + Worker 双进程架构**：
- Runner 进程：守护进程，负责启动和监控 Worker 进程，处理重启（退出码 42）
- Worker 进程：实际执行 MainSystem 逻辑

### 5.2 智能体系统关键类

#### AutonomousAgent

**文件**: [agent.py](file:///c:/Users/lmq/.trae-cn/worktrees/MaiBot/docs-code-wiki-generation-DL8IFc/src/maisaka/agent_autonomy/agent.py)

自主智能体的门面类，持有：
- `ThinkingOrgan` — 思维管道
- `EmotionManager` — 情绪管理
- `InnerNeedEngine` — 欲望引擎
- `BehaviorIntentEngine` — 行为意图引擎
- `InnerWorld` — 内心世界门面

#### AgentConfigRegistry

**文件**: [registry.py](file:///c:/Users/lmq/.trae-cn/worktrees/MaiBot/docs-code-wiki-generation-DL8IFc/src/maisaka/agent/registry.py)

智能体配置注册表（全局单例），从 `agents/` 目录加载所有智能体配置。

#### AgentRouter

**文件**: [router.py](file:///c:/Users/lmq/.trae-cn/worktrees/MaiBot/docs-code-wiki-generation-DL8IFc/src/maisaka/agent/router.py)

智能体路由层，管理会话与智能体的绑定关系（支持多智能体共居）。

路由优先级：会话绑定主发言 → 群配置绑定 → 默认智能体

### 5.3 记忆系统关键类

#### AMemorixHostService

**文件**: [host_service.py](file:///c:/Users/lmq/.trae-cn/worktrees/MaiBot/docs-code-wiki-generation-DL8IFc/src/A_memorix/host_service.py)

A_memorix 唯一对外服务入口，通过 `invoke(component_name, args)` 统一分发调用。

```python
# 调用示例
result = a_memorix_host_service.invoke("search_memory", {"query": "...", "limit": 5})
result = a_memorix_host_service.invoke("observe", {"text": "...", "valence": "positive"})
```

#### MemoryField

**文件**: [memory_field.py](file:///c:/Users/lmq/.trae-cn/worktrees/MaiBot/docs-code-wiki-generation-DL8IFc/src/A_memorix/core/connectionist/memory_field.py)

连接主义记忆系统的核心运行时，组合 8 个子组件：

```python
class MemoryField:
    async def observe(text, valence, ...) -> None:
        """观察文本 → 提取概念 → 评估显著性 → 创建 Trace"""

    async def recall(seeds, agent_id, min_weight, max_results) -> list[RecallItem]:
        """通过激活扩散算法回忆相关概念"""

    async def derive_profile(subject, observer, now) -> ProfileView:
        """实时推导画像"""

    async def reflect(subject, agent_id) -> dict:
        """反思，揭示不同内心声音下的矛盾"""

    async def granular_decay(elapsed_hours) -> None:
        """粒度退化，按智能体性格调整衰减速度"""
```

#### MemoryPersonalityV2

智能体记忆性格参数：
- `decay_rate` — 衰减率 [0.1, 5.0]
- `emotional_sensitivity` — 情感敏感度 [0.1, 3.0]
- `association_depth` — 联想深度 [1, 4]
- `reinforcement_boost` — 强化增益 [0.1, 0.5]
- `attention_tags` — 关注标签
- `positive_affinity` / `negative_affinity` — 正/负向亲和度
- `curiosity` — 好奇心 [0.5, 2.0]

### 5.4 消息系统关键类

#### ChatBot

**文件**: [bot.py](file:///c:/Users/lmq/.trae-cn/worktrees/MaiBot/docs-code-wiki-generation-DL8IFc/src/chat/message_receive/bot.py)

消息入口，全局单例 `chat_bot`。

```python
class ChatBot:
    async def message_process(self, message_data: dict) -> None:
        """消息处理主入口（适配器调用）"""

    async def receive_message(self, message: SessionMessage) -> None:
        """接收消息并路由到 HeartFlow"""

    async def echo_message_process(self, message_data: dict) -> None:
        """消息 ID 回显处理"""
```

#### SessionMessage

**文件**: [message.py](file:///c:/Users/lmq/.trae-cn/worktrees/MaiBot/docs-code-wiki-generation-DL8IFc/src/chat/message_receive/message.py)

内部消息核心数据模型，继承 `MaiMessage`。

关键字段：`message_id`, `timestamp`, `platform`, `session_id`, `is_mentioned`, `is_at`, `is_notify`, `processed_plain_text`, `raw_message`

关键方法：
- `process(enable_heavy_media_analysis, enable_voice_transcription)` — 并行处理所有组件
- `from_maim_message(message)` / `to_maim_message()` — 与 maim_message 互转
- `to_db_instance()` / `from_db_instance(record)` — 数据库模型互转

#### BotChatSession

**文件**: [session_types.py](file:///c:/Users/lmq/.trae-cn/worktrees/MaiBot/docs-code-wiki-generation-DL8IFc/src/chat/message_receive/session_types.py)

会话核心数据模型，继承 `MaiChatSession`。

关键字段：`session_id`, `platform`, `group_id`, `user_id`, `agent_id`, `is_group_session`, `account_id`, `scope`

#### SessionUtils.calculate_session_id

**文件**: [utils_session.py](file:///c:/Users/lmq/.trae-cn/worktrees/MaiBot/docs-code-wiki-generation-DL8IFc/src/common/utils/utils_session.py)

会话 ID 计算函数（MD5 哈希）：

```python
# 群聊：components = [platform, *route_components, group_id]
# 私聊：components = [platform, *route_components, user_id, "private"]
# route_components = [f"account:{account_id}", f"scope:{scope}"]
session_id = hashlib.md5("_".join(components).encode()).hexdigest()
```

> **规范**：除聊天流创建/注册链路外，业务模块不应自行调用此函数，应通过 `SessionRepository` Protocol 查询。

### 5.5 服务层关键类

#### SendServiceMessagePortV2

**文件**: [send_service.py](file:///c:/Users/lmq/.trae-cn/worktrees/MaiBot/docs-code-wiki-generation-DL8IFc/src/services/send_service.py)

直接实现 MessagePortV2 Protocol，提供唯一的 `send_message()` 方法：

```python
async def send_message(
    self,
    session_id: str,
    message: MessageSequence,
    *,
    reply_to_id: str = "",
    agent_id: str = "",
    source: str = "core",
) -> SendMessageResult:
```

#### LLMOrchestrator

**文件**: [utils_model.py](file:///c:/Users/lmq/.trae-cn/worktrees/MaiBot/docs-code-wiki-generation-DL8IFc/src/llm_models/utils_model.py)

LLM 请求核心调度器：

```python
class LLMOrchestrator:
    def __init__(self, task_name, request_type, session_id=""):
        """初始化 LLM 调度器"""

    async def generate_response(self, messages, ...) -> APIResponse:
        """文本生成"""

    async def generate_response_for_image(self, ...) -> APIResponse:
        """图像理解"""

    async def get_embedding(self, text) -> list[float]:
        """文本嵌入"""
```

### 5.6 配置系统关键类

#### ConfigManager

**文件**: [config.py](file:///c:/Users/lmq/.trae-cn/worktrees/MaiBot/docs-code-wiki-generation-DL8IFc/src/config/config.py)

```python
class ConfigManager:
    async def initialize(self) -> None:
        """加载 bot_config.toml 和 model_config.toml"""

    async def start_file_watcher(self) -> None:
        """启动文件监视器"""

    def register_reload_callback(self, callback) -> None:
        """注册配置变更回调"""

    async def stop_file_watcher(self) -> None:
        """停止文件监视器"""
```

#### Config（总配置）

包含 25+ 配置段：`bot`, `personality`, `chat`, `experimental`, `visual`, `expression`, `jargon`, `a_memorix`, `message_receive`, `voice`, `emoji`, `keyword_reaction`, `agent`, `agent_autonomy`, `agent_interaction`, `plugin_runtime`, `webui`, `database`, `mcp`, ...

---

## 6. 依赖关系

### 6.1 模块间依赖

```
bot.py
  └─ src/main.py (MainSystem)
       ├─ src/config/ (配置管理)
       ├─ src/core/adapters/ (Protocol 适配器)
       │    └─ src/chat/message_receive/ (ChatManager)
       ├─ src/plugin_runtime/ (插件运行时)
       ├─ src/A_memorix/ (记忆系统)
       ├─ src/prompt/ (提示词管理)
       ├─ src/emoji_system/ (表情包)
       ├─ src/webui/ (WebUI 服务器)
       ├─ src/services/ (业务服务)
       └─ src/maisaka/ (智能体系统)
            ├─ agent_autonomy/ (自主性架构)
            ├─ chat_loop_service.py (对话循环)
            └─ runtime.py (会话运行时)
                 └─ src/chat/heart_flow/ (HeartFlow)
```

### 6.2 核心隔离原则

```
核心层 (src/core/) 
  ├─ 只依赖 Protocol 接口
  ├─ 不导入 chat_manager / send_service / HeartFlow 具体实现
  └─ 不导入 A_memorix 内部模块

适配器层 (src/core/adapters/)
  ├─ 唯一允许导入组件具体类的地方
  └─ 实现 Protocol 接口

A_memorix (src/A_memorix/)
  ├─ core/ 内部模块禁止导入 MaiBot 服务层
  ├─ 通过 AMemorixServicePorts 容器获取外部能力
  └─ host_service 是唯一允许导入 MaiBot 服务层的模块
```

### 6.3 外部依赖（pyproject.toml）

**核心依赖**：

| 依赖 | 用途 |
|------|------|
| `fastapi` + `uvicorn` | WebUI 和消息服务器 |
| `sqlalchemy` + `sqlmodel` | 数据库 ORM |
| `faiss-cpu` | 向量检索 |
| `numpy` + `scipy` | 数值计算 + 稀疏矩阵 |
| `openai` | OpenAI 兼容 LLM 客户端 |
| `google-genai` | Google Gemini 客户端 |
| `jieba` | 中文分词 |
| `pypinyin` | 拼音转换 |
| `pydantic` | 数据模型验证 |
| `structlog` + `rich` | 结构化日志 |
| `aiohttp` + `httpx[socks]` | 异步 HTTP 客户端 |
| `pillow` | 图片处理 |
| `playwright` | 浏览器自动化 |
| `tomlkit` | TOML 配置解析 |
| `watchfiles` | 文件监视 |
| `maim-message` | 消息协议库 |
| `maibot-dashboard` | WebUI 前端包 |
| `maibot-plugin-sdk` | 插件 SDK |
| `mcp` | Model Context Protocol |
| `rapidfuzz` | 模糊字符串匹配 |
| `ahocorasick-rs` | 多模式字符串匹配 |
| `pandas` + `pyarrow` | 数据分析 |
| `json-repair` | JSON 修复 |
| `msgpack` | 二进制序列化（插件 IPC） |

**开发依赖**：`pytest`, `pytest-asyncio`, `ruff`, `zstandard`

### 6.4 Python 版本要求

`requires-python = ">=3.12"`（目标运行环境 Python 3.14.6）

---

## 7. 项目运行方式

### 7.1 Docker 部署（推荐）

**docker-compose.yml** 包含三个服务：

| 服务 | 容器名 | 端口 | 说明 |
|------|--------|------|------|
| core | maim-bot-core | 18001:8001 | MaiBot 主程序 |
| napcat | maim-bot-napcat | 6099:6099 | NapCat QQ 协议实现 |
| sqlite-web | sqlite-web | 8120:8080 | SQLite Web 管理界面 |

**启动命令**：

```bash
docker-compose up -d
```

**关键环境变量**：

| 变量 | 说明 |
|------|------|
| `TZ` | 时区（Asia/Shanghai） |
| `EULA_AGREE` | EULA 同意哈希 |
| `PRIVACY_AGREE` | 隐私条款同意哈希 |
| `MAIBOT_LOCALE` | 语言设置（zh-CN/en-US/ja-JP） |
| `MAIBOT_WORKER_PROCESS` | Worker 进程标记（内部使用） |
| `WEBUI_HOST` | WebUI 监听地址 |

**数据卷**：
- `./docker-config/mmc` — 配置文件
- `./data/MaiMBot` — 数据目录
- `./src` — 源码（宿主机修改即时生效）
- `./prompts` — 提示词
- `./agents` — 智能体配置
- `site-packages` — Python 包持久化
- `hf-cache` — HuggingFace 模型缓存

### 7.2 本地运行

**依赖安装**（使用 uv）：

```bash
uv sync
```

**启动**：

```bash
python bot.py
```

**首次启动**：
1. 程序会要求确认 EULA 和隐私条款
2. 需要配置 `bot_config.toml` 和 `model_config.toml`
3. WebUI 默认端口 8001（Docker 映射为 18001）

### 7.3 WebUI 开发

**后端**：随主程序启动，端口 7999（开发模式）或 8001（生产）

**前端**（dashboard 目录）：

```bash
cd dashboard
bun install    # 或 npm install
bun run dev    # 开发服务器
bun run build  # 构建生产版本
```

### 7.4 配置文件

| 文件 | 说明 |
|------|------|
| `config/bot_config.toml` | 主配置（机器人信息、聊天、记忆、插件等） |
| `config/model_config.toml` | 模型配置（API Provider、模型、任务映射） |
| `agents/*.md` | 智能体配置（Markdown Frontmatter 格式） |
| `prompts/{locale}/*.prompt` | 提示词模板 |

**配置版本**：
- bot_config: 8.23.0
- model_config: 1.17.6

### 7.5 测试

```bash
# 运行所有测试
uv run pytest

# 运行特定测试
uv run pytest pytests/webui/

# 代码检查
uv run ruff check src/
```

### 7.6 进程架构

```
Runner 进程 (bot.py)
  └─ Worker 进程 (MAIBOT_WORKER_PROCESS=1)
       ├─ MainSystem
       │    ├─ 消息服务器 (FastAPI + uvicorn)
       │    ├─ WebUI 服务器 (独立线程)
       │    ├─ 插件运行时 (子进程)
       │    │    ├─ 内置插件 Supervisor
       │    │    └─ 第三方插件 Supervisor
       │    ├─ A_memorix 记忆系统
       │    ├─ HeartFlow 运行时管理
       │    └─ 异步任务管理器
       └─ 信号处理 (SIGINT → 优雅关闭)
```

**重启机制**：Worker 退出码 42 → Runner 重启 Worker 进程

---

## 8. 开发规范与架构原则

### 8.1 智能体自主性架构原则

1. **智能体决策权原则**：外部系统不应替智能体做业务决策，消息是否需要回复由智能体自身规则引擎决定
2. **通知消息处理原则**：通知消息应到达智能体，由智能体自主分类处理
3. **规则引擎优先原则**：待命状态的环境感知必须是纯规则计算，不调用 LLM
4. **组件兼容核心原则**：核心定义接口契约，组件实现契约，核心不依赖组件具体实现
5. **记忆是连接而非对象原则**：记忆是概念之间的激活模式，不是带标签的标本
6. **主智能体-子智能体协作原则**：主智能体是"哲学守护者"，子智能体是"代码专家"

### 8.2 代码规范

- **import 规范**：标准库/第三方库在前（`from` 在前，`import` 在后），本地模块在后（相对导入在前，绝对导入在后）
- **注释规范**：保持良好注释，重构时保留原有注释
- **类型注解**：复杂函数和参数较多的函数必须添加类型注解
- **变量规范**：确定类型时不用 `or` fallback
- **类属性**：减少 `getattr`/`setattr`，优先使用类属性直接访问
- **debug 规范**：精准定位问题核心，不用兜底掩盖错误

### 8.3 运行环境规范

- 优先使用 `uv` 管理依赖
- 依赖项以 `pyproject.toml` 为准，同步更新 `requirements.txt`
- 配置文件修改只改模板，新增版本号，不改动 `legacy_migration`
- 提示词修改需三语同步（zh-CN / en-US / ja-JP）

### 8.4 WebUI 规范

- 显示聊天流信息优先显示实际名称（群名称或"xxx的私聊"），而非 session_id
- 开发服务固定起到 7999 端口
- 修改完不自动 `npm run build`，手动执行

### 8.5 会话 ID 规范

除聊天流创建/注册链路外，业务模块不应自行调用 `SessionUtils.calculate_session_id`，应通过 `SessionRepository` Protocol 接口查询已存在的真实聊天流。

### 8.6 架构债务追踪

重大架构变更完成后，应同步更新 `AGENTS.md` 和 `tasks.md` 中的相关描述，确保规则性文件与代码实际状态一致。

---

## 附录

### A. 智能体配置

智能体配置位于 `agents/` 目录，采用 Markdown Frontmatter 格式。当前包含 12 个角色：

| 智能体 | 说明 |
|--------|------|
| silver_wolf | 银狼（默认主智能体） |
| tighnari | 提纳里 |
| bronya | 布洛妮娅 |
| columbina | 哥伦比娅 |
| elysia | 爱莉希雅 |
| fu_hua | 符华 |
| himeko | 姬子 |
| kiana | 琪亚娜 |
| mei | 芽衣 |
| seele | 希儿 |
| signora | 夫人 |
| veliona | 维罗娜 |
| welt | 瓦尔特 |

### B. 提示词模板

提示词位于 `prompts/{locale}/` 目录，支持三语：

| 模板 | 用途 |
|------|------|
| `maisaka_chat.prompt` | 主对话提示词 |
| `maisaka_chat_focus.prompt` | 专注模式对话提示词 |
| `maisaka_replyer.prompt` | 回复生成器提示词 |
| `default_expressor.prompt` | 表情选择 |
| `emoji_selection.prompt` | 表情包选择 |
| `learn_behavior.prompt` | 行为学习 |
| `learn_jargon.prompt` | 黑话学习 |
| `learn_style.prompt` | 风格学习 |
| `image_description.prompt` | 图片描述 |

### C. 关键架构决策记录

| 决策 | 状态 | 说明 |
|------|------|------|
| 微内核 + Protocol 接口 | ✅ 完成 | 13 个 Protocol，核心零组件依赖 |
| Agent-owns-Thinking | ✅ 完成 | 每个智能体独立 ThinkingOrgan |
| 管家系统 | ✅ 完成 | 三层过滤 + 插话协调 + 提醒流 |
| MessagePortV2 统一发送 | ✅ 完成 | 7 方法 → 1 方法，dict 序列化消除 |
| ChatManager 单例拆分 | ✅ 完成 | 604→143 行，6 个子模块 |
| A_memorix 核心隔离 | ✅ 完成 | core/ 零违规导入 |
| 记忆范式迁移 | 🔄 进行中 | DUAL_WRITE 阶段，第 5-6 批待推进 |
| SDKMemoryKernel 瘦身 | ✅ 完成 | 9650→2911 行 |

---

> **文档说明**：本文档基于 MaiBot v1.0.11 源码分析生成，涵盖项目架构、模块职责、关键类说明、依赖关系和运行方式。如有架构变更，请同步更新此文档。
