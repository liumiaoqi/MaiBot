# 服务管理器（ZG-1）

> 需求规格：`.codeartsdoer/specs/zg1_service_manager/spec.md`
> 技术设计：`.codeartsdoer/specs/zg1_service_manager/design.md`
> 编码任务：`.codeartsdoer/specs/zg1_service_manager/tasks.md`

## 定位

服务管理器是 MaiBot 运行时服务治理的核心模块，将启动期组件纳入运行时管理，提供生命周期控制、健康检查、故障恢复和系统健康聚合。

**OS 映射**：systemd / init — 组件生命周期管理 + 健康监控 + 自动恢复

## 架构

```
src/core/
├── protocols.py                          # ServiceManagerPort + CoreReadinessPort + HealthProbePort
├── service_manager_port_registry.py      # Port 注册
├── service_manager/
│   ├── types.py                          # 6 枚举 + 8 dataclass
│   ├── exceptions.py                     # 6 异常类
│   ├── dependency_graph.py               # 依赖图引擎（纯逻辑）
│   ├── state_aggregator.py               # 状态聚合引擎（纯内存）
│   ├── recovery.py                       # 故障恢复引擎（退避+风暴保护）
│   ├── health_check.py                   # 健康检查引擎（主动探测+被动心跳）
│   └── lifecycle.py                      # 生命周期管理引擎（级联+校验）
├── adapters/
│   ├── service_manager_adapter.py        # ServiceManagerPort 适配器（组装 5 引擎）
│   └── core_readiness_port.py            # CoreReadinessPort 适配器
```

## Protocol 接口

### ServiceManagerPort（12 方法）

生命周期控制：`stop` / `start` / `restart` / `adopt_from_startup`
状态查询：`get_state` / `list_states` / `get_system_health_view` / `get_fault_history`
被动接收：`report_heartbeat` / `report_external_fault`
事件订阅：`subscribe_health_change` / `unsubscribe_health_change`

### CoreReadinessPort（3 方法）

`get_core_readiness` / `is_core_ready` / `update_flag`

### HealthProbePort（1 方法）

`health_probe` — 受管组件实现，返回存活状态

## 9 状态生命周期

```
未纳入 → 运行中 → 停止中 → 已停止 → 重启中 → 运行中
                ↓                        ↓
              故障 ←── 健康检查失败 ──→ 降级
                ↓
      故障(需人工) ← 风暴保护
```

## 5 引擎

| 引擎 | 职责 | I/O | async |
|------|------|-----|-------|
| DependencyGraph | 依赖关系 + 拓扑排序 + 环检测 | 无 | 否 |
| StateAggregator | 四等级计算 + 事件推送 | 无 | 否 |
| RecoveryEngine | 指数退避 + 风暴保护 + OOM 重应用 | 无 | 是 |
| HealthCheckEngine | 主动探测 + 被动心跳 + 连续失败转故障 | 探针 | 是 |
| LifecycleManager | stop/start/restart + 级联 + 校验 | 组件回调 | 是 |

## 配置项

| 配置项 | 默认值 | 范围 |
|--------|--------|------|
| 健康检查间隔 | 30s | [5, 3600]s |
| 主动探测超时 | 5s | - |
| 连续失败阈值 | 2 次 | - |
| 指数退避基数 | 1s | - |
| 退避上限 | 300s | - |
| 风暴窗口 | 600s | - |
| 风暴阈值 | 5 次 | - |
| 停止超时 | 30s | - |
| 故障历史 | 100 条/组件 | - |

## 与其他 ZG 任务协作

- **ZG-2（看门狗）**：看门狗检测到组件异常时调用 `report_external_fault` 上报
- **ZG-3（资源监控）**：资源耗尽时调用 `report_external_fault` 触发恢复
- **ZG-9（OOM 保护）**：恢复引擎通过 `oom_hook` 重应用 OOM 优先级

## 核心禁止项

- 禁止核心直接导入 `ServiceManagerAdapter`（与现有适配器隔离规则一致）
- 核心只通过 `ServiceManagerPort` Protocol 交互