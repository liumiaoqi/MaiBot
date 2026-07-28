# Phoenix-7b：V1 插件系统内部优化 — 技术设计

## 1. 实现模型

### 1.1 上下文视图

本次优化仅涉及 `src/plugin_runtime/` 内部，不改变任何外部接口。优化后的 V1 运行时对 V1 插件开发者、V4 兼容层、主程序均透明。

### 1.2 服务/组件总体架构

```
优化前                              优化后
─────────                           ─────────
RequestIdGenerator.next()           RequestIdGenerator.next()
  async def → await 协程切换          def → 直接返回，零开销

Runner 主循环                        Runner 主循环
  while + asyncio.sleep(1.0)         while + _shutdown_event.wait()
  每秒唤醒一次                        零唤醒，Event 通知

_wait_for_runner_connection          _wait_for_runner_connection
  while + asyncio.sleep(0.1)         _connection_event.wait()
  100ms 轮询                          Event 通知，零延迟

except Exception:                   except Exception as exc:
  吞掉异常信息                         logger.debug("...", exc_info=exc)

getattr(supervisor, "method")       supervisor.method()
  反射调用，无类型安全                  直接调用，IDE 可追踪
```

### 1.3 实现设计文档

#### T1: RequestIdGenerator.next() 同步化

**文件**：`src/plugin_runtime/protocol/envelope.py:52-61`

**变更**：
```python
# 优化前
async def next(self) -> int:
    current = self._counter
    self._counter += 1
    return current

# 优化后
def next(self) -> int:
    current = self._counter
    self._counter += 1
    return current
```

**调用方适配**：所有 `await gen.next()` 改为 `gen.next()`。搜索 `RequestIdGenerator` 的使用点：
- `src/plugin_runtime/host/rpc_server.py` — `send_request()` 中调用
- `src/plugin_runtime/runner/rpc_client.py` — `send_request()` / `send_event()` 中调用

**风险**：无。`_counter += 1` 是纯 CPU 操作，不需要 async。Python GIL 保证线程安全（单进程内 asyncio 是协作式调度）。

#### T2: Runner 主循环 Event 化

**文件**：`src/plugin_runtime/runner/runner_main.py:474-477`

**变更**：
```python
# 优化前
while not self._shutting_down:
    await asyncio.sleep(1.0)

# 优化后
# __init__ 中新增：self._shutdown_event = asyncio.Event()
# shutdown 触发时：self._shutdown_event.set()
while not self._shutting_down:
    await self._shutdown_event.wait()
```

**关键点**：
- `PluginRunner.__init__` 新增 `self._shutdown_event: asyncio.Event`
- `_handle_shutdown` / `_handle_prepare_shutdown` 方法中调用 `self._shutdown_event.set()`
- `Event.wait()` 在 `set()` 之前调用会阻塞；在 `set()` 之后调用立即返回——两种情况均正确
- 需要确保 Event 在正确的 asyncio loop 上创建（`__init__` 中不能用 `asyncio.Event()`，因为 loop 可能尚未运行；应在 `_async_main` 中创建）

**实现细节**：在 `_async_main` 的 `self._runner = PluginRunner(...)` 之后、`await runner.run()` 之前创建 Event，或改为在 `run()` 方法开头创建。

#### T3: Runner 连接等待 Event 化

**文件**：`src/plugin_runtime/host/supervisor.py:841-906`

**变更**：

`_wait_for_runner_connection`：
```python
# 优化前：轮询
while True:
    if self._rpc_server.is_connected:
        return
    await asyncio.sleep(0.1)

# 优化后：Event 通知
# RPCServer 新增 _connection_event: asyncio.Event
# _handle_connection 中 set()
# stop() 中 clear()
await self._rpc_server.connection_event.wait()
```

`_wait_for_runner_ready`：
```python
# 优化前：轮询
while True:
    if self._runner_ready_events.is_set():
        return self._runner_ready_payloads
    await asyncio.sleep(0.1)

# 优化后：已有 Event，直接 wait
# 注意：self._runner_ready_events 已经是 asyncio.Event
# 只需将轮询改为 wait，保留异常检查逻辑
```

**关键点**：
- `_runner_ready_events` 已经是 `asyncio.Event`（L887 `is_set()` 调用可推断），可以直接 `wait()`
- `_rpc_server.is_connected` 需要新增对应的 Event：在 `RPCServer._handle_connection` 中 `set()`，在 `stop()` 中 `clear()`
- 异常检查（`_running`、`_get_runner_startup_failure_reason`）需要在 wait 超时后执行，或改为 wait + 超时组合

**实现策略**：使用 `asyncio.wait_for(event.wait(), timeout=check_interval)` + 异常检查循环，将 `sleep(0.1)` 替换为 `event.wait()`，大幅减少无效唤醒。

#### T4: 宽泛异常捕获改善

**文件**：多个文件，16 处

**变更模式**：
```python
# 优化前
except Exception:
    # 静默处理

# 优化后
except Exception as exc:
    logger.debug("异常被捕获: %s", exc)
    # 原有处理逻辑不变
```

**豁免列表**（保留原样）：
- `src/plugin_runtime/runner/log_handler.py` 3 处 — 日志系统内部，避免递归

**逐文件处理**：

| 文件 | 行号 | 当前行为 | 优化 |
|------|------|---------|------|
| `supervisor.py` | 451 | `except Exception: raise` | `except Exception as exc: logger.debug("启动失败", exc_info=True); raise` |
| `supervisor.py` | 1201 | 静默吞掉 | `except Exception as exc: logger.debug("驱动注册失败: %s", exc)` |
| `supervisor.py` | 1390 | 静默回退 | `except Exception as exc: logger.debug("RouteKey 构建失败: %s", exc)` |
| `integration.py` | 505 | 吞掉并行启动异常 | `except Exception as exc: logger.debug("并行启动异常: %s", exc)` |
| `capabilities/core.py` | 34 | 宽泛捕获 | `except Exception as exc: logger.debug("能力注册异常: %s", exc)` |
| `host/message_utils.py` | 358 | 宽泛捕获 | `except Exception as exc: logger.debug("消息处理异常: %s", exc)` |
| `transport/uds.py` | 91 | 静默吞掉 | `except Exception as exc: logger.debug("UDS 传输异常: %s", exc)` |
| `transport/named_pipe.py` | 123 | 静默吞掉 | `except Exception as exc: logger.debug("Named Pipe 传输异常: %s", exc)` |
| `runner/rpc_client.py` | 42 | 回退到 "1.0.0" | `except Exception as exc: logger.debug("SDK 版本读取失败: %s", exc)` |
| `runner/plugin_loader.py` | 301 | 吞掉路径解析异常 | `except Exception as exc: logger.debug("模块路径解析失败: %s", exc)` |
| `runner/plugin_loader.py` | 530 | 吞掉插件加载异常 | `except Exception as exc: logger.debug("插件加载失败: %s", exc)` |
| `runner/manifest_validator.py` | 1268 | 宽泛捕获 | `except Exception as exc: logger.debug("manifest 校验异常: %s", exc)` |
| `runner/manifest_validator.py` | 1295 | 宽泛捕获 | `except Exception as exc: logger.debug("manifest 校验异常: %s", exc)` |

**关键约束**：所有 `logger.debug` 级别——不影响生产日志量，仅在调试时可见。不改变异常传播语义。

#### T5: 代码质量提升

**5a: `_EVENT_TYPE_MAP` 冗余映射清理**

文件：`src/plugin_runtime/integration.py:62-73`

当前所有 key==value，映射表完全冗余。删除整个 `_EVENT_TYPE_MAP`，直接使用事件类型字符串。

**5b: `_instantiate_supervisor` 反射构造消除**

文件：`src/plugin_runtime/integration.py:247-271`

当前使用 `inspect.signature` 反射构造 Supervisor。`PluginRunnerSupervisor` 构造签名是已知的，改为直接传参。

```python
# 优化前
signature = inspect.signature(supervisor_cls)
accepts_var_keyword = any(...)
if accepts_var_keyword:
    return supervisor_cls(**kwargs)
supported_kwargs = {k: v for k, v in kwargs.items() if k in signature.parameters}
return supervisor_cls(**supported_kwargs)

# 优化后
return supervisor_cls(**kwargs)
```

**5c: `getattr(supervisor, "method")` 反射调用消除**

文件：`src/plugin_runtime/integration.py:296-302, 744-749, 788-796`

```python
# 优化前 (L296-302)
set_blocked_plugin_reasons = getattr(supervisor, "set_blocked_plugin_reasons", None)
if callable(set_blocked_plugin_reasons):
    set_blocked_plugin_reasons(self._blocked_plugin_reasons)

# 优化后
supervisor.set_blocked_plugin_reasons(self._blocked_plugin_reasons)
```

```python
# 优化前 (L744)
for plugin_id, registration in getattr(supervisor, "_registered_plugins", {}).items():

# 优化后：Supervisor 新增公开方法 get_registered_plugins()
for plugin_id, registration in supervisor.get_registered_plugins().items():
```

```python
# 优化前 (L788-796)
get_reasons = getattr(supervisor, "get_plugin_load_failure_reasons", None)
if callable(get_reasons):
    reasons.update(get_reasons())

# 优化后
reasons.update(supervisor.get_plugin_load_failure_reasons())
```

**5d: Supervisor 新增 `get_registered_plugins()` 公开方法**

文件：`src/plugin_runtime/host/supervisor.py`

```python
def get_registered_plugins(self) -> Dict[str, Any]:
    """返回当前已注册插件的映射。"""
    return self._registered_plugins
```

## 2. 接口设计

### 2.1 总体设计

本次优化不新增任何外部接口。所有变更为内部实现优化。

### 2.2 接口清单

| 变更类型 | 接口 | 变更 |
|---------|------|------|
| 内部方法签名变更 | `RequestIdGenerator.next()` | `async def` → `def` |
| 内部新增属性 | `PluginRunner._shutdown_event` | `asyncio.Event` |
| 内部新增属性 | `RPCServer.connection_event` | `asyncio.Event` 属性 |
| 内部新增方法 | `PluginRunnerSupervisor.get_registered_plugins()` | 公开方法，替代直接访问 `_registered_plugins` |
| 内部删除常量 | `_EVENT_TYPE_MAP` | 冗余映射，直接使用字符串 |
| 内部方法简化 | `_instantiate_supervisor()` | 移除反射，直接构造 |

## 4. 数据模型

### 4.1 设计目标

不新增任何数据模型。优化仅涉及行为变更。

### 4.2 模型实现

无新增模型。现有 `Envelope`、`PluginRuntimeSnapshot` 等模型不变。