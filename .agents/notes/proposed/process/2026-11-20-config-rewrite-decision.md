# Agent Note: 配置系统物理重写 —— 删旧、留 schema 真源、Rust 纯引擎

Status: proposed（2026-11-20 lmq 拍板方向：物理删除 + 强制解耦；执行清单待分批实施）

## Problem

旧配置系统已经演进了半年，每次都在旧结构上打补丁，结果**每加一层就多一个真源**。三处硬证据（详见 `../../../.shared/research/2026-11/config_system_cross_discipline_1120.md`）：

1. **三个隐式真源**：组件自治 `declarations/prefer`、智能体 `model_config_override`（只传 `agent_id` 才生效）、**`models` 数组顺序**（`model_registry.py:69-72` → `:270-281` → `:292`，容器内实测：换顺序即换默认模型，`source` 仍是 `default`）。
2. **五处同步**：新增一个开关要同步 `official_configs.py` → `types.py` → `app_config_port.py` → 模板 toml → 部署 toml（实测 `context_identity_enabled` 链路共 6 处）。
3. **唯一的解释器没有接出去**：`get_effective_config` 已返回 `resolved_model` + `param_sources`，**全仓零生产消费**。

Phase 3 的六项收尾（`2026-11-19-phase3-config-decisions.md`）已证明"渐进"收不完：`#2(b)` 要等前端先迁、`#5` 要等 8 类编辑器、`#3` 因组合系统形态未定而暂停。**渐进路线的前提是旧结构能承载新语义，而这个前提不成立。**

## Decision

### 一、物理删除（按目录/文件精确列出）

| 删 | 规模 | 身份 |
|---|---|---|
| `dashboard/` | 445 文件 / 114351 行 | 老前端（2026-10-15 起已冻结，compose 里只是 `mingtang/dist` 的回退） |
| `src/config/config.py` | 1153 | `Config` 单例 + `config_manager` + `global_config` |
| `src/config/config_lifecycle.py` | 517 | 生命周期 |
| `src/config/file_watcher.py` | 264 | 热重载监听 |
| `src/config/config_upgrade_hooks.py` | 929 | 版本迁移钩子 |
| `src/config/config_base.py` | 342 | TOML 读写与 `.bak` 机制 |
| `src/config/model_configs.py` | 840 | **旧 LLM 配置**：`model_task_config` / `APIProvider` 超集 / `client_type` 裸 `str` |
| `src/webui/routers/config.py` 的旧读/旧写 8 个端点 | ~900 | `GET/POST /bot`、`GET/POST /model`、`POST /bot/section/{name}`、`POST /model/section/{name}` |
| `.bak` + `old/` 留档机制 | — | 由 Git（内容摘要式 revision）接管 |

### 二、明确保留（这些**不是**旧系统）

| 留 | 理由 |
|---|---|
| `src/config/official_configs.py`（7940 行 pydantic schema） | **是新的**：Phase 3 的 schema 真源，也是配置目录文档与表单元数据的派生源。删它 = 重写 7940 行 |
| `src/webui/routers/config.py` 的 `/get`、`/mutate`、`/schema/{bot,model,section}` | **已在真机跑通**：扁平条目表、409 `BIZ_STATE_CONFLICT`、`revision 1→2`（`../../../.shared/decisions/phase3_new_config_roadmap.md:207-219`） |
| `role('secret')` 四处脱敏 + presence marker | 与 dsh 同构，且是"整份 replace 会静默删密钥"的唯一防线 |
| `@model_requirement` + `capabilities` + `ModelRegistry` | **是新的**：ZG-12 用来替代 `model_task_config` 的抽象。只删它的两个旧真源（数组顺序、`model_config_override`），不删能力声明 |
| `/prompts*`、`/prompt-generator*` 端点 | prompt 是内容资产，不属于配置系统 |

### 三、新系统的边界（语言即解耦边界）

三段，缺一不可：

**Rust 侧 = 纯配置引擎，无 AI 语义。**

- 输入：JSON Schema（Python 侧 `model_json_schema()` 导出）+ 有序层列表（TOML/JSON）
- 输出：
  ```json
  {
    "values": {"chat.max_context_size": 40},
    "provenance": {"chat.max_context_size": {"layer": "profile", "file": "dev.toml", "overwritten_by": ["overlay-2"]}},
    "warnings": [{"kind": "overridden|shadowed|redundant|unmatched", "key": "...", "detail": "..."}],
    "violations": [{"path": "...", "reason": "..."}],
    "revision": "<content-hash>"
  }
  ```
- 合并语义（与 dsh 对齐）：plain object 递归合并；**其余值含数组整体替换**；`undefined`/缺失不覆盖下层。
- 形态：**一次性进程**（`maibot-config resolve --schema s.json --layer a.toml --layer b.toml`），无状态。**不做常驻、不做文件监听**——何时重算是 Python 侧的决定。
- 不碰：角色、prompt、模型语义、记忆参数、任何 `@model_requirement`。

**Python 侧 = AI 语义配置 + 注入。**

- `official_configs.py` 仍是唯一的 schema 声明处（pydantic），新增开关只改这一处 + 一处消费者。
- AI 语义配置（角色人格、记忆、欲望、prompt 参数）留在 Python，不导出给 Rust。
- 通过引擎拿 `values` + `provenance`，然后注入。

**Rust 引擎不做的三件事**（否则解耦失效）：

1. 不解析 TOML 的语义歧义（只按规范读，不做"善意猜测"）
2. 不自动修复冲突（冲突必须报 `violations`，由 Python 侧决定）
3. 不认识任何业务键名（只认 JSON Schema 的 `$id` 与类型）

### 四、为什么"删干净"优于"并行"

并行（新系统先跑通再删旧的）在这个项目的具体代价是**两个真源共存期**，而两个真源正是本决策要消灭的东西——`/config/bot` 与 `/config/get` 并存已经制造过一次"前端改的地方不是权威源"。删干净让"绕过接缝"在物理上不可能。

代价是：**新引擎上线前，WebUI 配置页不可用**（2026-11-20 确认接受）；期间调参走手工编辑 TOML + 重启容器。

## Consequences

### 执行顺序（每批可独立回滚，回滚靠 git 分支 + 镜像 tag）

**批 0：收敛核心契约的配置接口面（不改行为）**

原计划是「把 `protocols.py:19-20` 的四个旧配置类换成 Protocol 侧自有类型」。**实测不成立**：`ModelConfigPort` 的四个方法仍有 **35 处生产调用**（`get_model_config` 22 · `get_task_config` 6 · `get_model_info` 5 · `get_provider` 2），类型依赖要等批 3 改完这些调用点才可能切断。

本轮实际做的是**砍掉零调用者**（`ModelConfigPort` 从 8 个 `get_*` 减到 6）：

| 删掉 | 依据 |
|---|---|
| `get_all_providers()` | 全仓只有 Protocol 定义与适配器实现，**零调用者（含测试）** |
| `get_models_by_capability()` | 同上。原 docstring 写「供 WebUI 渲染/插件枚举」，实测无消费者——又一个「docstring 承诺但未接线」（§七 缺陷模式 8） |

判据：`rg "get_all_providers|get_models_by_capability"` 只剩 git 历史；两文件 lint 零新增；import 冒烟通过（`ModelConfigPort` 方法表实测为 `get_effective_config` / `get_last_success_time` / `get_model_config` / `get_model_info` / `get_provider` / `get_task_config`）。

**批 1：删老前端**

`dashboard/` 整目录 + `docker-compose.yml` 的回退分支 + `AGENTS.md` §四 的状态行 + `mingtang` 主题层对 dashboard 的引用 + `scripts/` 里 i18n 脚本的扫描路径。

判据：`mingtang` 三绿（lint/test/build）；容器重建后 WebUI 可用；`rg -l dashboard --glob '!changelogs/**'` 只剩文档叙述。

> **已执行（2026-11-21）**，实测：
> - `dashboard/` 删除（493 个 git 跟踪文件；删前 `git status --porcelain dashboard/` 为空，无未提交改动）。
> - **连带改动 7 处**（都是真依赖，不是注释）：`scripts/i18n_validate.py` 整条 dashboard locale 校验链（5 个函数 + 1 常量，删后 5 个 F401 已清）；`pytests/i18n_test/test_i18n_validate.py` 三个 dashboard 测试与 helper；`pytests/webui/test_app.py` 一个重复的 dashboard 回退测试（另一个改用 `custom-webui/dist`）；`crowdin.yml` 的 dashboard 同步条目；`pyproject.toml` 的 `maibot-dashboard>=1.5.4`（实测 `src/` 零 import）；`scripts/i18n_extract_candidates.py` 的排除项；`scripts/verify_a_memorix_webui.sh` **删除**（依赖已删的 Electron 驱动且 macOS 专用）。
> - **运行零风险已证**：`_resolve_static_path()` 的 `_DEFAULT_STATIC_DIR` 就是 `mingtang/dist`，**没有 dashboard 兜底分支**（`src/webui/app.py:297-302`）；容器 healthcheck 查的也是 `mingtang/dist/index.html`（`docker-compose.yml:77`）。
> - 文档同步：`AGENTS.md`（目录索引表删行、版本基线、先例路径、§四 前端状态）、`CODE_WIKI.md`（5 处）、`docker-compose.yml` 注释 3 处。
> - 测试：`pytests/webui` + `pytests/i18n_test` **321 passed / 2 skipped**。

**批 2：新引擎落地并接管读路径**

Rust 引擎 + Python 侧 `ConfigResolver`（`resolve(key) → value, provenance`）。`/schema/*` 与 `/get` 改由引擎的结果供给，`get_effective_config` 接线并扩到标量开关。

判据：**同一份两层 TOML 下，引擎输出的 `values` 与今天 `config_manager` 的解析结果逐键相同**（621 键全等，可脚本比对）；`provenance` 能指回真实文件；给任一 key，`source_layer` 与实际改动的那层一致。

**批 3：删旧读/旧写端点与旧 LLM 真源**

8 个旧端点、`model_configs.py`、`model_task_config` 全部 8 个消费点、`.bak`/`old/` 机制。

判据：`rg "model_task_config"` 零命中；`openapi.json` 路径数按预期下降且无残留引用；陈旧快照写入返 409 而非静默失败。

**批 4：删 `src/config` 剩余骨架**

`config.py` / `config_lifecycle.py` / `file_watcher.py` / `config_upgrade_hooks.py` / `config_base.py`。

判据：`rg "config_manager|global_config"` 零生产命中；容器重建 healthy；启动摘要能打印关键开关的「值 + 来源」。

### 三个不可逆点（不是回滚点，是"回不去"的点）

1. **批 3 之后**：旧读端点消失，任何依赖 `/config/bot` 的外部脚本都会断。**先 grep 一遍外部引用再执行。**
2. **批 4 之后**：`.bak` 机制消失，回滚只能靠 git。**批 4 之前必须先确认 Git 留档已上线并跑过一次真实回滚演练。**
3. **镜像最后一次带旧代码的构建**：`ghcr.io/liumiaoqi/maibot` 的旧 tag 是唯一"能跑起来的旧世界"。**保留至少一个旧 tag，别清理。**

### 取代关系

本决策取代：`2026-11-19-config-composition-system.md` 的 A/B 之争（不再需要：换引擎后组合是引擎的输入形状，不是架构分歧）、`2026-11-19-phase3-config-decisions.md` 的 `#2(b)`/`#3`/`#5`（不再需要前端迁移与 104 域接入）、`2026-11-19-rust-migration-direction.md` 的候选顺序（配置引擎直接成为第一个 Rust 件，不再是"等真实需求触发"）。

## Alternatives considered

- **并行上线再删（渐进）**：见 §四，会重新长出两个真源——正是要消灭的东西。拒绝。
- **只删老前端、配置系统原地重构**：`official_configs.py` 7940 行的 schema 可以留，但"三个隐式真源 + 五处同步"是**结构**问题，原地改不出结构。拒绝。
- **Rust 侧连存储与热重载一起接管**：一致性强，但引擎变成有状态服务，验证面从"纯函数"变成"服务"，且文件监听与 Python 侧的重启逻辑要重新协调。本期不做，作为批 2 之后的独立议题。
- **换 Pkl / CUE 而不是自研 Rust 引擎**：两者都是成熟配置语言，能省合并与校验的实现。但引入新语言作为**配置的唯一表达**，等于把 Python 的 pydantic schema 真源让位；且它们不支持"层+provenance"这类运行时语义。保留作为引擎内部实现的候选（可以先 `cue export` 或 Pkl evaluator 当参考实现）。
- **保留 `model_task_config` 只改文档**：`systemic-issues` note 已证它造过真实事故（改完不生效），拒绝。

## Acceptance criteria（整体）

1. `src/config` 只剩 `official_configs.py`；`rg "config_manager|global_config|model_task_config"` 零生产命中。
2. 配置的「生效值 + 来源」可由**一条命令**产出（CLI），且启动摘要打印关键开关的值与来源层。
3. 新增一个开关只需改**两处**（schema 声明 + 消费者），不再有五处同步——由批 2 的 `resolve(key)` 保证。
4. 三个隐式真源全部消失：模型选择只剩一个权威源，`models` 顺序必须显式写在 `prefer` 里或被 UI 展示。
5. 引擎的合并语义有单测覆盖「对象递归 / 数组整体替换 / 缺失不覆盖 / 冲突报 violations」四类。

## 参考

- dsh 的可照抄机制（`config-editor` 写入五道闸、`describe` 三层投影、`renderConfigDump` 前缀差分、内容摘要式 revision）：`E:\Users\lmq\deepseek-harness\packages\boot\config-editor\src\index.ts`、`packages/settings/settings/src/index.ts:319-332`、`packages/boot/app-boot/src/index.ts:648-746`
- 跨学科依据与文献位置：`../../../.shared/research/2026-11/config_system_cross_discipline_1120.md`
- 已有真机实证：`../../../.shared/decisions/phase3_new_config_roadmap.md:207-219`
- 问题陈述：`2026-11-20-config-system-systemic-issues.md`
