# QQ用户记忆插件 — 实现方案文档

> 版本：7.0.0  
> 日期：2026-05-29  
> 状态：设计  
> 语言：简体中文  
> 对应需求规格：spec.md v7.0.0  
> 变更说明：v7.0.0 重大版本升级实现方案——(1) P0 replyer.before_model_request Hook 主动注入记忆上下文（已实现）；(2) P1 WebUI 全面升级为现代化前端（待实现）；(3) P1 消息上下文深度结合（部分已实现）；保留 v6.1.0/v6.2.0 全部设计

---

# **1. 实现模型**

## **1.1 上下文视图**

插件位于 MaiBot 插件运行时环境中，通过 `maibot-plugin-sdk 2.5.2` 提供的装饰器和上下文对象与框架交互。插件拥有自管理 SQLite 数据库，不依赖 `ctx.db`。可选通过 A_Memorix 的 Tool 标准接口双向同步数据（写入+检索），需在 `_manifest.json` 声明 `api.call` 能力。WebUI 通过独立 HTTP 服务（aiohttp，端口8121）提供管理界面，含 token 鉴权中间件。v7.0.0 新增 replyer Hook 注入通道，通过 `maisaka.replyer.before_model_request` Hook 在模型请求前主动注入记忆摘要到 messages。

```plantuml
@startuml
!define PLUGIN_COLOR #E8F5E9
!define SDK_COLOR #E3F2FD
!define DB_COLOR #FFF3E0
!define NEW_COLOR #FFF9C4

rectangle "MaiBot 框架" as framework #SDK_COLOR {
  component "插件运行时" as runtime
  component "ctx 能力集" as ctx
  component "能力授权" as cap
  component "Replyer\n(模型请求构建)" as replyer
}

rectangle "QQ用户记忆插件" as plugin #PLUGIN_COLOR {
  component "插件主类\n(QQUserMemoryPlugin)" as main
  component "哈希工具\n(hash_utils)" as hash
  component "数据库层\n(db_manager)" as db
  component "白名单服务\n(whitelist_service)" as wl
  component "A_Memorix 同步\n(amemorix_sync)" as sync
  component "配置模型\n(config)" as config
  component "智能提取\n(smart_extract)" as smart
  component "嵌入服务\n(embedding_service)" as embed
  component "合并服务\n(merge_service)" as merge
  component "WebUI服务\n(webui_service)" as webui
  component "时间工具\n(time_utils)" as time
  component "鉴权中间件\n(auth_middleware)" as auth
  component "群聊消息分类\n(group_classifier)" as gcls
  component "记忆注入处理器\n(handle_memory_injection)" as inject #NEW_COLOR
}

database "自管理 SQLite\n(qq_user_memory.db)" as sqlite #DB_COLOR
database "A_Memorix\n(标准Tool接口)" as memorix #DB_COLOR

runtime --> main : 生命周期(on_load/on_unload)
ctx --> main : send/logger/person/chat/config/llm
cap --> main : capabilities授权(api.call)
replyer --> inject : before_model_request Hook\n(含messages, session_id, task_name)
inject --> replyer : 返回改写后messages\n(含注入记忆摘要)
main --> hash : QQ号→hashed_user_id
main --> wl : 两阶段校验(操作者+被记忆对象)
main --> db : 记忆CRUD(含group_id过滤)
main --> sync : A_Memorix双向同步(chat_id=group_id)
main --> smart : 智能提取/分类/评估
main --> embed : 向量嵌入/检索
main --> merge : 合并去重
main --> webui : WebUI管理页面
main --> gcls : 群聊消息分类(@指令/闲聊)
inject --> wl : 白名单校验
inject --> db : 双重隔离检索
inject --> config : 注入配置(位置/条数/模板/追踪)
webui --> auth : token鉴权
webui --> wl : 白名单过滤展示
db --> sqlite : 持久化
sync --> memorix : ingest_text/search_memory(需api.call)
embed --> sqlite : 向量存储

note right of inject : v7.0.0新增 P0\nreplyer Hook注入\n记忆主动注入到LLM上下文\nsystem_append/standalone_user
note right of webui : v7.0.0升级 P1\n现代化卡片式布局\n统计面板+暗色主题\n前端静态资源独立部署
note right of cap : v6.1.0新增\napi.call能力授权\n降级策略
note right of smart : v6.1.0优化\nprompt+JSON schema\n裸key名检测+结果类型日志
@enduml
```

## **1.2 服务/组件总体架构**

```plantuml
@startuml
skinparam componentStyle rectangle

package "QQ用户记忆插件 v7.0.0" {

  package "接入层" {
    [retrieve_user_memory\n@Tool] as tool_retrieve
    [add_user_memory\n@Tool] as tool_add
    [delete_user_memory\n@Tool] as tool_delete
    [/记忆查看\n@Command] as cmd_view
    [/记忆添加\n@Command] as cmd_add
    [/记忆删除\n@Command] as cmd_delete
    [auto_memory_recorder\n@HookHandler] as hook_auto
    [auto_memory_bot_reply\n@HookHandler] as hook_reply
    [handle_memory_injection\n@HookHandler(before_model_request)] as hook_inject [new v7.0.0]
  }

  package "校验层" {
    [WhitelistService\n两阶段校验] as whitelist
    [GroupClassifier\n消息分类] as classifier
    [CapabilityChecker\n能力授权校验] as capcheck
  }

  package "业务层" {
    [_do_add_memory\n统一添加逻辑] as add_logic
    [_do_retrieve_memory\n统一检索逻辑] as retrieve_logic
    [SmartExtractService\n优化prompt+裸key检测] as smart
    [MergeService] as merge
    [AMemorixSyncService\n含降级策略] as sync
    [MemoryInjectionHandler\n记忆注入+格式化+截断] as injector [new v7.0.0]
  }

  package "数据层" {
    [DBManager\n含source字段] as db
    [EmbeddingService] as embed
  }

  package "展示层" {
    [WebUIService\n现代化卡片+统计+暗色主题] as webui [v7.0.0升级]
    [AuthMiddleware] as auth
    [StaticResourceServer\n前端静态资源] as static [new v7.0.0]
  }
}

tool_retrieve --> whitelist
tool_add --> whitelist
tool_add --> smart
cmd_add --> whitelist
cmd_add --> smart
hook_auto --> whitelist
hook_auto --> classifier
hook_reply --> whitelist
hook_inject --> whitelist
hook_inject --> injector
injector --> db
injector --> retrieve_logic
add_logic --> smart
add_logic --> merge
add_logic --> sync
add_logic --> db
add_logic --> embed
retrieve_logic --> db
retrieve_logic --> embed
retrieve_logic --> sync
sync --> capcheck
smart --> db
webui --> db
webui --> embed
webui --> merge
webui --> auth
webui --> static

note right of hook_inject : v7.0.0新增 P0\nreplyer.before_model_request\n记忆主动注入到LLM上下文
note right of injector : v7.0.0新增\n摘要检索+格式化+截断\n注入位置策略
note right of webui : v7.0.0升级 P1\n卡片式布局\n统计面板(图表)\n群聊标签式筛选\n暗色主题(CSS变量)\n操作反馈增强\n批量操作增强
note right of static : v7.0.0新增\n前端资源独立部署\nHTML/CSS/JS静态文件\n通过插件路由提供服务
@enduml
```

## **1.3 实现设计文档**

### **1.3.1 方向1：Replyer Hook 记忆注入（P0）— 已实现**

> 对应需求：REQ-110 ~ REQ-119  
> 实现状态：**已编码完成**，以下为已实现的架构设计和关键逻辑文档化

#### **1.3.1.1 Hook 注册与配置**

**变更文件**：`plugin.py`、`config.py`

**Hook 注册方式**：

```python
@HookHandler(
    "maisaka.replyer.before_model_request",
    mode=HookMode.OBSERVE,
    order=HookOrder.LATE,
)
async def handle_memory_injection(self, **kwargs: Any) -> dict[str, Any]:
```

- **Hook 事件名**：`maisaka.replyer.before_model_request`
- **Hook 模式**：`HookMode.OBSERVE`（观察模式，可改写 kwargs 后返回）
- **Hook 顺序**：`HookOrder.LATE`（晚执行，确保在 replyer 完成消息构建后介入）
- **返回值**：改写后的 `kwargs`（含修改后的 `messages`）

**配置模型（MemoryInjectionConfig）**：

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `enable_memory_injection` | bool | True | 启用记忆注入（总开关） |
| `injection_max_memories` | int | 5 (1-20) | 注入的最大记忆条数 |
| `injection_summary_template` | str | 见下方 | 注入摘要模板 |
| `injection_position` | str | "system_append" | 注入位置策略 |
| `enable_injection_tracking` | bool | True | 启用注入效果追踪 |

默认注入摘要模板：
```
【用户记忆参考】
{memories}
请参考以上记忆信息回复，自然地融入相关内容，不要刻意提及"我记得"。
```

注入位置策略选项：
- `system_append`：追加到 system message 末尾（默认，与系统指令融合）
- `standalone_user`：作为独立 user message 插入（更明确区分记忆上下文）

#### **1.3.1.2 session_id 解析 — user_id 和 group_id 提取**

**实现逻辑**：从 replyer Hook 上下文的 `session_id` 字段中解析 `user_id` 和 `group_id`。

**session_id 格式**：MaiBot 框架中 session_id 的格式为包含 `user_{qq号}` 和 `group_{群号}` 的下划线分隔字符串。

```python
session_id = str(kwargs.get("session_id", "") or "").strip()
user_id = ""
group_id = ""
if session_id:
    parts = session_id.split("_")
    for i, p in enumerate(parts):
        if p == "user" and i + 1 < len(parts):
            user_id = parts[i + 1]
        if p == "group" and i + 1 < len(parts):
            group_id = parts[i + 1]
```

**降级策略**：
- `session_id` 为空或无法解析出 `user_id` → 不注入记忆，返回原始 kwargs
- 解析出 `user_id` 但不在被记忆用户白名单 → 不注入记忆，返回原始 kwargs
- 解析出 `group_id` 但群聊隔离关闭（`enable_group_isolation=False`）→ 将 `group_id` 置为 None，仅检索全局记忆

#### **1.3.1.3 记忆检索与双重隔离**

**检索流程**：

1. 通过 `compute_hash(user_id)` 计算哈希 ID
2. 调用 `self._db.query_memories(hashed, limit, group_id=group_id)` 进行双重隔离检索
3. DBManager 的双重隔离逻辑：
   - `group_id` 非空（群聊）：返回全局记忆（group_id IS NULL OR group_id = ''）+ 当前群记忆
   - `group_id` 为空（私聊）：仅返回全局记忆
4. 检索结果为空 → 不注入记忆，返回原始 kwargs

#### **1.3.1.4 记忆摘要格式化**

**格式化逻辑**：

```python
memory_lines = []
for i, m in enumerate(memories, 1):
    imp = m.get("importance", 3)
    cat = m.get("category", "general")
    content = m.get("content", "")
    memory_lines.append(f"{i}. [{cat}/★{imp}] {content}")

memories_text = "\n".join(memory_lines)
template = self.config.memory_injection.injection_summary_template
injection_text = template.replace("{memories}", memories_text)
```

**格式示例**：
```
1. [preference/★4] 喜欢吃火锅
2. [fact/★5] 对花生过敏
3. [habit/★3] 每天晚上跑步
```

#### **1.3.1.5 注入位置策略实现**

**system_append 策略**（默认）：

```python
if position == "system_append":
    for msg in messages:
        if isinstance(msg, dict) and msg.get("role") == "system":
            original = msg.get("content", "")
            if isinstance(original, str):
                msg["content"] = original + "\n\n" + injection_text
            break
    else:
        # 无 system message 时，插入为首个 system message
        messages.insert(0, {"role": "system", "content": injection_text})
```

**standalone_user 策略**：

```python
elif position == "standalone_user":
    messages.append({"role": "user", "content": injection_text})
```

#### **1.3.1.6 注入效果追踪**

当 `enable_injection_tracking=True` 时，通过 `ctx.logger.debug` 记录注入统计：

```python
self.ctx.logger.debug(
    "记忆注入: user=%s... group=%s memories=%d position=%s",
    hashed[:8], group_id or "私聊", len(memories), position,
)
```

追踪信息包含：哈希用户ID前8位、群聊ID（或"私聊"）、注入记忆条数、注入位置策略。

#### **1.3.1.7 异常降级策略**

| 异常场景 | 降级行为 | 日志级别 |
|---------|---------|---------|
| `enable_memory_injection=False` | 不注入，返回原始 kwargs | 无日志 |
| 插件降级模式（`_degraded=True`） | 不注入，返回原始 kwargs | 无日志 |
| session_id 为空或无法解析 user_id | 不注入，返回原始 kwargs | 无日志 |
| 用户不在被记忆用户白名单 | 不注入，返回原始 kwargs | 无日志 |
| 用户无任何记忆 | 不注入，返回原始 kwargs | 无日志 |
| Hook 处理中任何异常 | 不注入，返回原始 kwargs | DEBUG |
| messages 为空或格式异常 | 不注入，返回原始 kwargs | 隐含在异常处理中 |

**核心设计原则**：Hook 处理异常**绝对不影响** replyer 正常流程。任何异常均被 `try/except` 捕获，静默降级为不注入。

#### **1.3.1.8 注入与 Tool Call 的互补关系**

- 记忆注入后，`retrieve_user_memory` Tool **仍保留可用性**
- 注入摘要为精简版（最多 `injection_max_memories` 条，按重要性排序），Tool 可返回更完整的记忆列表
- LLM 可根据需要选择是否额外调用 Tool 获取更详细信息
- 两者互补而非替代：注入提供"基础记忆上下文"，Tool 提供"按需深度检索"

---

### **1.3.2 方向2：WebUI 全面升级（P1）— 待实现**

> 对应需求：REQ-120 ~ REQ-127  
> 实现状态：**待实现**，以下为详细设计方案

#### **1.3.2.1 前端技术选型**

| 决策项 | 选型 | 理由 |
|--------|------|------|
| 框架 | 纯 Vanilla JS + CSS | 零依赖，无需构建流程，与 MaiBot WebUI 插件路由机制兼容，不引入独立打包 |
| UI 范式 | 卡片式布局 + CSS Grid/Flexbox | 响应式，替代旧版表格为主布局 |
| 主题系统 | CSS 自定义属性（CSS Variables） | 运行时切换无重载，`prefers-color-scheme` 媒体查询跟随系统 |
| 图表库 | Chart.js（轻量 CDN 引入） | 单文件 ~60KB gzip，支持饼图/环形图/柱状图/折线图 |
| 图标 | Lucide Icons（SVG 内联） | 轻生轻量，暗色主题兼容 |
| HTTP 客户端 | 原生 fetch API | 无需额外依赖 |
| 鉴权 | sessionStorage token + X-Memory-Token Header | 复用现有鉴权逻辑 |

**不引入 Vue/React/Svelte 的理由**：
- 插件职责边界约束：不负责 WebUI 框架的打包构建
- 零依赖部署：静态资源直接放入插件目录，无需 npm/webpack/vite
- 性能考量：记忆管理页面功能单一，SPA 框架过重

#### **1.3.2.2 页面结构设计**

**页面布局**（从上到下）：

```
┌─────────────────────────────────────────────┐
│  Header (插件名称 + 嵌入状态 + 主题切换按钮)  │
├─────────────────────────────────────────────┤
│  统计面板 (3-4 个统计卡片 + 图表区域)         │
│  ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐      │
│  │总记忆│ │总用户│ │平均  │ │群聊数│      │
│  └──────┘ └──────┘ └──────┘ └──────┘      │
│  ┌────────────┐ ┌────────────┐ ┌──────────┐│
│  │分类分布饼图│ │群聊分布柱图│ │趋势折线图││
│  └────────────┘ └────────────┘ └──────────┘│
├─────────────────────────────────────────────┤
│  筛选栏 (类别/重要性/用户/群聊标签式/时间范围)│
├─────────────────────────────────────────────┤
│  记忆卡片列表 (按用户分组，卡片内含记忆条目)  │
│  ┌─ 用户A (15条) ──────────────────────┐    │
│  │  [记忆1] [记忆2] [记忆3] ...        │    │
│  └─────────────────────────────────────┘    │
│  ┌─ 用户B (8条) ───────────────────────┐    │
│  │  [记忆1] [记忆2] ...               │    │
│  └─────────────────────────────────────┘    │
├─────────────────────────────────────────────┤
│  分页控件                                    │
└─────────────────────────────────────────────┘
```

**Tab 导航**（与旧版保持一致，功能增强）：
- **概览 Tab**：用户卡片列表 + 统计概要 + 高级操作
- **记忆列表 Tab**：全部记忆条目 + 筛选 + 批量操作
- **统计 Tab**（新增）：分类分布图表 + 群聊分布图表 + 记忆趋势折线图

#### **1.3.2.3 记忆详情面板设计**

点击记忆条目展开详情面板，完整展示字段：

| 字段 | 展示方式 |
|------|---------|
| content | 完整文本，多行可滚动 |
| category | 彩色标签（preference=蓝/habit=绿/fact=橙/relation=紫/temporary=灰/general=深灰） |
| importance | 星标 + 数字（★★★ 3） |
| source | 来源标签（自动/手动/机器人回复/合并/A_Memorix同步） |
| group_id | 群号（空则显示"全局"） |
| created_at | 完整时间 + 时间距离描述（如"3天前"） |
| updated_at | 完整时间（与 created_at 不同时显示） |
| tags | 标签列表，逗号分隔 |
| 向量状态 | ✓ 已嵌入 / ✗ 未嵌入 |

#### **1.3.2.4 群聊标签式筛选**

替代旧版下拉框，采用标签式筛选：

```html
<div class="group-tags">
  <button class="group-tag active" data-group="">全部</button>
  <button class="group-tag" data-group="__private__">私聊</button>
  <button class="group-tag" data-group="123456">123456 (15条)</button>
  <button class="group-tag" data-group="789012">789012 (8条)</button>
</div>
```

- 每个标签显示群号和记忆数量
- 点击标签高亮并筛选
- 支持多选（按住 Ctrl/Cmd 点击），记忆列表为所选群的并集
- "私聊"标签筛选 `group_id IS NULL OR group_id = ''`

#### **1.3.2.5 操作反馈增强**

| 操作 | 反馈方式 |
|------|---------|
| 删除 | 按钮显示 loading 旋转图标 + 禁用，完成后 toast 提示成功/失败 |
| 批量删除（>10条） | 弹出二次确认对话框，显示影响条数 |
| 合并去重 | 按钮显示 loading，完成后 toast 提示合并结果 |
| 向量补算 | 按钮显示 loading，轮询任务状态 |
| 操作失败 | toast 错误提示（中文）+ 重试按钮 |

**Toast 通知组件**（增强版）：
- 成功/失败/信息三种类型
- 自动消失（3秒），可手动关闭
- 支持操作链接（如"查看详情"）

#### **1.3.2.6 批量操作增强**

**新增批量操作**：

| 操作 | API 端点 | 参数 |
|------|---------|------|
| 按 category 批量删除 | `POST /api/operations/batch-delete` | `{category: "temporary", confirm: true}` |
| 按时间范围批量删除 | `POST /api/operations/batch-delete` | `{before_days: 30, confirm: true}` |
| 按 category + 时间组合删除 | `POST /api/operations/batch-delete` | `{category: "temporary", before_days: 30, confirm: true}` |
| 按 importance 范围删除 | `POST /api/operations/batch-delete` | `{max_importance: 1, confirm: true}` |

**流程**：选择条件 → 预览影响条数 → 二次确认 → 执行 → 反馈结果

#### **1.3.2.7 统计面板**

**新增 API 端点**：`GET /api/stats`

返回数据结构：
```json
{
  "category_distribution": {
    "preference": 45, "habit": 30, "fact": 25,
    "relationship": 10, "temporary": 8, "general": 20, "period": 5
  },
  "group_distribution": {
    "123456": 15, "789012": 8, "__global__": 23
  },
  "daily_trend": [
    {"date": "2026-05-28", "count": 12},
    {"date": "2026-05-27", "count": 8}
  ],
  "total_memories": 143,
  "total_users": 23,
  "total_groups": 5
}
```

**图表实现**：
- 分类分布：Chart.js 环形图（doughnut）
- 群聊分布：Chart.js 水平柱状图（horizontal bar）
- 记忆趋势：Chart.js 折线图（line），展示近30天每日新增数量

**DBManager 新增方法**：

```python
def get_category_distribution(self) -> dict[str, int]:
    """获取各 category 的记忆数量分布。"""

def get_daily_trend(self, days: int = 30) -> list[dict[str, Any]]:
    """获取近 N 天每日新增记忆数量趋势。"""
```

#### **1.3.2.8 暗色主题实现**

**CSS 变量体系**：

```css
:root {
  /* 亮色主题 */
  --bg-primary: #f5f5f5;
  --bg-card: #ffffff;
  --text-primary: #333333;
  --text-secondary: #666666;
  --accent: #667eea;
  --border: #eeeeee;
  --shadow: rgba(0, 0, 0, 0.1);
  /* ... */
}

[data-theme="dark"] {
  /* 暗色主题 */
  --bg-primary: #1a1a2e;
  --bg-card: #16213e;
  --text-primary: #e0e0e0;
  --text-secondary: #a0a0a0;
  --accent: #7c8ddb;
  --border: #2a2a4a;
  --shadow: rgba(0, 0, 0, 0.3);
  /* ... */
}
```

**主题切换逻辑**：

```javascript
// 检测系统偏好
const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
// 读取用户偏好（localStorage 优先）
const savedTheme = localStorage.getItem('memory-theme');
const theme = savedTheme || (prefersDark ? 'dark' : 'light');
document.documentElement.setAttribute('data-theme', theme);

// 切换按钮
function toggleTheme() {
  const current = document.documentElement.getAttribute('data-theme');
  const next = current === 'dark' ? 'light' : 'dark';
  document.documentElement.setAttribute('data-theme', next);
  localStorage.setItem('memory-theme', next);
}
```

**对比度要求**：所有文字与背景的对比度满足 WCAG AA 标准（4.5:1）。

#### **1.3.2.9 前端资源独立部署**

**目录结构**：

```
qq_user_memory_plugin/
├── webui/
│   ├── index.html          # 主页面
│   ├── css/
│   │   ├── main.css        # 主样式（含 CSS 变量）
│   │   ├── components.css   # 组件样式（卡片/标签/面板）
│   │   └── themes.css      # 主题定义（亮色+暗色）
│   ├── js/
│   │   ├── app.js          # 主逻辑
│   │   ├── api.js          # API 客户端（authFetch 封装）
│   │   ├── components.js   # UI 组件（Toast/Modal/Card）
│   │   └── charts.js       # Chart.js 图表封装
│   └── assets/
│       └── icons/          # SVG 图标
├── plugin.py
├── config.py
├── ...
```

**WebUIService 变更**：

- 移除 `_HTML_TEMPLATE` 内嵌 HTML 字符串
- `start()` 方法中注册静态资源路由：
  ```python
  # 静态文件服务
  webui_path = os.path.join(os.path.dirname(__file__), "webui")
  app.router.add_static("/static/", webui_path)
  # 首页路由
  app.router.add_get("/", handle_index)  # 返回 index.html
  ```
- 保留 API 端点不变，仅前端消费方式改变

---

### **1.3.3 方向3：消息上下文深度结合（P1）— 部分已实现**

> 对应需求：REQ-130 ~ REQ-133  
> 实现状态：**部分已实现**（bot_info 属性安全访问、群聊记忆发送者前缀），以下为已完成和待完成的设计

#### **1.3.3.1 bot_info 属性安全访问 — 已实现**

**现状**：插件在获取 bot 信息（如 bot_user_id、bot_nickname）时，已采用 `getattr` 安全访问模式：

```python
bot_info = getattr(message, "bot_info", None) or {}
bot_user_id = str(getattr(bot_info, "user_id", "") or "").strip()
```

**设计决策**：保留 `getattr` 方式而非直接属性访问，原因：
- `bot_info` 为 rc.2 新增属性，旧版框架可能不存在
- `getattr` + 默认值实现安全降级，无 `bot_info` 时自动回退

#### **1.3.3.2 群聊记忆发送者前缀 — 已实现**

当群聊环境自动记忆时，在记忆内容前添加发送者昵称前缀：

```python
# 群聊记忆发送者前缀策略
if group_id and self.config.group_chat.enable_group_sender_prefix:
    sender_name = self._extract_nickname(message, user_id)
    if sender_name:
        content = f"{sender_name}说：{content}"
```

- 记忆仍归属到发送者的 `hashed_user_id`
- 前缀仅丰富记忆内容，不改变归属逻辑
- LLM 检索时可自行判断信息主体

#### **1.3.3.3 replyer Hook 上下文信息利用 — 待实现**

**REQ-133**：利用 Hook 上下文中的 `task_name` 和 `request_type` 优化注入策略。

**设计方案**：

1. **任务类型过滤**：新增 `injection_task_filter` 配置项（List[str]，默认空列表=全部注入）
   ```python
   injection_task_filter: List[str] = Field(
       default_factory=list,
       description="注入任务类型过滤(空列表=全部注入，如['chat','reply'])",
   )
   ```

2. **在 handle_memory_injection 中实现过滤**：
   ```python
   task_name = kwargs.get("task_name", "")
   request_type = kwargs.get("request_type", "")
   if self.config.memory_injection.injection_task_filter:
       if task_name not in self.config.memory_injection.injection_task_filter:
           return kwargs
   ```

3. **重试场景处理**：`request_type` 含 retry 指示时，仍注入记忆（保证 LLM 在重试时有记忆参考）

#### **1.3.3.4 智能提取 JSON 解析稳健性改进 — 待实现**

**REQ-132**：增强对非标准 JSON 的解析容错。

**增强策略**（在 `smart_extract.py` 的 JSON 解析逻辑中）：

| 非标准模式 | 修复方法 |
|-----------|---------|
| 多余逗号（如 `{"a":1,}`） | 正则移除 `,\s*}` 和 `,\s*]` |
| 单引号（如 `{'a':'b'}`） | 替换单引号为双引号 |
| 前后非 JSON 文本 | 正则提取最外层花括号内容 |
| 代码块包裹（如 ` ```json ... ``` `） | 移除代码块标记 |

---

### **1.3.4 保留的 v6.1.0 设计**

#### **1.3.4.1 方向1：A_Memorix 权限授权（P0）**

> 对应需求：REQ-080、REQ-081、REQ-082

**_manifest.json 添加 api.call 能力声明**：
```json
{
  "capabilities": [
    "send.text", "config.get", "person.get_id", "llm.generate", "api.call"
  ]
}
```

**AMemorixSyncService 授权失败检测与降级**：
- `_capability_denied: bool = False` 标记
- 检测 `CAPABILITY_DENIED` 异常后设置标记，后续调用直接跳过
- 降级为独立运行模式后本地记忆完全正常

#### **1.3.4.2 方向2：智能提取 LLM 优化（P1）**

> 对应需求：REQ-083 ~ REQ-086

- **prompt 模板优化**：添加 JSON schema 约束、完整示例、反例警告
- **裸 key 名检测**：扩展检测集合，直接降级不重试
- **LLM 返回结果类型日志**：各分支记录 `llm_result_type` 标记
- **重试强调 prompt 优化**：与主 prompt 的 JSON schema 约束一致

#### **1.3.4.3 方向3：WebUI 体验优化（P1）**

> 对应需求：REQ-087 ~ REQ-090

- 记忆列表"群聊"列显示优化（空→"全局"）
- 群聊筛选下拉框新增"全局记忆"选项
- 批量删除 bot_reply 记忆按钮
- 记忆详情展示 source 和 category 信息

---

# **2. 接口设计**

## **2.1 总体设计**

v7.0.0 的接口变更集中在四个方面：

1. **replyer Hook 注册**：新增 `maisaka.replyer.before_model_request` Hook 处理器
2. **MemoryInjectionConfig 配置**：新增记忆注入配置节（5个配置项）
3. **WebUI API 新增**：统计面板 API、增强批量操作 API
4. **前端资源独立部署**：WebUI 前端资源从内嵌 HTML 迁移为静态文件

## **2.2 接口清单**

### **2.2.1 Hook 接口**

| Hook 事件 | 处理方法 | 模式 | 顺序 | 触发时机 | 返回值 |
|-----------|---------|------|------|---------|--------|
| `maisaka.replyer.before_model_request` | `handle_memory_injection` | OBSERVE | LATE | replyer 构建完模型请求后 | 改写后的 kwargs（含注入记忆的 messages） |

**Hook 上下文字段**：

| 字段 | 类型 | 说明 |
|------|------|------|
| `messages` | list[dict] | LLM 请求消息列表（可改写） |
| `session_id` | str | 会话 ID（含 user_id、group_id） |
| `task_name` | str | 任务名称（如 chat、reply、summarize） |
| `request_type` | str | 请求类型（如 normal、retry） |

### **2.2.2 配置接口（MemoryInjectionConfig）**

| 配置项 | 类型 | 默认值 | 约束 | 说明 |
|--------|------|--------|------|------|
| `enable_memory_injection` | bool | True | - | 启用记忆注入（总开关） |
| `injection_max_memories` | int | 5 | 1-20 | 注入的最大记忆条数 |
| `injection_summary_template` | str | 见 1.3.1.1 | 含 `{memories}` | 注入摘要模板 |
| `injection_position` | str | "system_append" | 枚举 | 注入位置策略 |
| `enable_injection_tracking` | bool | True | - | 启用注入效果追踪 |

### **2.2.3 WebUI API 新增/变更（v7.0.0）**

| 端点 | 方法 | 说明 | 状态 |
|------|------|------|------|
| `/api/stats` | GET | 获取统计面板数据（分类分布+群聊分布+趋势） | 新增 |
| `/api/operations/batch-delete` | POST | 增强批量删除（支持 category+时间+importance 组合） | 增强 |
| `/api/memories/{id}/detail` | GET | 获取记忆完整详情（含 updated_at、source 等全部字段） | 新增 |

**统计面板 API 详细设计**：

`GET /api/stats`

**响应结构**：
```json
{
  "category_distribution": {"preference": 45, "habit": 30, "fact": 25, "relationship": 10, "temporary": 8, "general": 20, "period": 5},
  "group_distribution": [{"group_id": "123456", "count": 15}, {"group_id": "__global__", "count": 23}],
  "daily_trend": [{"date": "2026-05-28", "count": 12}],
  "importance_distribution": {"1": 8, "2": 15, "3": 50, "4": 40, "5": 30},
  "total_memories": 143,
  "total_users": 23,
  "total_groups": 5
}
```

**增强批量删除 API 详细设计**：

`POST /api/operations/batch-delete`

**请求体**：
```json
{
  "category": "temporary",
  "before_days": 30,
  "max_importance": 2,
  "confirm": true
}
```

**参数说明**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `category` | str | 否 | 按 category 过滤 |
| `before_days` | int | 否 | 删除 N 天前的记忆 |
| `max_importance` | int | 否 | 删除 importance <= 该值的记忆 |
| `confirm` | bool | 是 | 二次确认标志 |

**预览模式**：`confirm=false` 时返回匹配条数，不执行删除。

### **2.2.4 _manifest.json 变更**

| 字段 | 变更类型 | 变更前 | 变更后 |
|------|---------|--------|--------|
| `version` | 修改 | `"6.1.0"` | `"7.0.0"` |
| `config_version` | 修改 | `"8.0.0"` | `"8.0.0"`（保持，config 已含注入配置） |
| `capabilities` | 不变 | 含 `api.call` | 不变 |

---

# **3. 数据模型**

## **3.1 设计目标**

v7.0.0 数据模型变更目标：
1. **无需新增数据库表或字段**：replyer Hook 注入使用现有 `memory_entries` 表的检索结果，不新增持久化数据
2. **统计聚合查询**：新增统计面板所需的聚合查询方法
3. **批量操作增强**：扩展批量删除条件组合

## **3.2 模型实现**

### **3.2.1 现有数据模型（不变）**

**数据库 Schema 版本**：6（无需升级）

**核心表**：

| 表名 | 说明 | v7.0.0 变更 |
|------|------|-------------|
| `user_profiles` | 用户画像（hashed_user_id、memory_count、时间戳） | 无变更 |
| `memory_entries` | 记忆条目（entry_id、content、importance、category、tags、group_id、expiry_at、summary、merged_from、source） | 无变更 |
| `memory_vectors` | 记忆向量（entry_id、vector BLOB、dimension） | 无变更 |
| `_schema_meta` | Schema 版本元数据 | 无变更 |

### **3.2.2 DBManager 新增方法（v7.0.0）**

| 方法 | 签名 | 说明 |
|------|------|------|
| `get_category_distribution` | `() -> dict[str, int]` | 获取各 category 记忆数量分布 |
| `get_daily_trend` | `(days: int = 30) -> list[dict]` | 获取近 N 天每日新增记忆数量 |
| `get_importance_distribution` | `() -> dict[int, int]` | 获取各 importance 等级的记忆数量 |
| `batch_delete_advanced` | `(category: str=None, before_days: int=None, max_importance: int=None, confirm: bool=False) -> dict` | 增强批量删除（条件组合） |
| `get_memory_detail` | `(entry_id: str) -> dict | None` | 获取记忆完整详情（含全部字段） |

### **3.2.3 记忆注入运行时数据结构（非持久化）**

**注入摘要结构**（运行时生成，不持久化）：

```python
@dataclass
class InjectionSummary:
    """记忆注入摘要（运行时数据结构）。"""
    user_id_hash: str          # hashed_user_id（前8位用于日志）
    group_id: str | None       # 群聊 ID（None=私聊）
    memory_count: int          # 注入的记忆条数
    injection_position: str    # 注入位置策略
    injection_text: str        # 注入文本内容
    estimated_tokens: int      # 估算 token 数（基于字符数/4）
```

---

# **4. 风险与降级策略**

## **4.1 Replyer Hook 注入风险**

| 风险 | 影响 | 降级策略 | 优先级 |
|------|------|---------|--------|
| Hook 处理异常导致 replyer 流程中断 | LLM 无法回复 | try/except 全包裹，异常时返回原始 kwargs | P0 |
| session_id 格式变更导致解析失败 | 无法注入记忆 | 解析失败时静默降级为不注入，日志 debug | P0 |
| 注入记忆过多导致 context 超限 | LLM 请求失败 | `injection_max_memories` 限制条数（默认5） | P0 |
| 注入记忆内容不当影响 LLM 回复风格 | 回复不自然 | 模板中包含"自然地融入相关内容，不要刻意提及'我记得'" | P1 |
| system_append 注入位置被 LLM 忽略 | 记忆未被参考 | 提供 standalone_user 备级方案 | P2 |
| MaiBot 版本不支持 replyer Hook | Hook 注册失败 | 框架兼容：不注册 Hook，降级为仅 Tool Call | P0 |

## **4.2 WebUI 升级风险**

| 风险 | 影响 | 降级策略 | 优先级 |
|------|------|---------|--------|
| 静态资源文件缺失 | 页面无法加载 | 显示降级提示页面 | P1 |
| Chart.js CDN 加载失败 | 图表不可用 | 图表区域显示"图表暂不可用"，文字统计仍显示 | P2 |
| 暗色主题 CSS 变量缺失 | 主题异常 | 回退为亮色主题 | P2 |
| 浏览器不支持 CSS Grid/Flexbox | 布局错乱 | 最低支持 Chrome 80+/Firefox 80+，提供基础表格降级 | P3 |
| 统计聚合查询耗时过长 | 统计面板加载慢 | 2秒超时，超时显示"统计暂不可用" | P1 |
| 批量操作中途失败 | 数据不一致 | SQLite 事务回滚 | P1 |

## **4.3 兼容性风险**

| 风险 | 影响 | 降级策略 | 优先级 |
|------|------|---------|--------|
| MaiBot < rc.2 不支持 replyer Hook | Hook 注册报错 | on_load 中检测 Hook 支持情况，不支持则跳过注册 | P0 |
| 旧版 WebUI API 客户端 | 请求失败 | 保留旧版 API 端点路径和数据格式不变 | P1 |
| config.toml 缺少新配置项 | 配置解析异常 | MemoryInjectionConfig 使用合理默认值 | P1 |

---

# **5. 迁移策略**

## **5.1 从 v6.2.0 升级到 v7.0.0**

1. **配置迁移**：无需手动迁移，`MemoryInjectionConfig` 使用默认值，旧版 config.toml 缺少新字段时自动使用默认值
2. **数据库迁移**：无需迁移，Schema 版本保持 6，无新增表或字段
3. **_manifest.json 更新**：`version` 从 `"6.2.0"` 更新为 `"7.0.0"`
4. **前端资源部署**：新增 `webui/` 目录，包含静态资源文件

## **5.2 回退策略**

- 关闭 `enable_memory_injection=False` → 行为与 v6.2.0 完全一致
- 关闭 WebUI 新功能 → 旧版 API 端点仍可用
- 删除 `webui/` 目录 → 回退为内嵌 HTML（需保留旧版 `_HTML_TEMPLATE` 作为降级方案）
