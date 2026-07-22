# Claude Code — MaiBot 项目笔记

## 项目概要

MaiBot 是基于 LLM 的多智能体聊天机器人框架，14 个角色共居一个聊天室，由管家协调发言。架构是微内核 + Protocol 接口契约——核心只依赖 Protocol，不依赖具体实现。

## 运行环境

- Docker 容器：`maim-bot-core`，Python 3.14.6
- 依赖管理：**uv**，不用 pip
- 代码修改后需重启容器才能生效，**我来执行 `docker restart maim-bot-core`，不需要先问用户**
- WSL 环境，Docker 通过 Docker Desktop 在 Windows 侧运行

## 角色分工

- **CodeArts**（华为云码道）：需求分析、架构设计、SSD 文档、代码审查
- **我（Claude Code）**：编码执行、运行时验证、调试排障、提交管理
- 我们之间没有直接通信链路，用户是中继

## 用户偏好

**革命而非改良。** 用户不喜欢过渡期兼容——不做 DeprecationWarning 渐进式迁移，不做 fallback 回退路径，不保留新旧两套 API 并存。一次性改到位，炸了就修调用方。正确的代码比兼容的代码重要。

具体表现：
- 删除旧方法 > 标记 DeprecationWarning
- 统一入口 > 多套签名并存
- 异常上浮 > try-except 兜底
- 一次性移除死代码 > 留着"以防万一"

## 核心约束（来自 AGENTS.md）

1. **组件兼容核心** — 核心只依赖 Protocol，不依赖具体实现类
2. **不兜底** — 错误完整暴露，不用 fallback 掩盖
3. **大道至简** — 不堆砌设定，零开箱抽象
4. **改主程序先请示** — 插件在 /plugins 下独立仓库，改 src/ 需先请求许可
5. **配置文件只改模板** — 新增版本号，不改动 legacy_migration
6. **提示词三语同步** — zh-CN / en-US / ja-JP
7. **提交标记** — commit message 末尾加 `[CC]`

## 架构常识

- **连接主义记忆**：以概念连接为第一公民，observe → Fragment → Episode → Saga 三层叙事自组织
- **分类学记忆**：旧范式，已 DEPRECATED 且零调用
- **MemoryServicePort**：核心访问记忆的唯一 Protocol 接口。新增 `observe_experience()`（连接主义路径）
- **纯数据类型应放 common 层**：MemoryHit/MemorySearchResult/MemoryWriteResult 等纯数据结构不应属于 core。放 `src/common/` 让 core 和 A_memorix 都导入
- **MigrationRouter**：当前处于 NEW_INDEPENDENT 阶段，所有请求走连接主义路径
- **AgentMemoryAdapter**：智能体间交互记忆隔离，用 `agent_interaction:{A}:{B}` 命名空间

## 协作流程

1. 开始新任务：读 `.shared/active_task.md` → 读 `.codeartsdoer/specs/{task}/tasks.md`
2. 编码过程中：遇到架构问题查 `AGENTS.md` 的核心禁止项和 Protocol 表格
3. 提交代码：按 `CONVENTIONS.md` 命名规则加 `[CC]`
4. 交接反馈：在 `.shared/handoff/` 按命名规则写反馈文件
5. CodeArts 写完 SSD 后会交接给我执行，遇到设计问题通过用户转达

## 踩坑记录

### 代码层面
1. **模块级实例化** — `emoji_manager.py` 等文件在 import 时创建 LLMOrchestrator，此时 ModelConfigPort 尚未注入。
2. **`from ... import __init__` 不可用** — `__init__` 是 Python 特殊属性。
3. **`@dataclass` 容易丢失** — 编辑类定义时注意保留装饰器。MemoryWriteResult 曾因编辑时丢失 @dataclass 导致 TypeError。
4. **ThinkAction vs SilenceReason** — `INTENTIONAL` 是 SilenceReason 枚举值，不是 ThinkAction。action=SILENT + silence_reason=INTENTIONAL 才是"深思熟虑后不回"。
5. **Python 的 `field()` 无 @dataclass 时只是类型注解**，不会生成 __init__。

### 设计层面
6. **不要本地镜像类型** — 在 A_memorix 内创建核心类型的副本注定不同步。正确方案是把类型下放到 common 层。
7. **`**{k:v}` 透传丢失类型安全** — host_service 的 migration_ingest_text 等分支曾用此模式，应显式列出参数。
8. **if-elif 长链分派** — 已在 host_service._ADMIN_HANDLER_MAP 类变量中部分解决。
