# 迁移到 dsh 内核：飞书优先新建接入层

**Status**: proposed（方向已拍板，待形态验证）
**日期**: 2026-11-21

## 背景

三件事同时发生，把「继续自研内核」这个选项挤到了角落。

**一、QQ 第三方协议端在收缩。** NapCat 等框架已下架，本机还能跑是因为手上留着一个镜像（容器 `maim-bot-core` 里那个）。这不是可持续的基础设施：镜像哪天出问题，整个系统的接入就断了。

**二、dsh 的生态规模远超预期。** `dsh-plugin` 这个 GitHub topic 下有 **33,833 个公开仓库、22.9k followers**（2026-11-21 实测）。社区里已有的东西直接覆盖我们要做的事：

| 插件 | 与我们的关系 |
|---|---|
| `JohnXu22786/context-pruner` | 会话上下文整理：修剪过期/重复/失败/过大的上下文省 token——几乎是我们 `token_budget` 的完整替代 |
| `dsh-session-sync` | 跨设备会话同步，专用 git 镜像 + 追加式冲突裁决 |
| `bpc-oss/dsh-routed-subagent` | 从任意 session 挂任意 preset 跑一次性 subagent |
| `bpc-oss/dsh-fork-to-preset` | 把 session fork 到另一个 agent preset，继承已完成回合 |
| `zjuatri/dsh-feishu-plugin` | 飞书接入（上游） |
| `FrederickWilhelmChen/dsh-superagent-work-context` | 飞书跨群工作上下文 + 提醒（上面那个的派生） |

**三、自研内核的结构债已经量过。** 不是感觉，是 11 个具体位置（见下）。

## 决策

### 1. 内核迁移到 dsh，以 bundle 形式二次开发

形态照 `D:\Users\lmq\dsh-superagent`：`package.json` 声明 `dsh.bundle.patch`，用 `cordis.patch.yml` 的 `insert:` 挂插件，**不改 dsh 内核**。那个实例的规模是 92 个 TS 文件 / 847 KB / 两个生产依赖——证明这条路的体量可控。

### 2. 飞书是优先接入通道

不是因为「多一个渠道」，是因为它在技术上比第三方 QQ 协议端强：

| | QQ（第三方协议端） | 飞书 |
|---|---|---|
| 接口性质 | 模拟客户端行为 | 官方开放 API |
| 长期可用 | 已大规模下架，靠镜像 | 不会下架 |
| 消息能力 | 受限 | 富文本、消息卡片、交互组件、文件、群管理 |
| 生态 | 要自己写 | 社区已有插件 |

「飞书常被用于办公」是场景标签，不是技术判断——按能力选，飞书优先。

### 3. 飞书接入新做一套，不做 QQ 语义的映射

按飞书原生模型设计（群、话题、卡片、交互事件），**但保留角色关系的语义**。

理由：角色关系是 MaiBot 的资产（AGENTS.md §十二：人的本质是一切社会关系的总和），而消息载体不该限制它。映射式迁移会把 QQ 的能力边界（纯文本流、无交互回执）焊进飞书侧，等于用旧容器装新能力。

### 4. NapCat 保留，但降级为独立插件

镜像还能用就继续用，做成一个与飞书对等的接入插件。接入层坏了只影响一个插件，不牵连内核。

## 为什么不是继续自研

### 缓存命中率这个理由已经不成立

2026-10 那次切过一刀之后：`memory_flow_service` 的中位首分歧 163 → 408 token，命中上限 37.8% → 93.8%，**主对话现在 88%**。

所以「自研做不到 dsh 那么高的缓存利用率」对主对话**已经不对**。换内核的动机不是命中率，是下面两件事。

### 结构债是真实的，但根子在一个「位置」

请求体现在没有「从状态派生」的位置——每轮现搭，而「这轮与上轮是什么关系」从不被记录，只能事后用请求快照反推（`logs/maisaka_prompt/*.json`）。

具体破坏前缀稳定性的 11 处（完整清单见 `.shared/research/2026-11/maibot_context_current_state.md`）：

| # | 位置 | 什么在变 |
|---|---|---|
| P1 | `src/maisaka/agent_autonomy/prompt_builder.py:148` | 模板第 6 行 `{agent_interaction_memory}` 查 DB |
| P2 | `src/maisaka/agent_autonomy/prompt_builder.py:144-154` | favor 在第 7 行（ZG-26 开关默认关） |
| P3 | `src/maisaka/agent_autonomy/prompt_builder.py:170` | `{cohabitant_states}` 第 10 行每轮重算 |
| P4 | `src/maisaka/agent_autonomy/thinking_organ.py:161-162` | `[回复风格]` 尾段含 `random.choice` |
| P5 | `src/maisaka/chat_loop_service.py:1035-1043` | 非角色化遗留路径，emotion/relationship 仍在 system |
| P6 | `src/maisaka/chat_loop_service.py:1637` | 摘要头部插入，分歧落 `msg[0]` |
| P7 | `src/maisaka/context/token_budget.py:70` | 越阈值逐轮丢一条头部消息 |
| P8 | `src/maisaka/context/history.py:282-326` | 重排 tool 结果 |
| P9 | `src/maisaka/chat_loop_service.py:1193-1199` | compaction 段替换 |
| P10 | `src/maisaka/visual/message_limiter.py:31-39` | 旧图改内容 |
| P11 | `src/maisaka/chat_loop_service.py:1073-1093` | 跨天时间消息插入（这处做对了） |

现有护栏 `tests/unit/prompt_cache/lcp_probe.py` 只判「首分歧是否落在 system/tools」，**P6-P10 全部漏检**——它们不是首分歧，是整段位移。

dsh 的答案不是逐个修，是取消状态本身：**log IS the state**（`.agents/notes/implemented/architecture/2026-06-11-event-sourced-sessions.md`），状态与日志分叉在结构上不可能。附带铁律 **Model-visible means logged**（`packages/core/session/README.md:106`）。

### 生态和维护

33,833 个仓库意味着大量能力不用自己写；dsh 内核随上游发展，我们只维护 bundle。这两条是现在最稀缺的东西。

## 放弃了什么

1. **自研内核**：上下文组装、`token_budget`、session 管理、工具调用循环、配置分层——全部让位给 dsh。
2. **现在的 88% 命中率会先掉下来**。结构换掉之后前缀关系要重建，短期一定是退步。这是明确付出的代价，不粉饰。
3. **「飞书 + QQ 语义映射」这条低成本路线**。选了新做一套，就要按飞书的能力面重新想一遍交互。
4. **短期稳定性**。迁移期间系统会有相当长一段时间不如现在稳。
5. **一部分领域逻辑要重写**（角色调度那层），不是搬过去就行。

## 保留什么

1. **角色关系的语义**——十三个角色、谁在客厅、谁该回、谁想插话。这是项目灵魂，不随内核走。
2. **A_memorix 不重写**。dsh 有现成范式：`packages/experimental/ptc-runtime-python` 用 **JSON-lines over fd 3** 与 CPython 子进程通信，stdout/stderr 留给程序自己，跨语言常量有镜像测试钉死（`protocol.d.ts` 的 `PROTOCOL_FD = 3`）。它继续做 Python 进程，但形态从「被调用的记忆服务」改成「站在拦截点上的主动参与者」。
3. **NapCat 镜像**——降级为独立插件继续用。
4. **三份测绘报告里的现状分析**，尤其那 11 处分歧点：它们将来是「确认新结构真的解决了老问题」的对照表，不是废纸。

## A_memorix 的形态改变（这条单独说）

现在的定位是「一个被调用的记忆服务」——错了。它要主动发挥作用。

dsh 的 `docs/cookbook/extension-cookbook.md` 给了落点：**hook plugin** 是「拦截点上的普通 Cordis 插件，不需要外部协议」。可拦截的点包括 `tools/pre-execute`、`tools/execute`、`tools/post-execute`、`tools/result`、`ctx.tools.guard()`。

所以它的新形态是：

- 订阅 `session/event`，消息进入时**主动**判断该不该记
- 挂 `tools/pre-execute`，模型动手前**主动**注入相关记忆
- 监听回合边界，在合适时机**主动**发起检索或写入

不是被调用，是站在拦截点上。

## 分四段走，每段单独可验证

### 阶段 0：形态验证（最小代价，最重要）

一个 dsh bundle，只装「一个角色 + 一个假群聊流 + A_memorix 子进程」，验四件事：

1. session 能不能长期不结束（不是靠 fork 续命）
2. 插件能不能拿到多输入源（群聊流，而不是单个 prompt）
3. A_memorix 作为 hook plugin 能否主动注入与记录
4. 一条群消息从入站到出站的完整链路能否闭合

四件里任一不成立，就在阶段 1 之前改方案。

### 阶段 1：飞书接入

按飞书原生模型做接入插件。社区已有 `zjuatri/dsh-feishu-plugin` 可参考。目标是让接入层独立于内核——之后飞书或 QQ 哪个坏，都只影响一个插件。

### 阶段 2：A_memorix 主动化

从「被调用」改成「站在拦截点上」。Python 进程本身不动。

### 阶段 3：角色与群聊调度迁移

十三个角色的存在判定、回应选择、插话时机。工程量最大，也是唯一必须真正重写的部分。

### 阶段 4：旧内核下线

同删 dashboard 的做法：新链路跑稳之后，物理删除旧内核。

## 验证方式

- 阶段 0 的四件事各有可复跑的判据（不是「看起来能跑」）
- 缓存利用率的对照基线是现在主对话的 88%——新结构要么追上并超过，要么给出为什么追不上的解释
- 每一段都要有「这一步之后，P1-P11 里哪几条已经不可能再发生」的对应关系

## 翻案条件

任一条成立就停下来重新评估：

1. **阶段 0 的第 1 条不通过**——dsh 的 session 无法长期不结束。这是唯一的硬阻塞。
2. **飞书接入的权限/审批成本远超预期**（例如需要企业主体、审核周期以月计）。
3. **dsh 的 peer 包版本不稳定**，bundle 跟不上上游节奏，迁移变成另一种自研。
4. 迁移中途发现角色关系语义确实无法在新模型里表达——这要看具体是什么表达不出来，再决定是改设计还是回退。

## 未坐实的事

写这份文档时明确的空白：

1. dsh 的 session 是否原生支持长期不结束——**未验证**，这是阶段 0 的第一件事。
2. `dsh-plugin` topic 的 33,833 个仓库里有大量同名噪声，实际可用插件的比例未统计。
3. NapCat 镜像的可维护性（能否更新、出问题能否修）未确认，这决定阶段 1 的紧迫程度。
4. 社区飞书插件只是搜到，**没有读过源码**，能否直接复用未评估。
5. dsh 的 `v0→v3` 三条格式迁移边只读到摘要级（`march-7th` 的报告里已标注）。

## 相关

- 缓存机制测绘：`.shared/research/2026-11/dsh_prompt_cache_mechanism.md`
- 事件模型测绘：`.shared/research/2026-11/dsh_session_event_model.md`
- 现状测绘：`.shared/research/2026-11/maibot_context_current_state.md`
- 配置系统重写：[2026-11-20-config-rewrite-decision.md](../process/2026-11-20-config-rewrite-decision.md)（本决策若落地，那篇的「Rust 纯引擎」部分需要重新评估——dsh 的配置分层可能已经覆盖它）
- 向 dsh 看齐的路线图：[2026-10-17-dsh-alignment-roadmap.md](../process/2026-10-17-dsh-alignment-roadmap.md)（本决策是那篇的激进版本）
