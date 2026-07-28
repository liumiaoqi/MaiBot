# 炉火纯青（ChunQing）— 编码任务

## T1: identity.py None 防御修复（CQ-3）

- [ ] 修复 `get_bot_account()` L58：`get_bot_config_port()` 返回 None 时返回 `""`
- [ ] 修复 `get_all_bot_accounts()` L73：`get_bot_config_port()` 返回 None 时返回 `{}`
- [ ] 验证 `is_bot_self()` 在 BotConfigPort 未注册时返回 `False`（应已安全，确认即可）
- [ ] 检查 `statistic.py` 是否有其他直接调用 `get_bot_config_port()` 的路径
- [ ] 单元测试：BotConfigPort 未注册时调用三个函数，验证返回安全默认值
- 验收：`get_bot_account("qq")` 在 port=None 时返回 `""`，不抛 AttributeError
- 负责人：Codex（定义清晰，机械修复）

## T2: bare `except:` 消除（CQ-1，4 处）

- [ ] `src/A_memorix/core/utils/io.py:53` — `except:` → `except (OSError, ValueError) as exc:` + logger.warning
- [ ] `src/A_memorix/core/utils/io.py:82` — 同上
- [ ] `src/A_memorix/core/storage/graph_store.py:1392` — `except:` → `except Exception as exc:` + logger.error
- [ ] `src/A_memorix/scripts/process_knowledge.py:212` — `except:` → `except Exception as exc:` + logger.error
- 验收：`grep -rn 'except:' src/` 返回 0（排除注释/字符串）
- 负责人：Codex（4 处纯替换）

## T3: `src/core/` 异常处理改造（~5 处）

- [ ] 逐处检查 `src/core/` 下 `except Exception: pass` 和 `except Exception:` 无日志
- [ ] 按设计文档日志级别判定规则添加日志
- [ ] 确保 `src/core/adapters/` 改造不破坏 Port 语义
- 验收：`src/core/` 下无 `except Exception: pass`
- 负责人：Codex（核心层面积小，风险低）

## T4: `src/maisaka/` 异常处理改造（~50 处）

- [ ] 按子模块分批改造：`agent/`、`agent_interaction/`、`agent_autonomy/`、`builtin_tool/`、`replyer/`、`display/`、`memory/`、`deepseek/`、`subagent/`、`relationship/`、其他
- [ ] 每个子模块改造后运行该模块相关测试（如有）
- [ ] 关键路径（runtime.py、chat_loop_service.py、orchestrator.py）使用 `logger.error + exc_info=True`
- [ ] 非关键路径使用 `logger.warning`
- 验收：`src/maisaka/` 下无 `except Exception: pass`
- 负责人：CC（面积大，需逐处判断日志级别）

## T5: `src/A_memorix/` 异常处理改造（~60 处）

- [ ] 按 `MODIFICATION_POLICY.md` 约束进行改造
- [ ] 按 service 模块分批：`kernel_initializer.py`、`vector_pool.py`、`embedding_recovery.py`、`feedback_correction.py`、其他
- [ ] A_memorix 内部已有 `get_logger` 模式，确保改造后一致
- 验收：`src/A_memorix/` 下无 `except Exception: pass`
- 负责人：CC（A_memorix 面积大，需逐处判断）

## T6: `src/webui/` + `src/services/` + `src/chat/` + `src/learners/` + 其他（~45 处）

- [ ] `src/webui/` ~15 处：routes/service 层，`logger.warning` 为主
- [ ] `src/services/` ~10 处：memory_flow_service 等关键服务用 `logger.error`
- [ ] `src/chat/` ~5 处
- [ ] `src/learners/` ~5 处
- [ ] `src/plugin_runtime/` + `src/plugin_runtime_v2/` + `src/main.py` + 其他 ~20 处
- 验收：对应目录下无 `except Exception: pass`
- 负责人：Codex（定义清晰，批量执行）

## T7: 全局验证 + ruff 守卫

- [ ] 运行 `ruff check src/ --select BLE`，确认 bare `except:` 为 0
- [ ] 运行一次性验证脚本：扫描 `except Exception:` 后跟 `pass` 的模式，确认为 0
- [ ] Docker 中启动 MaiBot，确认无 NameError
- [ ] 运行现有测试套件
- 验收：0 违规 + 启动正常 + 测试通过
- 负责人：CC（最终验证需 ruff 守卫 + Docker）

## T8: 系统协调调研（CQ-8 子项）

- [ ] 调研方向 1：V1/V2 双运行时启动序列竞态
- [ ] 调研方向 2：配置热重载跨子系统传播一致性
- [ ] 调研方向 3：关闭序列协调（gRPC + V1 IPC + HeartFlow 优雅退出）
- [ ] 调研方向 4：消息流在 V1/V2 双路径下的去重与顺序保证
- [ ] 产出调研报告：`.shared/handoff/ca2cc_chunqing_system_coordination_0726.md`
- 验收：报告覆盖 4 方向，每方向有明确结论和行动建议
- 负责人：CA（调研分析是 CA 核心能力）

## 依赖关系

```
T1 ──→ T7（identity.py 修复需在全局验证前完成）
T2 ──→ T7
T3 ──→ T7
T4 ──→ T7
T5 ──→ T7
T6 ──→ T7
T8（独立，无依赖）
```

T1~T6 可并行执行。T7 依赖所有改造完成。T8 独立执行。

## 派发建议

| 任务 | 负责人 | 理由 |
|------|--------|------|
| T1 | Codex | 定义清晰，机械修复 |
| T2 | Codex | 4 处纯替换 |
| T3 | Codex | 核心层面积小，风险低 |
| T4 | CC | 面积大，需逐处判断日志级别 |
| T5 | CC | A_memorix 面积大，需逐处判断 |
| T6 | Codex | 定义清晰，批量执行 |
| T7 | CC | 最终验证需 ruff 守卫 + Docker |
| T8 | CA | 调研分析是 CA 核心能力 |