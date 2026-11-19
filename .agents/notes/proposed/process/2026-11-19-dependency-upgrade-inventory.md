# Agent Note: 依赖升级清单与分批计划

Status: proposed

## Problem

Dependabot 在 `liumiaoqi/MaiBot` 上开着 268 条告警，但其中 209 条（78%）来自本不该被扫描的路径：

| manifest | 条数 | 情况 |
|---|---|---|
| `dashboard/pnpm-lock.yaml` + `package.json` | 96 | 旧前端。compose 默认用 `mingtang/dist`，`dashboard/dist` 只是回退 |
| `scripts/embedding_finetune/uv.lock` | 70 | 独立实验脚本，自带 lock |
| `docs/archive/officeArtWorks/uv.lock` | 43 | 归档目录，按 `docs/AGENTS.md` 的规矩本就该冻结 |
| `uv.lock`（主仓） | 50 | 真正要紧的 |
| `mingtang/pnpm-lock.yaml` | 9 | 当前前端 |

告警数量因此不能作为判断依据。真正要看的是「哪些包落后了、落后多少」，而这份清单此前没有。

另有一处仓库卫生问题：`requirements.txt` 不是依赖清单，是 1775 行、UTF-16 编码的错误日志
（内容是某次 `uv export --no-dev > requirements.txt 2>&1` 失败后的输出）。它已被 `.dockerignore`
排除，但仍留在仓库里，任何按它装依赖的人都会失败。

## Proposal

先砍噪音，再按风险分批升级。当前实际过期：Python 47 个，Node 22 个。

### 第零批：先做净简化（不动代码）

这一批不减一个包、不升一个版本，但它是六批里收益最大的，因为它处理的是「本来就不该存在」的东西。

#### 0.1 砍掉噪音源（209 条）

删 `docs/archive/officeArtWorks/uv.lock`（归档目录不该有 lock），确认 `dashboard/` 与
`scripts/embedding_finetune/` 是否还在维护。这三处合计 209 条，处理完告警从 268 降到 59。

`scripts/embedding_finetune/` 值得单独说明：它是个独立项目，自己的 `pyproject.toml` 写着
`requires-python = ">=3.12,<3.13"`（主项目是 3.14）、描述是「与主项目隔离」。
它有自己的 `uv.lock` 就必然进依赖图，所以那 70 条告警是结构性的，不是配置问题。
要么在 `.github/dependabot.yml` 里排除该路径，要么把它移出主仓。

同时删掉或重新生成 `requirements.txt`。

#### 0.2 按「体积 vs 引用」重新分层

容器里 `site-packages` 的体积分布很不均匀，但体积最大的不等于最该留：

| 包 | 体积 | `src/` 引用 | 判定 |
|---|---|---|---|
| `pyarrow` | 162 MB | **1 个文件**（`A_memorix/scripts/convert_lpmm.py`，一次性转换脚本） | 删 |
| `playwright` | 137 MB | 1 个文件（`services/html_render_service.py`） | **保留，有真实用途** |
| `scipy` + `.libs` | 113 MB | 2 个文件，含核心的 `A_memorix/core/storage/graph_store.py` | **保留，有真实用途** |
| `jieba` | 42 MB | 词表就是它的价值 | 保留 |
| `pandas` | 41 MB | **零引用** | 删或移入 extra |
| `qiskit` + `qiskit-aer` | 68 MB | **主代码零引用**，只在 `scripts/embedding_finetune/trading/` 的 94 个脚本里 | **移入 optional extra** |

**判据：体积不等于必要性，看引用落在哪。**

`qiskit` 这一项不是「删」，因为量子实验有计划接进 MaiBot。正确的位置是可选依赖：

```toml
[project.optional-dependencies]
quantum = ["qiskit>=2.5", "qiskit-aer>=0.17"]
```

默认 `uv sync` 不装，做实验时 `uv sync --extra quantum`。这样计划保留，默认镜像不背 68 MB
加传递依赖。真接进核心之后再挪回主依赖，那是升级决定，不是默认状态。

`pyarrow` 与 `pandas` 若是同一批实验脚本在用，可一并归入 extra 而不是直接删。

另有一处可合并：`httpx` 用在 4 个文件，`aiohttp` 只用 1 个，统一到 httpx 能少一整套 HTTP 客户端栈。

### 第一批：唯一仍在用的自家包

三个「自家包」里只有一个还在用：

| 包 | 当前 | 最新 | 使用方 |
|---|---|---|---|
| `maim-message` | 0.6.8 | 0.7.5 | `plugins/maibot-team.napcat-adapter/maim_message_bridge.py` |

它是 MaiBot 生态的消息协议库，定义标准消息格式并提供基于 WebSocket 的通信机制，
用来解耦核心服务、平台适配器与插件。主仓代码不直接 import，只在 `src/common/logger.py`
里接管它的日志，所以它是通过插件间接使用的。升级时要连带确认 napcat-adapter 那边。

### 第一批附：两个已废弃的自家包，应当移除而不是升级

| 包 | 当前 | 最新 | 状态 |
|---|---|---|---|
| `maibot-plugin-sdk` | 2.13.0 | 2.23.0 | 已废弃，除非做兼容模式否则不用 |
| `maibot-dashboard` | 1.9.2 | 1.10.7 | 已废弃，前端早已换成 `mingtang/` |

两者仍留在 `pyproject.toml`（`maibot-dashboard>=1.5.4`、`maibot-plugin-sdk>=2.7.0`），
`src/` 里对 dashboard 零引用，对 plugin-sdk 只通过 `src/plugin_runtime/local_sdk.py`
走本地路径加载。

**留着它们只会让告警数虚高，而且每次出新版都白算一次落后。** 移除比升级彻底，
但要先确认 `local_sdk.py` 的本地路径回退逻辑在没有这个 pip 包时仍然成立。

### 第二批：安全补丁（零风险，先做）

这些都是解析库或证书包，升级只换数据不改 API：

| 包 | 当前 | 最新 | 说明 |
|---|---|---|---|
| `certifi` | 2026.7.22 | 2026.10.23 | emSign 根证书被攻破，影响 TLS 信任链 |
| `pyasn1` | 0.6.4 | 0.6.5 | quadratic DoS |
| `opentelemetry-api` | 1.45.1 | 1.45.2 | DoS |

### 第三批：Python 补丁级（17 个）

| 包 | 当前 | 最新 | 备注 |
|---|---|---|---|
| `annotated-doc` | 0.0.5 | 0.0.7 |  |
| `click` | 8.5.0 | 8.5.1 |  |
| `google-auth` | 2.62.0 | 2.62.2 |  |
| `json-repair` | 0.64.0 | 0.64.9 |  |
| `msgpack` | 1.2.3 | 1.2.4 |  |
| `numpy` | 2.5.4 | 2.5.5 |  |
| `opentelemetry-api` | 1.45.1 | 1.45.2 | **有 CVE** |
| `pyarrow` | 26.0.0 | 26.0.1 |  |
| `pyasn1` | 0.6.4 | 0.6.5 | **有 CVE** |
| `pydantic` | 2.14.1 | 2.14.3 |  |
| `pydantic-core` | 2.50.1 | 2.50.4 |  |
| `pydantic-settings` | 2.16.0 | 2.16.3 |  |
| `python-multipart` | 0.0.32 | 0.0.34 |  |
| `sqlalchemy` | 2.1.4 | 2.1.9 |  |
| `sqlmodel` | 0.0.48 | 0.0.50 |  |
| `tomlkit` | 0.15.1 | 0.15.2 |  |
| `typing-inspection` | 0.4.4 | 0.4.5 |  |

### 第四批：Python 小版本（24 个）

| 包 | 当前 | 最新 | 备注 |
|---|---|---|---|
| `anyio` | 4.15.1 | 4.16.0 |  |
| `certifi` | 2026.7.22 | 2026.10.23 | **有 CVE** |
| `faiss-cpu` | 1.15.1 | 1.16.0 |  |
| `fastapi` | 0.143.1 | 0.165.0 |  |
| `grpcio` | 1.84.0 | 1.85.3 |  |
| `grpcio-reflection` | 1.84.0 | 1.85.3 |  |
| `httpcore2` | 2.13.1 | 2.16.2 |  |
| `httpx2` | 2.13.1 | 2.16.2 |  |
| `jiter` | 0.17.0 | 0.19.0 |  |
| `maibot-dashboard` | 1.9.2 | 1.10.7 | **自家包** |
| `maibot-plugin-sdk` | 2.13.0 | 2.23.0 | **自家包** |
| `maim-message` | 0.6.8 | 0.7.5 | **自家包** |
| `markdown-it-py` | 4.2.0 | 4.3.0 |  |
| `multidict` | 7.1.0 | 7.2.1 |  |
| `openai` | 3.31.0 | 3.55.1 |  |
| `pandas` | 3.0.6 | 3.1.1 |  |
| `playwright` | 1.64.0 | 1.65.2 |  |
| `pycparser` | 3.11 | 3.12 |  |
| `qiskit` | 2.5.2 | 2.6.2 |  |
| `qiskit-aer` | 0.17.2 | 0.18.4 |  |
| `sse-starlette` | 3.5.0 | 3.7.0 |  |
| `starlette` | 1.8.0 | 1.10.0 |  |
| `stevedore` | 5.9.1 | 5.10.0 |  |
| `tenacity` | 9.1.4 | 9.2.1 |  |

### 第五批：Python 大版本（6 个）

| 包 | 当前 | 最新 | 备注 |
|---|---|---|---|
| `google-genai` | 2.31.0 | 3.6.1 |  |
| `mcp` | 1.30.0 | 2.3.0 | **MCP 协议大版本** |
| `pillow` | 12.3.0 | 13.0.0 | **有 CVE** · **跨大版本** |
| `pyee` | 14.0.0 | 16.1.0 |  |
| `python-dateutil` | 2.9.0.post0 | 4.0.0 | **可疑，跳到 4.0 不合常理** |
| `websockets` | 16.1.1 | 17.4 |  |

### 第六批：Node（22 个）

大版本 4 个：

| 包 | 当前 | 最新 | 类型 | 备注 |
|---|---|---|---|---|
| `@xyflow/react` | 12.12.0 | 13.0.2 | prod |  |
| `i18next` | 26.4.4 | 27.1.5 | prod |  |
| `jsdom` | 30.1.2 | 31.0.1 | dev |  |
| `react-i18next` | 17.0.16 | 18.0.2 | prod |  |

小版本与补丁 18 个：

| 包 | 当前 | 最新 | 类型 | 备注 |
|---|---|---|---|---|
| `@tailwindcss/vite` | 4.3.3 | 4.3.5 | dev |  |
| `@tanstack/react-query` | 5.104.2 | 5.108.0 | prod |  |
| `@tanstack/react-router` | 1.170.44 | 1.170.46 | prod |  |
| `@testing-library/user-event` | 14.6.8 | 14.6.12 | dev |  |
| `@typescript-eslint/parser` | 8.71.2 | 8.73.0 | dev |  |
| `@vitejs/plugin-react` | 6.1.2 | 6.3.0 | dev |  |
| `eslint` | 10.12.0 | 10.15.0 | dev |  |
| `eslint-plugin-security` | 4.2.0 | 4.2.1 | dev |  |
| `i18next-browser-languagedetector` | 8.2.1 | 8.3.1 | prod |  |
| `katex` | 0.19.0 | 0.19.1 | prod | **有 CVE** |
| `lucide-react` | 1.57.0 | 1.75.0 | prod |  |
| `prettier` | 3.9.10 | 3.10.1 | dev |  |
| `react` | 19.3.0 | 19.3.1 | prod |  |
| `react-dom` | 19.3.0 | 19.3.1 | prod |  |
| `tailwindcss` | 4.3.3 | 4.3.5 | prod |  |
| `typescript-eslint` | 8.71.2 | 8.73.0 | dev |  |
| `vite` | 8.3.4 | 8.3.8 | dev |  |
| `vitest` | 5.0.4 | 5.1.1 | dev |  |

## Alternatives considered

### Why not 一次性把所有包升到 latest？

两件事会同时发生：Pillow 从 12.3 跳到 13.0、mcp 从 1.30 跳到 2.3、google-genai 从 2.31 跳到 3.6。
三者互相独立，出问题时无法归因到哪一个。分批的价值不在稳妥，在于**失败时能定位**。

### Why not 只升有 CVE 的 9 个包？

这是本文最初的倾向之一，后来被推翻了两次。

第一版理由是「自家包契约漂移比 CVE 更该先看」。查过实际使用情况后发现，三个自家包里
两个已废弃、一个是通过插件间接使用的，这个理由不成立。

但「只升 CVE」仍然不是最优，因为它漏掉了两种本该处理的东西：一是废弃包留在依赖里，
每次出新版都白算一次落后，应该移除而不是放着；二是 `mcp`、`Pillow`、`google-genai`
这些跨大版本的包，即使当下没有 CVE，落后太多之后升级成本只会更高。

所以正确的切法不是「按有没有 CVE」，而是「按能不能独立验证」——能一条命令验证完的成批做，
需要逐个确认的单独做。

### Why not 让 Dependabot 开自动 PR？

268 条告警里 209 条来自不该扫的目录，自动 PR 会把噪音变成 PR 洪水。
第零批不做完，自动化只会放大混乱。

### Why not 现在就把六批全跑完？

改依赖会动 `uv.lock` 与 `pnpm-lock.yaml`，而 CA 正在同一工作区推进
`.codeartsdoer/specs/webui_contract`。两个 lock 文件同时被两边改动会很难合。
先落清单，等边界清楚再执行。

## Acceptance criteria

第零批完成的标准：Dependabot 打开告警数从 268 降到 59 上下，且 `dashboard/`、
`scripts/embedding_finetune/`、`docs/archive/` 三处不再产生告警；`requirements.txt` 不再是错误日志。

依赖分层完成的标准：`qiskit` 与 `qiskit-aer` 从主依赖移入 `[project.optional-dependencies]`，
默认 `uv sync` 后镜像里 `site-packages` 不含 `qiskit*`，镜像体积相应下降；
`uv sync --extra quantum` 能装上并跑通 `scripts/embedding_finetune/trading/` 里的一个实验脚本。
`pandas` 与 `pyarrow` 若判定为实验专用，同样归入 extra。

废弃包移除的标准：`pyproject.toml` 里不再有 `maibot-dashboard` 与 `maibot-plugin-sdk`，
且移掉之后 `src/plugin_runtime/local_sdk.py` 的本地路径加载仍然工作、
容器重建后 healthy、`plugins/` 两个子仓仍能加载。

每批升级完成的标准：`uv lock` 或 `pnpm install` 成功，容器重建后 healthy，
`mingtang` 的 `pnpm build` 与 `pnpm test` 全绿，告警数按预期下降。

第五批（大版本）的额外标准：每个包单独一次提交，且提交信息写明升了哪个、依据是什么。
`mcp` 放在最后，因为它会改变 MCP 客户端的协议行为。

## Risks

`python-dateutil` 显示 2.9.0.post0 到 4.0.0，不符合该包的正常版本线（2.9.x 是当前线）。
这是 `uv pip list --outdated` 的已知盲区：别名包与同名不同源的包会被混在一起。
这一项必须人工核实，不能照表升。

`Pillow` 跨大版本且带 CVE，是清单里唯一「必须升但升了可能坏」的包。应先扫一遍代码里
用到的 Pillow API（`pyproject.toml` 现在写的是 `pillow>=12.3.0`，升级要一并改约束）。

两个 lock 文件（`uv.lock`、`mingtang/pnpm-lock.yaml`）与 CA 的工作区重叠，这是本文停在
proposed 的直接原因。
