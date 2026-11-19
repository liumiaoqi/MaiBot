# Agent Note: 模型配置按「格式」分层，而不是按「厂商」堆超集

Status: proposed

## Problem

接入不同厂商、不同模态的模型时，MaiBot 的配置层难以配合。三处证据：

`APIProvider`（`src/config/model_configs.py:111`）有 18 个字段，其中相当一部分只有某一家用得上：
`organization` 与 `project` 是 OpenAI 官方的，`auth_query_name` 是 Gemini 把 key 放 query 时用的，
`reasoning_parse_mode` 与 `tool_argument_parse_mode` 是各家推理与工具调用格式差异的补丁。
这是把「各家的差异」摊进一个超集类的做法。

`client_type`（同文件 163 行）声明为裸 `str`，文档字符串写「可选: openai/google」，类型上没有任何约束。
它带着 `json_schema_extra={"x-widget": "select"}`，说明前端是按 schema 渲染下拉的，
但裸 `str` 生成的 schema 没有 `enum`，下拉没有选项来源。`category`（482 行）同样是裸 `str`。

同文件 84 行定义了 `OpenAICompatibleAuthType(str, Enum)` 与 `ReasoningParseMode(str, Enum)`，
但 `auth_type`、`reasoning_parse_mode` 两个字段仍声明为 `str`。枚举写了，字段没用上。

把这三条放在一起看，问题不在前端。前端拿不到「该显示哪些字段、每个字段有哪些取值」的信号，
是因为后端 schema 没有把这些信息暴露出去。前端只能写死一份，于是后端每加一个 `client_type`，
前端就漏一个。

真正的结构问题在第三层：`client_type` 分的是「厂商」（openai / gemini），不是「协议格式」。
每接一家新厂商就要写一个新的 client 实现，这是「不同厂商的模型很难配合」的根因。

## Proposal

分三层，规模递增，可以分阶段独立落地。

第一层，补类型约束。把 `client_type` 改成 `Literal["openai", "gemini"]` 或一个 `str, Enum`，
`category` 同样处理，把已经定义但没接入的枚举挂到字段上。Pydantic 生成的 JSON Schema 会自带
`enum` 列表，现有的 `x-widget: select` 立刻有选项。这一层不动任何运行时逻辑。

第二层，把 Provider 的接入差异下沉。`APIProvider` 只保留公共字段（name / base_url / api_key /
timeout / retry 组），按 `client_type` 挂不同的 Pydantic 子模型，各自声明只属于它的字段。
前端可以按类型动态渲染，选 OpenAI 就只显示 organization / project，选 Gemini 才显示 auth_query_name。

第三层，把 `client_type` 换成 `api_format`。取值从「厂商」变成「协议」：
`openai_chat` / `openai_responses` / `anthropic_messages` / `gemini`。
再配一张「厂商 → 格式」的数据表，新厂商只要兼容某一种格式就零代码接入，
而不是每接一家写一个 client。

三层的借鉴来源是分开的。第一层与第二层借 dsh 的做法：`dsh-llm` 只定义抽象，
`dsh-llm-deepseek`、`dsh-llm-pi-ai` 各自实现，每个 provider 用自己的 schema 声明 Config，
差异被压进各自的 schema 而不是一个超集。第三层借 cc-switch 的做法：它做
Anthropic Messages、OpenAI Chat Completions、OpenAI Responses 三者互转，
厂商差异被格式层吃掉；它的 90 多个 provider 预设也是数据，不是代码。

一致性上有一点值得注意：`ModelInfo.capabilities`（ZG-12）已经在用「标签集声明能力」，
和 dsh 的 `resolve_by_capability` 是同一套心智。第三层的 `api_format` 应该沿用这个形状，
不要再造一套「厂商枚举」。

## Alternatives considered

### Why not 只改前端，把选项写死？

那样后端每加一个枚举值，前端就要跟着发一次版，而且两边一旦不同步就是静默错配：
配置里写了 `client_type = "xxx"`，前端下拉里没有，用户改不动，系统还照跑。
把选项放在 schema 里，只有一处真源。

### Why not 直接做第三层，跳过前两层？

第三层动的是核心词汇，`client_type` 一旦改成语义不同的 `api_format`，
所有现存配置、快照、测试夹具都要迁移。在没有类型约束的前提下做这个迁移，
等于在一个连取值集合都没定义清楚的字段上做语义变更。前两层是它的前置条件。

### Why not 引入 pi-ai 那样的外部模型数据源？

pi-ai 的数据解决的是「有哪些模型、什么价格、什么能力」，不解决「这家厂商的接口长什么样」。
MaiBot 需要的是后者。两者的边界不同，混在一起会让模型清单的维护权也一起交出去。

### Why not 现在动手？

CA 侧正在推进 `.codeartsdoer/specs/webui_contract`（WebUI 契约层），范围与本文前两层直接相邻。
那份工作管的是前端一侧：`ApiClient` 的入参出参与异常、`config-api.ts` 的缓存契约、
试点域手写类型的真实形状、生成物校验，以及门禁对新增文件的覆盖边界。

本文前两层的验收标准都要求前端按 schema 渲染，而「schema 怎么到前端、类型怎么生成」
正落在它的范围内。在两边把 schema 形状对齐之前动手，前端生成物大概率要返工。
先把结论落下来，等边界对齐后再决定从哪一层开始。

## Acceptance criteria

第一层完成的标准：`client_type` 与 `category` 的类型是封闭集合，导出的 JSON Schema 里带 `enum`，
前端 select 的选项从 schema 读取，不再有本地写死的副本。

第二层完成的标准：`APIProvider` 的字段按类型分组，前端渲染时只显示当前类型相关的字段，
且不相关的字段在 schema 里对该类型不可见。

第三层完成的标准：新增一个厂商只需要在「厂商 → 格式」表里加一行，不写新的 client 实现，
就能完成配置、请求、响应解析全链路。

## Risks

与 `.codeartsdoer/specs/webui_contract` 的重叠在**前两层**，不是第三层。那两份工作的分工应当写成：
本文负责「后端 schema 暴露什么」（`enum` 取值集、按类型的子模型形状），
webui_contract 负责「前端怎么取、怎么生成类型」。边界本身清楚，但如果两边各自先动 schema，
前端生成物会先按旧形状定型，之后返工。

因此动手前要做一件事：把本文第一层将要定下的 `client_type` 与 `category` 取值集合，
先交给 webui_contract 那边确认，再落代码。取值集合一旦定下就是两边共同的前置。

第三层虽然不涉及前端，但它会改变 `client_type` 的语义，同样会经 schema 传到前端。
所以三层都不能在边界对齐之前启动。

第一层虽然小，但它是破坏性的：任何配置里写了不在集合内的 `client_type`，升级后会立刻校验失败。
现有配置里到底有哪些取值，需要先扫一遍再定集合，不能照着文档字符串写。

第二层拆子模型会让 `APIProvider` 的序列化形状变化，已有的配置迁移与快照反序列化都要一并处理。
