# 日志与调试系统升级 — 编码任务

## T1：L1 动态日志级别调整 API

**负责人**：CC
**类型**：新 API 路由

### 步骤

- [ ] 新增 `src/webui/routers/log.py`：
  - `GET /api/webui/log/levels`：遍历 `logging.getLogger().manager.loggerDict`，返回每个 logger 的有效级别（`getEffectiveLevel()`）
  - `PATCH /api/webui/log/levels`：接受 `{modules: {name: level}, prefix: {prefix: level}}`，对每个模块调用 `setLevel`，前缀模式遍历匹配
  - 添加 `require_auth` 依赖
- [ ] 注册路由到 `src/webui/routers/__init__.py`
- [ ] 提交：`feat(webui): 动态日志级别调整 API [CC]`

## T2：L2 日志搜索 API

**负责人**：CC
**类型**：新 API + JSONL 读取逻辑

### 步骤

- [ ] 在 `src/webui/routers/log.py` 新增：
  - `GET /api/webui/log/search`：查询参数 module, level, since, until, keyword, limit
  - 实现倒序 JSONL 读取：从最新文件开始，每文件从末尾逐行解析
  - 应用过滤条件后返回
- [ ] 提交：`feat(webui): 日志搜索与过滤 API [CC]`

## T3：L3 ThinkCycleLog 写入

**负责人**：CC
**类型**：新增日志函数 + 集成到 thinking_organ

### 步骤

- [ ] 在 `src/common/logger.py` 新增 `log_think_cycle()` 函数：
  - 写入 `logs/think_cycles_{timestamp}.log.jsonl`
  - 使用独立 FileHandler 或直接 append 写入
- [ ] 在 `src/maisaka/agent_autonomy/thinking_organ.py` 的思考循环结束处调用 `log_think_cycle()`
  - 需确认 ThinkResult 的产出点，在产出时调用
- [ ] 提交：`feat(maisaka): ThinkCycleLog 写入 [CC]`

## T4：L3 ThinkCycleLog 查询 API

**负责人**：CC
**类型**：新 API

### 步骤

- [ ] 在 `src/webui/routers/log.py` 新增：
  - `GET /api/webui/log/think-cycles`：查询参数 agent_id, since, until, action, limit
  - 从 `logs/think_cycles_*.log.jsonl` 倒序读取
- [ ] 提交：`feat(webui): ThinkCycleLog 查询 API [CC]`

## T5：验证

**负责人**：CA

### 步骤

- [ ] 确认 API 路由注册成功（WebUI 启动无 404）
- [ ] 确认动态级别调整立即生效
- [ ] 确认日志搜索返回正确结果
- [ ] 确认 ThinkCycleLog 写入和查询正常