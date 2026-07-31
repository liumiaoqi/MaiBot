# ZG-2 验收对照表（T-15.5 产出）

> 验收日期：2026-08-01
> 执行者：CC（maibot-zg2 worktree）
> 提交：zg2_log_pipeline 分支（T-03~T-15 共 8 个提交）

## 6 域 33 需求 + 49 验收映射

| 域 | 需求 | 验证结果 |
|----|------|---------|
| ING-01~04 | CQ-11 清理 + 入口约束 | ✅ A 类 12 文件 + B 类 2 文件清理；banned-api 防回归（TID251 实测） |
| BUF-01~05 | 环形缓冲 | ✅ 单测 8 + 集成验证（容量/ERROR 优先/双上限/截断/并发） |
| RTL-01~04 | ratelimit | ✅ 单测 6 + 集成验证（100→10 精确抑制/白名单/ERROR 豁免/摘要） |
| SUP-01~03 | 降级抑制 | ✅ 单测 8 + 集成验证（FAULT debug 抑制/豁免组件） |
| STT-01~02 | 状态衔接 | ✅ 接入点单测（注入/回退/异常隔离） |
| NFR-PER-01~03 | 性能 | ✅ 基准：0.0034ms / 0.0042ms / 330KB |
| NFR-REL-01~03 | 可靠性 | ✅ 异常隔离集成测试 + 崩溃导出 best-effort |
| NFR-MNT-01~02 | 配置/内省 | ✅ 12 键 + merge 兜底 + 8.26.0；/status 内省 |
| NFR-CMP-01~05 | 兼容 | ✅ JSONL/WS/API 契约不变；V1 不改；微内核（log_pipeline 不依赖 core） |

## 测试统计

- 新增单测/集成/基准：**31 个**（ring_buffer 8 + ratelimit 6 + suppressor 8 + integration 6 + benchmark 3）
- 全绿：31/31（benchmark 单独 -m benchmark 跑）
- 常规 pytest 正确排除 benchmark（28/31 collected）

## ruff

- 改动文件：**零告警**（T-01~T-14 涉及全部）
- 残留错误 = 基线文件（A_memorix scripts 其他 / core/types / memory_service / routing_adapter / orchestrator 等，与 main 基线一致）

## 启动冒烟（容器）

- ✅ import 正常、管线挂载（SuppressionFilter + RingBufferHandler）
- ✅ 日志落盘/缓冲写入/内省/摘要/崩溃导出工作
- ✅ /search?source=buffer + /status 端点存在
- ✅ 错误收集：容器 82 vs 基线 30（环境差异：镜像旧 pytests + config_manager 未初始化；**基线以 CA Windows 侧 30 为准，合并后 CA 重测确认**）

## 遗留

1. 容器 pytest 全量受环境限制（config_manager 初始化）——由 CA 在 Windows 侧重跑全量
2. ZG-2 合并后需 T-02 遗留的 dump 清理链实际运行验证（当前无 dump 文件进入清理窗口）
3. ZG-6 落地后接线 set_health_level_provider（预留完成）
