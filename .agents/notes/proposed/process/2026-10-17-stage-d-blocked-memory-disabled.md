# Agent Note: 轨二阶段 D 的前置 —— 记忆子系统当前是关闭的（含开启清单）

Status: proposed

## Problem

阶段 D（让 `relations.confidence` 从"恒 1.0"变成"会学习"）被一个阻塞了多轮的问题卡住：**输入端两处已经接好**（件 A 的 0004 真值回路 + 心跳发起者 `29849643b`），但**数据面全是 0**。

2026-10-17 夜间的只读取证链，从"信号在哪"一路挖到"是不是看错库"，结论如下（每一步都有实测）：

1. `episodes` / `sagas` / `fragment_status` / `traces` **全部 0 行**
2. `_episode_generation_loop` **全历史无定义**（`git log -S"def _episode_generation_loop"` = 0 命中；`-S` 的 6 笔全是批量搬迁噪声）⇒ 启动分支不可达 ⇒ **生成线从未启动**（"缺实现"，不是"被删"）
3. 写者在：`NarrativeWeaver`（`-S"INSERT INTO episodes"` 仅 1 笔引入）+ 存储 `EpisodeStore`；**缺的是驾驶者**
4. 最底层的 `traces` 层**是接通的**：`Observer.py:143 → TraceStore.create_trace(:130) → _persist_upsert(:203)`（生产调用点在主链上）
5. 配置 `data/a-memorix`、容器挂载 `E:\Users\lmq\MaiBot\data\MaiMBot -> /MaiMBot/data` ⇒ **此前探的库就是容器那份**（"看错库"排除）
6. 实例**在用**：`MaiBot.db-wal` 4.1 MB @ 13:52、日志写到 14:03 —— 但记忆侧三份 `connectionist.db` 停在 07-13 / 08-02 / 08-03，`metadata.db` 停在 08-21

**根因（一行）**：`docker-config/mmc/bot_config.toml:116-117`

```
[a_memorix.plugin] # 长期记忆系统的总开关
enabled = false    # 是否启用长期记忆系统
```

启动日志**六次**说同一句：`[a_memorix.host_service] A_Memorix 未启用，跳过长期记忆运行时初始化`。

⇒ **今晚所有"测得 0"都由这一行解释**：不是代码不接、不是看错库、不是没人用，是**整块记忆运行时没初始化**。`enabled = false` 出现在可观察的每一份配置（仓库副本、容器活配置、`.bak`、10-16/10-17 备份）⇒ **长期状态**，非今日手滑。

## Decision

**阶段 D 的第一件事不是写代码，是部署决定**：打开长期记忆系统，再谈"学什么"。

开启清单（每一步都可回退）：

1. 改 `docker-config/mmc/bot_config.toml:117` 的 `enabled` 为 `true` —— **只改这一个值**；`config/bot_config.toml` 是副本（容器不读它），别动
2. `docker restart maim-bot-core`
   - **验收第一行**：启动日志里 `A_Memorix 未启用，跳过长期记忆运行时初始化` **必须消失**
3. 盯三个数（本清单的核心预测）
   - `traces` ⇒ **应开始增长**（Observer 在生产）
   - `fragment_status` ⇒ **预计仍 0**（只有 `weave` 写它，而 weave 没有驾驶者）
   - `episodes` / `sagas` ⇒ **预计仍 0**（`_episode_generation_loop` 无定义）
   ⇒ **"打开后 traces 会长、其余不动"这件事本身就是"生成线是真缺口"的实验证明**（今天只有静态证据）
4. 回滚：`enabled = false` + `docker restart`
5. **开之前先备份 `data\MaiMBot\`**（记忆运行时一启动就会碰 `metadata.db`，那是红线对象）
6. ⚠️ **风险**：若 Embedding 走外部 API，开启会产生调用与费用 —— 需先确认

**开启之后**，阶段 D 的顺序恢复为：生成线（补驾驶者）→ 对象产生 → 边表 → 影子模式 → 才谈 confidence。

## Alternatives considered

- **先补驾驶者再说**：拒绝。对象一个都没有，补完只是"给没水的渠装水泵"；而且 `enabled = false` 时连 `traces` 都不产生，"驾驶者补好"无法被任何真实调用验证。
- **改 `config/bot_config.toml`（仓库那份）**：拒绝。容器挂载的是 `docker-config/mmc`，改错地方看起来做了事、实际没生效（今晚"看错地方"族的又一形态）。
- **直接给 `relations.confidence` 赋值**：拒绝。设计阶段已明确——没有信号的调参不是学习。
- **假定 `enabled = false` 是模板默认**：未核。配置被 gitignore、无历史可追；"长期状态"是观察结论，不是"默认值"结论。

## Consequences

- ⚠️ **配置被 gitignore** ⇒ 改它**不会进 git** ⇒ 开了之后要在别处留痕（`.shared/decisions/`），否则未来没人知道"什么时候、为什么开的"。
- ⚠️ **`data/MaiMBot` 会被写入**（记忆运行时）⇒ 备份先行；`metadata.db` 基线 `274411520` / `2026-09-27 16:08:28.199`，开完复报。
- ✅ 开完后，"生成线缺口"从**静态结论**变成**可观测事实**，阶段 D 的下一步才有依据。
- ⚠️ **教训（入方法账）**：**在往下挖代码之前，先问"这个功能现在是不是开着"** —— 查法一行：`docker logs <容器> | Select-String '未启用|skip|disabled'`。这次那行答案在启动日志第一屏，一共出现六次，而我们从代码往下挖了六轮。
