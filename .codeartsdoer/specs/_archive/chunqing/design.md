# 炉火纯青（ChunQing）— 设计方案

## 1. 总体架构

改造分三个独立子系统，无相互依赖，可并行执行：

```
CQ-1 = 异常处理改造(CQ-9+CQ-10) + identity.py修复(CQ-3) + 系统协调调研(CQ-8)
```

## 2. 异常处理改造（CQ-9 + CQ-10）

### 2.1 改造策略

采用**分层改造 + ruff 守卫**方案：

1. **第一层：bare `except:` → `except Exception`**（4 处，纯替换）
2. **第二层：`except Exception: pass` → 添加日志**（160 处，逐处判断日志级别）
3. **第三层：`except Exception:` 无日志 → 补日志**（336 - 160 = 176 处，已有 `as exc` 但无 logger 调用）

### 2.2 日志级别判定规则

| 调用上下文 | 日志级别 | 理由 |
|-----------|---------|------|
| 核心消息管道（receive/think/respond） | `logger.error` + `exc_info=True` | 消息丢失是严重问题 |
| LLM 调用 | `logger.error` + `exc_info=True` | LLM 失败影响回复质量 |
| 数据库/存储写入 | `logger.error` + `exc_info=True` | 数据丢失不可接受 |
| 缓存操作 | `logger.warning` | 缓存失败可降级 |
| 统计/显示/渲染 | `logger.warning` | 非关键路径 |
| 配置热重载回调 | `logger.error` | 配置不一致影响全局 |
| 插件加载/通信 | `logger.warning` | 插件失败应隔离 |
| 启动初始化 | `logger.error` + 继续运行 | 启动失败需记录但不崩溃 |

### 2.3 改造模板

**模板 A：关键路径（error + exc_info）**
```python
# 改造前
except Exception:
    pass

# 改造后
except Exception as exc:
    logger.error("描述性消息: 详情", exc_info=True)
```

**模板 B：非关键路径（warning）**
```python
# 改造前
except Exception:
    pass

# 改造后
except Exception as exc:
    logger.warning("描述性消息: %s", exc)
```

**模板 C：bare except → 具体异常**
```python
# 改造前
except:
    pass

# 改造后
except (OSError, ValueError) as exc:
    logger.warning("IO/值错误: %s", exc)
```

### 2.4 ruff 守卫规则

新增 ruff 自定义规则（在 `pyproject.toml` 的 `lint.flake8-blind-except` 或自定义插件中）：

```toml
[tool.ruff.lint]
select = ["E", "F", "BLE"]  # BLE = blind except (已内置)

# 新增：检测 except Exception: pass 模式
# 需要自定义规则或使用 flake8-bugbear 的 B001
```

实际上 ruff 内置 `BLE001` 已检测 bare `except:`。对于 `except Exception: pass`，需要自定义规则或使用 `tryceratops` 的 `TRY003`/`TRY004`。**建议**：先不做自定义 ruff 规则（过度工程化），改造完成后用一次性脚本验证即可。

### 2.5 分批执行顺序

按模块分批，每批独立可验证：

| 批次 | 模块 | 预估处数 | 风险等级 |
|------|------|---------|---------|
| T1 | `src/core/` | ~5 | 低（核心已较规范） |
| T2 | `src/maisaka/` | ~50 | 中（面积大，需逐处判断） |
| T3 | `src/A_memorix/` | ~60 | 中（独立模块，可隔离测试） |
| T4 | `src/webui/` | ~15 | 低 |
| T5 | `src/services/` + `src/chat/` + `src/learners/` | ~30 | 中 |
| T6 | `src/plugin_runtime/` + `src/plugin_runtime_v2/` + `src/main.py` + 其他 | ~20 | 低 |
| T7 | bare `except:` 4 处 | 4 | 低（纯替换） |

## 3. identity.py None 防御修复（CQ-3）

### 3.1 修复方案

`_get_configured_qq_account()` 已有 None 检查（L41-42），但 `get_bot_account()` L58 和 `get_all_bot_accounts()` L73 仍直接调用 `get_bot_config_port()` 无 None 检查。

**修复**：提取 `_get_bot_config_port_safe()` 辅助函数，返回 port 或 None，调用方检查 None 后返回安全默认值。

```python
def _get_bot_config_port_safe():
    """获取 BotConfigPort，未注册时返回 None。"""
    return get_bot_config_port()

def get_bot_account(platform: str) -> str:
    port = _get_bot_config_port_safe()
    if port is None:
        return ""
    # ... 现有逻辑，用 port 替代 get_bot_config_port() 直接调用

def get_all_bot_accounts() -> dict[str, str]:
    port = _get_bot_config_port_safe()
    if port is None:
        return {}
    # ... 现有逻辑
```

### 3.2 statistic.py 时序竞争

`is_bot_self()` 已调用 `get_bot_account()` → `_get_configured_qq_account()`，后者已有 None 检查返回 `""`。所以 `is_bot_self()` 在 BotConfigPort 未注册时会返回 `False`（因为 `user_id` 不会等于空字符串），**已安全**。

需验证：`statistic.py` 是否还有其他直接调用 `get_bot_config_port()` 的路径。

## 4. 系统协调调研（CQ-8 子项）

### 4.1 调研方法

每个方向按以下步骤调研：

1. **代码走读**：阅读 bootstrap.py、main.py 启动序列，标注 V1/V2 初始化时序
2. **配置传播追踪**：grep `register_reload_callback` 和 `on_config_reload`，绘制回调链
3. **关闭序列追踪**：grep `shutdown`/`cleanup`/`atexit`/`signal`，绘制关闭顺序
4. **消息流追踪**：从 `message_receive` 入口追踪到 V1/V2 分发点，检查去重逻辑

### 4.2 调研产出

写入 `.shared/handoff/ca2cc_chunqing_system_coordination_0726.md`，格式：

```markdown
# 系统协调调研报告

## 方向 1：V1/V2 启动序列竞态
### 结论：有风险 / 无风险
### 风险描述：...
### 修复优先级：P0/P1/P2
### 预估工作量：X 人天

## 方向 2：配置热重载一致性
...
```

## 5. 验证方案

### 5.1 异常改造验证

1. **静态验证**：改造完成后运行 `ruff check src/ --select BLE`，应为 0 违规
2. **脚本验证**：一次性脚本扫描 `except Exception:` 后跟 `pass` 的模式，应为 0
3. **功能验证**：Docker 中启动 MaiBot，确认无 NameError（logger 变量引用正确）
4. **回归测试**：现有测试套件全部通过

### 5.2 identity.py 验证

1. **单元测试**：在 BotConfigPort 未注册时调用 `get_bot_account()`/`get_all_bot_accounts()`/`is_bot_self()`，验证返回安全默认值
2. **集成验证**：Docker 中启动，确认 statistic.py 不崩溃

### 5.3 调研验证

1. 报告覆盖 4 个方向
2. 每个方向有明确结论
3. 有风险的给出修复建议