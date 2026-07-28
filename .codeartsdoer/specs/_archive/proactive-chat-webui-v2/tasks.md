# Proactive Chat WebUI v2 — 编码任务规划

> 基于需求规格 `spec.md` 和实现方案 `design.md` 生成
> 插件目录：`data/MaiMBot/plugins/proactive-chat/`
> 主要修改文件：`webui.py`（前端 HTML/CSS/JS + 后端 API）、`plugin.py`、`persistence.py`、`cooldown.py`
> 任务编号从 49 开始（原有任务 1-48 已完成）
> 前端约束：纯原生 HTML/CSS/JS，HTML 嵌入 Python 字符串 `_HTML_PAGE`，不引入外部 JS/CSS 库

---

## 49. WebUIServer 构造函数扩展与 WebSocket 连接管理

- [ ] 修改 `webui.py` 的 `WebUIServer.__init__()` 构造函数：
  - 新增参数 `agent`（`AgentCore` 类型，用于手动触发决策）
  - 新增参数 `config_getter: Callable`（用于读取当前配置）
  - 新增参数 `config_updater: Callable`（用于更新配置并回调 `on_config_update`）
  - 新增实例属性 `_ws_connections: set[web.WebSocketResponse] = set()`
  - 新增实例属性 `_trigger_timestamps: dict[str, float] = {}`（手动触发频率限制）
  - 保留现有的 `_cooldown`、`_persistence`、`_app`、`_runner`、`_site` 属性
- [ ] 实现 `_handle_ws(request: web.Request)` 异步方法：
  - 验证请求 Origin 头，仅允许同源连接（`request.headers.get('Origin', '')` 与 `request.host` 比对）
  - 非同源返回 HTTP 403
  - 执行 WebSocket 升级：`ws = web.WebSocketResponse()`，`await ws.prepare(request)`
  - 加入 `_ws_connections` 集合
  - 进入消息循环：`async for msg in ws:`，忽略客户端发送的消息（仅服务端推送）
  - 连接断开时从 `_ws_connections` 移除
  - 内部 try/except 包裹，确保异常不影响其他连接
- [ ] 实现 `broadcast_event(event_type: str, data: dict)` 异步方法：
  - 构建消息：`{"type": event_type, "data": data, "timestamp": time.time()}`
  - 遍历 `_ws_connections`，向每个连接发送 JSON 消息
  - 发送失败（连接已断开）时从集合中移除该连接
  - 内部 try/except 包裹，确保广播失败不影响调用方
  - 无活跃连接时直接返回，不做任何操作
- [ ] 在 `start()` 方法中注册 WebSocket 路由：`self._app.router.add_get("/ws/proactive-chat", self._handle_ws)`
- [ ] 在 `stop()` 方法中关闭所有 WebSocket 连接：遍历 `_ws_connections` 调用 `ws.close()`，然后清空集合
- 涉及文件：`plugins/proactive-chat/webui.py`
- 验收方式：`WebUIServer` 可接受 WebSocket 连接升级；`broadcast_event()` 可向所有活跃连接发送消息；连接断开时自动从集合移除；非同源请求被拒绝；广播失败不影响业务逻辑

**依赖**：无（webui.py 现有代码已稳定）

---

## 50. 前端 WebSocket 客户端与连接状态指示器

- [ ] 在 `_HTML_PAGE` 的 `<style>` 中新增连接状态指示器样式：
  - `.ws-status`：`display:inline-flex;align-items:center;gap:6px;font-size:.8rem`
  - `.ws-dot`：`width:8px;height:8px;border-radius:50%`
  - `.ws-dot.connected`：`background:var(--green)`
  - `.ws-dot.polling`：`background:var(--yellow)`
  - `.ws-dot.disconnected`：`background:var(--red)`
- [ ] 修改页面头部 `.header .status` 区域，替换现有 `.dot` 为连接状态指示器：
  - 显示连接状态圆点 + 文字（"实时连接" / "轮询模式" / "连接断开"）
- [ ] 在 `<script>` 中新增 WebSocket 客户端逻辑：
  - `let ws = null` — WebSocket 实例
  - `let wsReconnectDelay = 1000` — 重连延迟
  - `const WS_MAX_DELAY = 30000` — 最大重连延迟
  - `const WS_THROTTLE_MS = 500` — 消息节流间隔
  - `let wsLastProcessTime = 0` — 上次处理消息时间
  - `let wsPendingMsg = null` — 待处理的最新消息
  - `let wsPendingCount = 0` — 待处理消息计数
- [ ] 实现 `connectWS()` 函数：
  - 构建 WebSocket URL：`ws://` + `location.host` + `/ws/proactive-chat`
  - 创建 `new WebSocket(url)`
  - `onopen`：设置 `wsReconnectDelay = 1000`，更新状态指示器为"实时连接"绿色，停止轮询（`clearInterval(refreshTimer)`）
  - `onmessage`：调用 `handleWSMessage(event.data)` 处理消息
  - `onclose`：更新状态指示器为"连接断开"红色，恢复轮询（10 秒间隔），启动重连定时器
  - `onerror`：同 `onclose` 处理
- [ ] 实现 `handleWSMessage(data)` 函数：
  - 解析 JSON 消息，获取 `type` 和 `data` 字段
  - 消息节流：如果距上次处理不足 500ms，缓存该消息，递增 `wsPendingCount`，延迟处理
  - 处理消息时：如果 `wsPendingCount > 1`，Toast 显示"收到 N 条新决策"合并通知
  - 根据 `type` 分发处理：
    - `new_decision`：显示 Toast 通知，刷新决策记录和统计
    - `cooldown_started` / `cooldown_expired` / `cooldown_reset`：刷新冷却状态
    - `phase_changed`：局部更新对应记录行的处理阶段标签
    - `config_updated`：刷新配置页面（如果当前在配置标签页）
  - 每次收到消息后触发一次完整数据刷新，确保数据一致性
- [ ] 实现 `reconnectWS()` 函数：
  - 指数退避：`setTimeout(connectWS, wsReconnectDelay)`
  - `wsReconnectDelay = Math.min(wsReconnectDelay * 2, WS_MAX_DELAY)`
- [ ] 修改 `init()` 函数，在末尾调用 `connectWS()`
- [ ] 修改轮询逻辑：WebSocket 连接成功时停止轮询，断开时恢复轮询
- 涉及文件：`plugins/proactive-chat/webui.py`（`_HTML_PAGE` 常量）
- 验收方式：页面加载后自动建立 WebSocket 连接；连接状态指示器正确显示当前状态；WebSocket 断线后自动重连（指数退避）；消息节流避免频繁 DOM 操作；降级为轮询时数据仍可正常更新

**依赖**：任务 49（后端 WebSocket 端点已注册）

---

## 51. Toast 通知组件

- [ ] 在 `_HTML_PAGE` 的 `<style>` 中新增 Toast 样式：
  - `.toast-container`：`position:fixed;bottom:20px;right:20px;z-index:1000;display:flex;flex-direction:column;gap:8px;max-width:360px`
  - `.toast`：`background:var(--card);border:1px solid var(--border);border-left:3px solid var(--accent);border-radius:8px;padding:12px 16px;font-size:.85rem;box-shadow:0 4px 12px rgba(0,0,0,.3);opacity:0;transform:translateX(100%);transition:opacity .25s,transform .25s`
  - `.toast.show`：`opacity:1;transform:translateX(0)`
  - `.toast.hide`：`opacity:0;transform:translateX(100%);transition:opacity .2s,transform .2s`
  - `.toast-title`：`font-weight:600;margin-bottom:4px`
  - `.toast-body`：`color:var(--text2);font-size:.8rem`
- [ ] 在 `<body>` 末尾新增 Toast 容器：`<div class="toast-container" id="toast-container"></div>`
- [ ] 在 `<script>` 中实现 Toast 通知系统：
  - `const MAX_TOASTS = 3` — 最多同时显示 3 条
  - `let activeToasts = []` — 当前活跃 Toast 列表
  - `let toastQueue = []` — 等待队列
  - 实现 `showToast(title, body, duration=5000)` 函数：
    - 创建 Toast DOM 元素，设置标题和内容
    - 如果活跃 Toast 数量已达上限，加入等待队列
    - 添加到容器，触发 `show` 类名切换（滑入动画 250ms）
    - `duration` 毫秒后调用 `hideToast()` 滑出（200ms），然后移除 DOM
    - 移除后检查等待队列，显示下一条
  - 实现 `hideToast(toastEl)` 函数：添加 `hide` 类名，200ms 后移除 DOM
- [ ] 在 `handleWSMessage()` 的 `new_decision` 处理中调用 `showToast()`：
  - 标题格式："新决策：{意图名称}"
  - 内容格式："{动作标签}，置信度 {confidence}"
  - 点击 Toast 时滚动到对应决策记录行并高亮
- 涉及文件：`plugins/proactive-chat/webui.py`（`_HTML_PAGE` 常量）
- 验收方式：WebSocket 推送新决策时右下角显示 Toast 通知；Toast 5 秒后自动消失；最多同时 3 条，多的排队等待；Toast 出入场有滑入/滑出动画

**依赖**：任务 50（WebSocket 客户端已实现，`handleWSMessage` 已有框架）

---

## 52. 事件广播集成：plugin.py 调用 broadcast_event

- [ ] 修改 `plugin.py` 的 `on_load()` 中 `WebUIServer` 初始化：
  - 传入 `agent=self._agent`
  - 传入 `config_getter=lambda: self._config`（或使用 `functools.partial`）
  - 传入 `config_updater=self._handle_webui_config_update`（新增方法，见任务 56）
  - 示例：`self._webui = WebUIServer(cooldown_manager=..., persistence_manager=..., agent=self._agent, config_getter=..., config_updater=...)`
- [ ] 修改 `agent.py` 的 `AgentCore`，新增 `webui` 属性：
  - 在 `__init__` 中新增 `webui: WebUIServer | None = None` 参数（默认 None）
  - 保存为 `self._webui`
  - 在 `decision_loop()` 各阶段调用 `self._broadcast_if_available()`：
    - 感知阶段开始前：`phase_changed`，`{stream_id, phase: "perceiving"}`
    - 推理阶段开始前：`phase_changed`，`{stream_id, phase: "reasoning"}`
    - 行动阶段开始前：`phase_changed`，`{stream_id, phase: "acting"}`
    - 反思阶段完成后：`new_decision`，`{stream_id, action_taken, intent?, confidence?, record_status}`
  - 实现 `_broadcast_if_available(event_type, data)` 方法：
    - 如果 `self._webui` 不为 None，调用 `asyncio.create_task(self._webui.broadcast_event(event_type, data))`
    - 内部 try/except，确保广播失败不影响决策循环
- [ ] 修改 `plugin.py` 的 `on_load()`，在创建 `AgentCore` 后设置 `self._agent._webui = self._webui`
- [ ] 修改 `cooldown.py` 的 `CooldownManager`，新增 `webui` 属性：
  - 在 `__init__` 中新增 `webui: WebUIServer | None = None` 参数（默认 None）
  - 保存为 `self._webui`
  - 在 `mark_triggered()` 中，持久化成功后调用 `self._broadcast_if_available("cooldown_started", {stream_id, intent?, remaining_seconds})`
  - 实现 `_broadcast_if_available()` 方法（同 AgentCore 中的模式）
- [ ] 修改 `plugin.py` 的 `on_load()`，在创建 `CooldownManager` 后设置 `self._cooldown_manager._webui = self._webui`
- [ ] 修改 `webui.py` 的 `_handle_cooldown_reset()` 方法，在重置成功后调用 `self.broadcast_event("cooldown_reset", {stream_id, remaining_seconds: 0})`
- 涉及文件：`plugins/proactive-chat/webui.py`、`plugins/proactive-chat/agent.py`、`plugins/proactive-chat/cooldown.py`、`plugins/proactive-chat/plugin.py`
- 验收方式：决策循环各阶段触发 WebSocket 事件推送；冷却开始/重置触发事件推送；广播失败不影响业务逻辑；无 WebSocket 连接时跳过广播

**依赖**：任务 49（`broadcast_event` 方法已实现）

---

## 53. 统计概览 API 扩展：intent_distribution 字段

- [ ] 修改 `webui.py` 的 `_handle_stats()` 方法，在响应数据中新增 `intent_distribution` 字段：
  - 初始化：`intent_distribution = {"topic_supplement": 0, "silence_break": 0, "missed_reply": 0, "memory_recall": 0}`
  - 遍历 `today_decisions`，提取 `analysis_result.intent`，匹配则递增对应计数
  - 将 `intent_distribution` 加入响应 `data` 字典
- [ ] 确保统计缓存（`_stats_cache_data`）包含新增字段
- 涉及文件：`plugins/proactive-chat/webui.py`
- 验收方式：`GET /api/proactive-chat/stats` 响应包含 `intent_distribution` 字段，各意图计数正确；无决策记录时所有值为 0

**依赖**：无（`_handle_stats` 现有代码已稳定）

---

## 54. 决策分布饼图（conic-gradient 环形图）

- [ ] 在 `_HTML_PAGE` 的 `<style>` 中新增饼图样式：
  - `.pie-chart-container`：`display:flex;align-items:center;gap:16px;margin-top:12px`
  - `.pie-chart`：`width:120px;height:120px;border-radius:50%;position:relative;background:conic-gradient(...)`，使用 CSS 变量设置各扇区颜色
  - `.pie-chart.empty`：`background:var(--border)`，中心显示"暂无数据"
  - `.pie-hole`：`position:absolute;width:60px;height:60px;border-radius:50%;background:var(--card);top:50%;left:50%;transform:translate(-50%,-50%);display:flex;align-items:center;justify-content:center;font-size:.75rem;color:var(--text2)`
  - `.pie-legend`：`display:flex;flex-direction:column;gap:6px`
  - `.pie-legend-item`：`display:flex;align-items:center;gap:8px;font-size:.8rem`
  - `.pie-legend-dot`：`width:10px;height:10px;border-radius:50%`
  - `.pie-tooltip`：`position:absolute;background:var(--card);border:1px solid var(--border);border-radius:6px;padding:6px 10px;font-size:.75rem;pointer-events:none;z-index:100;white-space:nowrap;box-shadow:0 2px 8px rgba(0,0,0,.3)`
  - 条形图降级样式 `.bar-fallback`：`display:flex;flex-direction:column;gap:4px;width:100%`
  - `.bar-fallback-item`：`display:flex;align-items:center;gap:8px;font-size:.75rem`
  - `.bar-fallback-bar`：`height:8px;border-radius:4px;transition:width .3s`
- [ ] 在统计概览卡片中新增饼图容器：`<div id="pie-chart-content"></div>`
- [ ] 在 `<script>` 中实现 `renderPieChart(d)` 函数：
  - 从 `statsData.intent_distribution` 获取数据
  - 检测 `conic-gradient` 支持：创建临时元素，设置 `background: conic-gradient(red, blue)`，检查是否生效
  - 支持时：计算各扇区角度，生成 `conic-gradient` 值，渲染环形饼图 + 图例
  - 不支持时：降级为横向条形图
  - 无数据时：显示灰色空心圆环 + "暂无数据"
  - 某意图占比为 0 时：不显示扇区，但图例中仍列出
  - 鼠标悬停显示 tooltip：意图名称、决策数、占比
- [ ] 修改 `loadStats()` 函数，在渲染统计项后调用 `renderPieChart(d)`
- 涉及文件：`plugins/proactive-chat/webui.py`（`_HTML_PAGE` 常量）
- 验收方式：统计概览卡片显示决策意图分布环形饼图；各扇区颜色与 badge 颜色一致；鼠标悬停显示 tooltip；无数据时显示空状态；不支持 conic-gradient 时降级为条形图

**依赖**：任务 53（`intent_distribution` 数据已可用）

---

## 55. 冷却时间线视图

- [ ] 在 `_HTML_PAGE` 的 `<style>` 中新增时间线样式：
  - `.timeline-container`：`margin-top:16px;overflow-x:auto`
  - `.timeline-row`：`display:flex;align-items:center;height:32px;margin-bottom:4px;position:relative`
  - `.timeline-label`：`width:120px;font-size:.75rem;color:var(--text2);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;flex-shrink:0`
  - `.timeline-track`：`flex:1;height:16px;background:var(--border);border-radius:8px;position:relative;overflow:hidden`
  - `.timeline-band`：`position:absolute;height:100%;border-radius:8px;opacity:.6`
  - `.timeline-band.active`：`background:var(--accent)`
  - `.timeline-band.expired`：`background:var(--accent);opacity:.3;border:1px dashed var(--accent2)`
  - `.timeline-dot`：`position:absolute;width:8px;height:8px;border-radius:50%;background:var(--green);top:50%;transform:translateY(-50%);z-index:2`
  - `.timeline-axis`：`display:flex;justify-content:space-between;font-size:.65rem;color:var(--text2);margin-top:4px;padding-left:120px`
  - `.timeline-tooltip`：同饼图 tooltip 样式
- [ ] 在冷却状态卡片中新增时间线容器：`<div id="timeline-content"></div>`
- [ ] 在 `<script>` 中实现 `renderTimeline(cooldownData)` 函数：
  - 时间范围：最近 2 小时（左端 = 2 小时前，右端 = 当前时刻）
  - 遍历冷却记录，每个聊天流占一行
  - 计算触发圆点位置：`(triggered_at - rangeStart) / rangeDuration * 100%`
  - 计算冷却色带位置和宽度：从触发点延伸到冷却到期
  - 已过冷却期的色带使用虚线样式
  - 无冷却记录时显示"暂无冷却记录"空状态
  - 鼠标悬停显示 tooltip（触发时间、意图、剩余冷却时间）
- [ ] 修改 `loadCooldown()` 函数，在渲染冷却列表后调用 `renderTimeline(d)`
- 涉及文件：`plugins/proactive-chat/webui.py`（`_HTML_PAGE` 常量）
- 验收方式：冷却状态卡片下方显示水平时间线；每个聊天流占一行，触发时刻标记为圆点，冷却区间标记为色带；已过冷却期显示虚线；鼠标悬停显示 tooltip；无冷却记录时显示空状态

**依赖**：无（冷却 API 数据已足够）

---

## 56. 置信度分布直方图

- [ ] 在 `_HTML_PAGE` 的 `<style>` 中新增直方图样式：
  - `.histogram-container`：`margin-top:16px`
  - `.histogram-bars`：`display:flex;align-items:flex-end;gap:4px;height:80px`
  - `.histogram-bar-group`：`flex:1;display:flex;flex-direction:column;align-items:center`
  - `.histogram-bar`：`width:100%;border-radius:4px 4px 0 0;background:var(--accent);transition:height .3s;min-height:0`
  - `.histogram-bar.empty`：`background:var(--border);min-height:2px`
  - `.histogram-label`：`font-size:.65rem;color:var(--text2);margin-top:4px;text-align:center`
  - `.histogram-count`：`font-size:.7rem;color:var(--text);margin-bottom:2px`
- [ ] 在统计概览卡片中新增直方图容器：`<div id="histogram-content"></div>`
- [ ] 在 `<script>` 中实现 `renderHistogram(d)` 函数：
  - 从 `statsData` 中提取置信度数据（需新增 API 字段，见下方）
  - 5 个区间：0-0.2、0.2-0.4、0.4-0.6、0.6-0.8、0.8-1.0
  - 计算每个区间的记录数
  - 渲染柱状图，柱子高度按比例计算
  - 某区间无记录时柱子高度为 0，显示最小高度占位
  - 柱子上方显示记录数
- [ ] 修改 `_handle_stats()` API，新增 `confidence_distribution` 字段：
  - 遍历 `today_decisions`，提取 `analysis_result.confidence`
  - 按 5 个区间统计计数
  - 格式：`{"0-0.2": N, "0.2-0.4": N, "0.4-0.6": N, "0.6-0.8": N, "0.8-1.0": N}`
- [ ] 修改 `loadStats()` 函数，在渲染统计项后调用 `renderHistogram(d)`
- 涉及文件：`plugins/proactive-chat/webui.py`（`_HTML_PAGE` 常量 + `_handle_stats` 方法）
- 验收方式：统计概览卡片显示置信度分布直方图；5 个区间柱子高度按比例渲染；某区间无记录时柱子高度为 0；柱子上方显示记录数

**依赖**：任务 53（`_handle_stats` 已扩展，可在此基础上新增字段）

---

## 57. 数据导出 API（CSV/JSON）

- [ ] 在 `webui.py` 中实现 `_handle_export(request: web.Request)` 异步方法：
  - 解析查询参数：`format`（csv/json，必填）、`stream_id`、`intent`、`action`、`record_status`、`start_time`、`search`
  - 调用 `self._persistence.query_decisions()` 按筛选条件查询全部记录（`limit=0`）
  - 如果记录数 > 5000，先返回 `{confirm_required: true, count: N}` 供前端确认
  - CSV 格式：
    - 设置响应头：`Content-Type: text/csv; charset=utf-8`，`Content-Disposition: attachment; filename="proactive-decisions-YYYY-MM-DD.csv"`
    - 首行写入 BOM（`\ufeff`）确保 Excel 正确识别 UTF-8
    - 表头：时间、聊天流、意图、置信度、动作、原因、状态、耗时
    - 每条记录一行，字段用逗号分隔，文本字段用双引号包裹
  - JSON 格式：
    - 设置响应头：`Content-Type: application/json; charset=utf-8`，`Content-Disposition: attachment; filename="proactive-decisions-YYYY-MM-DD.json"`
    - 返回与 `_handle_decisions` 的 records 格式一致的 JSON 数组
  - 异常处理：try/except 包裹，失败返回 `{success: false, error: "..."}`
- [ ] 在 `start()` 方法中注册新路由：`self._app.router.add_get("/api/proactive-chat/decisions/export", self._handle_export)`
- 涉及文件：`plugins/proactive-chat/webui.py`
- 验收方式：`GET /api/proactive-chat/decisions/export?format=csv` 返回 CSV 文件下载；`format=json` 返回 JSON 文件下载；文件名包含日期；CSV 包含 8 列且 Excel 可正确打开；超过 5000 条时返回确认提示

**依赖**：无（`query_decisions` 已支持筛选参数）

---

## 58. 前端数据导出按钮与交互

- [ ] 在 `_HTML_PAGE` 的决策记录工具栏中新增导出按钮组：
  - "导出 CSV" 按钮：`<button onclick="exportData('csv')">导出 CSV</button>`
  - "导出 JSON" 按钮：`<button onclick="exportData('json')">导出 JSON</button>`
  - 按钮样式：与现有"筛选"按钮一致，但使用 `var(--card)` 背景区分
- [ ] 在 `<script>` 中实现 `exportData(format)` 函数：
  - 构建导出 URL：`/api/proactive-chat/decisions/export?format=` + format + 当前筛选参数
  - 使用 `fetch()` 发送请求
  - 如果响应 Content-Type 为 JSON 且包含 `confirm_required`：
    - 弹出确认对话框："将导出 N 条记录，文件可能较大，是否继续？"
    - 确认后重新请求（附加 `&confirmed=true` 参数）
  - 如果响应为文件下载：
    - 从 Content-Disposition 提取文件名
    - 创建 Blob 和临时 `<a>` 元素触发下载
  - 当前筛选结果为空时：导出按钮禁用，显示"无数据可导出"提示
  - 导出超时（30 秒）时：显示"导出超时，请缩小筛选范围后重试"提示
- [ ] 修改 `_handle_export` 支持确认参数：`confirmed=true` 时跳过确认提示直接导出
- [ ] 修改 `loadDecisions()` 函数，根据 `total` 值更新导出按钮状态（total=0 时禁用）
- 涉及文件：`plugins/proactive-chat/webui.py`（`_HTML_PAGE` 常量 + `_handle_export` 方法）
- 验收方式：点击"导出 CSV"按钮触发文件下载；点击"导出 JSON"按钮触发文件下载；超过 5000 条时弹出确认对话框；无数据时按钮禁用；导出超时显示提示

**依赖**：任务 57（导出 API 已实现）

---

## 59. 搜索增强：后端 search 参数与前端搜索框

- [ ] 修改 `persistence.py` 的 `query_decisions()` 方法签名，新增 `search: str = ""` 参数：
  - 透传到 `_query_decisions_sync()` 内部方法
- [ ] 修改 `_query_decisions_sync()` 方法，新增搜索过滤逻辑：
  - 如果 `search` 非空，转为小写 `search_lower`
  - 对每条记录，检查 `input_summary` 和 `analysis_result.reason` 是否包含 `search_lower`
  - 不匹配的记录跳过
  - 搜索关键词最大长度 200 字符（在 API 层截断）
- [ ] 修改 `webui.py` 的 `_handle_decisions()` 方法，新增 `search` 查询参数：
  - `search = request.query.get("search", "")[:200]`
  - 透传到 `query_decisions(search=search)` 调用
- [ ] 在 `_HTML_PAGE` 的决策记录工具栏中新增搜索输入框：
  - `<input id="filter-search" placeholder="搜索原因或摘要..." style="width:180px" maxlength="200">`
  - 按回车触发搜索：`onkeydown="if(event.key==='Enter')loadDecisions()"`
- [ ] 修改 `loadDecisions()` 函数，在请求 URL 中新增 `search` 参数：
  - `const search = document.getElementById('filter-search').value.trim()`
  - `if(search) url += '&search=' + encodeURIComponent(search)`
- [ ] 实现搜索高亮功能：
  - 新增 `highlightText(text, keyword)` JS 函数：
    - 如果 `keyword` 非空且 `text` 包含关键词（不区分大小写），将匹配文本用 `<mark>` 标签包裹
    - `<mark>` 样式：`background:var(--yellow);color:var(--bg);border-radius:2px;padding:0 2px`
  - 修改 `renderDecisionsTable()` 中原因列和详情面板的渲染，对搜索关键词调用 `highlightText()`
  - 搜索框为空时不添加高亮
- 涉及文件：`plugins/proactive-chat/persistence.py`、`plugins/proactive-chat/webui.py`
- 验收方式：在搜索框输入关键词按回车后，仅显示匹配的决策记录；原因列和详情面板中匹配文本高亮显示；搜索结果为空时显示"未找到匹配的决策记录"；搜索框为空时不发送搜索请求

**依赖**：无（persistence.py 和 webui.py 现有代码已稳定）

---

## 60. 配置在线编辑：后端 API

- [ ] 在 `webui.py` 中实现 `_handle_get_config(request: web.Request)` 异步方法：
  - 通过 `self._config_getter()` 获取当前 `ProactiveChatConfig` 实例
  - 调用 `mask_config_for_display()` 将配置转为字典，敏感字段脱敏
  - 返回 `web.json_response(data)`
- [ ] 实现 `mask_config_for_display(config: ProactiveChatConfig) -> dict` 模块级函数：
  - 调用 `config.model_dump()` 获取完整字典
  - 对 `deepseek_api_key` 字段脱敏：非空时显示为 `sk-***...***`（前 3 位 + `***` + 后 3 位），空值显示空字符串
  - 返回脱敏后的字典
- [ ] 实现 `_handle_update_config(request: web.Request)` 异步方法：
  - 读取请求体 JSON（部分更新的配置字段）
  - 读取当前完整配置：`current_config = self._config_getter()`
  - 合并修改字段到当前配置字典
  - 使用 `ProactiveChatConfig(**merged)` 校验
  - 校验失败返回 `{success: false, error: "校验错误信息"}`
  - 校验通过后调用 `self._config_updater(merged)` 更新配置
  - 记录配置修改审计日志（修改了哪些字段、旧值、新值）
  - 成功后调用 `self.broadcast_event("config_updated", {"updated_fields": list(updated_keys)})`
  - 返回 `{success: true}` 或 `{success: false, error: "..."}`
  - 失败时前端应回滚到修改前的值（由前端负责）
- [ ] 在 `start()` 方法中注册新路由：
  - `self._app.router.add_get("/api/proactive-chat/config", self._handle_get_config)`
  - `self._app.router.add_post("/api/proactive-chat/config", self._handle_update_config)`
- [ ] 在 `plugin.py` 中实现 `_handle_webui_config_update(merged_data)` 方法：
  - 将合并后的配置写入 `config.toml` 文件
  - 调用 `self.on_config_update()` 触发配置热更新
  - 返回更新是否成功
- 涉及文件：`plugins/proactive-chat/webui.py`、`plugins/proactive-chat/plugin.py`
- 验收方式：`GET /api/proactive-chat/config` 返回脱敏后的配置；`POST /api/proactive-chat/config` 可更新配置并即时生效；敏感字段脱敏显示；配置修改审计日志记录完整；更新失败时返回错误信息

**依赖**：任务 49（WebUIServer 构造函数已扩展，包含 `config_getter` 和 `config_updater`）

---

## 61. 配置在线编辑：前端配置标签页与表单

- [ ] 在 `_HTML_PAGE` 的 `<style>` 中新增标签页样式：
  - `.tabs`：`display:flex;gap:0;border-bottom:2px solid var(--border);margin-bottom:20px`
  - `.tab-btn`：`padding:10px 24px;font-size:.9rem;color:var(--text2);cursor:pointer;border:none;background:none;border-bottom:2px solid transparent;margin-bottom:-2px;transition:color .2s,border-color .2s`
  - `.tab-btn.active`：`color:var(--accent);border-bottom-color:var(--accent)`
  - `.tab-btn:hover`：`color:var(--text)`
  - `.tab-content`：`display:none;opacity:0;transition:opacity .2s`
  - `.tab-content.active`：`display:block;opacity:1`
  - 配置表单样式：
    - `.config-section`：`margin-bottom:24px`
    - `.config-section h3`：`font-size:.95rem;font-weight:600;margin-bottom:12px;color:var(--accent2)`
    - `.config-field`：`display:flex;align-items:center;gap:12px;margin-bottom:10px`
    - `.config-label`：`min-width:160px;font-size:.85rem;color:var(--text2)`
    - `.config-input`：`background:var(--bg);border:1px solid var(--border);color:var(--text);padding:6px 12px;border-radius:6px;font-size:.85rem;flex:1;max-width:300px`
    - `.config-input:focus`：`border-color:var(--accent);outline:none`
    - `.config-error`：`color:var(--red);font-size:.75rem;margin-top:4px`
    - `.config-actions`：`display:flex;gap:12px;margin-top:20px`
- [ ] 修改页面结构，将现有内容包裹在"数据面板"标签页中，新增"配置"标签页：
  - 页面头部下方新增标签页导航：`<div class="tabs"><button class="tab-btn active" onclick="switchTab('dashboard')">数据面板</button><button class="tab-btn" onclick="switchTab('config')">配置</button></div>`
  - 现有内容包裹在 `<div class="tab-content active" id="tab-dashboard">...</div>`
  - 新增 `<div class="tab-content" id="tab-config">...</div>`
- [ ] 在 `<script>` 中实现标签页切换逻辑：
  - `let currentTab = 'dashboard'`
  - `switchTab(tab)` 函数：切换 `active` 类名，更新 `currentTab`
- [ ] 实现配置表单渲染 `loadConfig()` 函数：
  - 调用 `GET /api/proactive-chat/config` 获取配置
  - 按 `ProactiveChatConfig` 的嵌套配置段分组展示
  - 每个配置段一个 `<div class="config-section">`
  - 布尔字段渲染为复选框
  - 数值字段渲染为数字输入框
  - 字符串字段渲染为文本输入框
  - `deepseek_api_key` 字段使用 `type="password"` 输入框
  - 保存原始值用于回滚
- [ ] 实现配置保存 `saveConfig()` 函数：
  - 收集表单中修改过的字段（与原始值对比）
  - 前端校验：
    - `cooldown_seconds` ≥ 60
    - `deepseek_temperature` 0.0-2.0
    - 其他数值字段按 `Field(ge=..., le=...)` 约束校验
  - 校验失败在对应字段下方显示错误提示
  - 校验通过后弹出确认对话框："确认保存配置修改？"
  - 调用 `POST /api/proactive-chat/config` 提交修改
  - 成功后显示"保存成功"提示
  - 失败时回滚表单值到修改前，显示"保存失败：[错误信息]"
- [ ] 实现敏感字段交互：
  - `deepseek_api_key` 输入框点击时清空脱敏值，允许输入新值
  - 未修改时提交空值（不覆盖现有值）
- 涉及文件：`plugins/proactive-chat/webui.py`（`_HTML_PAGE` 常量）
- 验收方式：页面顶部显示"数据面板"和"配置"两个标签页；点击"配置"切换到配置编辑界面；配置按段分组展示；修改配置后点击保存可即时生效；校验失败显示错误提示；保存失败回滚表单值；敏感字段脱敏展示

**依赖**：任务 60（配置 API 已实现）

---

## 62. 手动触发决策：后端 API

- [ ] 在 `webui.py` 中实现 `_handle_trigger(request: web.Request)` 异步方法：
  - 读取请求体 JSON：`stream_id`（必填）、`force`（可选，默认 false）
  - 校验 `stream_id` 非空
  - 频率限制检查：`_check_trigger_cooldown(stream_id)`
    - 同一 `stream_id` 30 秒内仅允许一次手动触发
    - 不满足时返回 `{success: false, error: "请等待 30 秒后重试"}`
  - 非强制模式下：
    - 白名单校验：调用 `self._config_getter().scope` 检查 `stream_id` 是否在白名单
    - 不在白名单时返回 `{success: false, error: "该聊天流不在白名单范围内，无法触发"}`
    - 冷却校验：调用 `self._cooldown.is_cooled_down(stream_id)` 检查是否在冷却期
    - 在冷却期时返回 `{success: false, error: "该聊天流正在冷却中，请等待冷却结束"}`
  - 触发决策：`asyncio.create_task(self._agent.decision_loop(stream_id=stream_id, ctx=None, config=self._config_getter()))`
    - 注意：手动触发时 `ctx` 为 None，需确保 `decision_loop` 中 `ctx` 为 None 时的处理（perceive 中获取消息可能失败，需静默降级）
  - 记录触发时间戳：`self._trigger_timestamps[stream_id] = time.time()`
  - 返回 `{success: true, message: "已触发决策循环"}`
  - 异常处理：try/except 包裹
- [ ] 实现 `_check_trigger_cooldown(stream_id: str) -> bool` 方法：
  - `last_ts = self._trigger_timestamps.get(stream_id, 0)`
  - 返回 `(time.time() - last_ts) >= 30`
- [ ] 在 `start()` 方法中注册新路由：`self._app.router.add_post("/api/proactive-chat/trigger", self._handle_trigger)`
- 涉及文件：`plugins/proactive-chat/webui.py`
- 验收方式：`POST /api/proactive-chat/trigger` 可触发指定聊天流的决策循环；频率限制生效（30 秒内仅允许一次）；白名单校验生效；冷却校验生效；强制模式跳过白名单和冷却检查

**依赖**：任务 49（WebUIServer 构造函数已扩展，包含 `agent` 引用）

---

## 63. 手动触发决策：前端触发面板

- [ ] 在 `_HTML_PAGE` 的决策记录工具栏中新增"手动触发"按钮：
  - `<button onclick="showTriggerDialog()">手动触发</button>`
  - 按钮样式：与现有按钮一致
- [ ] 实现触发对话框：
  - 使用内联模态框（不用 `prompt()`）
  - 样式：`.trigger-dialog`：`background:var(--card);border:1px solid var(--border);border-radius:12px;padding:20px;position:fixed;top:50%;left:50%;transform:translate(-50%,-50%);z-index:1000;min-width:360px;box-shadow:0 8px 32px rgba(0,0,0,.4)`
  - 输入框：聊天流 ID（必填）
  - 复选框：强制触发（可选，默认不勾选）
  - 按钮："触发"和"取消"
  - 背景遮罩：`.dialog-overlay`：`position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,.5);z-index:999`
- [ ] 在 `<script>` 中实现 `showTriggerDialog()` 和 `hideTriggerDialog()` 函数
- [ ] 实现 `triggerDecision()` 函数：
  - 获取输入的 `stream_id` 和 `force` 值
  - 校验 `stream_id` 非空
  - 调用 `POST /api/proactive-chat/trigger`
  - 成功后显示"已触发决策循环"提示，关闭对话框
  - 失败时显示具体错误信息
- 涉及文件：`plugins/proactive-chat/webui.py`（`_HTML_PAGE` 常量）
- 验收方式：点击"手动触发"按钮弹出输入对话框；输入聊天流 ID 并点击触发后调用 API；成功后显示提示并关闭对话框；失败时显示错误信息；30 秒内重复触发被拒绝

**依赖**：任务 62（手动触发 API 已实现）

---

## 64. 批量归档：后端 API

- [ ] 在 `webui.py` 中实现 `_handle_batch_archive(request: web.Request)` 异步方法：
  - 读取请求体 JSON：`record_keys`（数组，每个元素为 `[ts, stream_id]`，最大长度 100）
  - 校验 `record_keys` 非空且长度 ≤ 100
  - 遍历 `record_keys`，对每个调用 `self._persistence.update_record_status((ts, stream_id), {"record_status": "archived"})`
  - 统计成功和失败数
  - 部分失败时返回 `{success: true, archived_count: N, failed_count: M, errors: [...]}`
  - 全部成功时返回 `{success: true, archived_count: N, failed_count: 0}`
  - 异常处理：try/except 包裹
- [ ] 在 `start()` 方法中注册新路由：`self._app.router.add_post("/api/proactive-chat/decisions/batch-archive", self._handle_batch_archive)`
- 涉及文件：`plugins/proactive-chat/webui.py`
- 验收方式：`POST /api/proactive-chat/decisions/batch-archive` 可批量归档多条记录；部分失败时返回详细错误信息；最大 100 条限制

**依赖**：无（`update_record_status` 已实现）

---

## 65. 批量归档：前端复选框与批量操作

- [ ] 在 `_HTML_PAGE` 的 `<style>` 中新增复选框和批量操作样式：
  - `.batch-bar`：`display:flex;align-items:center;gap:12px;padding:8px 0;margin-bottom:8px`
  - `.batch-bar button:disabled`：`opacity:.4;cursor:default`
  - 表格复选框列样式：`th.cb-col, td.cb-col`：`width:30px;text-align:center`
- [ ] 修改决策记录表格，新增复选框列（第一列）：
  - 表头：`<th class="cb-col"><input type="checkbox" id="select-all" onchange="toggleSelectAll()"></th>`
  - 每行：`<td class="cb-col"><input type="checkbox" class="row-cb" data-key="ts:stream_id" onchange="updateBatchBar()"></td>`
- [ ] 在决策记录工具栏中新增批量操作栏：
  - `<span id="selected-count">已选 0 条</span>`
  - `<button id="batch-archive-btn" onclick="batchArchive()" disabled>批量归档</button>`
- [ ] 在 `<script>` 中实现 `toggleSelectAll()` 函数：
  - 勾选表头复选框 → 当前页所有记录被选中
  - 取消表头复选框 → 当前页所有选中取消
- [ ] 实现 `updateBatchBar()` 函数：
  - 统计当前选中的记录数
  - 更新"已选 N 条"文本
  - 选中数 > 0 时启用"批量归档"按钮，否则禁用
- [ ] 实现 `batchArchive()` 函数：
  - 收集所有选中的 `record_keys`：`[[ts, stream_id], ...]`
  - 弹出确认对话框："确认归档 N 条记录？"
  - 调用 `POST /api/proactive-chat/decisions/batch-archive`
  - 成功后显示"已归档 N 条记录"提示，刷新决策记录列表
  - 部分失败时显示"已归档 N 条，M 条失败"
- [ ] 修改 `renderDecisionsTable()` 函数，为每行渲染复选框
- [ ] 翻页时清空选中状态
- 涉及文件：`plugins/proactive-chat/webui.py`（`_HTML_PAGE` 常量）
- 验收方式：决策记录表格新增复选框列；表头复选框可全选/取消全选；选中记录后"批量归档"按钮启用；批量归档成功后记录从列表消失；未选中时按钮禁用

**依赖**：任务 64（批量归档 API 已实现）

---

## 66. 骨架屏加载效果

- [ ] 在 `_HTML_PAGE` 的 `<style>` 中新增骨架屏样式：
  - `.skeleton`：`background:linear-gradient(90deg,var(--card) 25%,var(--border) 50%,var(--card) 75%);background-size:200% 100%;animation:shimmer 1.5s infinite;border-radius:6px`
  - `@keyframes shimmer`：`0%{background-position:200% 0}100%{background-position:-200% 0}`
  - `.skeleton-line`：`height:16px;margin-bottom:8px`
  - `.skeleton-line.short`：`width:60%`
  - `.skeleton-line.medium`：`width:80%`
  - `.skeleton-circle`：`width:40px;height:40px;border-radius:50%`
  - `.skeleton-card`：`padding:20px`
  - `.skeleton-table-row`：`display:flex;gap:12px;padding:8px 0;border-bottom:1px solid var(--border)`
- [ ] 实现骨架屏渲染函数：
  - `renderStatsSkeleton()`：统计概览骨架屏（6 行 skeleton-line）
  - `renderCooldownSkeleton()`：冷却状态骨架屏（3 行 skeleton-line）
  - `renderDecisionsSkeleton()`：决策记录骨架屏（5 行 skeleton-table-row）
- [ ] 修改页面初始加载，显示骨架屏而非"加载中..."文本：
  - 统计概览：`<div id="stats-content">renderStatsSkeleton()</div>`
  - 冷却状态：`<div id="cooldown-content">renderCooldownSkeleton()</div>`
  - 决策记录：`<div id="decisions-content">renderDecisionsSkeleton()</div>`
- [ ] 修改 `loadStats()`、`loadCooldown()`、`loadDecisions()` 函数：
  - 记录加载开始时间
  - 数据加载完成后，确保骨架屏最少显示 200ms（`Math.max(0, 200 - elapsed)`）
  - 骨架屏到实际内容的过渡时间不超过 300ms（使用 `opacity` 过渡）
- [ ] 新增 `prefers-reduced-motion` 媒体查询：
  - `@media (prefers-reduced-motion: reduce)`：禁用 shimmer 动画，骨架屏使用纯色背景
- 涉及文件：`plugins/proactive-chat/webui.py`（`_HTML_PAGE` 常量）
- 验收方式：页面首次加载时显示骨架屏（shimmer 动画）；数据加载完成后骨架屏平滑过渡为实际内容；骨架屏最少显示 200ms 避免闪烁；`prefers-reduced-motion` 下禁用动画

**依赖**：无（纯前端样式变更）

---

## 67. 过渡动画与微交互

- [ ] 在 `_HTML_PAGE` 的 `<style>` 中新增过渡动画样式：
  - 新记录行滑入：`.row-enter`：`overflow:hidden;max-height:0;opacity:0;transition:max-height .3s ease-out,opacity .3s ease-out`
  - `.row-enter.show`：`max-height:200px;opacity:1`
  - 记录行移除：`.row-exit`：`max-height:0;opacity:0;transition:max-height .2s ease-in,opacity .2s ease-in`
  - 卡片展开/收起：`.detail-panel` 新增 `transition:max-height .25s ease-out,opacity .25s ease-out`
  - 标签页切换：`.tab-content` 新增 `transition:opacity .2s`
  - 数字变化动效：`.stat-value.animate-up`：`color:var(--green);transition:color .3s`
  - `.stat-value.animate-down`：`color:var(--red);transition:color .3s`
  - 按钮点击反馈：`.btn-press`：`transform:scale(.95);transition:transform .1s`
  - 冷却进度条完成：`.cd-progress-bar.completing`：`background:var(--green);transition:background .5s`
- [ ] 在 `<script>` 中实现数字变化动效：
  - 修改 `loadStats()` 函数，对比新旧统计值
  - 增大时添加 `animate-up` 类（绿色），减小时添加 `animate-down` 类（红色）
  - 300ms 后移除动画类
- [ ] 实现按钮点击反馈：
  - 为所有按钮添加 `onmousedown="this.classList.add('btn-press')" onmouseup="this.classList.remove('btn-press')" onmouseleave="this.classList.remove('btn-press')"`
- [ ] 实现冷却进度条完成动效：
  - 进度条满格时添加 `completing` 类，颜色从 `var(--accent)` 过渡到 `var(--green)`
- [ ] 新增 `prefers-reduced-motion` 媒体查询：
  - 减少或禁用所有过渡动画
- 涉及文件：`plugins/proactive-chat/webui.py`（`_HTML_PAGE` 常量）
- 验收方式：新决策记录出现时有滑入动画；归档移除记录时有滑出动画；统计数字变化时有颜色反馈；按钮点击有缩放反馈；冷却进度条完成时颜色变绿；`prefers-reduced-motion` 下动画减少

**依赖**：任务 66（骨架屏已实现，过渡动画与骨架屏衔接）

---

## 68. 暗色主题优化与响应式增强

- [ ] 修改 `_HTML_PAGE` 的 `<style>` 中现有样式：
  - 行悬停效果：将 `rgba(108,92,231,.05)` 改为 `rgba(108,92,231,.08)`，提高可辨识度
  - 卡片阴影：新增 `box-shadow:0 2px 8px rgba(0,0,0,.2)` 增加层次感
  - 统计数值与背景对比度：确保 ≥ 4.5:1（WCAG AA），调整 `.stat-value` 的 `color` 为更亮的白色 `#f0f0f0`
- [ ] 新增响应式媒体查询：
  - `@media (max-width: 768px)`：
    - `.grid` 改为单列：`grid-template-columns:1fr`
    - `.table-wrap` 新增 `overflow-x:auto`
  - `@media (max-width: 480px)`：
    - 工具栏控件换行：`.toolbar` 新增 `flex-wrap:wrap`
    - 按钮组缩小：`.time-btn` 的 `padding` 减小
    - 标签页按钮缩小
- 涉及文件：`plugins/proactive-chat/webui.py`（`_HTML_PAGE` 常量）
- 验收方式：暗色主题对比度符合 WCAG AA 标准；卡片有阴影层次感；行悬停效果更明显；窄屏下卡片单列堆叠；表格可水平滚动；工具栏控件换行

**依赖**：无（纯 CSS 变更）

---

## 69. WebSocket 消息节流与合并通知完善

- [ ] 完善 `handleWSMessage()` 函数的消息节流逻辑：
  - 使用 `setTimeout` 实现 500ms 节流窗口
  - 窗口内收到的消息缓存到 `wsPendingMsg`，递增 `wsPendingCount`
  - 窗口结束时处理最后一条消息
  - 如果 `wsPendingCount > 1` 且消息类型为 `new_decision`：
    - Toast 标题改为"收到 N 条新决策"
    - 不再逐条显示 Toast
  - 非 `new_decision` 类型的消息（如 `cooldown_started`）立即处理，不节流
- [ ] 确保消息处理后触发一次完整数据刷新，保证数据一致性
- [ ] 修改 `phase_changed` 消息处理：
  - 不触发完整刷新，仅局部更新对应记录行的处理阶段标签
  - 通过 DOM 查找对应 `stream_id` 的行，更新 `processing_phase` 标签
- 涉及文件：`plugins/proactive-chat/webui.py`（`_HTML_PAGE` 常量）
- 验收方式：短时间内收到多条 WebSocket 消息时，500ms 内仅处理最后一条；多条新决策合并为一条 Toast 通知；页面不卡顿；`phase_changed` 消息仅局部更新 DOM

**依赖**：任务 50（WebSocket 客户端已实现）、任务 51（Toast 通知已实现）

---

## 70. 冷却到期自动推送事件

- [ ] 在 `cooldown.py` 的 `CooldownManager` 中新增冷却到期检测：
  - 新增 `_expiry_check_task: asyncio.Task | None = None` 属性
  - 新增 `start_expiry_checker(webui=None)` 方法：
    - 保存 `webui` 引用
    - 创建定时任务 `_expiry_check_loop()`，每 10 秒检查一次
  - 新增 `stop_expiry_checker()` 方法：取消定时任务
  - 新增 `async _expiry_check_loop()` 方法：
    - 循环中 `await asyncio.sleep(10)`
    - 遍历 `_records`，检查 `time.time() - rec.triggered_at >= cooldown_seconds`
    - 对刚到期的记录（上一次检查时未到期），调用 `webui.broadcast_event("cooldown_expired", {stream_id, intent?, remaining_seconds: 0})`
    - 从 `_records` 中移除已到期的记录
  - 内部 try/except 包裹，确保异常不影响下次检查
- [ ] 修改 `plugin.py` 的 `on_load()`，在 `CooldownManager` 初始化后调用 `self._cooldown_manager.start_expiry_checker(self._webui)`
- [ ] 修改 `plugin.py` 的 `on_unload()`，在清理时调用 `self._cooldown_manager.stop_expiry_checker()`
- 涉及文件：`plugins/proactive-chat/cooldown.py`、`plugins/proactive-chat/plugin.py`
- 验收方式：冷却到期时通过 WebSocket 推送 `cooldown_expired` 事件；前端收到事件后自动刷新冷却状态；到期检测不影响其他功能

**依赖**：任务 49（`broadcast_event` 已实现）、任务 52（事件广播集成框架已搭建）

---

## 71. 前端自动刷新策略优化

- [ ] 修改 `init()` 函数中的自动刷新逻辑：
  - WebSocket 连接成功时：停止定时轮询（`clearInterval(refreshTimer)`），仅通过 WebSocket 事件触发局部更新
  - WebSocket 断线时：恢复定时轮询（10 秒间隔），状态指示器显示"轮询模式"
  - WebSocket 重连成功时：停止轮询，状态指示器恢复"实时连接"
- [ ] 修改 `handleWSMessage()` 函数：
  - `new_decision` 事件：刷新决策记录表格和统计概览
  - `cooldown_started` / `cooldown_expired` / `cooldown_reset` 事件：刷新冷却状态
  - `phase_changed` 事件：仅局部更新对应记录行的处理阶段标签（不刷新整个表格）
  - `config_updated` 事件：如果当前在配置标签页，刷新配置表单
- [ ] 确保轮询模式和 WebSocket 模式切换时不会出现重复刷新
- 涉及文件：`plugins/proactive-chat/webui.py`（`_HTML_PAGE` 常量）
- 验收方式：WebSocket 连接正常时无轮询请求；WebSocket 断线后自动恢复轮询；重连后停止轮询；各事件类型触发正确的局部刷新

**依赖**：任务 50（WebSocket 客户端已实现）、任务 52（事件广播集成已实现）

---

## 72. conic-gradient 降级方案完善

- [ ] 完善 `renderPieChart()` 函数的降级逻辑：
  - 检测 `conic-gradient` 支持：创建临时 `<div>`，设置 `background: conic-gradient(red, blue)`，检查 `getComputedStyle` 是否生效
  - 支持时：渲染环形饼图（conic-gradient）
  - 不支持时：渲染横向条形图降级方案
    - 每个意图一行，左侧标签，右侧按比例宽度的色带
    - 色带颜色与饼图扇区颜色一致
    - 显示具体数量和占比
  - 两种方案共享图例
- [ ] 确保降级方案在 Chrome 90-、Firefox 90-、Safari 15- 中正常工作
- 涉及文件：`plugins/proactive-chat/webui.py`（`_HTML_PAGE` 常量）
- 验收方式：支持 `conic-gradient` 的浏览器显示环形饼图；不支持的浏览器显示横向条形图；两种方案数据一致；图例正确

**依赖**：任务 54（饼图基础渲染已实现）

---

## 73. 搜索参数传递到导出 API

- [ ] 修改 `exportData(format)` 函数，在导出 URL 中包含当前搜索参数：
  - `const search = document.getElementById('filter-search').value.trim()`
  - `if(search) url += '&search=' + encodeURIComponent(search)`
- [ ] 确保 `_handle_export` 方法已支持 `search` 参数（在任务 57 中已包含）
- 涉及文件：`plugins/proactive-chat/webui.py`（`_HTML_PAGE` 常量）
- 验收方式：搜索状态下导出的数据仅包含匹配搜索条件的记录

**依赖**：任务 58（导出按钮已实现）、任务 59（搜索功能已实现）

---

## 74. WebUI v2 集成验证

- [ ] 验证 WebSocket 实时推送：
  - 页面加载后自动建立 WebSocket 连接
  - 触发一次决策循环，确认前端收到 `phase_changed` 和 `new_decision` 事件
  - 冷却开始/到期/重置时收到对应事件
  - 断开 WebSocket 后自动降级为轮询模式
  - 重连后恢复实时推送
- [ ] 验证数据可视化：
  - 决策分布饼图正确显示各意图占比
  - 冷却时间线正确显示各聊天流冷却状态
  - 置信度分布直方图正确显示各区间记录数
  - 不支持 conic-gradient 时降级为条形图
- [ ] 验证数据导出：
  - 导出 CSV 文件可正常下载并打开
  - 导出 JSON 文件格式正确
  - 超过 5000 条时弹出确认对话框
  - 搜索状态下导出仅包含匹配记录
- [ ] 验证配置在线编辑：
  - 配置标签页正确展示所有配置段
  - 修改配置后保存即时生效
  - 敏感字段脱敏展示
  - 校验失败显示错误提示
  - 保存失败回滚表单值
- [ ] 验证手动触发：
  - 手动触发决策成功
  - 频率限制生效
  - 白名单和冷却校验生效
- [ ] 验证批量归档：
  - 全选/取消全选正常
  - 批量归档成功
  - 部分失败时显示详细信息
- [ ] 验证搜索增强：
  - 搜索关键词正确过滤记录
  - 搜索高亮正常显示
  - 搜索结果为空时显示提示
- [ ] 验证视觉体验：
  - 骨架屏加载效果正常
  - 过渡动画平滑
  - Toast 通知出入场动画正常
  - 暗色主题对比度符合标准
  - 窄屏下响应式布局正常
  - `prefers-reduced-motion` 下动画减少
- [ ] 验证现有功能不受影响：
  - 统计概览数据正确
  - 冷却状态显示正确
  - 决策记录表格分页/排序/筛选/行展开详情正常
  - 归档操作正常
  - 冷却重置正常
  - 趋势图正常
- [ ] 性能验证：
  - 首屏加载时间不超过 1.5 秒
  - API 响应时间不超过 500ms
  - 决策记录表格渲染 100 条不超过 200ms
  - WebSocket 推送延迟不超过 1 秒
- 涉及文件：全部插件文件
- 验收标准：所有新增功能正常工作；现有功能不受影响；性能指标达标；降级场景正常

**依赖**：任务 49-73（所有功能任务完成）

---

## 75. WebUI v2 回归测试与收尾

- [ ] 运行现有 197 个测试，确认全部通过
- [ ] 修复测试中发现的问题
- [ ] 确认所有新增 API 端点遵循 `/api/proactive-chat/` 前缀规范
- [ ] 确认所有新增前端 JS 代码按功能模块组织，使用注释分隔
- [ ] 确认新增样式优先使用现有 CSS 变量（`--bg`、`--card`、`--accent` 等），避免硬编码颜色值
- [ ] 确认后端新增功能使用 `[proactive-chat]` 前缀记录日志，优先中文
- [ ] 确认 WebSocket 消息格式统一（`type` + `data` + `timestamp`）
- [ ] 确认配置修改审计日志记录完整
- [ ] 确认 Docker 部署环境下 WebUI 服务正常运行（端口 28001）
- [ ] 确认所有降级场景正常工作：
  - WebSocket 连接被拒绝 → 降级为轮询
  - conic-gradient 不支持 → 降级为条形图
  - 导出 API 超时 → 显示超时提示
  - 配置保存失败 → 回滚表单值
  - 手动触发频率超限 → 按钮禁用
  - 批量归档部分失败 → 显示详细错误
  - 搜索 API 超时 → 显示超时提示
- 涉及文件：全部插件文件
- 验收标准：197 个测试全部通过；代码规范符合要求；所有降级场景正常；Docker 环境正常运行

**依赖**：任务 74（集成验证通过）