# Phoenix-7b：V1 插件系统内部优化 — 编码任务

> 上一阶段文档：`.codeartsdoer/specs/phoenix-7b_v1_optimize/spec.md` + `design.md`

## 任务总览

| 编号 | 任务 | 优先级 | 受影响文件 | 预估行数 |
|------|------|--------|-----------|---------|
| T1 | RequestIdGenerator.next() 同步化 | P0 | envelope.py, rpc_server.py, rpc_client.py | ~10 |
| T2 | Runner 主循环 Event 化 | P0 | runner_main.py | ~15 |
| T3 | Runner 连接等待 Event 化 | P1 | supervisor.py, rpc_server.py | ~30 |
| T4 | 宽泛异常捕获改善 | P1 | 12 个文件，16 处 | ~32 |
| T5 | 代码质量提升 | P1 | integration.py, supervisor.py | ~40 |

---

## T1: RequestIdGenerator.next() 同步化 [P0]

**文件**：
- `src/plugin_runtime/protocol/envelope.py:52-61`
- `src/plugin_runtime/host/rpc_server.py`（调用方）
- `src/plugin_runtime/runner/rpc_client.py`（调用方）

**步骤**：
- [ ] 1.1 `envelope.py:52` — `async def next(self)` → `def next(self)`，移除 `async`
- [ ] 1.2 搜索所有 `await gen.next()` / `await self._request_id_gen.next()` 调用，移除 `await`
- [ ] 1.3 验证：`rg "RequestIdGenerator" src/plugin_runtime/` 确认无遗漏

**验收**：`gen.next()` 直接返回 int，无协程切换。

---

## T2: Runner 主循环 Event 化 [P0]

**文件**：`src/plugin_runtime/runner/runner_main.py:474-477`

**步骤**：
- [ ] 2.1 `PluginRunner` 类新增 `self._shutdown_event: asyncio.Event | None = None`
- [ ] 2.2 在 `run()` 方法开头（`async def run()` 内）创建 `self._shutdown_event = asyncio.Event()`
- [ ] 2.3 在 `_handle_shutdown` / `_handle_prepare_shutdown` 方法中调用 `self._shutdown_event.set()`
- [ ] 2.4 L474-477 — `while not self._shutting_down: await asyncio.sleep(1.0)` → `while not self._shutting_down: await self._shutdown_event.wait()`
- [ ] 2.5 验证：Runner 启动后空闲时无每秒日志输出

**验收**：Runner 空闲时零唤醒；shutdown 信号后立即退出主循环。

---

## T3: Runner 连接等待 Event 化 [P1]

**文件**：
- `src/plugin_runtime/host/supervisor.py:841-906`
- `src/plugin_runtime/host/rpc_server.py`

**步骤**：
- [ ] 3.1 `RPCServer` 新增 `self._connection_event = asyncio.Event()` 和 `connection_event` 属性
- [ ] 3.2 `RPCServer._handle_connection` 成功握手后调用 `self._connection_event.set()`
- [ ] 3.3 `RPCServer.stop()` 中调用 `self._connection_event.clear()`
- [ ] 3.4 `supervisor.py:851-863` — `_wait_for_runner_connection` 轮询改为 `self._rpc_server.connection_event.wait()` + 异常检查循环
- [ ] 3.5 `supervisor.py:884-899` — `_wait_for_runner_ready` 轮询改为 `self._runner_ready_events.wait()` + 异常检查循环（`_runner_ready_events` 已是 Event）
- [ ] 3.6 验证：Host 启动 Runner 后连接等待无 100ms 轮询日志

**验收**：Runner 连接/就绪后 Host 立即感知，无轮询延迟。

---

## T4: 宽泛异常捕获改善 [P1]

**文件**：12 个文件，16 处（3 处豁免）

**步骤**：
- [ ] 4.1 `host/supervisor.py:451` — `except Exception:` → `except Exception as exc: logger.debug("启动失败", exc_info=True); raise`
- [ ] 4.2 `host/supervisor.py:1201` — `except Exception:` → `except Exception as exc: logger.debug("驱动注册失败: %s", exc)`
- [ ] 4.3 `host/supervisor.py:1390` — `except Exception:` → `except Exception as exc: logger.debug("RouteKey 构建失败: %s", exc)`
- [ ] 4.4 `integration.py:505` — `except Exception:` → `except Exception as exc: logger.debug("并行启动异常: %s", exc)`
- [ ] 4.5 `capabilities/core.py:34` — `except Exception:` → `except Exception as exc: logger.debug("能力注册异常: %s", exc)`
- [ ] 4.6 `host/message_utils.py:358` — `except Exception:` → `except Exception as exc: logger.debug("消息处理异常: %s", exc)`
- [ ] 4.7 `transport/uds.py:91` — `except Exception:` → `except Exception as exc: logger.debug("UDS 传输异常: %s", exc)`
- [ ] 4.8 `transport/named_pipe.py:123` — `except Exception:` → `except Exception as exc: logger.debug("Named Pipe 传输异常: %s", exc)`
- [ ] 4.9 `runner/rpc_client.py:42` — `except Exception:` → `except Exception as exc: logger.debug("SDK 版本读取失败: %s", exc)`
- [ ] 4.10 `runner/plugin_loader.py:301` — `except Exception:` → `except Exception as exc: logger.debug("模块路径解析失败: %s", exc)`
- [ ] 4.11 `runner/plugin_loader.py:530` — `except Exception:` → `except Exception as exc: logger.debug("插件加载失败: %s", exc)`
- [ ] 4.12 `runner/manifest_validator.py:1268` — `except Exception:` → `except Exception as exc: logger.debug("manifest 校验异常: %s", exc)`
- [ ] 4.13 `runner/manifest_validator.py:1295` — `except Exception:` → `except Exception as exc: logger.debug("manifest 校验异常: %s", exc)`
- [ ] 4.14 豁免确认：`runner/log_handler.py` 3 处保持原样

**验收**：`rg "except Exception:" src/plugin_runtime/` 仅剩 `log_handler.py` 3 处。

---

## T5: 代码质量提升 [P1]

**文件**：`src/plugin_runtime/integration.py`、`src/plugin_runtime/host/supervisor.py`

**步骤**：
- [ ] 5.1 删除 `_EVENT_TYPE_MAP`（L62-73），所有引用改为直接使用字符串
- [ ] 5.2 简化 `_instantiate_supervisor`（L247-271），移除 `inspect.signature` 反射，改为 `supervisor_cls(**kwargs)`
- [ ] 5.3 L296-302 — `getattr(supervisor, "set_blocked_plugin_reasons", None)` → `supervisor.set_blocked_plugin_reasons(...)`
- [ ] 5.4 L744 — `getattr(supervisor, "_registered_plugins", {})` → `supervisor.get_registered_plugins()`
- [ ] 5.5 L788-796 — `getattr(supervisor, "get_plugin_load_failure_reasons", None)` → `supervisor.get_plugin_load_failure_reasons()`
- [ ] 5.6 `supervisor.py` 新增 `get_registered_plugins()` 公开方法
- [ ] 5.7 验证：`rg "getattr.*supervisor" src/plugin_runtime/integration.py` 无结果

**验收**：integration.py 中无 `getattr(supervisor, ...)` 反射调用；无 `inspect.signature` 使用；`_EVENT_TYPE_MAP` 已删除。

---

## 执行顺序

T1 → T2 → T3 → T4 → T5

T1/T2 为 P0 可并行；T3 依赖 T2 的 Event 模式理解；T4/T5 独立可并行。

## 验证命令

```bash
# 全量测试
docker exec maim-bot-core bash -c "cd /MaiMBot && PYTHONPATH=/MaiMBot uv run pytest tests/ -v --tb=short -k plugin"

# 宽泛异常残留检查
rg "except Exception:" src/plugin_runtime/ --include="*.py"

# 反射调用残留检查
rg "getattr.*supervisor" src/plugin_runtime/integration.py

# RequestIdGenerator await 残留检查
rg "await.*\.next()" src/plugin_runtime/ --include="*.py"
```