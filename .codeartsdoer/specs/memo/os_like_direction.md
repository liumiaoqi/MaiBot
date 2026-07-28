# MaiBot OS 化方向探索

> 2026-07-27，CA 整理，用户口述方向

## 当前已像 OS 的部分

| OS 概念 | MaiBot 对应 | 状态 |
|---------|------------|------|
| 微内核 | 核心 = 智能体 + 消息管道，组件可替换 | ✅ 已实现 |
| 系统调用 | Protocol 接口（16 个 Port） | ✅ 已实现 |
| 进程隔离 | Runner 子进程，gRPC IPC | ✅ 已实现 |
| 权限控制 | OAuth Scope 细粒度授权 | ✅ 已实现 |
| 驱动/设备 | napcat-adapter 等插件 | ✅ 已实现 |
| SysV init | 31 步顺序启动编排 | ✅ 已实现（但只有 Host 侧） |
| 信号 | asyncio 事件循环 + signal handler | ✅ 基础有 |
| 文件系统 | config.toml / SQLite / JSONL | 隐式存在 |

## 可以更像 OS 的方向（按价值排序）

### 1. 服务管理器（systemd 化）

**动机**：当前组件启动后就没有健康监测。A_Memorix 挂了？不知道。napcat-adapter WebSocket 断了？靠心跳超时才发现。

**OS 类比**：systemd 的 `systemctl status` / `journalctl` / 自动重启

**MaiBot 化**：
- 每个组件声明健康检查（`health_check()` → healthy/degraded/dead）
- 统一 `ServiceManager`：启动/停止/重启/状态查询
- 失败策略：`OnFailure=restart` / `OnFailure=ignore` / `OnFailure=shutdown`
- 替代当前散落的 try/except + logger.error

**复杂度**：低。当前 `_init_components` 的 StartupOrchestrator 已有雏形，扩展即可。

### 2. 声明式启动依赖（systemd After=/Requires=）

**动机**：当前 31 步手工排序，Port 之间互不依赖但串行启动，浪费 ~100ms。更重要的是——加新组件要手动找插入位置。

**OS 类比**：systemd 的 `After=network.target`

**MaiBot 化**：
```python
@component(name="a_memorix", after=["config", "database"])
async def init_memorix(): ...

@component(name="plugin_v2", after=["ports", "a_memorix"])  # 显式依赖
async def init_plugin_v2(): ...
```
编排器自动拓扑排序，无依赖的并行启动。

**复杂度**：中。需要写拓扑排序器 + 并行启动器。但 MaiBot 组件数 ~30，不会出现 systemd 那样的循环依赖地狱。

### 3. 统一日志管线（journald 化）

**动机**：当前日志碎片化——structlog + stdlib logging + print() + 子进程 logger 不初始化。排障靠运气。

**OS 类比**：journald 的结构化日志 + journalctl 查询

**MaiBot 化**：
- 所有组件统一走 structlog，结构化输出（JSON）
- 子进程日志通过 LogForwarder 汇聚到 Host
- 支持按组件/级别/时间范围查询（`log_query(component="napcat", since="5min")`）
- 替代当前 `docker logs` + 肉眼翻

**复杂度**：中。CQ-11 已在清理 `import logging` 残留，在此基础上加结构化。

### 4. 事件总线（D-Bus / inotify 化）

**动机**：当前组件间通信靠直接调用（Port 接口）。新增观察者要改调用方代码。

**OS 类比**：D-Bus 信号广播 / inotify 文件变更通知

**MaiBot 化**：
- AutonomyEventBusPort 已有雏形，但只用于自主性事件
- 扩展为通用事件总线：组件发布事件，其他组件订阅
- 例：A_Memorix 发布 `memory.updated`，WebUI 订阅并刷新显示

**复杂度**：中高。需要设计事件 schema + 订阅机制 + 背压控制。但 AutonomyEventBusPort 是起点。

### 5. 资源限制（cgroups 化）

**动机**：插件没有资源限制。一个插件疯狂调 LLM 可以烧光配额。

**OS 类比**：cgroups 的 CPU/内存/IO 限制

**MaiBot 化**：
- 每个 Runner 子进程声明资源配额（LLM 调用次数/分钟、内存上限）
- ServiceManager 监控并强制限制
- 超限策略：throttle / queue / reject

**复杂度**：高。需要 per-plugin 配额计数器 + 限流器。但 Scope 系统是起点。

## 不应该做的事

- **虚拟文件系统**（/proc 化）：MaiBot 状态量不大，SQLite + dict 够用，不需要 VFS 抽象
- **内核模块动态加载**（modprobe 化）：Python 的 import 已经是动态加载，不需要额外抽象
- **进程调度器**（CFS 化）：asyncio 事件循环就是调度器，不需要再抽象一层
- **系统调用号表**（syscall 化）：Protocol 接口已经是系统调用，不需要编号

## 建议路径

```
当前（SysV init 阶段）
  │
  ├── 第一步：服务管理器（systemd 化）—— 健康检查 + 失败策略
  │     价值最高，复杂度最低，CQ-16 子进程日志问题直接被解决
  │
  ├── 第二步：声明式启动依赖 —— 拓扑排序 + 并行启动
  │     让启动编排可扩展，新组件不用手动找插入位置
  │
  └── 第三步：统一日志管线 —— 结构化 + 可查询
        排障体验质变，但依赖前两步（服务管理器需要日志，启动依赖需要日志初始化保证）
```

## 与 CQ 的关系

- CQ-16（子进程日志初始化）→ 第三步的前置
- CQ-6（EventDispatcher 闭环）→ 第四步（事件总线）的前置
- 服务管理器 → 新 CQ 编号，但优先级低于 CQ-6/7

**结论**：OS 化方向正确，但先收尾 CQ-16/6/7，再开新线。服务管理器是第一个值得做的 OS 化特性。