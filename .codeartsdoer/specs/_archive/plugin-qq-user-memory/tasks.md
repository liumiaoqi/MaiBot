# QQ用户记忆插件 — 编码任务列表

> 版本：7.0.0  
> 日期：2026-05-29  
> 对应需求规格：spec.md v7.0.0  
> 对应实现方案：design.md v7.0.0  
> 变更说明：v7.0.0 待实现任务——WebUI 全面升级（P1）、注入 Hook 任务类型过滤（P1）、智能提取 JSON 解析稳健性增强（P1）

---

## 已完成任务

### ✅ P0: Replyer Hook 记忆注入（REQ-110 ~ REQ-119）
- [x] handle_memory_injection HookHandler 注册与实现（`plugin.py`）
- [x] MemoryInjectionConfig 配置模型定义（`config.py`）
- [x] session_id 解析 user_id/group_id
- [x] 记忆检索与双重隔离
- [x] 记忆摘要格式化（模板+截断）
- [x] 注入位置策略（system_append / standalone_user）
- [x] 注入效果追踪（after_response Hook）
- [x] 异常降级策略（全包裹 try/except）

### ✅ P0: bot_info getattr 安全访问修复
- [x] bot_info 属性获取改为 getattr 安全访问模式（`plugin.py`）

### ✅ P0: WebUI token 为空时不再弹 prompt
- [x] WebUI 鉴权 token 为空时不弹浏览器 prompt（`webui_service.py`）

### ✅ P1: 群聊记忆发送者前缀（REQ-091 ~ REQ-093）
- [x] 群聊记忆发送者前缀策略实现（`plugin.py`）
- [x] 发送者前缀与智能提取协作
- [x] 发送者昵称获取优先级

### ✅ P1: 群聊消息分类模块（REQ-050 ~ REQ-051）
- [x] GroupClassifier 群聊消息分类实现（`group_classifier.py`）

---

## 待实现任务

---

## 1. WebUI 后端 API 增强（REQ-120 ~ REQ-127）

> 对应需求：REQ-120（卡片布局数据）、REQ-122（记忆详情）、REQ-124（批量操作）、REQ-125（统计面板）  
> 优先级：P1 | 预计耗时：3h

- [ ] **T1.1** DBManager 新增统计聚合方法
  - 新增 `get_category_distribution() -> dict[str, int]`：获取各 category 记忆数量分布
  - 新增 `get_daily_trend(days=30) -> list[dict]`：获取近 N 天每日新增记忆数量
  - 新增 `get_importance_distribution() -> dict[int, int]`：获取各 importance 等级记忆数量
  - 涉及文件：`db_manager.py`
  - 验收标准：调用返回正确聚合数据，响应时间不超过 2 秒

- [ ] **T1.2** DBManager 新增增强批量删除方法
  - 新增 `batch_delete_advanced(category=None, before_days=None, max_importance=None, confirm=False) -> dict`
  - 支持按 category + 时间范围 + importance 组合条件删除
  - `confirm=False` 时仅返回匹配条数不执行删除
  - 涉及文件：`db_manager.py`
  - 验收标准：组合条件过滤正确，事务回滚保障数据一致性

- [ ] **T1.3** DBManager 新增记忆完整详情方法
  - 新增 `get_memory_detail(entry_id) -> dict | None`
  - 返回记忆全部字段（含 updated_at、source、vector_updated_at 等）
  - 涉及文件：`db_manager.py`
  - 验收标准：返回完整字段，entry_id 不存在返回 None

- [ ] **T1.4** WebUIService 新增统计面板 API 端点
  - 新增 `GET /api/stats` 端点，返回 category_distribution、group_distribution、daily_trend、importance_distribution、total_memories、total_users、total_groups
  - 涉及文件：`webui_service.py`
  - 验收标准：API 返回 JSON 格式正确，鉴权校验通过，聚合响应时间不超过 2 秒

- [ ] **T1.5** WebUIService 新增增强批量删除 API 端点
  - 增强 `POST /api/operations/batch-delete`，支持 category、before_days、max_importance、confirm 参数
  - 涉及文件：`webui_service.py`
  - 验收标准：预览模式（confirm=false）返回匹配条数，执行模式正确删除并返回统计

- [ ] **T1.6** WebUIService 新增记忆详情 API 端点
  - 新增 `GET /api/memories/{id}/detail`，返回记忆完整详情含全部字段
  - 涉及文件：`webui_service.py`
  - 验收标准：返回完整字段含 updated_at、source、向量状态等

---

## 2. WebUI 前端资源独立部署（REQ-127）

> 对应需求：REQ-127  
> 优先级：P1 | 预计耗时：2h

- [ ] **T2.1** 创建 webui/ 静态资源目录结构
  - 创建 `webui/index.html` 主页面
  - 创建 `webui/css/main.css`（主样式 + CSS 变量）
  - 创建 `webui/css/components.css`（组件样式：卡片/标签/面板/Toast/Modal）
  - 创建 `webui/css/themes.css`（亮色 + 暗色主题定义）
  - 创建 `webui/js/app.js`（主逻辑）
  - 创建 `webui/js/api.js`（API 客户端，authFetch 封装）
  - 创建 `webui/js/components.js`（UI 组件：Toast/Modal/Card）
  - 创建 `webui/js/charts.js`（Chart.js 图表封装）
  - 创建 `webui/assets/icons/`（SVG 图标目录）
  - 涉及文件：`webui/` 目录下全部文件
  - 验收标准：目录结构完整，index.html 可独立加载

- [ ] **T2.2** WebUIService 迁移为静态资源服务
  - 移除 `_HTML_TEMPLATE` 内嵌 HTML 字符串
  - `start()` 方法注册静态资源路由：`app.router.add_static("/static/", webui_path)`
  - 首页路由返回 `index.html`
  - 保留旧版 API 端点路径不变，仅前端消费方式改变
  - 静态资源缺失时显示降级提示页面
  - 涉及文件：`webui_service.py`
  - 验收标准：通过插件路由访问记忆管理页面正确加载静态资源，API 端点向后兼容

---

## 3. WebUI 前端 — 暗色主题系统（REQ-126）

> 对应需求：REQ-126  
> 优先级：P1 | 预计耗时：2h

- [ ] **T3.1** 定义 CSS 变量体系
  - 亮色主题变量（`:root`）：bg-primary、bg-card、text-primary、text-secondary、accent、border、shadow 等
  - 暗色主题变量（`[data-theme="dark"]`）：对应暗色值
  - 涉及文件：`webui/css/themes.css`
  - 验收标准：亮色/暗色两套变量完整，暗色下对比度满足 WCAG AA（4.5:1）

- [ ] **T3.2** 实现主题切换逻辑
  - 检测系统偏好：`window.matchMedia('(prefers-color-scheme: dark)')`
  - 读取用户偏好：`localStorage.getItem('memory-theme')`
  - 切换函数：`toggleTheme()` 设置 `data-theme` 属性并保存到 localStorage
  - 页面右上角主题切换按钮（日/月图标）
  - 涉及文件：`webui/js/app.js`、`webui/css/components.css`
  - 验收标准：点击切换无页面重载，刷新保持用户选择，默认跟随系统偏好

- [ ] **T3.3** 所有组件适配暗色主题
  - 卡片、标签、面板、Toast、Modal、按钮、输入框等组件颜色均使用 CSS 变量
  - 图标（SVG 内联）在暗色下正确显示（使用 currentColor 或 CSS 变量）
  - 涉及文件：`webui/css/components.css`、`webui/css/main.css`
  - 验收标准：暗色主题下所有文字可读、组件无颜色异常

---

## 4. WebUI 前端 — 现代化卡片式布局（REQ-120）

> 对应需求：REQ-120  
> 优先级：P1 | 预计耗时：3h

- [ ] **T4.1** 实现 Header 组件
  - 插件名称 + 嵌入状态指示 + 主题切换按钮
  - 响应式适配
  - 涉及文件：`webui/index.html`、`webui/css/components.css`、`webui/js/components.js`
  - 验收标准：Header 正确展示，嵌入状态实时反映

- [ ] **T4.2** 实现统计卡片区域
  - 3-4 个统计摘要卡片：总记忆数、总用户数、平均重要性、群聊数
  - 使用 CSS Grid 布局，桌面端多列、移动端单列
  - 涉及文件：`webui/css/components.css`、`webui/js/components.js`
  - 验收标准：统计卡片正确展示聚合数据，响应式布局无横向滚动

- [ ] **T4.3** 实现记忆卡片列表组件
  - 按用户分组展示为卡片，每个卡片包含：用户哈希ID（前8位）、记忆数量统计、记忆条目列表
  - 记忆条目紧凑展示：内容摘要、category 标签、importance 星标
  - 卡片使用 CSS Grid/Flexbox 布局，桌面端 2 列、移动端单列
  - 涉及文件：`webui/index.html`、`webui/css/components.css`、`webui/js/components.js`、`webui/js/app.js`
  - 验收标准：卡片按用户分组正确展示，响应式布局适配

- [ ] **T4.4** 实现 Tab 导航
  - 概览 Tab：用户卡片列表 + 统计概要
  - 记忆列表 Tab：全部记忆条目 + 筛选 + 批量操作
  - 统计 Tab：图表区域（后续任务实现）
  - 涉及文件：`webui/index.html`、`webui/js/app.js`
  - 验收标准：Tab 切换正确，各 Tab 内容区域正确展示

- [ ] **T4.5** 实现分页控件
  - 分页参数：page、page_size
  - 页码导航按钮
  - 涉及文件：`webui/js/components.js`、`webui/js/app.js`
  - 验收标准：分页查询正确，翻页数据正确加载

---

## 5. WebUI 前端 — 群聊标签式筛选（REQ-121）

> 对应需求：REQ-121  
> 优先级：P1 | 预计耗时：1.5h

- [ ] **T5.1** 实现群聊标签筛选组件
  - 替代旧版下拉框，采用标签式筛选按钮
  - 标签内容：群号 + 记忆数量（如"G1(15条)"、"全局(23条)"、"私聊(8条)"）
  - "全部"标签默认高亮
  - 涉及文件：`webui/js/components.js`、`webui/css/components.css`
  - 验收标准：标签列表正确展示群聊分布数据

- [ ] **T5.2** 实现群聊标签筛选交互
  - 点击标签高亮并筛选记忆列表
  - 支持多选（按住 Ctrl/Cmd 点击），记忆列表为所选群的并集
  - "私聊"标签筛选 `group_id IS NULL OR group_id = ''`
  - 涉及文件：`webui/js/app.js`
  - 验收标准：单选/多选筛选正确，"私聊"和"全局"筛选正确

---

## 6. WebUI 前端 — 记忆详情完整展示（REQ-122）

> 对应需求：REQ-122  
> 优先级：P1 | 预计耗时：1.5h

- [ ] **T6.1** 实现记忆详情展开面板
  - 点击记忆条目展开详情面板（或侧滑面板）
  - 完整展示字段：content（完整文本）、category（彩色标签）、importance（星标+数字）、source（来源标签）、group_id（群号/"全局"）、created_at（完整时间+时间距离）、updated_at（与 created_at 不同时显示）、tags（标签列表）、向量状态（✓已嵌入/✗未嵌入）
  - 涉及文件：`webui/js/components.js`、`webui/css/components.css`、`webui/js/app.js`
  - 验收标准：详情面板包含全部字段，时间距离描述正确（如"3天前"）

- [ ] **T6.2** 实现 category 彩色标签映射
  - preference=蓝、habit=绿、fact=橙、relationship=紫、temporary=灰、period=青、general=深灰
  - importance 星标渲染（1-5 星）
  - 涉及文件：`webui/css/components.css`、`webui/js/components.js`
  - 验收标准：各 category 颜色正确，星标渲染正确

---

## 7. WebUI 前端 — 操作反馈增强（REQ-123）

> 对应需求：REQ-123  
> 优先级：P1 | 预计耗时：1.5h

- [ ] **T7.1** 实现 Toast 通知组件
  - 成功/失败/信息三种类型
  - 自动消失（3 秒），可手动关闭
  - 支持操作链接（如"查看详情"）
  - 涉及文件：`webui/js/components.js`、`webui/css/components.css`
  - 验收标准：Toast 正确弹出和消失，三种类型样式区分

- [ ] **T7.2** 实现操作 loading 状态
  - 删除/合并/向量补算等操作：按钮显示 loading 旋转图标 + 禁用状态
  - 操作完成后恢复按钮状态 + Toast 提示成功/失败
  - 涉及文件：`webui/js/app.js`、`webui/css/components.css`
  - 验收标准：操作中按钮禁用+loading 图标，完成后 Toast 反馈

- [ ] **T7.3** 实现二次确认对话框
  - 批量操作影响超过 10 条记忆时弹出二次确认对话框，显示影响条数
  - 操作失败显示错误提示（中文）+ 重试按钮
  - 涉及文件：`webui/js/components.js`、`webui/css/components.css`
  - 验收标准：确认对话框正确弹出，显示影响条数，确认/取消逻辑正确

---

## 8. WebUI 前端 — 批量操作增强（REQ-124）

> 对应需求：REQ-124  
> 优先级：P1 | 预计耗时：1.5h

- [ ] **T8.1** 实现批量操作面板 UI
  - 操作条件选择：category 下拉、时间范围选择（天数）、importance 范围选择
  - "预览"按钮：调用 batch-delete API（confirm=false）获取匹配条数
  - "执行"按钮：二次确认后调用 batch-delete API（confirm=true）执行删除
  - 涉及文件：`webui/js/components.js`、`webui/css/components.css`、`webui/js/app.js`
  - 验收标准：条件组合正确，预览返回匹配条数，执行删除正确

- [ ] **T8.2** 实现批量操作流程
  - 流程：选择条件 → 预览影响条数 → 二次确认 → 执行 → Toast 反馈结果 + 刷新列表
  - 涉及文件：`webui/js/app.js`
  - 验收标准：完整流程可操作，删除后列表和统计自动刷新

---

## 9. WebUI 前端 — 统计面板 + Chart.js（REQ-125）

> 对应需求：REQ-125  
> 优先级：P1 | 预计耗时：2h

- [ ] **T9.1** Chart.js CDN 引入与封装
  - index.html 中引入 Chart.js CDN（~60KB gzip）
  - `charts.js` 封装：创建环形图（doughnut）、水平柱状图（horizontal bar）、折线图（line）的工厂函数
  - CDN 加载失败降级：图表区域显示"图表暂不可用"
  - 涉及文件：`webui/index.html`、`webui/js/charts.js`
  - 验收标准：Chart.js 正确加载，封装函数可用

- [ ] **T9.2** 实现统计 Tab 图表区域
  - 分类分布：Chart.js 环形图（doughnut）
  - 群聊分布：Chart.js 水平柱状图（horizontal bar）
  - 记忆趋势：Chart.js 折线图（line），展示近 30 天每日新增数量
  - 涉及文件：`webui/js/charts.js`、`webui/js/app.js`
  - 验收标准：三种图表正确渲染，数据与 `/api/stats` 一致

- [ ] **T9.3** 统计面板数据刷新
  - 执行记忆操作后统计面板自动刷新
  - 统计数据加载失败显示"统计暂不可用"
  - 涉及文件：`webui/js/app.js`
  - 验收标准：操作后统计自动刷新，失败时降级提示

---

## 10. WebUI 配置模型新增（REQ-126, REQ-127）

> 对应需求：REQ-126、REQ-127  
> 优先级：P1 | 预计耗时：0.5h

- [ ] **T10.1** 新增 WebUI 升级配置项
  - `webui_theme`：枚举 light/dark/auto，默认 "auto"
  - `webui_cards_per_row`：整数 1-4，默认 2
  - `webui_stats_enabled`：布尔，默认 True
  - `webui_chart_type`：枚举 simple/interactive，默认 "simple"
  - 涉及文件：`config.py`
  - 验收标准：配置项可正常读写，WebUI Schema 自动生成正确

---

## 11. 注入 Hook 任务类型过滤（REQ-114, REQ-133）

> 对应需求：REQ-114（注入任务类型过滤）、REQ-133（replyer Hook 上下文信息利用）  
> 优先级：P1 | 预计耗时：1h

- [ ] **T11.1** config.py 新增 injection_task_filter 配置项
  - `injection_task_filter: List[str]`，默认 `["chat", "reply"]`
  - 空列表表示所有任务类型均注入
  - 涉及文件：`config.py`
  - 验收标准：配置项可正常读写，WebUI Schema 正确

- [ ] **T11.2** handle_memory_injection 实现任务类型过滤
  - 从 kwargs 获取 `task_name` 和 `request_type`
  - `injection_task_filter` 非空时，task_name 不在列表中则跳过注入
  - `request_type` 含 retry 时仍注入（保证 LLM 重试时有记忆参考）
  - task_name 缺失时默认 "unknown"，不跳过注入（保守策略）
  - 涉及文件：`plugin.py`
  - 验收标准：任务类型过滤逻辑正确，重试场景注入，task_name 缺失保守注入

---

## 12. 智能提取 JSON 解析稳健性增强（REQ-132）

> 对应需求：REQ-132  
> 优先级：P1 | 预计耗时：1h

- [ ] **T12.1** 增强 JSON 解析容错逻辑
  - 多余逗号：正则移除 `,\s*}` 和 `,\s*]`
  - 单引号：替换单引号为双引号
  - 前后非 JSON 文本：正则提取最外层花括号内容
  - 代码块包裹：移除 ```json ... ``` 标记
  - 涉及文件：`smart_extract.py`
  - 验收标准：四种非标准 JSON 均可正确解析，解析失败降级为简单存储

- [ ] **T12.2** 增强解析日志记录
  - 解析成功记录 `llm_result_type="enhanced_parse_success"`
  - 解析失败记录 `llm_result_type="unparseable_after_enhanced_parse"`
  - 涉及文件：`smart_extract.py`
  - 验收标准：日志记录正确，便于调试

---

## 13. _manifest.json 版本更新

> 优先级：P1 | 预计耗时：0.5h

- [ ] **T13.1** 更新 _manifest.json 版本号
  - `version` 从 `"6.2.0"` 更新为 `"7.0.0"`
  - `config_version` 保持或更新为包含新增配置的版本
  - capabilities 保持不变（已含 api.call）
  - 涉及文件：`_manifest.json`
  - 验收标准：版本号正确，框架可正常加载插件

---

## 14. 验证与测试

> 优先级：P1 | 预计耗时：2h

- [ ] **T14.1** WebUI 后端 API 测试
  - 验证 `GET /api/stats` 返回正确聚合数据
  - 验证 `POST /api/operations/batch-delete` 组合条件正确
  - 验证 `GET /api/memories/{id}/detail` 返回完整字段
  - 验证 API 鉴权和白名单过滤
  - 验收标准：API 端点功能正确，鉴权有效

- [ ] **T14.2** WebUI 前端功能测试
  - 验证卡片式布局渲染正确
  - 验证暗色主题切换和持久化
  - 验证群聊标签式筛选（单选/多选）
  - 验证记忆详情完整展示
  - 验证操作反馈（loading/Toast/确认对话框）
  - 验证批量操作增强流程
  - 验证统计面板图表渲染
  - 验收标准：前端功能完整可用，无明显 UI 缺陷

- [ ] **T14.3** 注入 Hook 任务类型过滤测试
  - 验证 injection_task_filter 配置生效
  - 验证 task_name 不在过滤列表时不注入
  - 验证 request_type 含 retry 时仍注入
  - 验证空列表全部注入
  - 验收标准：过滤逻辑正确

- [ ] **T14.4** JSON 解析稳健性测试
  - 验证多余逗号、单引号、前后非 JSON 文本、代码块包裹均可正确解析
  - 验证解析失败降级为简单存储
  - 验收标准：容错解析正确，降级逻辑正确

- [ ] **T14.5** 向后兼容性验证
  - 关闭 `enable_memory_injection=False` → 行为与 v6.2.0 一致
  - 旧版 API 端点路径和数据格式不变
  - 前端资源缺失时降级提示
  - 验收标准：向后兼容无回归

---

## 15. 文档与发布

> 优先级：P1 | 预计耗时：0.5h

- [ ] **T15.1** 更新 CHANGELOG / 版本说明
  - 记录 v7.0.0 变更内容：WebUI 全面升级、注入 Hook 任务类型过滤、JSON 解析增强
  - 涉及文件：`CHANGELOG.md`（如存在）
  - 验收标准：变更记录完整

- [ ] **T15.2** 更新配置文件模版
  - 新增 WebUI 升级配置项（webui_theme、webui_cards_per_row、webui_stats_enabled、webui_chart_type）
  - 新增 injection_task_filter 配置项
  - 新增版本号
  - 涉及文件：配置模版文件
  - 验收标准：配置模版包含所有新增配置项

---

## 任务执行顺序建议

```
阶段一（后端基础，可并行）：
  T1（WebUI 后端 API 增强）  ← WebUI 升级的前置依赖
  T10（WebUI 配置模型新增）
  T11（注入 Hook 任务类型过滤）
  T12（JSON 解析稳健性增强）
  T13（_manifest.json 版本更新）

阶段二（前端基础，依赖阶段一）：
  T2（前端资源独立部署）    ← 依赖 T1 完成后端 API
  T3（暗色主题系统）        ← 依赖 T2 创建文件

阶段三（前端组件，依赖阶段二）：
  T4（卡片式布局）          ← 依赖 T2、T3
  T5（群聊标签式筛选）      ← 依赖 T4
  T6（记忆详情完整展示）    ← 依赖 T4
  T7（操作反馈增强）        ← 依赖 T4

阶段四（前端高级功能）：
  T8（批量操作增强）        ← 依赖 T7
  T9（统计面板 + Chart.js） ← 依赖 T4、T7

阶段五（验证与发布）：
  T14（验证与测试）         ← 依赖全部
  T15（文档与发布）         ← 依赖 T14
```

**关键路径**：T1 → T2 → T3 → T4 → T9 → T14 → T15（WebUI 后端→前端部署→主题→布局→统计→验证→发布）

**可并行执行的任务组**：
- 阶段一：T1、T10、T11、T12、T13 全部可并行
- 阶段三：T5、T6、T7 可并行（均依赖 T4）
- 阶段四：T8、T9 可并行
