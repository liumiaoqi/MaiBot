# Token 消耗优化规划

> 2026-07-27，CA 整理

## 持久化上下文归属

| 文件 | 归属 | 大小 | 注入方式 | 类比 |
|------|------|------|---------|------|
| `MaiBot智能体自主性架构.mdc` | **CA** | 9.3KB | CA 每轮稳定注入 | CA 独有，无其他智能体等价物 |
| `AGENTS.md` | **CX (Codex)** | 6.2KB | CX 每轮注入 | CX 的 CLAUDE.md |
| `CLAUDE.md` | **CC** | 5.7KB | CC 每轮注入 | CC 的 AGENTS.md |

> AGENTS.md 与 CX 的关系 = CLAUDE.md 与 CC 的关系：各自的全局行为指南，每轮注入。CA 没有等价于 CLAUDE.md 的文件，只有 session-rules。

## 问题

1. CA 稳定注入 9.3KB session-rules，但对话历史累积是主要 token 消耗源（200k 窗口后期 ~60% 是历史）
2. CA 上下文仅 200k，长对话体验不可控
3. CA 经常忘记用子代理（explore agent），直接 grep/glob 浪费上下文
4. 运行侧（MaiBot LLM 调用）成本低廉，不需优化
5. session-rules 9.3KB 中架构哲学/Phoenix 历史/CQ 债务表占 ~6KB，编码任务时大部分不需要

## 方案

### P0：session-rules 分层加载

当前：CA 每轮稳定注入 9.3KB session-rules，其中架构哲学/Phoenix/CQ 债务占 ~6KB

目标：按任务类型按需加载

| 层级 | 内容 | 大小 | 加载时机 |
|------|------|------|---------|
| 常驻 | 核心编码规范（import/类型/注释/变量）、核心禁止项、四主智能体约定 | ~2KB | 每次对话 |
| 编码 | Port 接口表、架构约束、debug 规范 | ~2KB | 编码任务 |
| 架构 | 架构哲学、核心进化方向、欲望系统、管家系统 | ~3KB | 架构设计/重构 |
| 债务 | CQ 债务全景表、Phoenix 历史 | ~4KB | CQ 任务 |
| 交接 | SSD 审查规范、四主协作约定细节 | ~2KB | 跨智能体交接 |

**实现方式**：
- session-rules 拆分为 `session-core.md`（常驻，~3KB）+ `session-philosophy.md`（按需）+ `session-phoenix.md`（按需）+ `session-cq.md`（按需）
- `.codeartsdoer/rule/` 下按任务类型放规则文件，IDE 按场景激活
- AGENTS.md 归 CX 管理，CA 不主动改（除非 CX 要求）

**预估节省**：编码任务 ~65%（9.3KB → 3KB），架构任务 ~35%

### P1：session-rules 已完成条目归档

当前 session-rules 中大量已完成条目：
- Phoenix-0~9 全 ✅（~2KB 历史细节）
- CQ-1~5 全 ✅（~1KB）
- CQ-9/10/3 全 ✅

**操作**：
- 已完成条目移到 `.codeartsdoer/specs/memo/archive_phoenix.md` 和 `.codeartsdoer/specs/memo/archive_cq.md`
- session-rules 只保留：当前活跃债务 + 归档文件路径引用
- 需要回顾时 `Read` 归档文件，不每轮注入
- AGENTS.md 归 CX，CA 不主动改其结构

**预估节省**：~3KB/轮

### P2：对话分段 + 交接文件

当前问题：一个对话背几十轮历史，后期每轮 token 消耗 = 规则 + 全部历史

**策略**：
- 每个 CQ 编号一个对话周期
- 对话结束前写交接文件到 `.shared/handoff/`
- 新对话开头 `Read` 交接文件，不背旧历史
- 200k 窗口利用率：当前 ~60% 历史 + 8% 规则 + 32% 有效 → 目标 20% 交接 + 4% 规则 + 76% 有效

### P3：子代理使用规范

CA 行为约束（写入 AGENTS.md）：

```
## 子代理使用规范
- 代码探索/搜索：必须用 Task(explore)，禁止直接 grep/glob/CodeSemanticSearch
- 文件读取：3 个以上文件用 Task(explore) 批量读，1-2 个直接 Read
- 调查任务：必须用 Task(explore)，结论写回交接文件
- 编码任务：CA 只做架构设计 + 代码审查，编码派发 CC/Codex
```

**预估节省**：~20%（子代理上下文独立，不污染主对话）

### P4：AGENTS.md 精简（CX 侧）

AGENTS.md 归 CX 管理，CA 不主动改。以下建议供 CX 参考：
- 代码规范 ~1KB
- 运行/调试/构建 ~0.5KB
- 核心架构（禁止项 + Port 表）~2KB
- CQ 债务全景 ~2KB
- CQ-16 详细修复表 ~2KB
- Phoenix 后路线 ~0.5KB
- SSD 审查规范 ~0.5KB

**精简方向**：
- CQ-16 修复表（26 行）→ 归档，AGENTS.md 只留 "CQ-16: ✅ 编码完成，⬜ Docker 验证"
- Port 接口表 → 保留但压缩（去掉实现者列，运行时可查）
- 核心禁止项 → 保留（这是硬约束）

## 优先级

| 优先级 | 方案 | 预估总节省 | 实施难度 |
|--------|------|-----------|---------|
| P0 | session-rules 分层加载 | ~65%（编码任务） | 中（需拆文件 + 配置加载机制） |
| P1 | 已完成条目归档 | ~3KB/轮 | 低（移文件 + 改引用） |
| P2 | 对话分段 | ~40%（长对话） | 低（行为习惯） |
| P3 | 子代理规范 | ~20% | 低（加规则） |
| P4 | AGENTS.md 精简 | ~2KB/轮 | 低（编辑） |

**建议执行顺序**：P1 → P4 → P3 → P2 → P0（先做低难度高收益的）

## 不做的事

- 运行侧 token 优化（成本已低廉，效果已满意）
- 缓存命中率优化（DeepSeek 特性，非架构能解）