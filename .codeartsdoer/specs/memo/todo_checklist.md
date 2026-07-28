# 待办清单

> 2026-07-27 整理，明天决定优先级

## CQ 债务（炉火纯青）

- [ ] CQ-16：子进程日志初始化 + emit_event 链路验证（差最后一公里）
- [ ] CQ-6：v2 EventDispatcher 闭环 + napcat-adapter 插件化（SSD 就绪）
- [ ] CQ-7：A_Memorix 最小修复 + 接口瘦身（SSD 就绪）
- [ ] CQ-11/14/13/15：Port 迁移残余（config_manager/heartflow_manager/chat_manager 直接导入）
- [ ] CQ-8：SQLAlchemy 3.14 兼容
- [ ] CQ-9x：napcat-adapter Tool 扩展（5→~30）

## Token 优化

- [ ] P1：session-rules 已完成条目归档（~3KB/轮）
- [ ] P4：AGENTS.md 精简（CX 侧）
- [ ] P3：CA 子代理使用规范（加到规则文件）
- [ ] P2：对话分段 + 交接文件（CQ 编号一个对话周期）
- [ ] P0：session-rules 分层加载（常驻 ~3KB + 按需加载）

## OS 化方向

- [ ] 服务管理器（systemd 化）：健康检查 + 失败策略
- [ ] 声明式启动依赖（拓扑排序 + 并行启动）
- [ ] 统一日志管线（journald 化）：结构化 + 可查询

## 启动编排

- [ ] 给 entrypoint.py 加日志初始化（CQ-16 的一部分）
- [ ] LogForwarder 防御（% 转义 + strip ANSI）
- [ ] Startup Trace（借鉴 OpenClaw，测每步耗时）
- [x] ~~Lazy Import~~ Python 3.15 特性，3.14.6 已有兼容问题，不升级
- [ ] Crash Loop Breaker（借鉴 OpenClaw，防无限重启）
- [ ] 启动算法实验（方案 A~F，等复杂度到阈值再比较）

## OpenClaw 借鉴

- [ ] SQLite-only storage（统一存储，减少碎片）
- [ ] doctor --fix migration（配置变更自动迁移）
- [x] ~~Lazy Import 模式~~ Python 3.15 特性，不适用
- [ ] Startup Trace 系统

## Maisaka 精简

- [ ] 评估多智能体协作层使用情况（管家/插话/回声检测在单聊场景是否激活）
- [ ] 决定：激活（群聊场景）or 精简（单聊场景不需要）

## Python 3.14.6

- [ ] WB 调研的 3.14.6 新特性（待 WB 交付报告）
- [ ] 明天：CA 指导用户写简单代码（热身）

## 备忘录文件索引

| 文件 | 内容 |
|------|------|
| `token_optimization.md` | Token 消耗优化规划 |
| `os_like_direction.md` | OS 化方向探索 |
| `startup_algorithms.md` | 启动编排算法方案集（A~F） |
| `component_map.md` | 组件地图（~120 个核心类） |