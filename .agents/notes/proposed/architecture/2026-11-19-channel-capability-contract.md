# Agent Note: 通道能力契约 —— 让上层知道当前通道能做什么

Status: proposed

## Problem

QQ 收紧第三方客户端政策，NapCat 道（OneBot11，个人号）随时可能断。而可替代的官方 Bot API
能力是子集：仅 @ 到才可见、没有群与成员列表、主动推送有配额、单条文本约 800 字。

三条通道的差别不是实现不同，是能力不同：

| 能力 | NapCat（现状） | QQ 官方 Bot | 飞书 |
|---|---|---|---|
| 收消息 | 全量 | 仅 @ 到的 | 全量（有权限即可） |
| 群 / 成员列表 | 有 | 没有 | 有 |
| 主动推送 | 无限 | 有配额 | 宽松 |
| 单条文本上限 | 无明确上限 | 约 800 字 | 远超 |
| 事件订阅 | 本地 WS | Webhook（要公网） | 长连接 WS（不要公网） |

`MessagePortV2.send_message()`（`src/core/protocols.py:623`）已经是统一入口，且 `source`
参数里单列了 `proactive`。但上层无从知道当前端口能做什么，换道之后是静默失效而非报错：
官方道把 800 字以后的部分切掉，仍返回成功。

## Proposal

给 `MessagePortV2` 增加一个与 `send_message` 并列的方法，返回能力集：

```python
def capabilities(self) -> PortCapabilities: ...
```

能力集分两槽，因为标签表达不了数值：`tags: frozenset[str]`
（`group_list` / `proactive_push` / `rich_text` / `file_upload`）与数值上限
（`max_text_len`、`push_quota_per_day`，0 表示不可用，-1 表示无配额）。

形状复用 LLM 侧已经确立的模式：`@model_requirement(capabilities=["vision"])` 与
`resolve_by_capability(["vision"])`（ZG-12）本来就在用标签集声明能力，保持同一套心智，
不引入第二套词汇。

`SendMessageResult`（`src/core/types.py`）增加一个降级标记：

```python
degraded: tuple[str, ...] = ()   # 例如 ("truncated",) / ("unsupported:proactive",)
```

现在只有 `success` / `message_id` / `error`。截断属于「成功但有损」，既不报 error，
也不是完整成功。一条被切掉后半的消息如果 `success=True` 且无标记，上层永远不会知道。
协议 docstring 自己写了「`reply_to_id` 找不到时降级为不引用」，那也是降级，现在同样没处记。

降级判断放在调用之前，不靠失败重试。截断类限制没有错误码，靠重试永远发现不了。
上层发消息前读 `max_text_len`，超长就分段或截断并记 `degraded`。

三条通道并列注册，由部署配置选一个，不做自动 failover。能力差太大，自动切换后
用户看到的是「机器人突然只回 @ 了」，比挂掉更让人困惑，排查时还会被当成 bug。
真要切，人工改配置，那是可解释的。

官方道的产品形态先定死再写适配器：只做「被 @ 才说话」与「短文本（必要时分条）」，
不做群列表、不做主动推送、不做富文本。官方道上的 `source="proactive"` 应当被直接拒
并记 `degraded`，而不是悄悄发不出去。

## Alternatives considered

### Why not 新建一个 ChannelCapabilityService？

只有一个消费者（上层发送路径），按本仓「三个调用点才考虑接口」的红线，现在不该建独立服务。
另立服务还会引入第二处「当前用哪个端口」的状态，与 `MessagePortV2` 自身重复。

### Why not 上层按 platform 分支判断？

那会把能力判断散落在业务代码里。加第三个通道时，每一处分支都得改，且没有集中的地方
能回答「当前到底能做什么」。

### Why not 用一维分级（full / limited）？

真实的组合是「能拉群列表但不能主动推送」，一维分级映射不住。

### Why not 自动 failover（NapCat 挂了自动切官方）？

能力差太大。切过去之后行为会突然退化而没有任何提示，用户会以为是故障。
宁可整体不可用（明确），也不要半可用（含糊）。

### Why not 先按 NapCat 的功能全量实现官方道，再砍？

能力决定形态，形态决定适配器接口。反序会写出用不上的代码，砍的时候还会留下半截逻辑。

## Acceptance criteria

先实测，再动手。四项结果决定后面所有实现细节，尤其第三项：

1. 群里不 @ 机器人，能否收到消息
2. 主动推送的实际配额（条 / 天）
3. 800 字上限是硬截断还是报错 —— 截断无声是静默失效，报错有声可重试，两者代码不同
4. 能否拉群成员列表

实测通过后：

- `capabilities()` 在 napcat / qq-official / feishu 三个实现上都有返回
- 发送超长文本后，`SendMessageResult.degraded` 含 `truncated`
- 官方道上 `source="proactive"` 被拒，且 `degraded` 含 `unsupported:proactive`
- NapCat 的现有行为不变

## Risks

能力集一旦公开，上层可能写死对某个标签的依赖。需要在能力契约里明确：标签是「当前通道
此刻具备的能力」，不是长期承诺，用它做降级可以，做功能开关不行。

官方道的配额与文本上限是平台策略，会变。数值上限应当是可配置的，不要在代码里写死。

飞书的场景与现在的 MaiBot 不匹配。它的能力远强于 QQ 官方，但那是工作协作场景，
没有闲聊的土壤，机器人主动发言会显得突兀。飞书这条线更适合做「工作助理」，
而不是「群里的一员」。这一点应当在决定 M7 的优先级之前拍板。
