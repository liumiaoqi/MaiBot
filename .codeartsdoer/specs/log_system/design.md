# 日志与调试系统升级 — 设计方案

## L1：动态日志级别调整

### API 设计

```
GET  /api/webui/log/levels          → 返回所有模块当前级别
PATCH /api/webui/log/levels         → 修改指定模块级别
```

**GET 响应**：
```json
{
  "root": "DEBUG",
  "maisaka_runtime": "INFO",
  "agent_autonomy.orchestrator": "INFO",
  ...
}
```

**PATCH 请求**：
```json
{
  "modules": {
    "maisaka_runtime": "DEBUG",
    "agent_autonomy.orchestrator": "DEBUG"
  },
  "prefix": null
}
```

**PATCH 请求（前缀批量）**：
```json
{
  "modules": {},
  "prefix": {"maisaka": "DEBUG"}
}
```

### 实现

1. 新增 `src/webui/routers/log.py` 路由文件
2. `GET /levels`：遍历 `logging.getLogger().manager.loggerDict`，返回每个 logger 的有效级别
3. `PATCH /levels`：
   - 对每个模块调用 `logging.getLogger(name).setLevel(level)`
   - 前缀模式：遍历所有 loggerDict，匹配前缀的设置级别
   - 不写配置文件，仅内存生效
4. 注册路由到 `webui/routers/__init__.py`

## L2：日志搜索与过滤

### API 设计

```
GET /api/webui/log/search?module=maisaka&level=ERROR&since=2026-07-27T00:00&until=2026-07-27T23:59&keyword=异常&limit=200
```

### 实现

1. 在 `src/webui/routers/log.py` 新增 search 路由
2. 搜索逻辑：
   - 从 `logs/` 目录按修改时间倒序遍历 `app_*.log.jsonl`
   - 每个文件从末尾开始读（`seek` 到文件末尾，逐行倒序）
   - 对每行 JSON 解析后应用过滤条件
   - 达到 limit 或遍历完所有文件后返回
3. 过滤条件：
   - `module`：前缀匹配（`maisaka` 匹配 `maisaka_runtime`）
   - `level`：级别 >= 指定级别（`ERROR` 包含 ERROR + CRITICAL）
   - `since`/`until`：时间戳范围
   - `keyword`：event 字段包含关键词

### 性能

- 单个 JSONL 文件最大 5MB，倒序读取用 `seek` + 逐行解析
- 不加载全部文件到内存，流式读取
- limit 默认 100，最大 1000

## L3：ThinkCycleLog 可视化

### 数据写入

1. 新增 `src/common/logger.py` 中的 `log_think_cycle()` 函数
2. 写入独立 JSONL 文件 `logs/think_cycles_{timestamp}.log.jsonl`
3. 格式：
```json
{
  "timestamp": "2026-07-27T12:34:56.789",
  "agent_id": "silver_wolf",
  "session_id": "private_12345",
  "cycle_id": 42,
  "trigger_source": "message",
  "action": "REPLY",
  "silence_reason": null,
  "thought_summary": "用户问天气，决定回答",
  "duration_ms": 1234,
  "llm_calls": 1
}
```

### 在 ThinkingOrgan 中集成

1. `src/maisaka/agent_autonomy/thinking_organ.py` 的思考循环结束时调用 `log_think_cycle()`
2. 需确认 ThinkCycleLog 的产出点

### API 设计

```
GET /api/webui/log/think-cycles?agent_id=silver_wolf&since=2026-07-27T00:00&limit=50
```

### 实现

1. 在 `src/webui/routers/log.py` 新增 think-cycles 路由
2. 从 `logs/think_cycles_*.log.jsonl` 倒序读取
3. 支持按 agent_id、since、action 过滤

## 执行顺序

1. L1（动态级别调整）→ 最简，纯 API
2. L2（日志搜索）→ 增量，复用 JSONL 读取逻辑
3. L3（ThinkCycleLog）→ 需在 thinking_organ 中集成写入