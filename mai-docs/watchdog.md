# 看门狗（ZG-3）

> 需求规格：`.codeartsdoer/specs/zg3_watchdog/spec.md`
> 技术设计：`.codeartsdoer/specs/zg3_watchdog/design.md`
> 编码任务：`.codeartsdoer/specs/zg3_watchdog/tasks.md`

## 定位

看门狗是 MaiBot 运行时健康监测的旁路模块，提供事件循环阻塞检测与 Runner 健康结果桥接上报。借鉴 Linux watchdog/hung_task 双层检测 + touch 机制。

**OS 映射**：watchdog / hung_task — 事件循环阻塞检测 + Runner 健康桥接

## 架构

```
src/core/
├── protocols.py                          # WatchdogPort Protocol
├── watchdog_port_registry.py             # Port 注册
├── watchdog/
│   ├── types.py                          # 3 枚举 + 3 dataclass
│   ├── config.py                         # WatchdogConfig
│   ├── exceptions.py                     # 3 异常类
│   ├── event_loop_monitor.py             # 事件循环阻塞检测引擎
│   └── runner_health_bridge.py           # Runner 健康桥接引擎
├── adapters/
│   └── watchdog_adapter.py               # WatchdogPort 适配器
```

## 核心能力

### 1. 事件循环阻塞检测（EventLoopMonitor）

- **touch 机制**：主循环协程以 ≤1s 间隔刷新存活时间戳
- **独立线程检测**：threading.Thread 按 5s 间隔判定，不依赖事件循环调度
- **双层判定**：轻度卡顿（3s）仅告警，严重阻塞（10s）连续 N=2 次后上报
- **冷却窗口**：30s 内不重复上报同一异常
- **恢复检测**：阻塞恢复后记录事件并重置冷却

### 2. Runner 健康桥接（RunnerHealthBridge）

- **V2 回调桥接**：订阅 HeartbeatManager timeout_callback + 轮询 get_health_status diff
- **V1 旁路轮询**：getattr 安全访问 _runner_process / _restart_count，不修改 V1 API
- **上报限流**：每 Runner 独立冷却窗口
- **恢复信号**：检测到 Runner 恢复时记录事件

## Protocol 接口

```python
class WatchdogPort(Protocol):
    async def start(self, main_loop: asyncio.AbstractEventLoop) -> None: ...
    async def stop(self) -> None: ...
    def touch(self) -> None: ...
    def get_status(self) -> WatchdogStatus: ...
    def get_runner_bridge_status(self, runner_id: str) -> Optional[RunnerBridgeStatus]: ...
    def list_runner_bridge_status(self) -> list[RunnerBridgeStatus]: ...
    def subscribe_status_change(self, callback) -> None: ...
    def unsubscribe_status_change(self, callback) -> None: ...
    def register_v2_supervisor(self, runner_id, supervisor, heartbeat_manager, component_id="") -> None: ...
    def register_v1_supervisor(self, runner_id, supervisor, component_id="") -> None: ...
    def unregister_runner(self, runner_id: str) -> None: ...
```

## 状态机

```
正常(NORMAL) ──轻度卡顿──→ 轻度卡顿(MILD_LAG) ──严重阻塞──→ 严重阻塞(SEVERE_BLOCK)
     ↑                          │                                    │
     │                          └── touch 恢复 ──→ 正常              │
     └──────────── 阻塞恢复 ──────────────────────────────────────┘
                                                       │
                                              连续 N 次后上报
                                              进入冷却窗口(30s)
```

## 配置项

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| touch_interval_s | 1.0 | touch 刷新间隔 |
| check_interval_s | 5.0 | 检测判定间隔 |
| mild_threshold_s | 3.0 | 轻度卡顿阈值 |
| severe_threshold_s | 10.0 | 严重阻塞阈值 |
| consecutive_report_threshold | 2 | 连续超时上报阈值 N |
| cooldown_s | 30.0 | 冷却窗口 |
| v1_poll_interval_s | 10.0 | V1 旁路轮询间隔 |
| v2_diff_interval_s | 5.0 | V2 状态 diff 轮询间隔 |

## 协作关系

- **ZG-1 服务管理器**：检测到异常时调用 `ServiceManagerPort.report_external_fault` 上报
- **ZG-2 统一日志管线**：检测/卡顿/上报事件经结构化日志输出（看门狗不直接写日志文件）
- **ZG-9 极端环境加固**：Docker OOM 保护确保看门狗检测线程不被 OOM killer 优先杀掉

## touch 机制与独立线程检测原理

```
主事件循环协程 ──touch()──→ _last_touch_time (Lock 保护)
                                    ↑
独立检测线程 ──读取──→ elapsed = now - last_touch
                        │
                        ├── elapsed < 3s  → 正常
                        ├── 3s ≤ elapsed < 10s → 轻度卡顿（告警）
                        └── elapsed ≥ 10s → 严重阻塞（连续 N 次后上报）
```

检测线程独立于事件循环，即使事件循环阻塞，检测线程仍能正常运行并检测到阻塞。